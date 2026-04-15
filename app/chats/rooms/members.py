"""
rooms_members — Управление участниками комнаты: список, кик, роли, мут, бан.
"""
from __future__ import annotations

import logging

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.models_rooms import EncryptedRoomKey, PendingKeyRequest, RoomMember, RoomRole
from app.peer.connection_manager import manager
from app.security.auth_jwt import get_current_user

from app.chats.rooms.helpers import (
    router,
    ChangeRoleRequest,
    _require_member,
)

import json as _json
from typing import Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _parse_perms(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        return _json.loads(raw)
    except Exception:
        return None


# Granular permission keys that owner/admin can toggle per member
PERMISSION_KEYS = [
    "can_send",           # Send messages
    "can_send_media",     # Send photos/videos/files
    "can_send_stickers",  # Send stickers & GIFs
    "can_send_links",     # Send links
    "can_pin",            # Pin messages
    "can_delete_others",  # Delete other's messages
    "can_invite",         # Add members
    "can_change_info",    # Edit room name/description/avatar
    "can_manage_calls",   # Start/end group calls
]


class SetTagRequest(BaseModel):
    tag: Optional[str] = Field(None, max_length=30)
    tag_color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")


class SetPermissionsRequest(BaseModel):
    permissions: dict


@router.get("/{room_id}/members")
async def members(
        room_id: int,
        u: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    actor = _require_member(room_id, u.id, db)
    all_m = db.query(RoomMember).filter(RoomMember.room_id == room_id).all()

    # Участники с pending key requests
    pending_ids = {
        p.user_id for p in db.query(PendingKeyRequest).filter(
            PendingKeyRequest.room_id == room_id
        ).all()
    }

    return {
        "my_role": actor.role.value,
        "members": [{
            "user_id":      m.user_id,
            "username":     m.user.username      if m.user else "\u2014",
            "display_name": m.user.display_name  if m.user else "\u2014",
            "avatar_emoji": m.user.avatar_emoji  if m.user else "\U0001f464",
            "avatar_url":   m.user.avatar_url   if m.user else None,
            "role":         m.role.value,
            "is_online":    manager.is_online(room_id, m.user_id),
            "is_muted":     m.is_muted,
            "is_banned":    m.is_banned,
            "is_bot":       bool(m.user.is_bot) if m.user else False,
            "x25519_pubkey":m.user.x25519_public_key if m.user else None,
            "has_key":      m.user_id not in pending_ids,
            "tag":          getattr(m, 'tag', None),
            "tag_color":    getattr(m, 'tag_color', None),
            "custom_permissions": _parse_perms(getattr(m, 'custom_permissions', None)),
        } for m in all_m],
    }


@router.post("/{room_id}/kick/{target_id}")
async def kick(
        room_id: int, target_id: int,
        u: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    actor = _require_member(room_id, u.id, db)
    if actor.role not in (RoomRole.ADMIN, RoomRole.OWNER):
        raise HTTPException(403, "Недостаточно прав")

    t = db.query(RoomMember).filter(
        RoomMember.room_id == room_id, RoomMember.user_id == target_id).first()
    if not t or t.role == RoomRole.OWNER:
        raise HTTPException(403)

    t.is_banned = True

    # Удаляем ключ кикнутого участника — он не должен иметь доступ к сообщениям
    db.query(EncryptedRoomKey).filter(
        EncryptedRoomKey.room_id == room_id,
        EncryptedRoomKey.user_id == target_id,
        ).delete()

    db.commit()
    await manager.send_to_user(room_id, target_id, {"type": "kicked"})

    # Ротация ключа — кикнутый участник не сможет расшифровать новые сообщения
    db.query(EncryptedRoomKey).filter(EncryptedRoomKey.room_id == room_id).delete()
    db.commit()
    await manager.broadcast_to_room(room_id, {"type": "key_rotated"})
    logger.info(f"Room key rotated after kick in room {room_id}")

    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# Управление ролями и модерация участников
# ══════════════════════════════════════════════════════════════════════════════

@router.put("/{room_id}/members/{target_id}/role")
async def change_member_role(
        room_id: int, target_id: int,
        body: ChangeRoleRequest,
        u: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """Изменить роль участника. Только OWNER может назначать/снимать админов."""
    actor = _require_member(room_id, u.id, db)
    if actor.role != RoomRole.OWNER:
        raise HTTPException(403, "Только владелец может менять роли")

    if target_id == u.id:
        raise HTTPException(400, "Нельзя изменить свою роль")

    t = db.query(RoomMember).filter(
        RoomMember.room_id == room_id, RoomMember.user_id == target_id).first()
    if not t:
        raise HTTPException(404, "Участник не найден")
    if t.role == RoomRole.OWNER:
        raise HTTPException(403, "Нельзя изменить роль владельца")

    new_role = RoomRole.ADMIN if body.role == "admin" else RoomRole.MEMBER
    t.role = new_role
    db.commit()

    await manager.broadcast_to_room(room_id, {
        "type": "member_updated",
        "user_id": target_id,
        "role": new_role.value,
    })
    logger.info(f"Role changed: user {target_id} -> {new_role.value} in room {room_id} by {u.username}")

    return {"ok": True, "role": new_role.value}


@router.put("/{room_id}/members/{target_id}/mute")
async def toggle_mute_member(
        room_id: int, target_id: int,
        u: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """Заглушить / разглушить участника. ADMIN и OWNER могут мутить."""
    actor = _require_member(room_id, u.id, db)
    if actor.role not in (RoomRole.ADMIN, RoomRole.OWNER):
        raise HTTPException(403, "Недостаточно прав")

    if target_id == u.id:
        raise HTTPException(400, "Нельзя заглушить себя")

    t = db.query(RoomMember).filter(
        RoomMember.room_id == room_id, RoomMember.user_id == target_id).first()
    if not t:
        raise HTTPException(404, "Участник не найден")
    if t.role == RoomRole.OWNER:
        raise HTTPException(403, "Нельзя заглушить владельца")
    if t.role == RoomRole.ADMIN and actor.role != RoomRole.OWNER:
        raise HTTPException(403, "Только владелец может заглушить админа")

    t.is_muted = not t.is_muted
    db.commit()

    await manager.broadcast_to_room(room_id, {
        "type": "member_updated",
        "user_id": target_id,
        "is_muted": t.is_muted,
    })
    logger.info(f"Mute toggled: user {target_id} is_muted={t.is_muted} in room {room_id} by {u.username}")

    return {"ok": True, "is_muted": t.is_muted}


@router.put("/{room_id}/members/{target_id}/ban")
async def toggle_ban_member(
        room_id: int, target_id: int,
        u: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """Забанить / разбанить участника. ADMIN и OWNER могут банить."""
    actor = _require_member(room_id, u.id, db)
    if actor.role not in (RoomRole.ADMIN, RoomRole.OWNER):
        raise HTTPException(403, "Недостаточно прав")

    if target_id == u.id:
        raise HTTPException(400, "Нельзя забанить себя")

    t = db.query(RoomMember).filter(
        RoomMember.room_id == room_id, RoomMember.user_id == target_id).first()
    if not t:
        raise HTTPException(404, "Участник не найден")
    if t.role == RoomRole.OWNER:
        raise HTTPException(403, "Нельзя забанить владельца")
    if t.role == RoomRole.ADMIN and actor.role != RoomRole.OWNER:
        raise HTTPException(403, "Только владелец может забанить админа")

    t.is_banned = not t.is_banned
    db.commit()

    if t.is_banned:
        # Удаляем ключ забаненного участника
        db.query(EncryptedRoomKey).filter(
            EncryptedRoomKey.room_id == room_id,
            EncryptedRoomKey.user_id == target_id,
        ).delete()
        db.commit()
        await manager.send_to_user(room_id, target_id, {"type": "kicked"})

    await manager.broadcast_to_room(room_id, {
        "type": "member_updated",
        "user_id": target_id,
        "is_banned": t.is_banned,
    })
    logger.info(f"Ban toggled: user {target_id} is_banned={t.is_banned} in room {room_id} by {u.username}")

    return {"ok": True, "is_banned": t.is_banned}


# ══════════════════════════════════════════════════════════════════════════════
# Теги участников
# ══════════════════════════════════════════════════════════════════════════════

@router.put("/{room_id}/members/{target_id}/tag")
async def set_member_tag(
        room_id: int, target_id: int,
        body: SetTagRequest,
        u: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """Назначить / снять тег участника. Только OWNER и ADMIN."""
    actor = _require_member(room_id, u.id, db)
    if actor.role not in (RoomRole.ADMIN, RoomRole.OWNER):
        raise HTTPException(403, "Недостаточно прав")

    t = db.query(RoomMember).filter(
        RoomMember.room_id == room_id, RoomMember.user_id == target_id).first()
    if not t:
        raise HTTPException(404, "Участник не найден")

    t.tag = body.tag
    t.tag_color = body.tag_color
    db.commit()

    await manager.broadcast_to_room(room_id, {
        "type": "member_updated",
        "user_id": target_id,
        "tag": t.tag,
        "tag_color": t.tag_color,
    })

    return {"ok": True, "tag": t.tag, "tag_color": t.tag_color}


# ══════════════════════════════════════════════════════════════════════════════
# Гранулярные права участников
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/{room_id}/permissions-schema")
async def get_permissions_schema(u: User = Depends(get_current_user)):
    """Возвращает список доступных прав для UI."""
    return {"permissions": PERMISSION_KEYS}


@router.put("/{room_id}/members/{target_id}/permissions")
async def set_member_permissions(
        room_id: int, target_id: int,
        body: SetPermissionsRequest,
        u: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """Установить гранулярные права участника. Только OWNER."""
    actor = _require_member(room_id, u.id, db)
    if actor.role != RoomRole.OWNER:
        raise HTTPException(403, "Только владелец может менять права")

    t = db.query(RoomMember).filter(
        RoomMember.room_id == room_id, RoomMember.user_id == target_id).first()
    if not t:
        raise HTTPException(404, "Участник не найден")

    # Validate keys
    cleaned = {k: bool(v) for k, v in body.permissions.items() if k in PERMISSION_KEYS}
    t.custom_permissions = _json.dumps(cleaned) if cleaned else None
    db.commit()

    await manager.broadcast_to_room(room_id, {
        "type": "member_updated",
        "user_id": target_id,
        "custom_permissions": cleaned,
    })

    return {"ok": True, "permissions": cleaned}


# ══════════════════════════════════════════════════════════════════════════════
# Bot commands in room — for slash command autocomplete
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/{room_id}/bot-commands")
async def get_room_bot_commands(
    room_id: int,
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all bot commands available in this room."""
    import json as _json
    from app.bots.bot_crud import Bot

    # Get bot user_ids in this room
    bot_members = db.query(RoomMember.user_id).filter(
        RoomMember.room_id == room_id,
    ).all()
    bot_user_ids = [m[0] for m in bot_members]

    # Find bots among members
    bots = db.query(Bot).filter(Bot.user_id.in_(bot_user_ids)).all() if bot_user_ids else []

    # Also include bots if this is a DM with a bot
    if not bots:
        other = db.query(RoomMember).filter(
            RoomMember.room_id == room_id,
            RoomMember.user_id != u.id,
        ).first()
        if other:
            bot = db.query(Bot).filter(Bot.user_id == other.user_id).first()
            if bot:
                bots = [bot]

    commands = []
    for bot in bots:
        cmds = bot.commands
        if isinstance(cmds, str):
            try:
                cmds = _json.loads(cmds)
            except Exception:
                cmds = []
        if isinstance(cmds, list):
            for c in cmds:
                if isinstance(c, dict) and c.get("command"):
                    commands.append({
                        "command": c["command"],
                        "description": c.get("description", ""),
                        "bot_name": bot.name,
                    })

    return {"commands": commands}
