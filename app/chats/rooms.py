"""
app/chats/rooms.py — Управление комнатами с децентрализованным распределением ключей.

Принципиальные изменения:
  1. Сервер НЕ генерирует и НЕ хранит ключ комнаты в открытом виде
  2. Клиент-создатель генерирует room_key локально и отправляет зашифрованную копию
  3. При вступлении нового участника запускается протокол key distribution:
       Новый участник → server → online-участники → key re-encryption → новый участник
  4. GET /rooms/{id}/key-bundle — клиент получает свой зашифрованный ключ
  5. POST /rooms/{id}/provide-key — любой участник может передать ключ для ожидающего

Полный flow создания комнаты:
  ┌─ Клиент ─────────────────────────────────────────────────────┐
  │  1. room_key = crypto.getRandomValues(32 bytes)              │
  │  2. enc = ECIES(room_key, own_pubkey)                        │
  │     → {ephemeral_pub: hex, ciphertext: hex}                  │
  │  3. POST /api/rooms {name, ..., encrypted_room_key: enc}     │
  └──────────────────────────────────────────────────────────────┘

  ┌─ Сервер ─────────────────────────────────────────────────────┐
  │  4. Создаёт Room (без room_key!)                              │
  │  5. Сохраняет EncryptedRoomKey для создателя                 │
  │  6. Возвращает room dict                                      │
  └──────────────────────────────────────────────────────────────┘

Полный flow вступления в комнату:
  1. POST /api/rooms/join/{invite_code}
     → Server создаёт RoomMember
     → Если online-участники есть → PendingKeyRequest + WebSocket broadcast "key_request"
     → Ответ: {joined, room, has_key: false}

  2. WebSocket-участник получает {type: "key_request", for_user_id, for_pubkey}
     → Расшифровывает room_key локально
     → Делает ECIES(room_key, for_pubkey) → {ephemeral_pub, ciphertext}
     → Отправляет через WS: {action: "key_response", for_user_id, ephemeral_pub, ciphertext}

  3. Сервер сохраняет EncryptedRoomKey для нового участника
     → Отправляет новому участнику через WS: {type: "room_key", ephemeral_pub, ciphertext}
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.models_rooms import EncryptedRoomKey, PendingKeyRequest, Room, RoomMember, RoomRole
from app.peer.connection_manager import manager
from app.security.auth_jwt import get_current_user
from app.security.key_exchange import validate_ecies_payload
from app.utilites.utils import generative_invite_code

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


# ══════════════════════════════════════════════════════════════════════════════
# Вспомогательные функции
# ══════════════════════════════════════════════════════════════════════════════

def _room_dict(r: Room) -> dict:
    return {
        "id":           r.id,
        "name":         r.name,
        "description":  r.description,
        "is_private":   r.is_private,
        "invite_code":  r.invite_code,
        "member_count": r.member_count(),
        "online_count": len(manager.get_online_users(r.id)),
        "created_at":   r.created_at.isoformat(),
    }


def _require_member(room_id: int, user_id: int, db: Session) -> RoomMember:
    m = db.query(RoomMember).filter(
        RoomMember.room_id == room_id,
        RoomMember.user_id == user_id,
        RoomMember.is_banned == False,
        ).first()
    if not m:
        raise HTTPException(403, "Вы не участник этой комнаты")
    return m


async def _broadcast_key_request(room_id: int, for_user_id: int, for_pubkey: str) -> None:
    """
    Рассылает всем online-участникам комнаты запрос на re-encryption ключа.
    Любой участник, у которого есть room_key, должен зашифровать его для нового участника.
    """
    await manager.broadcast_to_room(room_id, {
        "type":        "key_request",
        "for_user_id": for_user_id,
        "for_pubkey":  for_pubkey,
    }, exclude=for_user_id)


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
        invite_code = generative_invite_code(8),
        max_members = 200,
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

    logger.info(f"Room created: '{room.name}' (id={room.id}) by {u.username}")

    return JSONResponse(status_code=201, content={
        **_room_dict(room),
        "has_key": True,   # создатель уже имеет ключ
    })


# ══════════════════════════════════════════════════════════════════════════════
# Вступление в комнату
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/join/{invite_code}")
async def join_room(
        invite_code: str,
        u: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """
    Вступление в комнату по invite_code.

    После вступления запускается протокол получения ключа:
      1. Если у пользователя уже есть EncryptedRoomKey → возвращаем has_key=True
      2. Иначе создаём PendingKeyRequest и рассылаем online-участникам "key_request"
      3. Когда любой участник ответит → ключ доставляется через WebSocket

    has_key=False означает: нужно дождаться {type: "room_key"} через WebSocket.
    """
    if not u.x25519_public_key:
        raise HTTPException(400, "Необходим X25519 публичный ключ для вступления в комнату")

    room = db.query(Room).filter(Room.invite_code == invite_code.upper()).first()
    if not room:
        raise HTTPException(404, "Комната не найдена")

    # Проверяем существующее членство
    existing = db.query(RoomMember).filter(
        RoomMember.room_id == room.id,
        RoomMember.user_id == u.id,
        ).first()

    if existing:
        if existing.is_banned:
            raise HTTPException(403, "Вы заблокированы в этой комнате")
        # Уже участник — проверяем наличие ключа
        has_key = db.query(EncryptedRoomKey).filter(
            EncryptedRoomKey.room_id == room.id,
            EncryptedRoomKey.user_id == u.id,
            ).first() is not None
        return {"joined": False, "room": _room_dict(room), "has_key": has_key}

    if room.is_full():
        raise HTTPException(409, "Комната заполнена")

    # Добавляем участника
    db.add(RoomMember(room_id=room.id, user_id=u.id, role=RoomRole.MEMBER))

    # Создаём PendingKeyRequest (ожидаем ключ от online-участников)
    pending = PendingKeyRequest(
        room_id    = room.id,
        user_id    = u.id,
        pubkey_hex = u.x25519_public_key,
        expires_at = datetime.utcnow() + timedelta(hours=48),
    )
    db.add(pending)
    db.commit()

    # Рассылаем online-участникам запрос на re-encryption ключа
    online_count = len(manager.get_online_users(room.id))
    if online_count > 0:
        await _broadcast_key_request(room.id, u.id, u.x25519_public_key)
        logger.info(f"{u.username} joined room {room.id}, key_request sent to {online_count} online members")
    else:
        logger.info(f"{u.username} joined room {room.id}, no online members — key pending")

    return {
        "joined":   True,
        "room":     _room_dict(room),
        "has_key":  False,   # ключ придёт через WebSocket
        "message":  "Ожидайте ключ от участника комнаты через WebSocket",
    }


# ══════════════════════════════════════════════════════════════════════════════
# Предоставление ключа ожидающему участнику (HTTP-путь, альтернатива WebSocket)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/{room_id}/provide-key")
async def provide_key(
        room_id: int,
        body: ProvideKeyRequest,
        u: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """
    Участник передаёт зашифрованный ключ комнаты другому участнику.

    Вызывается когда участник расшифровал room_key локально и re-encrypt его
    для ожидающего участника. Может быть вызван через HTTP или через WebSocket
    (action: "key_response").

    Валидация:
      - Вызывающий должен быть участником комнаты
      - Получатель должен быть участником комнаты
      - Получатель должен иметь активный PendingKeyRequest
    """
    # Проверяем что вызывающий — участник
    _require_member(room_id, u.id, db)

    # Проверяем что получатель — участник
    target_member = db.query(RoomMember).filter(
        RoomMember.room_id == room_id,
        RoomMember.user_id == body.for_user_id,
        RoomMember.is_banned == False,
        ).first()
    if not target_member:
        raise HTTPException(404, "Получатель не является участником комнаты")

    # Получаем публичный ключ получателя
    from app.models import User as UserModel
    target_user = db.query(UserModel).filter(UserModel.id == body.for_user_id).first()
    if not target_user or not target_user.x25519_public_key:
        raise HTTPException(400, "У получателя нет X25519 публичного ключа")

    # Валидируем ECIES payload
    payload = {"ephemeral_pub": body.ephemeral_pub, "ciphertext": body.ciphertext}
    if not validate_ecies_payload(payload):
        raise HTTPException(400, "Некорректный формат ключа")

    # Сохраняем или обновляем EncryptedRoomKey для получателя
    existing_key = db.query(EncryptedRoomKey).filter(
        EncryptedRoomKey.room_id == room_id,
        EncryptedRoomKey.user_id == body.for_user_id,
        ).first()

    if existing_key:
        existing_key.ephemeral_pub = body.ephemeral_pub
        existing_key.ciphertext    = body.ciphertext
        existing_key.recipient_pub = target_user.x25519_public_key
        existing_key.updated_at    = datetime.utcnow()
    else:
        db.add(EncryptedRoomKey(
            room_id       = room_id,
            user_id       = body.for_user_id,
            ephemeral_pub = body.ephemeral_pub,
            ciphertext    = body.ciphertext,
            recipient_pub = target_user.x25519_public_key,
        ))

    # Удаляем PendingKeyRequest
    db.query(PendingKeyRequest).filter(
        PendingKeyRequest.room_id == room_id,
        PendingKeyRequest.user_id == body.for_user_id,
        ).delete()

    db.commit()

    # Доставляем ключ получателю через WebSocket если он онлайн
    delivered = await manager.send_to_user(room_id, body.for_user_id, {
        "type":         "room_key",
        "ephemeral_pub": body.ephemeral_pub,
        "ciphertext":   body.ciphertext,
    })

    logger.info(
        f"Key provided for user {body.for_user_id} in room {room_id} "
        f"by {u.username} (ws_delivered={delivered})"
    )

    return {"ok": True, "delivered_via_ws": delivered}


# ══════════════════════════════════════════════════════════════════════════════
# Получение зашифрованного ключа комнаты (для клиента)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/{room_id}/key-bundle")
async def get_key_bundle(
        room_id: int,
        u: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """
    Возвращает зашифрованный ключ комнаты для текущего пользователя.

    Клиент расшифровывает его локально:
      shared_key = HKDF(DH(user_priv, ephemeral_pub))
      room_key   = AES-GCM-decrypt(ciphertext, shared_key)
    """
    _require_member(room_id, u.id, db)

    enc_key = db.query(EncryptedRoomKey).filter(
        EncryptedRoomKey.room_id == room_id,
        EncryptedRoomKey.user_id == u.id,
        ).first()

    if not enc_key:
        # Проверяем есть ли pending request
        pending = db.query(PendingKeyRequest).filter(
            PendingKeyRequest.room_id == room_id,
            PendingKeyRequest.user_id == u.id,
            ).first()

        if pending and pending.is_expired:
            db.delete(pending)
            db.commit()
            pending = None

        if not pending:
            # Создаём новый запрос и рассылаем
            db.add(PendingKeyRequest(
                room_id    = room_id,
                user_id    = u.id,
                pubkey_hex = u.x25519_public_key,
                expires_at = datetime.utcnow() + timedelta(hours=48),
            ))
            db.commit()
            await _broadcast_key_request(room_id, u.id, u.x25519_public_key)

        return {
            "has_key": False,
            "message": "Ключ ожидается. Дождитесь {type: 'room_key'} через WebSocket",
        }

    return {
        "has_key":      True,
        "ephemeral_pub": enc_key.ephemeral_pub,
        "ciphertext":   enc_key.ciphertext,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Стандартные операции с комнатами
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/my")
async def my_rooms(u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ids   = [m.room_id for m in db.query(RoomMember).filter(
        RoomMember.user_id == u.id, RoomMember.is_banned == False).all()]
    rooms = db.query(Room).filter(Room.id.in_(ids)).all()

    # Для каждой комнаты проверяем наличие ключа
    key_set = {
        ek.room_id
        for ek in db.query(EncryptedRoomKey).filter(
            EncryptedRoomKey.user_id == u.id,
            EncryptedRoomKey.room_id.in_(ids),
            ).all()
    }
    return {"rooms": [{**_room_dict(r), "has_key": r.id in key_set} for r in rooms]}


@router.get("/public")
async def public_rooms(db: Session = Depends(get_db)):
    rooms = (db.query(Room).filter(Room.is_private == False)
             .order_by(Room.created_at.desc()).limit(50).all())
    return {"rooms": [_room_dict(r) for r in rooms]}


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

    db.delete(m)

    r = db.query(Room).filter(Room.id == room_id).first()
    if m.role == RoomRole.OWNER and r and r.member_count() <= 1:
        db.delete(r)
        db.commit()
        return {"left": True, "room_deleted": True}

    db.commit()
    return {"left": True, "room_deleted": False}


@router.get("/{room_id}/members")
async def members(
        room_id: int,
        u: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    _require_member(room_id, u.id, db)
    all_m = db.query(RoomMember).filter(RoomMember.room_id == room_id).all()

    # Участники с pending key requests
    pending_ids = {
        p.user_id for p in db.query(PendingKeyRequest).filter(
            PendingKeyRequest.room_id == room_id
        ).all()
    }

    return {"members": [{
        "user_id":      m.user_id,
        "username":     m.user.username      if m.user else "—",
        "display_name": m.user.display_name  if m.user else "—",
        "avatar_emoji": m.user.avatar_emoji  if m.user else "👤",
        "role":         m.role.value,
        "is_online":    manager.is_online(room_id, m.user_id),
        "x25519_pubkey":m.user.x25519_public_key if m.user else None,
        "has_key":      m.user_id not in pending_ids,
    } for m in all_m]}


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
    return _room_dict(r)


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
    return {"ok": True}


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