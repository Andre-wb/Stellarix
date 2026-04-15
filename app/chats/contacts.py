"""
app/chats/contacts.py — API управления контактами пользователя.

Эндпоинты:
  - GET    /api/contacts           — список контактов с информацией о пользователях
  - POST   /api/contacts           — добавить контакт
  - PUT    /api/contacts/{id}      — обновить никнейм контакта
  - DELETE /api/contacts/{id}      — удалить контакт
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.models.contact import Contact
from app.models_rooms import Room, RoomMember
from app.peer.connection_manager import manager
from app.security.auth_jwt import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/contacts", tags=["contacts"])
block_router = APIRouter(prefix="/api/users", tags=["users"])


# ══════════════════════════════════════════════════════════════════════════════
# Pydantic схемы
# ══════════════════════════════════════════════════════════════════════════════

class AddContactRequest(BaseModel):
    user_id: int


class UpdateContactRequest(BaseModel):
    nickname: str = Field(..., max_length=100)


# ══════════════════════════════════════════════════════════════════════════════
# Вспомогательные функции
# ══════════════════════════════════════════════════════════════════════════════

def _mask_phone(phone: str | None) -> str | None:
    """Маскирование номера телефона: показывает первые 4 и последние 2 символа."""
    if not phone or len(phone) < 7:
        return phone
    return phone[:4] + "*" * (len(phone) - 6) + phone[-2:]


def _find_dm_room(owner_id: int, contact_id: int, db: Session) -> int | None:
    """Находит DM комнату между двумя пользователями."""
    # Подзапрос: комнаты где is_dm=True и оба пользователя — участники
    rooms_owner = (
        db.query(RoomMember.room_id)
        .join(Room, Room.id == RoomMember.room_id)
        .filter(Room.is_dm == True, RoomMember.user_id == owner_id)
        .subquery()
    )
    dm_member = (
        db.query(RoomMember.room_id)
        .filter(
            RoomMember.room_id.in_(db.query(rooms_owner.c.room_id)),
            RoomMember.user_id == contact_id,
        )
        .first()
    )
    return dm_member[0] if dm_member else None


def _is_user_online(user_id: int, db: Session | None = None) -> bool:
    """Проверяет, подключён ли пользователь к какой-либо комнате или глобальному WS."""
    from starlette.websockets import WebSocketState

    # Проверяем глобальный WS (с валидацией состояния)
    if hasattr(manager, '_global_ws') and user_id in manager._global_ws:
        ws = manager._global_ws[user_id]
        if hasattr(ws, 'client_state') and ws.client_state != WebSocketState.CONNECTED:
            manager._global_ws.pop(user_id, None)
        else:
            return True
    # Проверяем подключение к любой комнате (с валидацией)
    for room_users in manager._rooms.values():
        conn = room_users.get(user_id)
        if conn:
            ws = conn.websocket
            if hasattr(ws, 'client_state') and ws.client_state != WebSocketState.CONNECTED:
                continue  # stale — будет очищен при следующем broadcast
            return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
# Эндпоинты
# ══════════════════════════════════════════════════════════════════════════════

@router.get("")
async def list_contacts(
        u:  User    = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """Список контактов текущего пользователя с информацией о каждом."""
    contacts = (
        db.query(Contact)
        .filter(Contact.owner_id == u.id)
        .order_by(Contact.created_at.desc())
        .all()
    )

    if not contacts:
        return {"contacts": []}

    # Batch load: все пользователи одним запросом (вместо N+1)
    contact_ids = [c.contact_id for c in contacts]
    users_list = db.query(User).filter(User.id.in_(contact_ids)).all()
    users_map = {usr.id: usr for usr in users_list}

    # Batch load: все DM комнаты одним запросом
    my_dm_room_ids = (
        db.query(RoomMember.room_id)
        .join(Room, Room.id == RoomMember.room_id)
        .filter(Room.is_dm == True, RoomMember.user_id == u.id)
        .scalar_subquery()
    )
    my_dm_rooms = (
        db.query(RoomMember.room_id, RoomMember.user_id)
        .join(Room, Room.id == RoomMember.room_id)
        .filter(Room.is_dm == True, RoomMember.room_id.in_(my_dm_room_ids),
                RoomMember.user_id.in_(contact_ids))
        .all()
    )
    dm_map = {row.user_id: row.room_id for row in my_dm_rooms}

    result = []
    for c in contacts:
        contact_user = users_map.get(c.contact_id)
        if not contact_user:
            continue

        _show_ls = getattr(contact_user, 'show_last_seen', True)
        if _show_ls is None:
            _show_ls = True
        result.append({
            "contact_id":   c.id,
            "user_id":      contact_user.id,
            "username":     contact_user.username,
            "display_name": contact_user.display_name or contact_user.username,
            "avatar_emoji": contact_user.avatar_emoji,
            "avatar_url":   contact_user.avatar_url,
            "phone":        _mask_phone(contact_user.phone),
            "nickname":     c.nickname,
            "is_online":    _is_user_online(contact_user.id),
            "last_seen":    contact_user.last_seen.isoformat() + "Z" if contact_user.last_seen and _show_ls else None,
            "show_last_seen": _show_ls,
            "custom_status": contact_user.custom_status,
            "status_emoji":  contact_user.status_emoji,
            "presence":      contact_user.presence or "online",
            "dm_room_id":   dm_map.get(c.contact_id),
            "created_at":   c.created_at.isoformat(),
            "x25519_public_key":    contact_user.x25519_public_key,
            "fingerprint_verified": bool(c.fingerprint_verified),
        })

    return {"contacts": result}


@router.post("", status_code=201)
async def add_contact(
        body: AddContactRequest,
        u:    User    = Depends(get_current_user),
        db:   Session = Depends(get_db),
):
    """Добавить пользователя в контакты."""
    if body.user_id == u.id:
        raise HTTPException(400, "Нельзя добавить себя в контакты")

    target = db.query(User).filter(User.id == body.user_id, User.is_active == True).first()
    if not target:
        raise HTTPException(404, "Пользователь не найден")

    existing = db.query(Contact).filter(
        Contact.owner_id == u.id,
        Contact.contact_id == body.user_id,
    ).first()
    if existing:
        raise HTTPException(409, "Контакт уже добавлен")

    contact = Contact(owner_id=u.id, contact_id=body.user_id)
    db.add(contact)
    db.commit()
    db.refresh(contact)

    dm_room_id = _find_dm_room(u.id, body.user_id, db)

    return {
        "contact_id":   contact.id,
        "user_id":      target.id,
        "username":     target.username,
        "display_name": target.display_name or target.username,
        "avatar_emoji": target.avatar_emoji,
        "avatar_url":   target.avatar_url,
        "phone":        _mask_phone(target.phone),
        "nickname":     contact.nickname,
        "is_online":    _is_user_online(target.id),
        "dm_room_id":   dm_room_id,
        "created_at":   contact.created_at.isoformat(),
    }


@router.put("/{contact_id}")
async def update_contact(
        contact_id: int,
        body:       UpdateContactRequest,
        u:          User    = Depends(get_current_user),
        db:         Session = Depends(get_db),
):
    """Обновить никнейм контакта."""
    contact = db.query(Contact).filter(
        Contact.id == contact_id,
        Contact.owner_id == u.id,
    ).first()
    if not contact:
        raise HTTPException(404, "Контакт не найден")

    contact.nickname = body.nickname
    db.commit()

    return {"ok": True, "contact_id": contact.id, "nickname": contact.nickname}


@router.delete("/{contact_id}")
async def delete_contact(
        contact_id: int,
        u:          User    = Depends(get_current_user),
        db:         Session = Depends(get_db),
):
    """Удалить контакт."""
    contact = db.query(Contact).filter(
        Contact.id == contact_id,
        Contact.owner_id == u.id,
    ).first()
    if not contact:
        raise HTTPException(404, "Контакт не найден")

    db.delete(contact)
    db.commit()

    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# Верификация fingerprint
# ══════════════════════════════════════════════════════════════════════════════

class VerifyFingerprintRequest(BaseModel):
    pubkey_hash: str = Field(..., min_length=64, max_length=64)


@router.post("/{contact_id}/verify-fingerprint")
async def verify_fingerprint(
        contact_id: int,
        body:       VerifyFingerprintRequest,
        u:          User    = Depends(get_current_user),
        db:         Session = Depends(get_db),
):
    """Отметить fingerprint контакта как проверенный."""
    contact = db.query(Contact).filter(
        Contact.id == contact_id,
        Contact.owner_id == u.id,
    ).first()
    if not contact:
        raise HTTPException(404, "Контакт не найден")

    contact.fingerprint_verified = True
    contact.fingerprint_verified_at = datetime.now(timezone.utc)
    contact.fingerprint_pubkey_hash = body.pubkey_hash
    db.commit()

    return {"ok": True, "contact_id": contact.id, "fingerprint_verified": True}


@router.delete("/{contact_id}/verify-fingerprint")
async def unverify_fingerprint(
        contact_id: int,
        u:          User    = Depends(get_current_user),
        db:         Session = Depends(get_db),
):
    """Снять верификацию fingerprint."""
    contact = db.query(Contact).filter(
        Contact.id == contact_id,
        Contact.owner_id == u.id,
    ).first()
    if not contact:
        raise HTTPException(404, "Контакт не найден")

    contact.fingerprint_verified = False
    contact.fingerprint_verified_at = None
    contact.fingerprint_pubkey_hash = None
    db.commit()

    return {"ok": True, "contact_id": contact.id, "fingerprint_verified": False}


# ══════════════════════════════════════════════════════════════════════════════
# Блокировка пользователей
# ══════════════════════════════════════════════════════════════════════════════

@block_router.get("/profile/{user_id}")
async def get_user_profile(
        user_id: int,
        u:       User    = Depends(get_current_user),
        db:      Session = Depends(get_db),
):
    """Полный профиль пользователя: данные, DM-комната, общие группы и медиа."""
    from app.models_rooms import FileTransfer

    target = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not target:
        raise HTTPException(404, "Пользователь не найден")

    dm_room_id = _find_dm_room(u.id, user_id, db)

    contact_row = db.query(Contact).filter(
        Contact.owner_id == u.id, Contact.contact_id == user_id,
    ).first()

    # Общие группы (не DM, где оба участники)
    my_rooms    = db.query(RoomMember.room_id).filter(RoomMember.user_id == u.id).subquery()
    their_rooms = db.query(RoomMember.room_id).filter(RoomMember.user_id == user_id).subquery()
    common_room_rows = (
        db.query(Room)
        .filter(
            Room.id.in_(db.query(my_rooms.c.room_id)),
            Room.id.in_(db.query(their_rooms.c.room_id)),
            Room.is_dm == False,
        )
        .all()
    )
    common_groups = [
        {"id": r.id, "name": r.name, "avatar_emoji": getattr(r, "avatar_emoji", None) or "💬"}
        for r in common_room_rows
    ]

    # Общие медиа (изображения из DM + общих групп)
    all_room_ids = ([dm_room_id] if dm_room_id else []) + [r.id for r in common_room_rows]
    shared_media = []
    if all_room_ids:
        media_rows = (
            db.query(FileTransfer)
            .filter(
                FileTransfer.room_id.in_(all_room_ids),
                FileTransfer.is_available == True,
                FileTransfer.mime_type.like("image/%"),
            )
            .order_by(FileTransfer.created_at.desc())
            .limit(12)
            .all()
        )
        shared_media = [
            {
                "id":          f.id,
                "room_id":     f.room_id,
                "stored_name": f.stored_name,
                "mime_type":   f.mime_type,
                "file_name":   f.original_name,
            }
            for f in media_rows
        ]

    return {
        "user": {
            "id":            target.id,
            "username":      target.username,
            "display_name":  target.display_name or target.username,
            "avatar_emoji":  target.avatar_emoji,
            "avatar_url":    target.avatar_url,
            "custom_status": target.custom_status,
            "status_emoji":  target.status_emoji,
            "presence":      target.presence or "online",
            "bio":           target.bio,
            "birth_date":    target.birth_date,
            "profile_bg":    target.profile_bg,
            "profile_icon":  target.profile_icon,
            "is_online":     _is_user_online(target.id),
            "last_seen":     target.last_seen.isoformat() + "Z" if target.last_seen and getattr(target, 'show_last_seen', True) not in (False,) else None,
            "show_last_seen": getattr(target, 'show_last_seen', True) is not False,
            "x25519_public_key": target.x25519_public_key,
        },
        "dm_room_id":    dm_room_id,
        "common_groups": common_groups,
        "shared_media":  shared_media,
        "fingerprint_verified": bool(contact_row.fingerprint_verified) if contact_row else False,
    }


@block_router.post("/block/{user_id}")
async def block_user(
        user_id: int,
        u:       User    = Depends(get_current_user),
        db:      Session = Depends(get_db),
):
    """Заблокировать пользователя — запрещает ему отправлять DM."""
    if user_id == u.id:
        raise HTTPException(400, "Нельзя заблокировать себя")

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(404, "Пользователь не найден")

    # Находим DM комнату и баним заблокированного пользователя
    dm_room_id = _find_dm_room(u.id, user_id, db)
    if dm_room_id:
        member = db.query(RoomMember).filter(
            RoomMember.room_id == dm_room_id,
            RoomMember.user_id == user_id,
        ).first()
        if member:
            member.is_banned = True
            db.commit()

    return {"ok": True, "blocked": True}
