"""Public-room key escrow endpoints (Variant B).

A small, opt-in fast-path for public rooms/channels/public-spaces:

    Room.is_private = False   → key may live on the server
    Room.is_private = True    → falls back to the ECIES per-member flow

Flow:
    * Owner/admin creates a public room and (optionally) POSTs the
      symmetric room key here in plaintext. Any member (or even an
      anonymous scraper, for channels) can later GET the key.
    * Clients cache the fetched key locally; after that, messages are
      decrypted with zero additional round-trips — offline catch-up and
      first-view are instant.
    * On a public→private flip (see crud.update_room), the server-held
      row is invalidated by ``invalidate_server_key`` so the old key
      can't be pulled by latecomers, and clients are expected to rotate.

Explicitly NOT a privacy feature: anything stored via this endpoint is
considered public. Don't use it for DMs or private groups — the /join
+ /provide-key flow in keys.py is the right path there.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.chats.rooms.helpers import router, _require_member
from app.database import get_db
from app.models import User
from app.models_rooms import PublicRoomKey, Room, RoomRole
from app.peer.connection_manager import manager
from app.security.auth_jwt import get_current_user

logger = logging.getLogger(__name__)

# 32-byte AES-256 key, hex-encoded → exactly 64 chars of [0-9a-f].
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


# ── Schemas ─────────────────────────────────────────────────────────────
class PublicKeyUpload(BaseModel):
    key_hex: str = Field(..., min_length=64, max_length=64,
                         description="AES-256 key, hex-encoded (32 bytes).")
    algorithm: str = Field("aes-256-gcm", max_length=32)


# ── Library helpers (imported by crud.update_room on visibility flip) ──
def invalidate_server_key(room_id: int, db: Session) -> bool:
    """Remove the server-held public key for a room.

    Called when the room flips public→private OR when an admin forces
    rotation. Returns True if a row was deleted.
    """
    n = db.query(PublicRoomKey).filter(PublicRoomKey.room_id == room_id).delete(
        synchronize_session=False,
    )
    if n:
        db.flush()
        logger.info("public_key: invalidated for room_id=%s", room_id)
    return bool(n)


def upsert_public_key(
    room_id: int,
    key_hex: str,
    algorithm: str,
    db: Session,
) -> tuple[PublicRoomKey, bool]:
    """Insert or replace the public room key. Returns (row, rotated)."""
    if not _HEX64.match(key_hex.lower()):
        raise ValueError(f"invalid key_hex for room_id={room_id}")
    row = db.query(PublicRoomKey).filter(PublicRoomKey.room_id == room_id).first()
    rotated = False
    if row is None:
        row = PublicRoomKey(
            room_id=room_id,
            key_hex=key_hex.lower(),
            algorithm=algorithm,
        )
        db.add(row)
    elif row.key_hex != key_hex.lower():
        row.key_hex = key_hex.lower()
        row.algorithm = algorithm
        row.rotated_at = datetime.now(timezone.utc)
        rotated = True
    db.flush()
    return row, rotated


async def store_public_key_and_propagate(
    room_id: int,
    key_hex: str,
    algorithm: str,
    db: Session,
    rotated: bool = False,
) -> None:
    """Write the key locally then push it to every active peer node.

    Called by crud.create_room and crud.update_room so every public room
    has a server-held key automatically. Best-effort fan-out — peers that
    are offline at the moment will learn the key via their own create/flip
    event if applicable, or via a dedicated reconciliation sweep later.
    """
    row, _ = upsert_public_key(room_id, key_hex, algorithm, db)

    # Broadcast to local WS members so they switch immediately.
    try:
        await manager.broadcast_to_room(room_id, {
            "type": "public_room_key_updated",
            "room_id": room_id,
            "rotated": rotated,
        })
    except Exception as e:
        logger.debug("local broadcast public_room_key_updated failed: %s", e)

    # Federate to peer nodes. Imported lazily to avoid a cycle on startup
    # (app.peer.peer_public_keys depends on app.chats.rooms indirectly).
    try:
        from app.peer.peer_public_keys import propagate_public_key
        await propagate_public_key(
            room_id=room_id,
            key_hex=row.key_hex,
            algorithm=row.algorithm,
            action="set",
        )
    except Exception as e:
        logger.debug("propagate_public_key failed: %s", e)


async def invalidate_and_propagate(room_id: int, db: Session) -> bool:
    """Delete locally then tell every peer to drop its copy too."""
    wiped = invalidate_server_key(room_id, db)
    try:
        await manager.broadcast_to_room(room_id, {
            "type": "public_room_key_deleted",
            "room_id": room_id,
        })
    except Exception as e:
        logger.debug("local broadcast public_room_key_deleted failed: %s", e)
    try:
        from app.peer.peer_public_keys import propagate_public_key
        await propagate_public_key(
            room_id=room_id,
            key_hex="",
            algorithm="",
            action="delete",
        )
    except Exception as e:
        logger.debug("propagate_public_key delete failed: %s", e)
    return wiped


# ── Endpoints ───────────────────────────────────────────────────────────
@router.post("/{room_id}/public-key")
async def set_public_key(
    room_id: int,
    body: PublicKeyUpload,
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """OWNER/ADMIN uploads (or rotates) the server-held room key.

    Rejects the call if the room is private — use the ECIES per-member
    flow in keys.py there. This is intentionally strict: we refuse to
    store a key the moment confidentiality matters, so an accidental
    API call can't widen the trust model.
    """
    if not _HEX64.match(body.key_hex.lower()):
        raise HTTPException(400, "key_hex must be 64 lowercase hex chars")

    actor = _require_member(room_id, u.id, db)
    if actor.role not in (RoomRole.ADMIN, RoomRole.OWNER):
        raise HTTPException(403, "Only OWNER/ADMIN can manage the public room key")

    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(404)
    if room.is_private:
        raise HTTPException(
            409,
            "Room is private — use /provide-key (ECIES) instead. "
            "If you want server-side escrow, flip the room to public first.",
        )

    row = db.query(PublicRoomKey).filter(PublicRoomKey.room_id == room_id).first()
    if row is None:
        row = PublicRoomKey(
            room_id=room_id,
            key_hex=body.key_hex.lower(),
            algorithm=body.algorithm,
        )
        db.add(row)
        rotated = False
    else:
        row.key_hex = body.key_hex.lower()
        row.algorithm = body.algorithm
        row.rotated_at = datetime.now(timezone.utc)
        rotated = True
    db.commit()

    # Tell current members to re-pull the key. Offline members will pick
    # it up on their next GET; no queuing needed because the DB row IS
    # the delivery mechanism.
    try:
        await manager.broadcast_to_room(room_id, {
            "type": "public_room_key_updated",
            "room_id": room_id,
            "rotated": rotated,
        })
    except Exception as e:  # broadcast is best-effort
        logger.debug("broadcast public_room_key_updated failed: %s", e)

    return {"ok": True, "rotated": rotated,
            "created_at": (row.created_at or datetime.now(timezone.utc)).isoformat()}


@router.get("/{room_id}/public-key")
async def get_public_key(
    room_id: int,
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fetch the plaintext room key for a public room.

    Any authenticated user can read — membership is not required because
    public rooms by definition allow anonymous readers. The auth check is
    still here so we don't serve keys to unauthenticated scrapers (a
    privacy-adjacent concern even for public content: it limits trivial
    enumeration).
    """
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(404)
    if room.is_private:
        raise HTTPException(403, "Room is private — no server-held key")

    row = db.query(PublicRoomKey).filter(PublicRoomKey.room_id == room_id).first()
    if row is None:
        raise HTTPException(404, "No public key set for this room yet")

    return {
        "room_id":    room_id,
        "key_hex":    row.key_hex,
        "algorithm":  row.algorithm,
        "created_at": (row.created_at or datetime.now(timezone.utc)).isoformat(),
        "rotated_at": row.rotated_at.isoformat() if row.rotated_at else None,
    }


@router.delete("/{room_id}/public-key")
async def delete_public_key(
    room_id: int,
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """OWNER/ADMIN forces key invalidation and expects clients to rotate."""
    actor = _require_member(room_id, u.id, db)
    if actor.role not in (RoomRole.ADMIN, RoomRole.OWNER):
        raise HTTPException(403, "Only OWNER/ADMIN can invalidate the key")
    wiped = invalidate_server_key(room_id, db)
    db.commit()
    return {"ok": True, "wiped": wiped}
