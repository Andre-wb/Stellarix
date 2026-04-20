"""Wave 4 — Advanced peer management.

  #16 Reputation scoring       — per-peer running score from observations
  #17 Per-peer rate limit       — individual token-bucket knob per pubkey
  #18 Whitelist-only mode       — reject anyone not on the list
  #19 Peer diagnostics          — ping / TLS / WebSocket probe
  #20 Blacklist with expiry     — 7d / 30d / permanent + auto-expiry

Reuses the peer_tools.py state file (adds new keys instead of creating
parallel storage).
"""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
import time
from pathlib import Path
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import peer_tools as _pt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin/peers", tags=["peer-advanced"])


def _env_file(request: Request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


# ══════════════════════════════════════════════════════════════════════════
# #16 — Reputation scoring
# ══════════════════════════════════════════════════════════════════════════
#
# Score in range [0.0, 100.0]. Starting 50.0. Updated via:
#   observe(peer, event) where event is one of:
#     "uptime_ok"       → +0.5
#     "envelope_valid"  → +0.1
#     "envelope_invalid"→ -5.0
#     "latency_ms":N    → -log10(N/100) ×  (capped)
#     "spam_suspected"  → -2.0
#     "abuse_reported"  → -25.0
# Score below 30 → auto-blacklist for 7 days.
# Score above 80 → badge "trusted".

class ObserveBody(BaseModel):
    pubkey:  str = Field(..., min_length=32, max_length=128, pattern=r"^[0-9a-fA-F]+$")
    event:   Literal["uptime_ok", "envelope_valid", "envelope_invalid",
                      "latency_ms", "spam_suspected", "abuse_reported"]
    value:   Optional[float] = None


def _event_delta(event: str, value: Optional[float]) -> float:
    if event == "uptime_ok":         return 0.5
    if event == "envelope_valid":    return 0.1
    if event == "envelope_invalid":  return -5.0
    if event == "spam_suspected":    return -2.0
    if event == "abuse_reported":    return -25.0
    if event == "latency_ms":
        v = float(value or 100.0)
        # Penalty: latency 100ms → 0, 1000ms → -1.0, 10000ms → -2.0
        import math
        return -max(0.0, math.log10(max(1.0, v) / 100.0))
    return 0.0


@router.post("/reputation/observe")
async def reputation_observe(body: ObserveBody, request: Request) -> dict:
    env_file = _env_file(request)
    state = _pt._load_state(env_file)
    rep = state.setdefault("reputation", {})
    pk = body.pubkey.lower()
    row = rep.get(pk, {"score": 50.0, "events": 0, "updated_at": 0})
    row["score"] = max(0.0, min(100.0, row["score"] + _event_delta(body.event, body.value)))
    row["events"] = int(row.get("events", 0)) + 1
    row["updated_at"] = int(time.time())
    rep[pk] = row
    _pt._save_state(env_file, state)

    # Auto-blacklist if score drops below threshold
    if row["score"] < 30.0:
        _add_blacklist_entry(env_file, pk, reason=f"auto: low reputation ({row['score']:.1f})",
                              expires=int(time.time()) + 7 * 86400)
    return {"ok": True, "pubkey": pk, "score": round(row["score"], 2)}


@router.get("/reputation")
async def reputation_list(request: Request) -> dict:
    state = _pt._load_state(_env_file(request))
    rep = state.get("reputation", {})
    rows = []
    for pk, row in rep.items():
        rows.append({"pubkey": pk, **row,
                     "tier": "trusted" if row["score"] >= 80 else
                              "normal"  if row["score"] >= 30 else "risky"})
    rows.sort(key=lambda r: r["score"], reverse=True)
    return {"peers": rows}


# ══════════════════════════════════════════════════════════════════════════
# #17 — Per-peer rate limit
# ══════════════════════════════════════════════════════════════════════════

class PerPeerRateBody(BaseModel):
    pubkey:     str = Field(..., min_length=32, max_length=128, pattern=r"^[0-9a-fA-F]+$")
    per_minute: int = Field(60, ge=0, le=100000)


@router.get("/rate_limits")
async def rate_limits_list(request: Request) -> dict:
    state = _pt._load_state(_env_file(request))
    return {"per_peer": state.get("per_peer_rate", {}),
            "default": state.get("quota", {}).get("daily_mb")}


@router.post("/rate_limits")
async def rate_limit_set(body: PerPeerRateBody, request: Request) -> dict:
    env_file = _env_file(request)
    state = _pt._load_state(env_file)
    rl = state.setdefault("per_peer_rate", {})
    pk = body.pubkey.lower()
    if body.per_minute == 0:
        rl.pop(pk, None)
    else:
        rl[pk] = {"per_minute": body.per_minute, "set_at": int(time.time())}
    _pt._save_state(env_file, state)
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
# #18 — Whitelist-only mode
# ══════════════════════════════════════════════════════════════════════════

class WhitelistSetBody(BaseModel):
    enabled:       bool
    pubkeys:       list[str] = Field(default_factory=list)


@router.get("/whitelist")
async def whitelist_get(request: Request) -> dict:
    state = _pt._load_state(_env_file(request))
    wl = state.get("whitelist", {"enabled": False, "pubkeys": []})
    return {"enabled": bool(wl.get("enabled")), "pubkeys": list(wl.get("pubkeys", []))}


@router.post("/whitelist")
async def whitelist_set(body: WhitelistSetBody, request: Request) -> dict:
    env_file = _env_file(request)
    state = _pt._load_state(env_file)
    state["whitelist"] = {
        "enabled": body.enabled,
        "pubkeys": [p.lower() for p in body.pubkeys
                    if all(c in "0123456789abcdefABCDEF" for c in p) and len(p) in (64, 128)],
    }
    _pt._save_state(env_file, state)
    return {"ok": True, "count": len(state["whitelist"]["pubkeys"])}


def is_whitelisted(env_file: Path, pubkey: str) -> Optional[bool]:
    """Helper for node-side inbound filter.
    Returns None if whitelist mode is off, else bool."""
    state = _pt._load_state(env_file)
    wl = state.get("whitelist", {})
    if not wl.get("enabled"): return None
    return pubkey.lower() in wl.get("pubkeys", [])


# ══════════════════════════════════════════════════════════════════════════
# #19 — Peer diagnostics
# ══════════════════════════════════════════════════════════════════════════

class DiagnoseBody(BaseModel):
    base_url:  str = Field(..., min_length=8, max_length=2048)


@router.post("/diagnose")
async def diagnose(body: DiagnoseBody) -> dict:
    """Deep probe: ICMP-ish reachability, TLS handshake, /health,
    WebSocket upgrade, p99 latency over 5 quick requests."""
    base = body.base_url.rstrip("/")
    out: dict = {"url": base, "checks": []}

    # 1. TCP reachability via httpx (no SSL enforcement)
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=3.0, verify=False) as c:
            r = await c.get(base + "/health")
            out["checks"].append({
                "name": "http_health",
                "ok":   r.status_code == 200,
                "status": r.status_code,
                "latency_ms": round((time.perf_counter()-t0)*1000, 1),
            })
    except Exception as e:
        out["checks"].append({"name": "http_health", "ok": False,
                              "detail": f"{type(e).__name__}: {e}"})

    # 2. TLS handshake probe (for https)
    if base.startswith("https://"):
        import urllib.parse as _u
        p = _u.urlparse(base)
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    p.hostname, p.port or 443, ssl=ssl.create_default_context(),
                    server_hostname=p.hostname,
                ), timeout=3.0,
            )
            peercert = writer.get_extra_info("peercert")
            writer.close(); await writer.wait_closed()
            out["checks"].append({
                "name": "tls_handshake",
                "ok":   True,
                "subject": [dict(n) for n in (peercert or {}).get("subject", [])],
                "not_after": (peercert or {}).get("notAfter"),
            })
        except Exception as e:
            out["checks"].append({"name": "tls_handshake", "ok": False,
                                  "detail": f"{type(e).__name__}: {e}"})

    # 3. WebSocket upgrade probe
    try:
        import websockets
        proto = "wss" if base.startswith("https") else "ws"
        ws_url = proto + "://" + base.split("://",1)[1] + "/ws"
        t0 = time.perf_counter()
        async with websockets.connect(ws_url, open_timeout=3.0, ssl=None) as _:  # type: ignore[arg-type]
            out["checks"].append({
                "name": "ws_upgrade", "ok": True,
                "latency_ms": round((time.perf_counter()-t0)*1000, 1),
            })
    except Exception as e:
        out["checks"].append({"name": "ws_upgrade", "ok": False,
                              "detail": f"{type(e).__name__}: {e}"})

    # 4. P99 latency over 5 probes
    lats = []
    for _ in range(5):
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=2.0, verify=False) as c:
                await c.get(base + "/health")
            lats.append((time.perf_counter()-t0)*1000)
        except Exception:
            pass
    if lats:
        lats_sorted = sorted(lats)
        p50 = lats_sorted[len(lats_sorted)//2]
        p99 = lats_sorted[-1]
        out["checks"].append({
            "name": "latency_samples",
            "ok":   True,
            "count": len(lats),
            "p50_ms": round(p50, 1),
            "p99_ms": round(p99, 1),
        })

    out["summary"] = "healthy" if all(c["ok"] for c in out["checks"]) else "degraded"
    return out


# ══════════════════════════════════════════════════════════════════════════
# #20 — Blacklist with expiry (extends peer_tools blocklist)
# ══════════════════════════════════════════════════════════════════════════

class ExpiringBlockBody(BaseModel):
    pubkey:      str = Field(..., min_length=32, max_length=128, pattern=r"^[0-9a-fA-F]+$")
    reason:      str = Field("", max_length=200)
    duration:    Literal["7d", "30d", "permanent"] = "7d"


def _add_blacklist_entry(env_file: Path, pk: str, reason: str,
                         expires: Optional[int] = None) -> None:
    state = _pt._load_state(env_file)
    bl = state.get("blocklist", [])
    bl = [b for b in bl if b.get("pubkey") != pk]
    entry = {"pubkey": pk, "reason": reason, "added_at": int(time.time())}
    if expires is not None:
        entry["expires_at"] = expires
    bl.append(entry)
    state["blocklist"] = bl
    _pt._save_state(env_file, state)


@router.post("/blacklist")
async def blacklist_set_expiring(body: ExpiringBlockBody, request: Request) -> dict:
    env_file = _env_file(request)
    pk = body.pubkey.lower()
    exp = None
    if body.duration == "7d":  exp = int(time.time()) + 7 * 86400
    if body.duration == "30d": exp = int(time.time()) + 30 * 86400
    _add_blacklist_entry(env_file, pk, body.reason, exp)
    return {"ok": True, "pubkey": pk, "expires_at": exp}


async def job_blacklist_expire(env_file: Path) -> dict:
    """Hourly job — drop blacklist entries past their expires_at."""
    state = _pt._load_state(env_file)
    bl = state.get("blocklist", [])
    now = int(time.time())
    kept = []
    dropped = 0
    for b in bl:
        if b.get("expires_at") and int(b["expires_at"]) <= now:
            dropped += 1
            continue
        kept.append(b)
    if dropped:
        state["blocklist"] = kept
        _pt._save_state(env_file, state)
    return {"message": f"expired {dropped} blacklist entries", "dropped": dropped}


def install_peer_adv_jobs(env_file: Path) -> None:
    from . import scheduler as _sched
    s = _sched.get(env_file)
    s.register("blacklist_expire", job_blacklist_expire, default_interval="hourly")
