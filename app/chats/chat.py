"""
app/chats/chat.py — E2E WebSocket чат. Сервер ретранслирует шифротекст, не расшифровывает.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ПРИНЦИП РАБОТЫ (E2E RELAY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Клиент A ──(ciphertext = AES-GCM(text, room_key))──► Сервер ──► Клиент B
                                                          │
                              Сервер ТОЛЬКО хранит и ретранслирует ciphertext.
                              Сервер НЕ ЗНАЕТ room_key.
                              Сервер НЕ МОЖЕТ прочитать сообщение.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ПРОТОКОЛ WEBSOCKET
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ── Отправка сообщения ────────────────────────────────────────────────
  Клиент → Сервер:
    {
      "action":    "message",
      "ciphertext": "<hex: nonce(12) + AES-GCM(text, room_key) + tag(16)>",
      "hash":       "<hex: BLAKE3(ciphertext)>",   // опционально
      "reply_to_id": 42                             // опционально
    }

  Сервер → все участники комнаты:
    {
      "type":       "message",
      "msg_id":     123,
      "sender_id":  5,
      "sender":     "alice",
      "display_name": "Alice",
      "avatar_emoji": "👩",
      "ciphertext": "<hex>",
      "hash":       "<hex>",
      "reply_to_id": 42,
      "created_at": "2024-01-01T12:00:00"
    }

  ── История сообщений ─────────────────────────────────────────────────
  Сервер → новому участнику (при подключении):
    {
      "type": "history",
      "messages": [
        { "msg_id": 1, "sender": "alice", "ciphertext": "<hex>", ... },
        ...
      ]
    }
  Клиент расшифровывает каждый ciphertext локально с room_key.

  ── Распределение ключей ──────────────────────────────────────────────
  Сервер → online-участникам (когда новый участник без ключа подключился):
    {"type": "key_request", "for_user_id": 7, "for_pubkey": "<hex>"}

  Участник → Сервер (после ECIES re-encryption на клиенте):
    {
      "action":       "key_response",
      "for_user_id":  7,
      "ephemeral_pub": "<hex>",
      "ciphertext":   "<hex>"
    }

  Сервер → ожидающему участнику:
    {"type": "room_key", "ephemeral_pub": "<hex>", "ciphertext": "<hex>"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter, Depends, File, HTTPException,
    Request, UploadFile, WebSocket, WebSocketDisconnect,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import Config
from app.database import get_db
from app.models import User
from app.models_rooms import (
    EncryptedRoomKey, FileTransfer, Message, MessageType,
    PendingKeyRequest, Room, RoomMember,
)
from app.peer.connection_manager import manager
from app.security.auth_jwt import get_current_user, get_user_ws
from app.security.crypto import hash_message
from app.security.key_exchange import validate_ecies_payload
from app.security.secure_upload import (
    FileAnomalyDetector, FileUploadConfig,
    calculate_file_hash, generate_secure_filename,
    read_file_chunked, validate_file_mime_type,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

_DANGEROUS_EXTS = frozenset({
    '.php', '.php3', '.php4', '.php5', '.phtml',
    '.asp', '.aspx', '.ascx', '.ashx',
    '.jsp', '.jspx', '.jws',
    '.cgi', '.pl', '.py', '.rb', '.sh', '.bash',
    '.exe', '.dll', '.bat', '.cmd', '.ps1', '.vbs',
})


def _check_double_extension(filename: str) -> bool:
    name  = Path(filename).name
    parts = name.split('.')
    if len(parts) <= 2:
        return False
    intermediate = {'.' + p.lower() for p in parts[1:-1]}
    return bool(intermediate & _DANGEROUS_EXTS)


# ══════════════════════════════════════════════════════════════════════════════
# E2E WebSocket чат
# ══════════════════════════════════════════════════════════════════════════════

@router.websocket("/ws/{room_id}")
async def ws_chat(
        websocket: WebSocket,
        room_id:   int,
        token:     Optional[str] = None,
        db:        Session       = Depends(get_db),
):
    """
    Основной WebSocket endpoint.

    Жизненный цикл:
      1. Аутентификация по токену (кука или query-параметр)
      2. Проверка членства в комнате
      3. Регистрация соединения в ConnectionManager
      4. Отправка зашифрованного ключа комнаты (если есть)
         ИЛИ рассылка key_request online-участникам
      5. Отправка зашифрованной истории (ciphertext без расшифровки)
      6. Отправка списка online-пользователей
      7. Цикл обработки входящих действий
      8. Очистка при отключении
    """
    # ── Аутентификация ────────────────────────────────────────────────────────
    try:
        raw_token = websocket.cookies.get("access_token") or token
        if not raw_token:
            await websocket.close(code=4401)
            return
        user = await get_user_ws(raw_token, db)
    except HTTPException:
        await websocket.close(code=4401)
        return

    # ── Проверка членства ─────────────────────────────────────────────────────
    member = db.query(RoomMember).filter(
        RoomMember.room_id == room_id,
        RoomMember.user_id == user.id,
        RoomMember.is_banned == False,
        ).first()
    if not member:
        await websocket.close(code=4403)
        return

    # ── Регистрация соединения ────────────────────────────────────────────────
    await manager.connect(
        room_id, user.id, user.username,
        user.display_name or user.username,
        user.avatar_emoji, websocket,
        )

    try:
        # ── Отправка зашифрованного ключа комнаты ─────────────────────────────
        await _deliver_or_request_room_key(room_id, user, db)

        # ── История (зашифрованная) ───────────────────────────────────────────
        await _send_history(room_id, user.id, db)

        # ── Online-пользователи ───────────────────────────────────────────────
        await manager.send_to_user(room_id, user.id, {
            "type":  "online",
            "users": manager.get_online_users(room_id),
        })

        # ── Рассылаем pending key_requests этому только что подключившемуся ───
        # (он может помочь другим участникам, у которых нет ключа)
        await _notify_pending_key_requests(room_id, user.id, db)

        # ── Основной цикл ─────────────────────────────────────────────────────
        while True:
            data   = await websocket.receive_json()
            action = data.get("action", "")

            if action == "message":
                await _handle_e2e_message(room_id, user, data, db)

            elif action == "edit_message":
                await _handle_edit_message(room_id, user, data, db)

            elif action == "delete_message":
                await _handle_delete_message(room_id, user, data, db)

            elif action == "key_response":
                # Участник re-encrypted ключ для ожидающего участника
                await _handle_key_response(room_id, user, data, db)

            elif action == "typing":
                await manager.set_typing(room_id, user.id, bool(data.get("is_typing")))

            elif action == "file_sending":
                await manager.broadcast_to_room(room_id, {
                    "type":         "file_sending",
                    "sender":       user.username,
                    "display_name": user.display_name or user.username,
                    "filename":     data.get("filename", ""),
                }, exclude=user.id)

            elif action == "stop_file_sending":
                await manager.broadcast_to_room(room_id, {
                    "type":   "stop_file_sending",
                    "sender": user.username,
                }, exclude=user.id)

            elif action == "ping":
                await manager.send_to_user(room_id, user.id, {"type": "pong"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WS error user={user.username} room={room_id}: {e}")
    finally:
        await manager.disconnect(room_id, user.id)


# ══════════════════════════════════════════════════════════════════════════════
# Внутренние обработчики WebSocket событий
# ══════════════════════════════════════════════════════════════════════════════

async def _deliver_or_request_room_key(room_id: int, user: User, db: Session) -> None:
    """
    Если у пользователя есть EncryptedRoomKey — отправляем его.
    Иначе рассылаем online-участникам запрос на re-encryption и создаём PendingKeyRequest.
    """
    enc_key = db.query(EncryptedRoomKey).filter(
        EncryptedRoomKey.room_id == room_id,
        EncryptedRoomKey.user_id == user.id,
        ).first()

    if enc_key:
        # Пользователь имеет зашифрованный ключ → отправляем для расшифровки на клиенте
        await manager.send_to_user(room_id, user.id, {
            "type":          "room_key",
            "ephemeral_pub": enc_key.ephemeral_pub,
            "ciphertext":    enc_key.ciphertext,
        })
        return

    # Нет ключа — создаём или обновляем PendingKeyRequest
    if not user.x25519_public_key:
        await manager.send_to_user(room_id, user.id, {
            "type":    "error",
            "message": "У вас не зарегистрирован X25519 публичный ключ",
        })
        return

    pending = db.query(PendingKeyRequest).filter(
        PendingKeyRequest.room_id == room_id,
        PendingKeyRequest.user_id == user.id,
        ).first()

    if not pending or pending.is_expired:
        if pending:
            db.delete(pending)
        db.add(PendingKeyRequest(
            room_id    = room_id,
            user_id    = user.id,
            pubkey_hex = user.x25519_public_key,
            expires_at = datetime.utcnow() + timedelta(hours=48),
        ))
        db.commit()

    # Рассылаем online-участникам запрос — кто-то поможет
    await manager.broadcast_to_room(room_id, {
        "type":        "key_request",
        "for_user_id": user.id,
        "for_pubkey":  user.x25519_public_key,
    }, exclude=user.id)

    await manager.send_to_user(room_id, user.id, {
        "type":    "waiting_for_key",
        "message": "Ожидание ключа комнаты от другого участника...",
    })


async def _notify_pending_key_requests(room_id: int, user_id: int, db: Session) -> None:
    """
    Отправляет только что подключившемуся участнику список pending key_requests.
    Если другие участники ждут ключа — этот участник может им помочь.
    """
    pending_requests = db.query(PendingKeyRequest).filter(
        PendingKeyRequest.room_id == room_id,
        PendingKeyRequest.user_id != user_id,
        PendingKeyRequest.expires_at > datetime.utcnow(),
        ).all()

    for req in pending_requests:
        await manager.send_to_user(room_id, user_id, {
            "type":        "key_request",
            "for_user_id": req.user_id,
            "for_pubkey":  req.pubkey_hex,
        })


async def _handle_e2e_message(room_id: int, user: User, data: dict, db: Session) -> None:
    """
    Обрабатывает входящее E2E сообщение.

    Клиент отправляет уже зашифрованный ciphertext — сервер НЕ расшифровывает.
    Сервер только:
      1. Валидирует формат (hex строка, минимальная длина)
      2. Сохраняет ciphertext в БД
      3. Ретранслирует всем участникам комнаты

    Protocol:
      Client → Server: {"action":"message","ciphertext":"<hex>","hash":"<hex>","reply_to_id":N}
      Server → Room:   {"type":"message","msg_id":N,"sender":"alice","ciphertext":"<hex>",...}
    """
    ciphertext_hex = data.get("ciphertext", "").strip()
    if not ciphertext_hex:
        return

    # Валидация: минимальная длина nonce(12)*2=24 hex chars + хоть что-то
    if len(ciphertext_hex) < 48:
        await manager.send_to_user(room_id, user.id, {
            "type": "error", "message": "Ciphertext слишком короткий"
        })
        return

    try:
        ciphertext_bytes = bytes.fromhex(ciphertext_hex)
    except ValueError:
        await manager.send_to_user(room_id, user.id, {
            "type": "error", "message": "Ciphertext не является корректным hex"
        })
        return

    # BLAKE3 хеш зашифрованного контента — для целостности (не расшифровки!)
    content_hash = None
    hash_hex     = data.get("hash", "")
    if hash_hex:
        try:
            content_hash = bytes.fromhex(hash_hex)
        except ValueError:
            pass
    if content_hash is None:
        # Вычисляем сами если клиент не передал
        content_hash_result = hash_message(ciphertext_bytes)
        if isinstance(content_hash_result, (bytes, bytearray)):
            content_hash = bytes(content_hash_result)

    reply_to_id = data.get("reply_to_id")
    if reply_to_id:
        # Верифицируем что reply сообщение принадлежит этой комнате
        reply_exists = db.query(Message.id).filter(
            Message.id      == reply_to_id,
            Message.room_id == room_id,
            ).first()
        if not reply_exists:
            reply_to_id = None

    # Сохраняем ЗАШИФРОВАННЫЙ контент — сервер не знает открытый текст
    msg = Message(
        room_id           = room_id,
        sender_id         = user.id,
        msg_type          = MessageType.TEXT,
        content_encrypted = ciphertext_bytes,
        content_hash      = content_hash,
        reply_to_id       = reply_to_id,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    # Relay payload — без расшифровки, только метаданные + ciphertext
    payload = {
        "type":         "message",
        "msg_id":       msg.id,
        "sender_id":    user.id,
        "sender":       user.username,
        "display_name": user.display_name or user.username,
        "avatar_emoji": user.avatar_emoji,
        "ciphertext":   ciphertext_hex,      # передаём как есть
        "hash":         hash_hex or (content_hash.hex() if content_hash else None),
        "reply_to_id":  reply_to_id,
        "created_at":   msg.created_at.isoformat(),
    }
    await manager.broadcast_to_room(room_id, payload)


async def _handle_edit_message(room_id: int, user: User, data: dict, db: Session) -> None:
    """
    Редактирование сообщения: заменяет ciphertext новым.
    Клиент зашифровал новый текст с тем же room_key и отправил новый ciphertext.
    Сервер не расшифровывает ни старый, ни новый контент.
    """
    msg_id         = data.get("msg_id")
    ciphertext_hex = data.get("ciphertext", "").strip()

    if not msg_id or not ciphertext_hex or len(ciphertext_hex) < 48:
        return

    try:
        ciphertext_bytes = bytes.fromhex(ciphertext_hex)
    except ValueError:
        return

    msg = db.query(Message).filter(
        Message.id        == msg_id,
        Message.room_id   == room_id,
        Message.sender_id == user.id,
        Message.msg_type  == MessageType.TEXT,
        ).first()
    if not msg:
        return

    content_hash_result = hash_message(ciphertext_bytes)
    msg.content_encrypted = ciphertext_bytes
    msg.content_hash      = bytes(content_hash_result) if isinstance(content_hash_result, (bytes, bytearray)) else None
    msg.is_edited         = True
    db.commit()

    await manager.broadcast_to_room(room_id, {
        "type":       "message_edited",
        "msg_id":     msg_id,
        "ciphertext": ciphertext_hex,   # новый зашифрованный текст
        "is_edited":  True,
    })


async def _handle_delete_message(room_id: int, user: User, data: dict, db: Session) -> None:
    msg_id = data.get("msg_id")
    if not msg_id:
        return

    msg = db.query(Message).filter(
        Message.id        == msg_id,
        Message.room_id   == room_id,
        Message.sender_id == user.id,
        ).first()
    if not msg:
        return

    db.delete(msg)
    db.commit()

    await manager.broadcast_to_room(room_id, {
        "type":   "message_deleted",
        "msg_id": msg_id,
    })


async def _handle_key_response(room_id: int, user: User, data: dict, db: Session) -> None:
    """
    Участник re-encrypted ключ комнаты для ожидающего участника.

    Ожидаемый payload:
      {
        "action":       "key_response",
        "for_user_id":  7,
        "ephemeral_pub": "<64 hex chars>",
        "ciphertext":   "<hex>"
      }

    Клиент (JavaScript):
      1. Получил {type: "key_request", for_user_id: 7, for_pubkey: "aabbcc..."}
      2. room_key = await eciesDecrypt(my_enc_key.ephemeral_pub, my_enc_key.ciphertext, myPriv)
      3. new_enc  = await eciesEncrypt(room_key, for_pubkey)
      4. ws.send(JSON.stringify({action: "key_response", for_user_id: 7, ...new_enc}))
    """
    for_user_id   = data.get("for_user_id")
    ephemeral_pub = data.get("ephemeral_pub", "")
    ciphertext    = data.get("ciphertext", "")

    if not for_user_id or not validate_ecies_payload({"ephemeral_pub": ephemeral_pub, "ciphertext": ciphertext}):
        await manager.send_to_user(room_id, user.id, {
            "type": "error", "message": "Некорректный key_response формат"
        })
        return

    # Проверяем что получатель является участником этой комнаты
    target_member = db.query(RoomMember).filter(
        RoomMember.room_id == room_id,
        RoomMember.user_id == for_user_id,
        RoomMember.is_banned == False,
        ).first()
    if not target_member:
        return

    # Получаем публичный ключ получателя для записи recipient_pub
    from app.models import User as UserModel
    target_user = db.query(UserModel).filter(UserModel.id == for_user_id).first()

    # Сохраняем или обновляем EncryptedRoomKey
    existing = db.query(EncryptedRoomKey).filter(
        EncryptedRoomKey.room_id == room_id,
        EncryptedRoomKey.user_id == for_user_id,
        ).first()

    if existing:
        existing.ephemeral_pub = ephemeral_pub
        existing.ciphertext    = ciphertext
        existing.updated_at    = datetime.utcnow()
    else:
        db.add(EncryptedRoomKey(
            room_id       = room_id,
            user_id       = for_user_id,
            ephemeral_pub = ephemeral_pub,
            ciphertext    = ciphertext,
            recipient_pub = target_user.x25519_public_key if target_user else None,
        ))

    # Удаляем PendingKeyRequest
    db.query(PendingKeyRequest).filter(
        PendingKeyRequest.room_id == room_id,
        PendingKeyRequest.user_id == for_user_id,
        ).delete()

    db.commit()

    # Доставляем ключ ожидающему участнику
    delivered = await manager.send_to_user(room_id, for_user_id, {
        "type":          "room_key",
        "ephemeral_pub": ephemeral_pub,
        "ciphertext":    ciphertext,
    })

    logger.info(
        f"Key re-encrypted by {user.username} for user {for_user_id} "
        f"in room {room_id} (ws_delivered={delivered})"
    )


# ══════════════════════════════════════════════════════════════════════════════
# История сообщений (зашифрованные блобы)
# ══════════════════════════════════════════════════════════════════════════════

async def _send_history(room_id: int, user_id: int, db: Session) -> None:
    """
    Отправляет последние 50 сообщений комнаты.

    ВАЖНО: сервер отправляет ТОЛЬКО зашифрованный контент (ciphertext hex).
    Клиент расшифровывает каждое сообщение локально с помощью room_key.
    Сервер не знает содержимого сообщений.
    """
    messages = (
        db.query(Message)
        .filter(Message.room_id == room_id)
        .order_by(Message.created_at.desc())
        .limit(50).all()
    )[::-1]

    history = []
    for m in messages:
        entry = {
            **m.to_relay_dict(),
            "type":         "history_msg",
            "sender":       m.sender.username      if m.sender else "—",
            "display_name": (m.sender.display_name or m.sender.username) if m.sender else "—",
            "avatar_emoji": m.sender.avatar_emoji   if m.sender else "👤",
        }

        # Для файловых сообщений добавляем ссылку на скачивание
        if m.msg_type in (MessageType.IMAGE, MessageType.FILE, MessageType.VOICE):
            ft = db.query(FileTransfer).filter(
                FileTransfer.room_id     == room_id,
                FileTransfer.original_name == m.file_name,
                FileTransfer.uploader_id == m.sender_id,
                ).order_by(FileTransfer.created_at.desc()).first()

            if ft:
                entry["download_url"] = f"/api/files/download/{ft.id}"
                entry["mime_type"]    = ft.mime_type

        history.append(entry)

    await manager.send_to_user(room_id, user_id, {
        "type":     "history",
        "messages": history,
    })


# ══════════════════════════════════════════════════════════════════════════════
# Загрузка файлов
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/api/files/upload/{room_id}")
async def upload_file(
        room_id: int,
        request: Request,
        file:    UploadFile          = File(...),
        u:       User                = Depends(get_current_user),
        db:      Session             = Depends(get_db),
):
    """
    Загрузка файла в комнату.

    Для полной E2E клиент должен зашифровать файл room_key ПЕРЕД отправкой:
      const encryptedFile = await encryptFile(fileBytes, roomKey);
      // Отправить encryptedFile как binary данные

    Сервер хранит зашифрованный blob — не может читать содержимое файла.
    Метаданные (имя, MIME) также могут быть зашифрованы клиентом.
    """
    member = db.query(RoomMember).filter(
        RoomMember.room_id == room_id,
        RoomMember.user_id == u.id,
        RoomMember.is_banned == False,
        ).first()
    if not member:
        raise HTTPException(403, "Нет доступа к комнате")

    filename = file.filename or "file"

    try:
        content, size = await read_file_chunked(file, FileUploadConfig.MAX_FILE_SIZE)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Ошибка чтения файла: {e}")

    if FileAnomalyDetector.detect_null_bytes(filename):
        raise HTTPException(400, "Недопустимые символы в имени файла")
    if FileAnomalyDetector.detect_path_traversal(filename):
        raise HTTPException(400, "Недопустимое имя файла")
    if _check_double_extension(filename):
        raise HTTPException(400, "Недопустимое расширение файла")
    if FileAnomalyDetector.detect_zip_bomb_indicators(content):
        raise HTTPException(400, "Файл имеет признаки архивной бомбы")

    mime_ok, mime_result = validate_file_mime_type(content, filename)
    if not mime_ok:
        raise HTTPException(415, mime_result or "Неподдерживаемый тип файла")
    mime_type = mime_result

    is_image = mime_type and mime_type.startswith("image/")
    if is_image:
        img_ok, img_err = await FileAnomalyDetector.validate_image_content(content)
        if not img_ok:
            raise HTTPException(400, img_err or "Неверное содержимое изображения")

    ext       = Path(filename).suffix.lower()
    file_hash = calculate_file_hash(content)

    Config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name    = generate_secure_filename(ext)
    stored_path  = Config.UPLOAD_DIR / safe_name
    stored_path.write_bytes(content)

    ft = FileTransfer(
        room_id      = room_id,
        uploader_id  = u.id,
        original_name= filename,
        stored_name  = safe_name,
        mime_type    = mime_type,
        size_bytes   = size,
        file_hash    = file_hash,
    )
    db.add(ft)
    db.commit()
    db.refresh(ft)

    download_url = f"/api/files/download/{ft.id}"

    is_voice = filename.startswith("voice_") and mime_type and mime_type.startswith("audio/")
    msg_type = MessageType.VOICE if is_voice else (MessageType.IMAGE if is_image else MessageType.FILE)

    # Создаём placeholder сообщение (ciphertext = пустой, метаданные открытые)
    # В полной E2E реализации клиент должен зашифровать имя файла тоже
    placeholder_encrypted = b"\x00" * 12 + b"\x00" * 16  # nonce + empty gcm
    msg = Message(
        room_id           = room_id,
        sender_id         = u.id,
        msg_type          = msg_type,
        content_encrypted = placeholder_encrypted,
        file_name         = filename,
        file_size         = size,
    )
    db.add(msg)
    db.commit()

    await manager.broadcast_to_room(room_id, {
        "type":         "file",
        "sender_id":    u.id,
        "sender":       u.username,
        "display_name": u.display_name or u.username,
        "avatar_emoji": u.avatar_emoji,
        "file_name":    filename,
        "file_size":    size,
        "mime_type":    mime_type,
        "download_url": download_url,
        "msg_type":     msg_type.value,
        "created_at":   ft.created_at.isoformat(),
    })

    return {"ok": True, "file_id": ft.id, "download_url": download_url}


@router.get("/api/files/download/{file_id}")
async def download_file(
        file_id: int,
        u:  User    = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    ft = db.query(FileTransfer).filter(
        FileTransfer.id == file_id, FileTransfer.is_available == True,
        ).first()
    if not ft:
        raise HTTPException(404, "Файл не найден")

    member = db.query(RoomMember).filter(
        RoomMember.room_id == ft.room_id,
        RoomMember.user_id == u.id,
        RoomMember.is_banned == False,
        ).first()
    if not member:
        raise HTTPException(403, "Нет доступа")

    path = Config.UPLOAD_DIR / ft.stored_name
    if not path.exists():
        raise HTTPException(404, "Файл не найден на диске")

    ft.download_count += 1
    db.commit()

    return FileResponse(
        path      = str(path),
        filename  = ft.original_name,
        media_type= ft.mime_type or "application/octet-stream",
    )


@router.get("/api/files/room/{room_id}")
async def list_room_files(
        room_id: int,
        u:  User    = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    member = db.query(RoomMember).filter(
        RoomMember.room_id == room_id,
        RoomMember.user_id == u.id,
        RoomMember.is_banned == False,
        ).first()
    if not member:
        raise HTTPException(403, "Нет доступа")

    files = db.query(FileTransfer).filter(
        FileTransfer.room_id     == room_id,
        FileTransfer.is_available == True,
        ).order_by(FileTransfer.created_at.desc()).limit(100).all()

    return {"files": [{
        "id":           f.id,
        "file_name":    f.original_name,
        "mime_type":    f.mime_type,
        "size_bytes":   f.size_bytes,
        "uploader":     f.uploader.username if f.uploader else "—",
        "download_url": f"/api/files/download/{f.id}",
        "created_at":   f.created_at.isoformat(),
    } for f in files]}


# ══════════════════════════════════════════════════════════════════════════════
# WebRTC сигнализация (без изменений, уже работает правильно)
# ══════════════════════════════════════════════════════════════════════════════

_signal_rooms: dict[int, dict[int, WebSocket]] = {}


@router.websocket("/ws/signal/{room_id}")
async def ws_signal(
        websocket: WebSocket,
        room_id:   int,
        db:        Session = Depends(get_db),
):
    """WebRTC сигнализация — пересылает SDP/ICE без хранения."""
    import json as _json

    raw_token = websocket.cookies.get("access_token")
    if not raw_token:
        await websocket.close(code=4401)
        return

    try:
        user = await get_user_ws(raw_token, db)
    except HTTPException:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    _signal_rooms.setdefault(room_id, {})[user.id] = websocket

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = _json.loads(raw)
            except Exception:
                continue

            msg["from"]     = user.id
            msg["username"] = user.username

            for uid, ws in list(_signal_rooms.get(room_id, {}).items()):
                if uid != user.id:
                    try:
                        await ws.send_text(_json.dumps(msg))
                    except Exception:
                        _signal_rooms[room_id].pop(uid, None)

    except WebSocketDisconnect:
        pass
    finally:
        _signal_rooms.get(room_id, {}).pop(user.id, None)