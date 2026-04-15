"""
app/chats/search.py — Поиск пользователей по различным критериям + поиск сообщений в комнатах.

Поддерживаемые запросы:
  - Телефон (если q похож на номер)
  - Email (если q содержит @)
  - IP-адрес (если q похож на x.x.x.x)
  - Имя пользователя / display_name (с фильтрацией по сходству)
  - Поиск сообщений в комнате (по file_name, sender, type, дате)
"""
from __future__ import annotations

import difflib
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.models.contact import Contact
from app.models_rooms import Message, MessageType, RoomMember
from app.security.auth_jwt import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/users", tags=["users"])

# Отдельный роутер для поиска сообщений внутри комнат
messages_search_router = APIRouter(prefix="/api/rooms", tags=["messages"])

_PHONE_LIKE_RE = re.compile(r"^\+?\d[\d\s\-()]{5,}$")
_IP_RE         = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


def _name_similarity(query: str, name: str | None) -> float:
    """Return 0-1 similarity score between query and a username/display_name."""
    if not name:
        return 0.0
    q = query.lower()
    n = name.lower()
    # Exact match
    if q == n:
        return 1.0
    # Starts-with gets a high score proportional to coverage
    if n.startswith(q):
        return 0.7 + 0.3 * (len(q) / len(n))
    # Substring match — score by how much of the target the query covers
    if q in n:
        return len(q) / len(n)
    # Fallback to SequenceMatcher
    return difflib.SequenceMatcher(None, q, n).ratio()


def _best_name_similarity(query: str, user: User) -> float:
    """Return similarity score for username only (display_name is freely changeable)."""
    return _name_similarity(query, user.username)


def _similarity_threshold(query_len: int) -> float:
    """Return the minimum similarity threshold based on query length."""
    if query_len <= 3:
        return 0.4
    if query_len <= 6:
        return 0.3
    return 0.25


def _mask_phone(phone: str | None) -> str | None:
    """Маскирование номера: первые 4 и последние 2 символа."""
    if not phone or len(phone) < 7:
        return phone
    return phone[:4] + "*" * (len(phone) - 6) + phone[-2:]


@router.get("/search")
async def search_users(
        q:  str     = Query(..., min_length=1, max_length=128),
        u:  User    = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """
    Поиск пользователей по телефону, email, IP или имени.
    Исключает текущего пользователя. Максимум 20 результатов.
    """
    q = q.strip()
    if not q:
        raise HTTPException(400, "Пустой запрос")

    filters = []

    # Телефон
    if _PHONE_LIKE_RE.match(q):
        clean_phone = re.sub(r"[\s\-()]", "", q)
        filters.append(User.phone.contains(clean_phone))

    # Email
    if "@" in q:
        filters.append(User.email.ilike(q))

    # IP-адрес
    if _IP_RE.match(q):
        filters.append(User.last_ip == q)

    # Username — only search by username (not display_name, since it's freely changeable)
    if len(q) >= 2:
        if len(q) <= 3:
            starts_q = f"{q}%"
            filters.append(User.username.ilike(starts_q))
        else:
            like_q = f"%{q}%"
            filters.append(User.username.ilike(like_q))

    if not filters:
        return {"users": []}

    users = (
        db.query(User)
        .filter(
            User.is_active == True,
            or_(*filters),
        )
        .limit(50)
        .all()
    )

    # Получаем id контактов текущего пользователя одним запросом
    contact_ids = set(
        row[0] for row in
        db.query(Contact.contact_id)
        .filter(Contact.owner_id == u.id)
        .all()
    )

    # Post-filter by similarity and sort best matches first
    threshold = _similarity_threshold(len(q))
    scored = []
    for user in users:
        sim = _best_name_similarity(q, user)
        # Always keep exact phone/email/IP matches regardless of name similarity
        is_exact = False
        if _PHONE_LIKE_RE.match(q):
            clean_phone = re.sub(r"[\s\-()]", "", q)
            is_exact = user.phone and clean_phone in user.phone
        if "@" in q:
            is_exact = is_exact or (user.email and user.email.lower() == q.lower())
        if _IP_RE.match(q):
            is_exact = is_exact or (user.last_ip == q)

        if is_exact or sim >= threshold:
            scored.append((sim, user))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for sim, user in scored[:20]:
        results.append({
            "user_id":            user.id,
            "username":           user.username,
            "display_name":       user.display_name or user.username,
            "avatar_emoji":       user.avatar_emoji,
            "avatar_url":         user.avatar_url,
            "phone":              _mask_phone(user.phone),
            "x25519_public_key":  user.x25519_public_key,
            "is_contact":         user.id in contact_ids,
            "is_self":            user.id == u.id,
        })

    return {"users": results}


@router.get("/global-search")
async def global_search(
    q: str = Query("", max_length=128),
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Единый поиск: пользователи + каналы + комнаты/DM."""
    q = q.strip()
    if not q or len(q) < 2:
        return {"users": [], "channels": [], "chats": []}

    # Users — search by username only (not display_name, since it's freely changeable)
    user_filters = [User.phone == q, User.email.ilike(q)]
    if len(q) <= 3:
        starts_q = f"{q}%"
        user_filters.append(User.username.ilike(starts_q))
    else:
        like_q = f"%{q}%"
        user_filters.append(User.username.ilike(like_q))

    users = db.query(User).filter(
        User.is_active == True,
        or_(*user_filters),
    ).limit(30).all()

    # Post-filter by similarity
    threshold = _similarity_threshold(len(q))
    scored_users = []
    for u2 in users:
        sim = _best_name_similarity(q, u2)
        is_exact = (u2.phone and u2.phone == q) or (u2.email and u2.email.lower() == q.lower())
        if is_exact or sim >= threshold:
            scored_users.append((sim, u2))
    scored_users.sort(key=lambda x: x[0], reverse=True)

    user_results = [{
        "type": "user",
        "user_id": u2.id,
        "username": u2.username,
        "display_name": u2.display_name or u2.username,
        "avatar_emoji": u2.avatar_emoji,
        "avatar_url": u2.avatar_url,
        "is_self": u2.id == u.id,
    } for _, u2 in scored_users[:10]]

    # Channels + public groups (by name, sorted by member count)
    # Include: all public rooms + private rooms where user is a member
    from app.models_rooms import Room, RoomMember
    like_q = f"%{q}%"
    my_room_ids_set = {m.room_id for m in db.query(RoomMember.room_id).filter(RoomMember.user_id == u.id).all()}
    public_rooms = db.query(Room).filter(
        Room.is_dm == False,
        Room.name.ilike(like_q),
        or_(Room.is_private == False, Room.id.in_(my_room_ids_set)),
    ).all()

    channel_results = []
    for ch in public_rooms:
        count = ch.members.count()
        channel_results.append({
            "type": "channel" if ch.is_channel else "group",
            "id": ch.id,
            "name": ch.name,
            "description": ch.description,
            "invite_code": ch.invite_code,
            "subscriber_count": count,
        })
    channel_results.sort(key=lambda x: x["subscriber_count"], reverse=True)

    # My rooms/DMs matching name
    my_rooms = db.query(Room).filter(
        Room.id.in_(my_room_ids_set),
        Room.name.ilike(like_q),
    ).limit(10).all()

    chat_results = [{
        "type": "dm" if r.is_dm else ("channel" if getattr(r, 'is_channel', False) else "room"),
        "id": r.id,
        "name": r.name,
        "is_dm": r.is_dm,
        "is_channel": getattr(r, 'is_channel', False),
    } for r in my_rooms]

    # Bots matching name or display_name
    bots = db.query(User).filter(
        User.is_bot == True,
        User.is_active == True,
        or_(
            User.username.ilike(f"%{q}%"),
            User.display_name.ilike(f"%{q}%"),
        ),
    ).limit(10).all()

    bot_results = [{
        "type": "bot",
        "user_id": b.id,
        "username": b.username,
        "display_name": b.display_name or b.username,
        "avatar_emoji": b.avatar_emoji,
        "avatar_url": b.avatar_url,
    } for b in bots]

    return {
        "users": user_results[:10],
        "channels": channel_results[:10],
        "bots": bot_results[:10],
        "chats": chat_results[:10],
    }


# ══════════════════════════════════════════════════════════════════════════════
# Поиск сообщений в комнате
# ══════════════════════════════════════════════════════════════════════════════

@messages_search_router.get("/{room_id}/messages/search")
async def search_messages(
    room_id:   int,
    q:         str | None  = Query(None, max_length=256),
    sender_id: int | None  = Query(None),
    type:      str | None  = Query(None),
    date_from: str | None  = Query(None, description="ISO date, e.g. 2026-01-01"),
    date_to:   str | None  = Query(None, description="ISO date, e.g. 2026-12-31"),
    limit:     int         = Query(50, ge=1, le=200),
    offset:    int         = Query(0, ge=0),
    u:         User        = Depends(get_current_user),
    db:        Session     = Depends(get_db),
):
    """
    Поиск сообщений в комнате с фильтрацией.

    ВАЖНО: поле content_encrypted зашифровано E2E — сервер НЕ может искать
    по тексту сообщений. Параметр `q` ищет только по file_name (имя файла)
    и по системным сообщениям. Полнотекстовый поиск по содержимому сообщений
    возможен только на клиенте после расшифровки.
    """
    # Проверяем членство в комнате
    member = db.query(RoomMember).filter(
        RoomMember.room_id == room_id,
        RoomMember.user_id == u.id,
        RoomMember.is_banned == False,
    ).first()
    if not member:
        raise HTTPException(403, "Вы не участник этой комнаты")

    query = db.query(Message).filter(Message.room_id == room_id)

    # Текстовый поиск — только по file_name (E2E: ciphertext недоступен серверу)
    if q:
        q_stripped = q.strip()
        if q_stripped:
            like_q = f"%{q_stripped}%"
            query = query.filter(Message.file_name.ilike(like_q))

    if sender_id is not None:
        query = query.filter(Message.sender_id == sender_id)

    if type is not None:
        try:
            msg_type = MessageType(type)
        except ValueError:
            raise HTTPException(400, f"Неизвестный тип сообщения: {type}")
        query = query.filter(Message.msg_type == msg_type)

    if date_from is not None:
        try:
            dt_from = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(400, "Неверный формат date_from (ожидается ISO)")
        query = query.filter(Message.created_at >= dt_from)

    if date_to is not None:
        try:
            dt_to = datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(400, "Неверный формат date_to (ожидается ISO)")
        query = query.filter(Message.created_at <= dt_to)

    total = query.count()
    messages = (
        query
        .order_by(Message.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    results = []
    for m in messages:
        sender = db.query(User).filter(User.id == m.sender_id).first() if m.sender_id else None
        results.append({
            "id":          m.id,
            "room_id":     m.room_id,
            "sender_id":   m.sender_id,
            "sender_name": (sender.display_name or sender.username) if sender else None,
            "msg_type":    m.msg_type.value if m.msg_type else None,
            "file_name":   m.file_name,
            "file_size":   m.file_size,
            "reply_to_id": m.reply_to_id,
            "is_edited":   m.is_edited,
            "created_at":  m.created_at.isoformat() if m.created_at else None,
        })

    return {"messages": results, "total": total, "limit": limit, "offset": offset}
