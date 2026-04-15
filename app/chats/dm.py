"""
app/chats/dm.py — API для личных сообщений (Direct Messages).

DM реализованы как комнаты с is_dm=True, max_members=2.
Ключи шифруются через ECIES как и в обычных комнатах.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.models.contact import Contact
from app.models_rooms import (
    EncryptedRoomKey, Message, PendingKeyRequest, Room, RoomMember, RoomRole,
)
from app.peer.connection_manager import manager
from app.security.auth_jwt import get_current_user
from app.security.key_exchange import validate_ecies_payload
from app.utilites.utils import generative_invite_code

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dm", tags=["dm"])


# ══════════════════════════════════════════════════════════════════════════════
# Pydantic схемы
# ══════════════════════════════════════════════════════════════════════════════

class EncryptedKeyPayload(BaseModel):
    ephemeral_pub: str = Field(..., min_length=64, max_length=64)
    ciphertext:    str = Field(..., min_length=24)


class CreateDMRequest(BaseModel):
    encrypted_room_key: EncryptedKeyPayload | None = None
    encrypted_key_for_target: EncryptedKeyPayload | None = None


# ══════════════════════════════════════════════════════════════════════════════
# Вспомогательные функции
# ══════════════════════════════════════════════════════════════════════════════

def _find_existing_dm(user_a: int, user_b: int, db: Session) -> Room | None:
    """Находит существующую DM комнату между двумя пользователями."""
    rooms_a = (
        db.query(RoomMember.room_id)
        .join(Room, Room.id == RoomMember.room_id)
        .filter(Room.is_dm == True, RoomMember.user_id == user_a)
        .subquery()
    )
    dm_room_id = (
        db.query(RoomMember.room_id)
        .filter(
            RoomMember.room_id.in_(db.query(rooms_a.c.room_id)),
            RoomMember.user_id == user_b,
        )
        .first()
    )
    if dm_room_id:
        return db.query(Room).filter(Room.id == dm_room_id[0]).first()
    return None


def _is_user_online(user_id: int) -> bool:
    """Проверяет, подключён ли пользователь к какому-либо WS."""
    if hasattr(manager, '_global_ws') and user_id in manager._global_ws:
        return True
    for room_users in manager._rooms.values():
        if user_id in room_users:
            return True
    return False


def _room_to_dict(room: Room, other_user: User, has_key: bool) -> dict:
    """Формирует ответ DM комнаты."""
    return {
        "room": {
            "id":           room.id,
            "name":         room.name,
            "is_dm":        True,
            "is_private":   True,
            "has_key":      has_key,
            "member_count": 2,
            "online_count": 0,
            "invite_code":  room.invite_code,
            "created_at":   room.created_at.isoformat(),
            "updated_at":   room.updated_at.isoformat() if room.updated_at else None,
        },
        "other_user": {
            "user_id":           other_user.id,
            "username":          other_user.username,
            "display_name":      other_user.display_name or other_user.username,
            "avatar_emoji":      other_user.avatar_emoji,
            "avatar_url":        other_user.avatar_url,
            "x25519_public_key": other_user.x25519_public_key,
            "kyber_public_key":  other_user.kyber_public_key,
            "is_bot":            getattr(other_user, 'is_bot', False) or False,
            "is_online":         _is_user_online(other_user.id),
            "last_seen":         other_user.last_seen.isoformat() if other_user.last_seen and getattr(other_user, 'show_last_seen', True) not in (False,) else None,
            "show_last_seen":    getattr(other_user, 'show_last_seen', True) is not False,
            "custom_status":     other_user.custom_status,
            "status_emoji":      other_user.status_emoji,
            "presence":          other_user.presence or "online",
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# Эндпоинты
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/{target_user_id}", status_code=200)
async def create_or_get_dm(
        target_user_id: int,
        body:           CreateDMRequest,
        u:              User    = Depends(get_current_user),
        db:             Session = Depends(get_db),
):
    """
    Получить или создать DM комнату с target_user_id.

    Если DM уже существует — возвращает её.
    Если нет — создаёт комнату с is_dm=True, добавляет обоих участников,
    сохраняет зашифрованный ключ для создателя и PendingKeyRequest для получателя.
    """
    if target_user_id == u.id:
        raise HTTPException(400, "Нельзя создать DM с самим собой")

    target = db.query(User).filter(
        User.id == target_user_id, User.is_active == True,
    ).first()
    if not target:
        raise HTTPException(404, "Пользователь не найден или деактивирован")

    # Проверяем существующий DM
    existing = _find_existing_dm(u.id, target_user_id, db)
    if existing:
        has_key = db.query(EncryptedRoomKey).filter(
            EncryptedRoomKey.room_id == existing.id,
            EncryptedRoomKey.user_id == u.id,
        ).first() is not None

        entry = _room_to_dict(existing, target, has_key)
        entry["other_user"]["is_contact"] = db.query(Contact).filter(
            Contact.owner_id == u.id,
            Contact.contact_id == target.id,
        ).first() is not None
        return entry

    # Создаём DM комнату
    min_id, max_id = sorted([u.id, target_user_id])
    room = Room(
        name        = f"dm:{min_id}:{max_id}",
        description = "",
        creator_id  = u.id,
        is_private  = True,
        invite_code = generative_invite_code(8),
        max_members = 2,
        is_dm       = True,
    )
    db.add(room)
    db.flush()

    db.add(RoomMember(room_id=room.id, user_id=u.id, role=RoomRole.OWNER))
    db.add(RoomMember(room_id=room.id, user_id=target_user_id, role=RoomRole.MEMBER))

    # Сохраняем зашифрованный ключ для создателя (если передан)
    if body.encrypted_room_key:
        payload = {
            "ephemeral_pub": body.encrypted_room_key.ephemeral_pub,
            "ciphertext":    body.encrypted_room_key.ciphertext,
        }
        if validate_ecies_payload(payload):
            db.add(EncryptedRoomKey(
                room_id       = room.id,
                user_id       = u.id,
                ephemeral_pub = body.encrypted_room_key.ephemeral_pub,
                ciphertext    = body.encrypted_room_key.ciphertext,
                recipient_pub = u.x25519_public_key,
            ))

    # Сохраняем зашифрованный ключ для получателя (если передан)
    if body.encrypted_key_for_target and target.x25519_public_key:
        payload_t = {
            "ephemeral_pub": body.encrypted_key_for_target.ephemeral_pub,
            "ciphertext":    body.encrypted_key_for_target.ciphertext,
        }
        if validate_ecies_payload(payload_t):
            db.add(EncryptedRoomKey(
                room_id       = room.id,
                user_id       = target_user_id,
                ephemeral_pub = body.encrypted_key_for_target.ephemeral_pub,
                ciphertext    = body.encrypted_key_for_target.ciphertext,
                recipient_pub = target.x25519_public_key,
            ))
    elif target.x25519_public_key:
        # Fallback: PendingKeyRequest если клиент не передал ключ для получателя
        db.add(PendingKeyRequest(
            room_id    = room.id,
            user_id    = target_user_id,
            pubkey_hex = target.x25519_public_key,
            expires_at = datetime.now(timezone.utc) + timedelta(hours=48),
        ))

    db.commit()
    db.refresh(room)

    logger.info(f"DM created: {u.username} ↔ {target.username} (room {room.id})")

    # ── Уведомляем получателя о новом DM через notification WS ────────────
    target_entry = _room_to_dict(room, u, has_key=bool(
        body.encrypted_key_for_target and target.x25519_public_key
    ))
    target_entry["other_user"]["is_contact"] = db.query(Contact).filter(
        Contact.owner_id == target_user_id,
        Contact.contact_id == u.id,
    ).first() is not None

    # BMP mode: new_dm notification goes through BMP room deposit
    # Target user will see the DM when polling their room BMP mailbox
    from app.config import Config
    if not Config.BMP_DELIVERY_ENABLED:
        await manager.notify_user(target_user_id, {
            "type":    "new_dm",
            "room":    target_entry["room"],
            "dm_user": target_entry["other_user"],
        })

    entry = _room_to_dict(room, target, has_key=True)
    entry["other_user"]["is_contact"] = db.query(Contact).filter(
        Contact.owner_id == u.id,
        Contact.contact_id == target.id,
    ).first() is not None
    return entry


class StoreKeyRequest(BaseModel):
    user_id:       int
    ephemeral_pub: str = Field(..., min_length=64, max_length=64)
    ciphertext:    str = Field(..., min_length=24)


@router.post("/store-key/{room_id}", status_code=200)
async def store_key_for_user(
        room_id: int,
        body:    StoreKeyRequest,
        u:       User    = Depends(get_current_user),
        db:      Session = Depends(get_db),
):
    """
    Сохранить зашифрованный ключ комнаты для другого пользователя.
    Вызывается создателем DM, чтобы получатель мог расшифровать сразу.
    """
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(404, "Комната не найдена")

    # Проверяем что вызывающий — участник комнаты
    is_member = db.query(RoomMember).filter(
        RoomMember.room_id == room_id,
        RoomMember.user_id == u.id,
    ).first()
    if not is_member:
        raise HTTPException(403, "Вы не участник этой комнаты")

    # Проверяем что целевой пользователь — тоже участник
    target_member = db.query(RoomMember).filter(
        RoomMember.room_id == room_id,
        RoomMember.user_id == body.user_id,
    ).first()
    if not target_member:
        raise HTTPException(400, "Пользователь не участник этой комнаты")

    # Не перезаписываем если ключ уже есть
    existing = db.query(EncryptedRoomKey).filter(
        EncryptedRoomKey.room_id == room_id,
        EncryptedRoomKey.user_id == body.user_id,
    ).first()
    if existing:
        return {"ok": True, "message": "Ключ уже существует"}

    payload = {"ephemeral_pub": body.ephemeral_pub, "ciphertext": body.ciphertext}
    if not validate_ecies_payload(payload):
        raise HTTPException(400, "Невалидный ECIES payload")

    target_user = db.query(User).filter(User.id == body.user_id).first()
    db.add(EncryptedRoomKey(
        room_id       = room_id,
        user_id       = body.user_id,
        ephemeral_pub = body.ephemeral_pub,
        ciphertext    = body.ciphertext,
        recipient_pub = target_user.x25519_public_key if target_user else None,
    ))

    # Удаляем PendingKeyRequest если есть
    db.query(PendingKeyRequest).filter(
        PendingKeyRequest.room_id == room_id,
        PendingKeyRequest.user_id == body.user_id,
    ).delete()

    db.commit()
    logger.info(f"Key stored for user {body.user_id} in room {room_id}")

    # Доставляем ключ получателю через room WS (если подключён) и notification WS
    key_payload = {
        "type":          "room_key",
        "room_id":       room_id,
        "ephemeral_pub": body.ephemeral_pub,
        "ciphertext":    body.ciphertext,
    }
    # BMP mode: key delivery through BMP room deposit
    from app.config import Config
    if Config.BMP_DELIVERY_ENABLED:
        try:
            from app.transport.blind_mailbox import deposit_envelope
            import json
            await deposit_envelope(room_id, json.dumps(key_payload))
        except Exception:
            pass
    else:
        delivered = await manager.send_to_user(room_id, body.user_id, key_payload)
        if not delivered:
            await manager.notify_user(body.user_id, key_payload)

    return {"ok": True}


@router.get("/list")
async def list_dms(
        u:  User    = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """Список всех DM комнат текущего пользователя, отсортированных по updated_at."""
    # Находим все DM комнаты пользователя
    dm_rooms = (
        db.query(Room)
        .join(RoomMember, RoomMember.room_id == Room.id)
        .filter(Room.is_dm == True, RoomMember.user_id == u.id)
        .order_by(Room.updated_at.desc())
        .all()
    )

    result = []
    for room in dm_rooms:
        # Находим другого участника
        other_member = (
            db.query(RoomMember)
            .filter(RoomMember.room_id == room.id, RoomMember.user_id != u.id)
            .first()
        )
        if not other_member:
            continue

        other_user = db.query(User).filter(User.id == other_member.user_id).first()
        if not other_user:
            continue

        has_key = db.query(EncryptedRoomKey).filter(
            EncryptedRoomKey.room_id == room.id,
            EncryptedRoomKey.user_id == u.id,
        ).first() is not None

        entry = _room_to_dict(room, other_user, has_key)

        # Проверяем, является ли собеседник контактом
        entry["other_user"]["is_contact"] = db.query(Contact).filter(
            Contact.owner_id == u.id,
            Contact.contact_id == other_user.id,
        ).first() is not None

        # Подсчёт непрочитанных сообщений
        my_member = db.query(RoomMember).filter(
            RoomMember.room_id == room.id,
            RoomMember.user_id == u.id,
        ).first()
        last_read = my_member.last_read_message_id or 0 if my_member else 0
        entry["room"]["unread_count"] = db.query(func.count(Message.id)).filter(
            Message.room_id == room.id,
            Message.id > last_read,
        ).scalar() or 0

        result.append(entry)

    return {"rooms": result}
