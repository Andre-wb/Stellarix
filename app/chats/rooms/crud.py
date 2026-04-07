"""
rooms_crud — CRUD-операции с комнатами: создание, получение, обновление, удаление, покидание.
"""
from __future__ import annotations

import io
import logging
import os
import secrets as _secrets

from fastapi import Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.models_rooms import EncryptedRoomKey, Message, Room, RoomMember, RoomRole
from app.peer.connection_manager import manager
from app.security.auth_jwt import get_current_user
from app.security.key_exchange import validate_ecies_payload
from app.utilites.utils import generative_invite_code

from app.chats.rooms.helpers import (
    router,
    RoomCreate,
    RoomUpdate,
    _room_dict,
    _require_member,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Создание комнаты
# ══════════════════════════════════════════════════════════════════════════════

@router.post("", status_code=201)
async def create_room(
        body: RoomCreate,
        u: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """
    Создаёт новую комнату.

    Клиент обязан передать encrypted_room_key — ключ комнаты, зашифрованный
    ECIES публичным ключом X25519 создателя. Сервер хранит зашифрованный blob
    и не может расшифровать его без приватного ключа создателя.

    Пример (JavaScript клиент):
      const roomKey    = crypto.getRandomValues(new Uint8Array(32));
      const encKey     = await eciesEncrypt(roomKey, myPubkeyHex);
      // encKey = {ephemeral_pub: "...", ciphertext: "..."}
      await fetch("/api/rooms", {method:"POST", body: JSON.stringify({
        name: "General",
        encrypted_room_key: encKey
      })})
    """
    if not u.x25519_public_key:
        raise HTTPException(400, "Необходим X25519 публичный ключ для создания комнаты")

    # Валидируем ECIES payload
    payload = body.encrypted_room_key.model_dump()
    if not validate_ecies_payload(payload):
        raise HTTPException(400, "Некорректный encrypted_room_key формат")

    # Создаём комнату без room_key — сервер не хранит ключ в открытом виде
    room = Room(
        name        = body.name,
        description = body.description,
        creator_id  = u.id,
        is_private  = body.is_private,
        is_voice    = body.is_voice,
        invite_code = generative_invite_code(8),
        max_members = 200,
        avatar_emoji = "🔊" if body.is_voice else "💬",
        # room_key намеренно отсутствует
    )
    db.add(room)
    db.flush()  # получаем room.id

    # Создаём участника-владельца
    db.add(RoomMember(room_id=room.id, user_id=u.id, role=RoomRole.OWNER))

    # Сохраняем зашифрованный ключ для создателя
    db.add(EncryptedRoomKey(
        room_id       = room.id,
        user_id       = u.id,
        ephemeral_pub = body.encrypted_room_key.ephemeral_pub,
        ciphertext    = body.encrypted_room_key.ciphertext,
        recipient_pub = u.x25519_public_key,
    ))

    db.commit()
    db.refresh(room)

    # Auto-add antispam bot to new rooms (skip DMs — they must have exactly 2 members)
    if not getattr(room, "is_dm", False):
        from app.bots.antispam_bot import add_antispam_bot_to_room
        add_antispam_bot_to_room(room.id, db)

    logger.info(f"Room created: '{room.name}' (id={room.id}) by {u.username}")

    return JSONResponse(status_code=201, content={
        **_room_dict(room),
        "has_key": True,   # создатель уже имеет ключ
    })


# ══════════════════════════════════════════════════════════════════════════════
# Стандартные операции с комнатами
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/my")
async def my_rooms(u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    members = db.query(RoomMember).filter(
        RoomMember.user_id == u.id, RoomMember.is_banned == False).all()
    member_map = {m.room_id: m for m in members}
    ids = list(member_map.keys())
    rooms = db.query(Room).filter(Room.id.in_(ids), Room.is_dm == False, Room.is_channel == False).all()

    # Для каждой комнаты проверяем наличие ключа
    key_set = {
        ek.room_id
        for ek in db.query(EncryptedRoomKey).filter(
            EncryptedRoomKey.user_id == u.id,
            EncryptedRoomKey.room_id.in_(ids),
            ).all()
    }

    result = []
    for r in rooms:
        d = {**_room_dict(r), "has_key": r.id in key_set}
        # Подсчёт непрочитанных сообщений
        m = member_map.get(r.id)
        last_read = m.last_read_message_id or 0 if m else 0
        d["unread_count"] = db.query(func.count(Message.id)).filter(
            Message.room_id == r.id,
            Message.id > last_read,
        ).scalar() or 0
        d["is_muted"] = m.is_muted if m else False
        d["my_role"] = m.role.value if m else None
        result.append(d)

    return {"rooms": result}


@router.get("/public")
async def public_rooms(
    q:           str  = "",
    type:        str  = "all",     # all | group | channel | voice
    min_members: int  = 0,
    sort:        str  = "newest",  # newest | popular | online
    offset:      int  = 0,
    limit:       int  = 40,
    db: Session = Depends(get_db),
):
    """Каталог публичных комнат с фильтрацией и пагинацией."""
    qs = db.query(Room).filter(Room.is_private == False)

    if type == "group":
        qs = qs.filter(Room.is_channel == False, Room.is_voice == False)
    elif type == "channel":
        qs = qs.filter(Room.is_channel == True)
    elif type == "voice":
        qs = qs.filter(Room.is_voice == True)

    if q:
        pattern = f"%{q}%"
        qs = qs.filter(Room.name.ilike(pattern) | Room.description.ilike(pattern))

    rooms_all = qs.all()

    if min_members > 0:
        rooms_all = [r for r in rooms_all if r.member_count() >= min_members]

    if sort == "popular":
        rooms_all.sort(key=lambda r: r.member_count(), reverse=True)
    elif sort == "online":
        rooms_all.sort(key=lambda r: len(manager.get_online_users(r.id)), reverse=True)
    else:
        rooms_all.sort(key=lambda r: r.created_at or "", reverse=True)

    total = len(rooms_all)
    page  = rooms_all[offset: offset + max(1, min(limit, 100))]
    return {"rooms": [_room_dict(r) for r in page], "total": total, "offset": offset}


@router.get("/{room_id}")
async def get_room(
        room_id: int,
        u: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    r = db.query(Room).filter(Room.id == room_id).first()
    if not r:
        raise HTTPException(404)
    _require_member(room_id, u.id, db)

    # Добавляем роль текущего пользователя для фронтенда
    member = db.query(RoomMember).filter(
        RoomMember.room_id == room_id, RoomMember.user_id == u.id,
    ).first()
    d = _room_dict(r)
    d["my_role"] = member.role.value if member else None
    return d


# ══════════════════════════════════════════════════════════════════════════════
# Обновление настроек комнаты
# ══════════════════════════════════════════════════════════════════════════════

@router.put("/{room_id}")
async def update_room(
        room_id: int,
        body: RoomUpdate,
        u: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """
    Обновляет настройки комнаты. Только OWNER или ADMIN.
    """
    actor = _require_member(room_id, u.id, db)
    if actor.role not in (RoomRole.ADMIN, RoomRole.OWNER):
        raise HTTPException(403, "Недостаточно прав для изменения настроек")

    r = db.query(Room).filter(Room.id == room_id).first()
    if not r:
        raise HTTPException(404)

    if body.name is not None:
        r.name = body.name.strip()[:100]
    if body.description is not None:
        r.description = body.description.strip()[:500]
    if body.avatar_emoji is not None:
        r.avatar_emoji = body.avatar_emoji[:10]
    if body.is_private is not None:
        r.is_private = body.is_private
    if body.auto_delete_seconds is not None:
        r.auto_delete_seconds = body.auto_delete_seconds if body.auto_delete_seconds > 0 else None
    if body.slow_mode_seconds is not None:
        r.slow_mode_seconds = max(0, body.slow_mode_seconds)
    if body.antispam_enabled is not None:
        r.antispam_enabled = body.antispam_enabled

        # Auto-add/remove antispam bot from room
        from app.bots.antispam_bot import add_antispam_bot_to_room, remove_antispam_bot_from_room
        if body.antispam_enabled:
            add_antispam_bot_to_room(room_id, db)
        else:
            remove_antispam_bot_from_room(room_id, db)

    if body.antispam_config is not None:
        # Validate JSON
        import json as _json
        try:
            parsed = _json.loads(body.antispam_config)
            if not isinstance(parsed, dict):
                raise ValueError
            # Sanitize: only allow known keys with valid values
            safe = {}
            if "threshold" in parsed and parsed["threshold"] in (5, 10, 15):
                safe["threshold"] = parsed["threshold"]
            if "action" in parsed and parsed["action"] in ("warn", "mute", "kick", "ban"):
                safe["action"] = parsed["action"]
            if "block_repeats" in parsed:
                safe["block_repeats"] = bool(parsed["block_repeats"])
            if "block_links" in parsed:
                safe["block_links"] = bool(parsed["block_links"])
            r.antispam_config = _json.dumps(safe)
        except (ValueError, _json.JSONDecodeError) as e:
            logger.warning("Room %s: invalid antispam_config JSON, keeping previous: %s", room_id, e)

    if body.discussion_enabled is not None:
        r.discussion_enabled = body.discussion_enabled

    # Channel-specific fields
    if body.reactions_type is not None:
        r.reactions_type = body.reactions_type
    if body.allowed_reactions is not None:
        r.allowed_reactions = body.allowed_reactions[:500]
    if body.admin_signatures is not None:
        r.admin_signatures = body.admin_signatures
    if body.copy_protection is not None:
        r.copy_protection = body.copy_protection
    if body.silent_default is not None:
        r.silent_default = body.silent_default
    if body.join_approval is not None:
        r.join_approval = body.join_approval
    if body.hashtags_enabled is not None:
        r.hashtags_enabled = body.hashtags_enabled

    db.commit()
    db.refresh(r)

    logger.info(f"Room {room_id} updated by {u.username}")

    # Уведомляем участников об изменении настроек
    await manager.broadcast_to_room(room_id, {
        "type":       "room_updated",
        "room":       _room_dict(r),
    })

    return _room_dict(r)


@router.post("/{room_id}/avatar")
async def upload_room_avatar(
        room_id: int,
        file: UploadFile = File(...),
        u: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """
    Загружает аватар комнаты. Только OWNER или ADMIN.
    Шаблон аналогичен /api/authentication/avatar.
    """
    actor = _require_member(room_id, u.id, db)
    if actor.role not in (RoomRole.ADMIN, RoomRole.OWNER):
        raise HTTPException(403, "Недостаточно прав")

    r = db.query(Room).filter(Room.id == room_id).first()
    if not r:
        raise HTTPException(404)

    from PIL import Image

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "Макс. 5 МБ")

    try:
        img = Image.open(io.BytesIO(content))
        img = img.convert("RGB")
        img.thumbnail((256, 256))
    except Exception:
        raise HTTPException(400, "Неверный формат изображения")

    os.makedirs("uploads/room_avatars", exist_ok=True)
    filename = f"{_secrets.token_hex(16)}.jpg"
    path = f"uploads/room_avatars/{filename}"
    img.save(path, "JPEG", quality=85)

    r.avatar_url = f"/uploads/room_avatars/{filename}"
    db.commit()

    logger.info(f"Room {room_id} avatar uploaded by {u.username}")

    # Уведомляем участников
    await manager.broadcast_to_room(room_id, {
        "type":       "room_updated",
        "room":       _room_dict(r),
    })

    return {"ok": True, "avatar_url": r.avatar_url}


@router.delete("/{room_id}/leave")
async def leave_room(
        room_id: int,
        u: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    m = db.query(RoomMember).filter(
        RoomMember.room_id == room_id, RoomMember.user_id == u.id).first()
    if not m:
        raise HTTPException(404)

    # Удаляем зашифрованный ключ участника
    db.query(EncryptedRoomKey).filter(
        EncryptedRoomKey.room_id == room_id,
        EncryptedRoomKey.user_id == u.id,
        ).delete()

    r = db.query(Room).filter(Room.id == room_id).first()
    remaining = r.member_count() - 1 if r else 0

    db.delete(m)

    if m.role == RoomRole.OWNER and r and remaining <= 0:
        db.delete(r)
        db.commit()
        return {"left": True, "room_deleted": True}

    db.commit()

    # Ротация ключа — покинувший участник не сможет расшифровать новые сообщения
    await manager.broadcast_to_room(room_id, {"type": "key_rotated"})
    logger.info(f"Room key rotated after leave in room {room_id}")

    return {"left": True, "room_deleted": False}


@router.delete("/{room_id}")
async def delete_room(
        room_id: int,
        u: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    m = _require_member(room_id, u.id, db)
    if m.role != RoomRole.OWNER:
        raise HTTPException(403, "Только владелец может удалить комнату")
    r = db.query(Room).filter(Room.id == room_id).first()
    if not r:
        raise HTTPException(404)
    await manager.broadcast_to_room(room_id, {"type": "room_deleted"})
    db.delete(r)
    db.commit()
    return {"ok": True}
