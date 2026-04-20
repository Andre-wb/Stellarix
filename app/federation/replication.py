"""
app/federation/replication.py — Cross-node envelope replication.

Hooked into the message send path for rooms whose owner opted into
`federated` replication (see Room.replication_mode in app/models_rooms/rooms.py).
Each outbound envelope is signed with this node's Ed25519 signing key and
best-effort fanned out to every active peer. Receivers verify the signature
and store the envelope locally, so the history survives the origin node
going down. Content stays E2E-encrypted — peer nodes can't decrypt it.

Metadata tradeoff is deliberate and documented: peer node operators see
`origin_pubkey`, `room_id_origin`, `sender_ts`, ciphertext size. The UI
shows a dismissible warning banner to participants (see banners.js).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Optional

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import Config
from app.database import get_db
from app.models_rooms import FederatedEnvelope
from app.peer.controller_client import NodeSigningKey, _canonical
from app.peer.peer_models import registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/federation", tags=["federation-replication"])


# Tune conservatively: peers are untrusted, we don't want one slow node to
# block message delivery.
_PUSH_TIMEOUT_SEC = 5.0
_LIST_LIMIT_MAX = 500


class FederatedEnvelopeBody(BaseModel):
    origin_pubkey:  str  = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    room_id_origin: int
    sender_ts:      int  = Field(..., ge=0)
    payload:        dict
    signature:      str  = Field(..., min_length=128, max_length=128, pattern=r"^[0-9a-f]{128}$")


def _envelope_hash(payload: dict) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


try:
    import vortex_chat as _vc_rust
    _HAS_RUST_VERIFY = hasattr(_vc_rust, "verify_signature")
except ImportError:
    _HAS_RUST_VERIFY = False


def _verify_signature(origin_pubkey_hex: str, payload: dict, signature_hex: str) -> bool:
    try:
        pub_b = bytes.fromhex(origin_pubkey_hex)
        sig_b = bytes.fromhex(signature_hex)
    except ValueError:
        return False
    if _HAS_RUST_VERIFY:
        try:
            return bool(_vc_rust.verify_signature(pub_b, _canonical(payload), sig_b))
        except Exception:
            return False
    try:
        pub = Ed25519PublicKey.from_public_bytes(pub_b)
        pub.verify(sig_b, _canonical(payload))
        return True
    except (ValueError, InvalidSignature):
        return False


@router.post("/envelopes")
async def receive_envelope(body: FederatedEnvelopeBody, db: Session = Depends(get_db)):
    """
    Accept a signed envelope from a peer node. Verifies the ed25519
    signature against `origin_pubkey`, dedups by SHA-256(payload), and
    stores the envelope locally.
    """
    if not _verify_signature(body.origin_pubkey, body.payload, body.signature):
        raise HTTPException(400, "invalid signature")

    env_hash = _envelope_hash(body.payload)
    existing = db.query(FederatedEnvelope).filter_by(envelope_hash=env_hash).first()
    if existing is not None:
        return {"status": "duplicate", "envelope_hash": env_hash}

    env = FederatedEnvelope(
        origin_pubkey_hex = body.origin_pubkey,
        room_id_origin    = body.room_id_origin,
        envelope_hash     = env_hash,
        payload_blob      = _canonical(body.payload),
        signature_hex     = body.signature,
        sender_ts         = body.sender_ts,
    )
    db.add(env)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        # Race condition: another request stored the same hash between the
        # SELECT above and our INSERT. Treat as success.
        existing = db.query(FederatedEnvelope).filter_by(envelope_hash=env_hash).first()
        if existing:
            return {"status": "duplicate", "envelope_hash": env_hash}
        logger.exception("federation: envelope store failed: %s", e)
        raise HTTPException(500, "storage error")

    return {"status": "stored", "envelope_hash": env_hash}


@router.get("/envelopes")
async def list_envelopes(
    origin_pubkey: str = Query(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"),
    since:         int = Query(0, ge=0),
    limit:         int = Query(200, ge=1, le=_LIST_LIMIT_MAX),
    db:            Session = Depends(get_db),
):
    """
    Retrieve replicated envelopes authored by `origin_pubkey`.

    Intended for recovery: a node that lost its local DB (or a new device
    signing in with the same seed) can pull its own history from any peer
    that stored it. Since each envelope is signed, the caller can verify
    authenticity client-side.
    """
    rows = (db.query(FederatedEnvelope)
              .filter(FederatedEnvelope.origin_pubkey_hex == origin_pubkey,
                      FederatedEnvelope.sender_ts >= since)
              .order_by(FederatedEnvelope.sender_ts.asc(),
                        FederatedEnvelope.id.asc())
              .limit(limit)
              .all())
    out = []
    for r in rows:
        try:
            payload = json.loads(r.payload_blob.decode("utf-8"))
        except Exception:
            continue
        out.append({
            "hash":           r.envelope_hash,
            "room_id_origin": r.room_id_origin,
            "sender_ts":      r.sender_ts,
            "signature":      r.signature_hex,
            "payload":        payload,
        })
    return {"count": len(out), "envelopes": out}


# ──────────────────────────────────────────────────────────────────────────
# Push (called from message send path)
# ──────────────────────────────────────────────────────────────────────────

async def push_envelope_to_peers(
    signing_key: NodeSigningKey,
    room_id_origin: int,
    payload: dict,
    sender_ts: int,
) -> dict:
    """Best-effort fanout of a signed envelope to all encrypted active peers.

    Failures on individual peers are logged but never raised — message
    delivery on the origin node must not block on a slow/down peer.
    Returns a dict {peer_ip: status} for diagnostics.
    """
    peers = [p for p in registry.active() if p.has_encryption()]
    if not peers:
        return {}

    try:
        signature = signing_key.sign(payload)
    except Exception as e:
        logger.error("federation: sign failed: %s", e)
        return {}

    body = {
        "origin_pubkey":  signing_key.pubkey_hex(),
        "room_id_origin": room_id_origin,
        "sender_ts":      sender_ts,
        "payload":        payload,
        "signature":      signature,
    }

    verify_tls = bool(getattr(Config, "FEDERATION_VERIFY_TLS", False))

    async def _one(peer) -> tuple[str, str]:
        url = f"{peer.base_url}/api/federation/envelopes"
        try:
            async with httpx.AsyncClient(timeout=_PUSH_TIMEOUT_SEC, verify=verify_tls) as client:
                r = await client.post(url, json=body)
                return peer.ip, f"http:{r.status_code}"
        except httpx.TimeoutException:
            return peer.ip, "timeout"
        except Exception as e:
            return peer.ip, f"err:{type(e).__name__}"

    results = await asyncio.gather(
        *[_one(p) for p in peers],
        return_exceptions=True,
    )

    report: dict[str, str] = {}
    for item in results:
        if isinstance(item, tuple) and len(item) == 2:
            report[item[0]] = item[1]
    if report:
        logger.debug("federation: fanout room=%s → %s", room_id_origin, report)
    return report


# ──────────────────────────────────────────────────────────────────────────
# Convenience: caller-side wrapper used from the WS handler
# ──────────────────────────────────────────────────────────────────────────

def _signing_key_from_app(app) -> Optional[NodeSigningKey]:
    sk = getattr(getattr(app, "state", None), "signing_key", None)
    return sk if isinstance(sk, NodeSigningKey) else None


async def maybe_replicate(room, payload: dict, sender_ts_epoch: int, app=None) -> None:
    """Entry point used by message handlers.

    Called after `db.commit()` in the send path. No-op unless the room's
    `replication_mode == 'federated'`. Never raises — failure to replicate
    must not break local delivery.
    """
    mode = getattr(room, "replication_mode", "none") or "none"
    if mode != "federated":
        return

    sk: Optional[NodeSigningKey] = None
    if app is not None:
        sk = _signing_key_from_app(app)
    if sk is None:
        try:
            sk = NodeSigningKey.load_or_create(Config.KEYS_DIR)
        except Exception as e:
            logger.warning("federation: cannot load signing key: %s", e)
            return

    try:
        await push_envelope_to_peers(
            signing_key     = sk,
            room_id_origin  = int(room.id),
            payload         = payload,
            sender_ts       = int(sender_ts_epoch),
        )
    except Exception as e:
        logger.warning("federation: push failed room=%s: %s", room.id, e)
