"""POST /v1/register and /v1/heartbeat.

Both accept a signed payload. Signature is verified against the pubkey inside
the payload, proving the caller controls the private key.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

from ..controller_crypto import verify_signature
from ..models import (
    HeartbeatRequest,
    RegisterAck,
    RegistrationRequest,
)

router = APIRouter(prefix="/v1", tags=["register"])

# Reject registrations with a timestamp drift larger than this
MAX_CLOCK_SKEW_SEC = 300


def _within_skew(ts: int) -> bool:
    return abs(int(time.time()) - ts) <= MAX_CLOCK_SKEW_SEC


@router.post("/register", response_model=RegisterAck)
async def register(req: RegistrationRequest, request: Request) -> RegisterAck:
    payload = req.payload

    if not _within_skew(payload.timestamp):
        raise HTTPException(400, "timestamp too far from server clock")

    # Verify signature proves pubkey ownership
    if not verify_signature(
        pubkey_hex=payload.pubkey,
        signature_hex=req.signature,
        payload=payload.model_dump(),
    ):
        raise HTTPException(401, "invalid signature")

    if not payload.endpoints:
        raise HTTPException(400, "endpoints must not be empty")
    if len(payload.endpoints) > 16:
        raise HTTPException(400, "too many endpoints (max 16)")
    for ep in payload.endpoints:
        if not isinstance(ep, str) or len(ep) > 512:
            raise HTTPException(400, "invalid endpoint")

    storage = request.app.state.storage
    auto_approve = request.app.state.auto_approve

    await storage.register(
        pubkey_hex=payload.pubkey,
        endpoints=payload.endpoints,
        metadata=payload.metadata,
        approved=auto_approve,
    )
    return RegisterAck(
        ok=True,
        approved=auto_approve,
        message=None if auto_approve else "pending manual approval",
    )


@router.post("/heartbeat", response_model=RegisterAck)
async def heartbeat(req: HeartbeatRequest, request: Request) -> RegisterAck:
    payload = req.payload

    if not _within_skew(payload.timestamp):
        raise HTTPException(400, "timestamp too far from server clock")

    if not verify_signature(
        pubkey_hex=payload.pubkey,
        signature_hex=req.signature,
        payload=payload.model_dump(),
    ):
        raise HTTPException(401, "invalid signature")

    storage = request.app.state.storage
    if not await storage.heartbeat(payload.pubkey):
        raise HTTPException(404, "node not registered; call /v1/register first")

    return RegisterAck(ok=True, approved=True)


# ── Batch heartbeat ────────────────────────────────────────────────────────
# For supernodes that aggregate heartbeats from downstream nodes.
# Uses Rust's ed25519-dalek batch verifier: 3-5× faster than per-item
# verify when N >= 8. Fails fast on ANY bad signature (batch semantics).
from pydantic import BaseModel
from typing import List

try:
    import vortex_chat as _vc_rust
    _HAS_RUST_BATCH = hasattr(_vc_rust, "batch_verify")
except ImportError:
    _HAS_RUST_BATCH = False


class BatchHeartbeat(BaseModel):
    items: List[HeartbeatRequest]


@router.post("/heartbeat/batch")
async def heartbeat_batch(req: BatchHeartbeat, request: Request) -> dict:
    if len(req.items) == 0:
        return {"ok": True, "accepted": 0}
    if len(req.items) > 500:
        raise HTTPException(400, "max 500 heartbeats per batch")

    # Validate timestamps and pre-parse signatures / pubkeys.
    pubkey_hex_list = []
    msgs = []
    sigs = []
    for it in req.items:
        p = it.payload
        if not _within_skew(p.timestamp):
            raise HTTPException(400, "timestamp too far from server clock")
        try:
            pubkey_hex_list.append(p.pubkey)
            sigs.append(bytes.fromhex(it.signature))
            from ..controller_crypto import canonical_json as _cj
            msgs.append(_cj(p.model_dump()))
        except ValueError:
            raise HTTPException(400, "invalid hex in pubkey or signature")

    if _HAS_RUST_BATCH:
        try:
            pubkeys_flat = b"".join(bytes.fromhex(h) for h in pubkey_hex_list)
            sigs_flat = b"".join(sigs)
            ok = _vc_rust.batch_verify(pubkeys_flat, msgs, sigs_flat)
        except Exception:
            ok = None
        if ok is False:
            raise HTTPException(401, "at least one signature invalid")
        if ok is None:
            # Fall through to per-item verify
            for it, m in zip(req.items, msgs):
                if not verify_signature(it.payload.pubkey, it.signature,
                                        it.payload.model_dump()):
                    raise HTTPException(401, "invalid signature")
    else:
        for it in req.items:
            if not verify_signature(it.payload.pubkey, it.signature,
                                    it.payload.model_dump()):
                raise HTTPException(401, "invalid signature")

    storage = request.app.state.storage
    missing = []
    for it in req.items:
        if not await storage.heartbeat(it.payload.pubkey):
            missing.append(it.payload.pubkey)

    return {
        "ok":       True,
        "accepted": len(req.items) - len(missing),
        "missing":  missing,
    }
