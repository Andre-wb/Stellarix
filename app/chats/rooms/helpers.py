"""
rooms_helpers — Общий router, Pydantic-модели, вспомогательные функции для модуля rooms.

Все route-модули (rooms_crud, rooms_members, rooms_keys, rooms_theme)
импортируют ``router`` отсюда, чтобы маршруты регистрировались на одном APIRouter.
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
# Pydantic схемы
# ══════════════════════════════════════════════════════════════════════════════

class EncryptedKeyPayload(BaseModel):
    """ECIES-зашифрованный ключ комнаты."""
    ephemeral_pub: str = Field(..., min_length=64, max_length=64,
                               description="X25519 ephemeral pubkey hex (32 bytes)")
    ciphertext:    str = Field(..., min_length=24,
                               description="AES-256-GCM ciphertext hex (nonce+ct+tag)")


class RoomCreate(BaseModel):
    name:        str              = Field(..., min_length=1, max_length=100)
    description: str              = Field("", max_length=500)
    is_private:  bool             = False
    is_voice:    bool             = False   # True = voice channel (persistent, join/leave)

    # Клиент генерирует room_key(32 bytes) локально и шифрует ECIES своим X25519 pubkey.
    # Сервер сохраняет этот зашифрованный blob — не может расшифровать без приватного ключа клиента.
    encrypted_room_key: EncryptedKeyPayload = Field(
        ...,
        description="room_key(32 bytes), зашифрованный ECIES публичным ключом X25519 создателя"
    )


class ProvideKeyRequest(BaseModel):
    """Запрос на передачу ключа ожидающему участнику (от online-участника)."""
    for_user_id:   int = Field(..., description="user_id участника, которому нужен ключ")
    ephemeral_pub: str = Field(..., min_length=64, max_length=64)
    ciphertext:    str = Field(..., min_length=24)


class RoomUpdate(BaseModel):
    """Обновление настроек комнаты (только owner/admin)."""
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
# Вспомогательные функции
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
        "online_count":        len(manager.get_online_users(r.id)),
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
        raise HTTPException(403, "Вы не участник этой комнаты")
    return m


async def _broadcast_key_request(room_id: int, for_user_id: int, for_pubkey: str,
                                  for_kyber_pubkey: str | None = None) -> None:
    """
    Рассылает всем online-участникам комнаты запрос на re-encryption ключа.
    Любой участник, у которого есть room_key, должен зашифровать его для нового участника.
    Включает kyber_public_key для гибридного PQ шифрования (если доступен).
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
        if body.wallpaper not in _VALID_WALLPAPERS and not body.wallpaper.startswith("http"):
            raise HTTPException(400, f"Недопустимый wallpaper: {body.wallpaper}")
        d["wallpaper"] = body.wallpaper
    if body.accent is not None:
        d["accent"] = body.accent
    if body.dark_mode is not None:
        d["dark_mode"] = body.dark_mode
    return _json.dumps(d, ensure_ascii=False)
