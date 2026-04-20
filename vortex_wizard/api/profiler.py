"""Per-endpoint latency profiler for the wizard.

In-memory only (no DB writes — this is hot path). Keeps a rolling sample
of the last N durations per (method, path_template) and on demand
computes P50/P95/P99. Also exports Prometheus-format counters so the
/metrics endpoint can dump them.

Only a few thousand samples are held at any time — this is about
diagnosing wizard-side bottlenecks, not a full-blown APM.
"""
from __future__ import annotations

import bisect
import logging
import threading
import time
from collections import defaultdict, deque
from typing import Awaitable, Callable, Deque, Dict, Iterable, Tuple

from fastapi import APIRouter, Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin/profiler", tags=["profiler"])

_BUCKET_MAX_SAMPLES = 500   # per (method, path) bucket
_STATUS_COUNTER_CAP = 10_000


class _PerEndpointStats:
    """Rolling samples + counters for one (method, path) tuple."""
    __slots__ = ("samples", "count", "status_counts")

    def __init__(self):
        self.samples: Deque[float] = deque(maxlen=_BUCKET_MAX_SAMPLES)
        self.count: int = 0
        self.status_counts: Dict[int, int] = {}

    def add(self, duration_ms: float, status: int) -> None:
        self.samples.append(duration_ms)
        self.count += 1
        self.status_counts[status] = self.status_counts.get(status, 0) + 1

    def percentile(self, p: float) -> float:
        if not self.samples:
            return 0.0
        sorted_samples = sorted(self.samples)
        idx = max(0, min(len(sorted_samples) - 1,
                         int(round((p / 100.0) * (len(sorted_samples) - 1)))))
        return sorted_samples[idx]


_stats: Dict[Tuple[str, str], _PerEndpointStats] = defaultdict(_PerEndpointStats)
_lock = threading.Lock()


# Normalize paths — otherwise every /api/rooms/42/replication becomes its
# own bucket and we explode the cardinality.
_PATH_PATTERNS = [
    (r"/api/rooms/\d+", "/api/rooms/{id}"),
    (r"/api/wiz/admin/db/table/[^/]+", "/api/wiz/admin/db/table/{name}"),
    (r"/api/chats/rooms/\d+", "/api/chats/rooms/{id}"),
    (r"/api/users/\d+", "/api/users/{id}"),
]


def _template(path: str) -> str:
    import re
    for pat, repl in _PATH_PATTERNS:
        path = re.sub(pat, repl, path)
    return path[:128]


class ProfilerMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable],
    ):
        # Skip polling-heavy endpoints to keep the picture signal-rich.
        skip_paths = ("/api/wiz/admin/logs", "/api/wiz/admin/metrics",
                      "/api/wiz/admin/profiler", "/api/wiz/admin/node/status",
                      "/api/wiz/admin/audit", "/static", "/locales",
                      "/favicon")
        path = request.url.path
        for sp in skip_paths:
            if path.startswith(sp):
                return await call_next(request)

        t0 = time.perf_counter()
        status = 0
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            dur_ms = (time.perf_counter() - t0) * 1000.0
            tpl = _template(path)
            key = (request.method, tpl)
            with _lock:
                _stats[key].add(dur_ms, status)


def render_prometheus() -> Iterable[str]:
    """Emit per-endpoint counters + quantile gauges for /metrics."""
    with _lock:
        items = list(_stats.items())

    if not items:
        return []

    lines: list[str] = []
    lines.append("# HELP vortex_http_requests_total Total requests by endpoint.")
    lines.append("# TYPE vortex_http_requests_total counter")
    for (method, tpl), st in items:
        for code, cnt in st.status_counts.items():
            lines.append(
                f'vortex_http_requests_total{{method="{method}",path="{tpl}",status="{code}"}} {cnt}'
            )
    lines.append("# HELP vortex_http_request_duration_seconds Rolling-window latency quantiles (ms / 1000).")
    lines.append("# TYPE vortex_http_request_duration_seconds gauge")
    for (method, tpl), st in items:
        for q, label in [(50, "0.5"), (90, "0.9"), (99, "0.99")]:
            v = st.percentile(q) / 1000.0
            lines.append(
                f'vortex_http_request_duration_seconds{{method="{method}",path="{tpl}",quantile="{label}"}} {v:.4f}'
            )
    return lines


@router.get("")
async def profiler_summary(top: int = 20) -> dict:
    top = max(1, min(top, 100))
    with _lock:
        items = list(_stats.items())

    rows = []
    for (method, tpl), st in items:
        rows.append({
            "method":   method,
            "path":     tpl,
            "count":    st.count,
            "p50_ms":   round(st.percentile(50), 1),
            "p95_ms":   round(st.percentile(95), 1),
            "p99_ms":   round(st.percentile(99), 1),
            "status_counts": dict(st.status_counts),
        })
    # Sort by p99 desc — slowest first
    rows.sort(key=lambda r: r["p99_ms"], reverse=True)
    return {"endpoints": rows[:top], "total": len(rows)}


@router.post("/reset")
async def profiler_reset() -> dict:
    with _lock:
        _stats.clear()
    return {"ok": True}
