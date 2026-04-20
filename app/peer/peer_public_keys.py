"""Cross-node replication of public-room keys (Variant B federation).

When a node creates/rotates/invalidates the server-held key for a public
room, it fans the change out to every active peer in the registry over
the existing encrypted P2P channel. The peer upserts its own row so that
clients connected to ANY federated node get the same catch-up behavior —
join a public channel on node B, fetch the key locally, no network hop
to the origin node required.

Non-goals:
    * Multi-hop propagation (we do a single fan-out per action; the
      origin node is authoritative and new peers pull via their own
      create/flip events or on-demand).
    * Conflict resolution (the last writer by absolute clock wins —
      acceptable because the only mutations are "set" and "delete",
      both idempotent).
    * Replicating private-room keys (never — those stay per-member ECIES).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models_rooms import PublicRoomKey, Room
from app.peer._router import router
from app.peer.connection_manager import manager as ws_manager
from app.peer.peer_discovery import _get_node_keys
from app.peer.peer_models import registry
from app.security.ssl_context import make_peer_ssl_context

logger = logging.getLogger(__name__)

_peer_ssl_ctx = make_peer_ssl_context()


# ── Outbound: we made a change, tell every peer ─────────────────────────
async def propagate_public_key(
    room_id: int,
    key_hex: str,
    algorithm: str,
    action: str,   # "set" | "delete"
) -> None:
    """Fan the change out to every active peer. Best-effort, fire-and-forget.

    Called from app.chats.rooms.public_keys after the local commit. The
    caller already awaits the DB flush, so a peer will never see a key
    that doesn't exist on this node.
    """
    peers = registry.active()
    if not peers:
        return

    node_priv_raw, node_pub_raw = _get_node_keys()
    node_priv = bytes(node_priv_raw) if not isinstance(node_priv_raw, bytes) else node_priv_raw
    node_pub  = bytes(node_pub_raw)  if not isinstance(node_pub_raw,  bytes) else node_pub_raw

    payload = {
        "action":    action,
        "room_id":   room_id,
        "key_hex":   key_hex,
        "algorithm": algorithm,
        "ts":        datetime.now(timezone.utc).isoformat(),
        # Origin pubkey lets the receiver skip re-propagating back to us.
        "source_pubkey": node_pub.hex(),
    }

    async def _one(peer):
        try:
            if peer.has_encryption():
                from app.security.key_exchange import encrypt_p2p_payload
                enc = encrypt_p2p_payload(payload, node_priv, peer.node_pubkey_hex)
                body = {
                    "ephemeral_pub": enc["ephemeral_pub"],
                    "ciphertext":    enc["ciphertext"],
                    "sender_pubkey": node_pub.hex(),
                }
            else:
                body = {
                    "plaintext_payload": payload,
                    "sender_pubkey":     node_pub.hex(),
                }
            async with httpx.AsyncClient(timeout=3.0, verify=_peer_ssl_ctx) as c:
                await c.post(f"{peer.base_url}/api/peers/sync-public-key", json=body)
        except Exception as e:
            logger.debug("sync-public-key to %s failed: %s", peer.ip, e)

    # Parallel fan-out; exceptions swallowed inside _one().
    await asyncio.gather(*[_one(p) for p in peers], return_exceptions=True)


# ── Inbound: a peer tells us about its change ───────────────────────────
class SyncRequest(BaseModel):
    ephemeral_pub:     Optional[str]  = Field(None, min_length=64, max_length=64)
    ciphertext:        Optional[str]  = None
    sender_pubkey:     Optional[str]  = None
    plaintext_payload: Optional[dict] = None


@router.post("/sync-public-key")
async def sync_public_key(body: SyncRequest, request: Request):
    """Receive a public-room key change from another node."""
    src_ip = request.client.host if request.client else "unknown"

    # Decrypt / validate the payload using the same gate as /api/peers/receive.
    if body.ephemeral_pub and body.ciphertext:
        node_priv_raw, _ = _get_node_keys()
        node_priv = bytes(node_priv_raw) if not isinstance(node_priv_raw, bytes) else node_priv_raw
        try:
            from app.security.key_exchange import decrypt_p2p_payload
            msg = decrypt_p2p_payload(body.ephemeral_pub, body.ciphertext, node_priv)
        except Exception as e:
            logger.warning("sync-public-key decrypt failed from %s: %s", src_ip, e)
            return {"ok": False, "error": "decrypt_failed"}
    elif body.plaintext_payload:
        peer = registry.get(src_ip)
        if not peer:
            return {"ok": False, "error": "unknown_peer"}
        msg = body.plaintext_payload
    else:
        return {"ok": False, "error": "missing_payload"}

    action    = msg.get("action")
    room_id   = msg.get("room_id")
    key_hex   = (msg.get("key_hex") or "").lower()
    algorithm = msg.get("algorithm") or "aes-256-gcm"

    if not isinstance(room_id, int) or action not in ("set", "delete"):
        return {"ok": False, "error": "bad_params"}

    db: Session = SessionLocal()
    try:
        room = db.query(Room).filter(Room.id == room_id).first()
        if room is None:
            # We don't host this room at all — drop. (Mirror nodes that
            # do host the room will still keep a copy; we're not trying
            # to force every node to hold keys it won't use.)
            return {"ok": True, "skipped": "room_not_present"}
        if room.is_private:
            # Safety net: never accept a public key for a room that's
            # currently marked private on this node. The source node may
            # be behind on the flip — let it catch up on its own pass.
            return {"ok": True, "skipped": "room_is_private"}

        if action == "set":
            if not key_hex or len(key_hex) != 64:
                return {"ok": False, "error": "bad_key_hex"}
            existing = db.query(PublicRoomKey).filter(
                PublicRoomKey.room_id == room_id).first()
            rotated = False
            if existing is None:
                db.add(PublicRoomKey(
                    room_id=room_id, key_hex=key_hex, algorithm=algorithm,
                ))
            elif existing.key_hex != key_hex:
                existing.key_hex = key_hex
                existing.algorithm = algorithm
                existing.rotated_at = datetime.now(timezone.utc)
                rotated = True
            else:
                # Identical copy — no-op. Prevents ping-pong between peers.
                db.commit()
                return {"ok": True, "noop": True}
            db.commit()
            # Tell locally-connected members to re-pull.
            try:
                await ws_manager.broadcast_to_room(room_id, {
                    "type": "public_room_key_updated",
                    "room_id": room_id,
                    "rotated": rotated,
                    "from_peer": True,
                })
            except Exception as e:
                logger.debug("local broadcast from peer sync failed: %s", e)
            return {"ok": True, "rotated": rotated}

        # action == "delete"
        n = db.query(PublicRoomKey).filter(
            PublicRoomKey.room_id == room_id).delete(synchronize_session=False)
        db.commit()
        if n:
            try:
                await ws_manager.broadcast_to_room(room_id, {
                    "type": "public_room_key_deleted",
                    "room_id": room_id,
                    "from_peer": True,
                })
            except Exception as e:
                logger.debug("local broadcast delete-from-peer failed: %s", e)
        return {"ok": True, "wiped": bool(n)}
    finally:
        db.close()
