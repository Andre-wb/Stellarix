"""Server-held room key for PUBLIC rooms only (Variant B escrow).

Design goal: in public rooms, channels, and public spaces, members can
catch up offline without waiting for an online peer to ECIES-wrap the
room key for them. The server stores the symmetric room key in plaintext
here — this is deliberate: "public" means anyone can read, so there's
no confidentiality left to preserve. The DB only holds keys for rooms
where ``Room.is_private is False``. On a public→private flip, the
row MUST be deleted and clients MUST rotate to a new key.

Private rooms keep the existing ECIES-per-member flow via
``EncryptedRoomKey`` — that code path is untouched.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, String,
)

from app.base import Base


class PublicRoomKey(Base):
    __tablename__ = "public_room_keys"

    # One row per public room. The PK-on-FK guarantees uniqueness without a
    # separate index, and ON DELETE CASCADE means dropping a room wipes the
    # key automatically (no dangling rows).
    room_id      = Column(
        Integer,
        ForeignKey("rooms.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # 32-byte AES-256 key, hex-encoded = 64 chars. Stored plaintext because
    # the room is public by definition; confidentiality was already given up
    # when the room was marked is_private=False.
    key_hex      = Column(String(64),  nullable=False)
    algorithm    = Column(String(32),  nullable=False, default="aes-256-gcm")
    created_at   = Column(DateTime,    default=lambda: datetime.now(timezone.utc))
    # Set when the key has been rotated in place (room owner re-uploads a
    # fresh key; old one remains usable for history decryption on clients
    # but all new messages use the new key).
    rotated_at   = Column(DateTime,    nullable=True)
