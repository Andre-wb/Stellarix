"""Prometheus-format metrics for the wizard + the node it manages.

Served at ``/api/wiz/admin/metrics``. Pure text, no auth — intended to be
scraped by a local Prometheus on the same machine. We don't import
``prometheus_client`` because most exporters only need a handful of
gauges/counters and pulling another ~1 MiB wheel into the .app bundle is
pointless for a single handler.

Metrics exposed (node_exporter-style names + HELP lines, OpenMetrics text
format 0.0.4):
  vortex_wizard_up
  vortex_node_up
  vortex_process_cpu_seconds_total
  vortex_process_resident_memory_bytes
  vortex_process_uptime_seconds
  vortex_peers_active_total
  vortex_rooms_active_total
  vortex_ws_active_total
  vortex_backup_byte_size
  vortex_backup_updated_at_seconds
  vortex_audit_entries_total
  vortex_audit_alerts_total
  vortex_http_requests_total{method,path,status}   (from profiler)
  vortex_http_request_duration_seconds{quantile="0.5|0.9|0.99",path}  (from profiler)
"""
from __future__ import annotations

import logging
import os
import resource
import sqlite3
import sys
import time
from pathlib import Path
from typing import Iterable

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from .audit import _audit_db_path
from . import profiler as _profiler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin", tags=["metrics"])

_START_TIME = time.time()


def _process_metrics() -> Iterable[str]:
    ru = resource.getrusage(resource.RUSAGE_SELF)
    cpu = ru.ru_utime + ru.ru_stime
    # Darwin: ru_maxrss is bytes; Linux: kilobytes. Keep honest.
    if sys.platform == "darwin":
        rss = ru.ru_maxrss
    else:
        rss = ru.ru_maxrss * 1024
    uptime = time.time() - _START_TIME

    yield "# HELP vortex_process_cpu_seconds_total Total user+system CPU seconds."
    yield "# TYPE vortex_process_cpu_seconds_total counter"
    yield f"vortex_process_cpu_seconds_total {cpu:.3f}"
    yield "# HELP vortex_process_resident_memory_bytes Resident set size (RSS)."
    yield "# TYPE vortex_process_resident_memory_bytes gauge"
    yield f"vortex_process_resident_memory_bytes {rss}"
    yield "# HELP vortex_process_uptime_seconds Seconds since wizard startup."
    yield "# TYPE vortex_process_uptime_seconds gauge"
    yield f"vortex_process_uptime_seconds {uptime:.1f}"


async def _node_metrics(env: dict) -> Iterable[str]:
    """Poll the node's own /health and /api/wiz/admin/traffic equivalents."""
    host = env.get("HOST", "127.0.0.1")
    if host == "0.0.0.0":
        host = "127.0.0.1"
    port = env.get("PORT", "9000")
    try:
        port_i = int(port)
    except ValueError:
        port_i = 9000
    proto = "https" if (Path("certs") / "vortex.crt").is_file() else "http"
    base = f"{proto}://{host}:{port_i}"

    alive = 0
    peers = rooms = ws = 0
    cpu = 0.0
    mem_mb = 0
    try:
        async with httpx.AsyncClient(timeout=2.0, verify=False) as c:
            r = await c.get(f"{base}/health")
            if r.status_code == 200:
                alive = 1
                try:
                    j = r.json()
                    peers = int(j.get("peers", 0))
                    rooms = int(j.get("rooms", 0))
                    ws    = int(j.get("ws_connections", 0))
                except Exception:
                    pass
    except Exception:
        alive = 0

    yield "# HELP vortex_node_up 1 if the managed node is responding on /health, else 0."
    yield "# TYPE vortex_node_up gauge"
    yield f"vortex_node_up {alive}"
    yield "# HELP vortex_peers_active_total Verified active peers."
    yield "# TYPE vortex_peers_active_total gauge"
    yield f"vortex_peers_active_total {peers}"
    yield "# HELP vortex_rooms_active_total Active rooms."
    yield "# TYPE vortex_rooms_active_total gauge"
    yield f"vortex_rooms_active_total {rooms}"
    yield "# HELP vortex_ws_active_total Currently-open WebSockets."
    yield "# TYPE vortex_ws_active_total gauge"
    yield f"vortex_ws_active_total {ws}"


def _audit_metrics(env_file: Path) -> Iterable[str]:
    total = alerts = 0
    try:
        c = sqlite3.connect(str(_audit_db_path(env_file)))
        try:
            total  = c.execute("SELECT COUNT(*) FROM audit_entries").fetchone()[0]
            alerts = c.execute("SELECT COUNT(*) FROM audit_entries WHERE alert=1").fetchone()[0]
        finally:
            c.close()
    except Exception:
        pass
    yield "# HELP vortex_audit_entries_total Audit log entry count."
    yield "# TYPE vortex_audit_entries_total gauge"
    yield f"vortex_audit_entries_total {total}"
    yield "# HELP vortex_audit_alerts_total Audit entries flagged as alerts."
    yield "# TYPE vortex_audit_alerts_total gauge"
    yield f"vortex_audit_alerts_total {alerts}"


def _backup_metrics(env_file: Path) -> Iterable[str]:
    # Infer backup presence from wizard's own knowledge — peeking into the
    # node's DB stats would require another fetch. Instead we rely on a
    # small state file the backup API updates on upload.
    marker = env_file.parent / "backup_last.meta"
    updated_at = 0
    byte_size = 0
    if marker.is_file():
        try:
            import json as _json
            d = _json.loads(marker.read_text())
            updated_at = int(d.get("updated_at", 0))
            byte_size  = int(d.get("byte_size", 0))
        except Exception:
            pass
    yield "# HELP vortex_backup_updated_at_seconds Epoch seconds of last backup."
    yield "# TYPE vortex_backup_updated_at_seconds gauge"
    yield f"vortex_backup_updated_at_seconds {updated_at}"
    yield "# HELP vortex_backup_byte_size Last uploaded backup blob size."
    yield "# TYPE vortex_backup_byte_size gauge"
    yield f"vortex_backup_byte_size {byte_size}"


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics(request: Request) -> PlainTextResponse:
    env_file = getattr(request.app.state, "env_file", None)
    if env_file is None:
        env_file = Path(".env")
    else:
        env_file = Path(env_file)

    env: dict = {}
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()

    lines: list[str] = []
    lines.append("# HELP vortex_wizard_up 1 if the wizard is serving.")
    lines.append("# TYPE vortex_wizard_up gauge")
    lines.append("vortex_wizard_up 1")

    lines.extend(_process_metrics())
    async for ln in _async_iter(_node_metrics(env)):
        lines.append(ln)
    lines.extend(_audit_metrics(env_file))
    lines.extend(_backup_metrics(env_file))
    lines.extend(_profiler.render_prometheus())

    body = "\n".join(lines) + "\n"
    return PlainTextResponse(
        content=body,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


# Tiny helper to adapt an async generator from `_node_metrics`.
async def _async_iter(agen):
    async for x in agen:
        yield x
