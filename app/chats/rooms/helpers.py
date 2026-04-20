"""
rooms_helpers — Shared router, Pydantic models, and helper functions for the rooms module.

All route modules (rooms_crud, rooms_members, rooms_keys, rooms_theme)
import ``router`` from here so that routes are registered on a single APIRouter.
"""
from __future__ import annotations

import json as _json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models_rooms import RoomMember, Room, RoomRole
from app.peer.connection_manager import manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rooms", tags=["rooms"])


# ══════════════════════════════════════════════════════════════════════════════
# Pydantic schemas
# ══════════════════════════════════════════════════════════════════════════════

class EncryptedKeyPayload(BaseModel):
    """ECIES-encrypted room key."""
    ephemeral_pub: str = Field(..., min_length=64, max_length=64,
                               description="X25519 ephemeral pubkey hex (32 bytes)")
    ciphertext:    str = Field(..., min_length=24,
                               description="AES-256-GCM ciphertext hex (nonce+ct+tag)")


class RoomCreate(BaseModel):
    name:        str              = Field(..., min_length=1, max_length=100)
    description: str              = Field("", max_length=500)
    is_private:  bool             = False
    is_voice:    bool             = False   # True = voice channel (persistent, join/leave)

    # Client generates room_key(32 bytes) locally and encrypts with ECIES using its X25519 pubkey.
    # Server stores the encrypted blob — cannot decrypt without the client's private key.
    encrypted_room_key: EncryptedKeyPayload = Field(
        ...,
        description="room_key(32 bytes), encrypted with ECIES using the creator's X25519 public key"
    )
    # Variant-B plaintext copy — used ONLY for is_private=False rooms so the
    # server can hand the key to new joiners without a round-trip to an
    # online member. Ignored for private rooms. If omitted on a public
    # room the server generates its own key server-side.
    public_room_key_hex: Optional[str] = Field(
        None, min_length=64, max_length=64,
        description="Plaintext 32-byte AES-256 room key (hex). Public rooms only."
    )


class ProvideKeyRequest(BaseModel):
    """Request to provide a key to a waiting member (from an online member)."""
    for_user_id:   int = Field(..., description="user_id of the member who needs the key")
    ephemeral_pub: str = Field(..., min_length=64, max_length=64)
    ciphertext:    str = Field(..., min_length=24)


class RoomUpdate(BaseModel):
    """Room settings update (owner/admin only)."""
    name:                Optional[str]  = Field(None, min_length=1, max_length=100)
    description:         Optional[str]  = Field(None, max_length=500)
    avatar_emoji:        Optional[str]  = Field(None, max_length=10)
    is_private:          Optional[bool] = None
    auto_delete_seconds: Optional[int]  = None   # None/0 = disabled, 30, 300, 3600, 86400
    slow_mode_seconds:   Optional[int]  = None   # 0 = disabled, 5, 15, 30, 60
    antispam_enabled:    Optional[bool] = None
    antispam_config:     Optional[str]  = None   # JSON: {threshold, action, block_repeats, block_links}
    discussion_enabled:  Optional[bool] = None   # Channel: enable comments under posts
    reactions_type:      Optional[str]  = Field(None, pattern=r"^(all|selected|off)$")
    allowed_reactions:   Optional[str]  = Field(None, max_length=500)  # comma-separated emojis
    admin_signatures:    Optional[bool] = None   # Show admin name under channel posts
    copy_protection:     Optional[bool] = None   # Disable copy/forward in channel
    silent_default:      Optional[bool] = None   # Posts silent by default
    join_approval:       Optional[bool] = None   # Require approval to join
    hashtags_enabled:    Optional[bool] = None   # Clickable hashtags


class ChangeRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(admin|member)$")


class RoomThemeBody(BaseModel):
    wallpaper: Optional[str] = Field(None, max_length=255)
    accent: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    dark_mode: Optional[bool] = None


# ══════════════════════════════════════════════════════════════════════════════
# Helper functions
# ══════════════════════════════════════════════════════════════════════════════

def _room_dict(r: Room) -> dict:
    from app.chats.voice import get_voice_participants
    d = {
        "id":                  r.id,
        "name":                r.name,
        "description":         r.description or "",
        "is_private":          r.is_private,
        "is_channel":          r.is_channel,
        "is_voice":            getattr(r, "is_voice", False) or False,
        "invite_code":         r.invite_code,
        "member_count":        r.member_count(),
        "online_count":        manager.count_online_from_set(r.member_user_ids()),
        "avatar_emoji":        r.avatar_emoji or "\U0001f4ac",
        "avatar_url":          r.avatar_url,
        "auto_delete_seconds": r.auto_delete_seconds,
        "slow_mode_seconds":   r.slow_mode_seconds or 0,
        "antispam_enabled":    r.antispam_enabled if r.antispam_enabled is not None else True,
        "antispam_config":     getattr(r, "antispam_config", None) or "{}",
        "creator_id":          r.creator_id,
        "created_at":          r.created_at.isoformat(),
        "theme_json":          r.theme_json,
        "discussion_enabled":  getattr(r, "discussion_enabled", False) or False,
        "reactions_type":      getattr(r, "reactions_type", "all") or "all",
        "allowed_reactions":   getattr(r, "allowed_reactions", "") or "",
        "admin_signatures":    getattr(r, "admin_signatures", False) or False,
        "copy_protection":     getattr(r, "copy_protection", False) or False,
        "silent_default":      getattr(r, "silent_default", False) or False,
        "join_approval":       getattr(r, "join_approval", False) or False,
        "hashtags_enabled":    getattr(r, "hashtags_enabled", True) if hasattr(r, "hashtags_enabled") else True,
        "replication_mode":    getattr(r, "replication_mode", "none") or "none",
        "is_dm":               bool(getattr(r, "is_dm", False)),
    }
    # Add voice participants for voice channels
    if d["is_voice"]:
        participants = get_voice_participants(r.id)
        d["voice_participants"] = participants
        d["voice_participant_count"] = len(participants)
    return d


def _require_member(room_id: int, user_id: int, db: Session) -> RoomMember:
    m = db.query(RoomMember).filter(
        RoomMember.room_id == room_id,
        RoomMember.user_id == user_id,
        RoomMember.is_banned == False,
        ).first()
    if not m:
        raise HTTPException(403, "You are not a member of this room")
    return m


async def _broadcast_key_request(room_id: int, for_user_id: int, for_pubkey: str,
                                  for_kyber_pubkey: str | None = None) -> None:
    """
    Broadcasts a key re-encryption request to all online room members.
    Any member who has the room_key should encrypt it for the new member.
    Includes kyber_public_key for hybrid PQ encryption (if available).
    """
    payload = {
        "type":        "key_request",
        "for_user_id": for_user_id,
        "for_pubkey":  for_pubkey,
    }
    if for_kyber_pubkey:
        payload["for_kyber_pubkey"] = for_kyber_pubkey
    await manager.broadcast_to_room(room_id, payload, exclude=for_user_id)


# ── Theme helpers ─────────────────────────────────────────────────────────────

_VALID_WALLPAPERS = {"none", "stars", "aurora", "sunset", "ocean-wave", "mesh", "deep-space"}


def _validate_theme(body: RoomThemeBody) -> str:
    """Validate and serialize theme to JSON string."""
    d = {}
    if body.wallpaper is not None:
        # Allow preset names or custom URLs
        if body.wallpaper not in _VALID_WALLPAPERS and not body.wallpaper.startswith("https://"):
            raise HTTPException(400, f"Invalid wallpaper: {body.wallpaper}")
        d["wallpaper"] = body.wallpaper
    if body.accent is not None:
        d["accent"] = body.accent
    if body.dark_mode is not None:
        d["dark_mode"] = body.dark_mode
    return _json.dumps(d, ensure_ascii=False)
