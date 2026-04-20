"""Wave 5 — peer management & diagnostics.

Five features in one router/module because they all deal with peer state:

  1. Peer blocklist — reject envelopes / registrations from these pubkeys.
  2. Bandwidth quota — track cross-node traffic, enforce daily cap.
  3. Connectivity tester — probe all known peers, report latency/status.
  4. Bootstrap peers JSON — export current known peers, import new set.
  5. Dual-seal badge — expose whether a peer has been verified both by
     the controller and on-chain (Solana), for UI display.

The wizard stores state in ``peer_tools_state.json`` next to .env.
The node queries wizard-managed state via loopback; the wizard stays the
system of record.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin/peers", tags=["peer-tools"])


def _env_file(request: Request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


def _state_path(env_file: Path) -> Path:
    return env_file.parent / "peer_tools_state.json"


def _load_state(env_file: Path) -> dict:
    p = _state_path(env_file)
    if not p.is_file():
        return {"blocklist": [], "quota": {}, "bootstrap": [], "badges": {}}
    try:
        data = json.loads(p.read_text())
        data.setdefault("blocklist", [])
        data.setdefault("quota", {})
        data.setdefault("bootstrap", [])
        data.setdefault("badges", {})
        return data
    except Exception:
        return {"blocklist": [], "quota": {}, "bootstrap": [], "badges": {}}


def _save_state(env_file: Path, state: dict) -> None:
    _state_path(env_file).write_text(json.dumps(state, indent=2))


# ══════════════════════════════════════════════════════════════════════════
# 1. Blocklist
# ══════════════════════════════════════════════════════════════════════════

class BlockBody(BaseModel):
    pubkey: str   = Field(..., min_length=32, max_length=128, pattern=r"^[0-9a-fA-F]+$")
    reason: str   = Field("", max_length=200)


@router.get("/blocklist")
async def blocklist_list(request: Request) -> dict:
    state = _load_state(_env_file(request))
    return {"blocklist": state["blocklist"]}


@router.post("/blocklist")
async def blocklist_add(body: BlockBody, request: Request) -> dict:
    env_file = _env_file(request)
    state = _load_state(env_file)
    pk = body.pubkey.lower()
    if any(e["pubkey"] == pk for e in state["blocklist"]):
        return {"ok": True, "already": True}
    state["blocklist"].append({
        "pubkey": pk,
        "reason": body.reason,
        "added_at": int(time.time()),
    })
    _save_state(env_file, state)
    return {"ok": True, "pubkey": pk}


@router.delete("/blocklist/{pubkey}")
async def blocklist_remove(pubkey: str, request: Request) -> dict:
    env_file = _env_file(request)
    state = _load_state(env_file)
    pk = pubkey.lower()
    before = len(state["blocklist"])
    state["blocklist"] = [e for e in state["blocklist"] if e["pubkey"] != pk]
    _save_state(env_file, state)
    return {"ok": True, "removed": before - len(state["blocklist"])}


def is_blocked(env_file: Path, pubkey: str) -> bool:
    """Helper the node can call via loopback to check inbound envelopes."""
    state = _load_state(env_file)
    pk = pubkey.lower()
    return any(e["pubkey"] == pk for e in state["blocklist"])


# ══════════════════════════════════════════════════════════════════════════
# 2. Bandwidth quota
# ══════════════════════════════════════════════════════════════════════════

class QuotaBody(BaseModel):
    daily_mb: int = Field(..., ge=0, le=1_000_000)   # 0 = no limit
    enabled:  bool = True


@router.get("/quota")
async def quota_get(request: Request) -> dict:
    state = _load_state(_env_file(request))
    q = state.get("quota", {})
    today = time.strftime("%Y-%m-%d")
    used_mb = int(q.get("counters", {}).get(today, 0))
    return {
        "daily_mb":  int(q.get("daily_mb", 0)),
        "enabled":   bool(q.get("enabled", False)),
        "today_mb":  used_mb,
        "remaining_mb": max(0, int(q.get("daily_mb", 0)) - used_mb) if q.get("enabled") else None,
    }


@router.post("/quota")
async def quota_set(body: QuotaBody, request: Request) -> dict:
    env_file = _env_file(request)
    state = _load_state(env_file)
    q = state.get("quota", {})
    q["daily_mb"] = body.daily_mb
    q["enabled"]  = body.enabled
    q.setdefault("counters", {})
    state["quota"] = q
    _save_state(env_file, state)
    return {"ok": True, "quota": {"daily_mb": body.daily_mb, "enabled": body.enabled}}


class QuotaCountBody(BaseModel):
    mb:  float = Field(..., ge=0)


@router.post("/quota/count")
async def quota_count(body: QuotaCountBody, request: Request) -> dict:
    """Called by the node to report cross-node bandwidth usage."""
    env_file = _env_file(request)
    state = _load_state(env_file)
    q = state.setdefault("quota", {})
    counters = q.setdefault("counters", {})
    today = time.strftime("%Y-%m-%d")
    counters[today] = float(counters.get(today, 0)) + float(body.mb)
    # GC old days — keep 14
    keys = sorted(counters.keys())
    for old in keys[:-14]:
        counters.pop(old, None)
    _save_state(env_file, state)
    exceeded = q.get("enabled") and q.get("daily_mb", 0) and counters[today] >= q["daily_mb"]
    return {"ok": True, "today_mb": counters[today], "exceeded": bool(exceeded)}


# ══════════════════════════════════════════════════════════════════════════
# 3. Connectivity tester
# ══════════════════════════════════════════════════════════════════════════

class TestBody(BaseModel):
    peers: list[str] = Field(..., description="list of base URLs to probe")
    timeout_sec: float = 3.0


@router.post("/test")
async def connectivity_test(body: TestBody) -> dict:
    if len(body.peers) > 50:
        raise HTTPException(400, "too many peers (max 50)")

    async def one(url: str) -> dict:
        url = url.rstrip("/")
        path = f"{url}/health"
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=body.timeout_sec, verify=False) as c:
                r = await c.get(path)
                return {
                    "url":       url,
                    "ok":        r.status_code == 200,
                    "status":    r.status_code,
                    "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                }
        except httpx.TimeoutException:
            return {"url": url, "ok": False, "status": 0, "latency_ms": None, "detail": "timeout"}
        except Exception as e:
            return {"url": url, "ok": False, "status": 0, "latency_ms": None,
                    "detail": f"{type(e).__name__}: {e}"}

    results = await asyncio.gather(*[one(u) for u in body.peers])
    ok_count = sum(1 for r in results if r["ok"])
    return {"results": results, "ok_count": ok_count, "total": len(results)}


# ══════════════════════════════════════════════════════════════════════════
# 4. Bootstrap peers JSON import/export
# ══════════════════════════════════════════════════════════════════════════

class BootstrapBody(BaseModel):
    peers: list[dict] = Field(..., description="list of {pubkey, url} records")


@router.get("/bootstrap/export")
async def bootstrap_export(request: Request) -> dict:
    state = _load_state(_env_file(request))
    return {
        "version":  1,
        "exported_at": int(time.time()),
        "peers":    state.get("bootstrap", []),
    }


@router.post("/bootstrap/import")
async def bootstrap_import(body: BootstrapBody, request: Request) -> dict:
    env_file = _env_file(request)
    cleaned: list[dict] = []
    for p in body.peers:
        pk = str(p.get("pubkey", "")).lower()
        url = str(p.get("url", "")).strip()
        if not pk or not url:
            continue
        if len(pk) not in (64, 128):
            continue
        cleaned.append({"pubkey": pk, "url": url, "added_at": int(time.time())})
    if not cleaned:
        raise HTTPException(400, "no valid peer entries in payload")
    state = _load_state(env_file)
    # Merge: dedup by pubkey
    by_pk = {p["pubkey"]: p for p in state.get("bootstrap", [])}
    for p in cleaned:
        by_pk[p["pubkey"]] = p
    state["bootstrap"] = list(by_pk.values())
    _save_state(env_file, state)
    return {"ok": True, "imported": len(cleaned), "total": len(state["bootstrap"])}


@router.delete("/bootstrap")
async def bootstrap_clear(request: Request) -> dict:
    env_file = _env_file(request)
    state = _load_state(env_file)
    n = len(state.get("bootstrap", []))
    state["bootstrap"] = []
    _save_state(env_file, state)
    return {"ok": True, "cleared": n}


# ══════════════════════════════════════════════════════════════════════════
# 5. Dual-seal badge
# ══════════════════════════════════════════════════════════════════════════

class BadgeBody(BaseModel):
    pubkey:      str  = Field(..., min_length=32, max_length=128, pattern=r"^[0-9a-fA-F]+$")
    ctrl_seal:   bool = False
    chain_seal:  bool = False
    chain_tx:    Optional[str] = None


@router.post("/badge")
async def badge_set(body: BadgeBody, request: Request) -> dict:
    """Record the verification state of a peer.

    Normally the node populates this automatically as it verifies peers,
    but the wizard exposes the endpoint so operators can manually mark
    a trusted peer (e.g. their own second node).
    """
    env_file = _env_file(request)
    state = _load_state(env_file)
    pk = body.pubkey.lower()
    state["badges"][pk] = {
        "ctrl_seal":  body.ctrl_seal,
        "chain_seal": body.chain_seal,
        "chain_tx":   body.chain_tx,
        "updated_at": int(time.time()),
    }
    _save_state(env_file, state)
    return {"ok": True, "pubkey": pk, "badge": state["badges"][pk]}


@router.get("/badges")
async def badges_list(request: Request) -> dict:
    state = _load_state(_env_file(request))
    out = []
    for pk, b in state.get("badges", {}).items():
        label = (
            "✓✓ dual" if (b["ctrl_seal"] and b["chain_seal"])
            else "✓ ctrl" if b["ctrl_seal"]
            else "✓ chain" if b["chain_seal"]
            else "—"
        )
        out.append({"pubkey": pk, **b, "label": label})
    return {"badges": out}


@router.delete("/badge/{pubkey}")
async def badge_delete(pubkey: str, request: Request) -> dict:
    env_file = _env_file(request)
    state = _load_state(env_file)
    pk = pubkey.lower()
    if pk in state.get("badges", {}):
        del state["badges"][pk]
        _save_state(env_file, state)
        return {"ok": True, "removed": True}
    return {"ok": True, "removed": False}
