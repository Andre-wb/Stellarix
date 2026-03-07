"""
app/chats/chat.py — E2E WebSocket чат. Сервер ретранслирует шифротекст, не расшифровывает.

Улучшения:
- ACK-подтверждения после каждого сохранённого сообщения (критерий 4)
- Дедупликация через connection_manager.deduplicator (критерий 2)
- Rate limiting через Token Bucket (критерий 4 — контроль перегрузки)
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
    # Аутентификация через cookie или query-param токен
    try:
        raw_token = websocket.cookies.get("access_token") or token
        if not raw_token:
            await websocket.close(code=4401)
            return
        user = await get_user_ws(raw_token, db)
    except HTTPException:
        await websocket.close(code=4401)
        return

    member = db.query(RoomMember).filter(
        RoomMember.room_id == room_id,
        RoomMember.user_id == user.id,
        RoomMember.is_banned == False,
        ).first()
    if not member:
        await websocket.close(code=4403)
        return

    await manager.connect(
        room_id, user.id, user.username,
        user.display_name or user.username,
        user.avatar_emoji, websocket,
        )

    try:
        await _deliver_or_request_room_key(room_id, user, db)
        await _send_history(room_id, user.id, db)
        await manager.send_to_user(room_id, user.id, {
            "type":  "online",
            "users": manager.get_online_users(room_id),
        })
        await _notify_pending_key_requests(room_id, user.id, db)

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

            elif action == "signal":
                await _handle_signal(room_id, user, data)

            elif action == "ping":
                await manager.send_to_user(room_id, user.id, {"type": "pong"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WS error user={user.username} room={room_id}: {e}")
    finally:
        await manager.disconnect(room_id, user.id)


# ══════════════════════════════════════════════════════════════════════════════
# WebRTC сигнализация
# ══════════════════════════════════════════════════════════════════════════════

async def _handle_signal(room_id: int, user: User, data: dict) -> None:
    payload = {k: v for k, v in data.items() if k != "action"}
    payload["type"]     = "signal"
    payload["from"]     = user.id
    payload["username"] = user.username

    await manager.broadcast_to_room(room_id, payload, exclude=user.id)

    try:
        from app.federation.federation import relay
        if relay.get_room(room_id) is not None:
            await relay.send_to_remote(room_id, payload)
    except Exception as e:
        logger.debug(f"Signal relay forward failed room={room_id}: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Внутренние обработчики WebSocket событий
# ══════════════════════════════════════════════════════════════════════════════

async def _deliver_or_request_room_key(room_id: int, user: User, db: Session) -> None:
    enc_key = db.query(EncryptedRoomKey).filter(
        EncryptedRoomKey.room_id == room_id,
        EncryptedRoomKey.user_id == user.id,
        ).first()

    if enc_key:
        await manager.send_to_user(room_id, user.id, {
            "type":          "room_key",
            "room_id":       room_id,
            "ephemeral_pub": enc_key.ephemeral_pub,
            "ciphertext":    enc_key.ciphertext,
        })
        return

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
    # ── Rate limiting (Token Bucket) ─────────────────────────────────────────
    if not manager.check_rate_limit(room_id, user.id):
        await manager.send_to_user(room_id, user.id, {
            "type":    "error",
            "message": "Слишком много сообщений. Пожалуйста, подождите.",
            "code":    "rate_limited",
        })
        return

    ciphertext_hex = data.get("ciphertext", "").strip()
    client_msg_id  = data.get("msg_id", "")   # идентификатор от клиента

    if not ciphertext_hex:
        return

    if len(ciphertext_hex) < 48:
        await manager.send_to_user(room_id, user.id, {
            "type": "error", "message": "Ciphertext слишком короткий"
        })
        return

    # ── Дедупликация по client_msg_id ─────────────────────────────────────────
    if client_msg_id:
        dedup_key = f"msg:{room_id}:{client_msg_id}"
        if await manager.is_duplicate_message(dedup_key):
            # Повторная отправка — шлём ACK без сохранения
            await manager.send_to_user(room_id, user.id, {
                "type":       "ack",
                "msg_id":     client_msg_id,
                "duplicate":  True,
            })
            return

    try:
        ciphertext_bytes = bytes.fromhex(ciphertext_hex)
    except ValueError:
        await manager.send_to_user(room_id, user.id, {
            "type": "error", "message": "Ciphertext не является корректным hex"
        })
        return

    content_hash = None
    hash_hex     = data.get("hash", "")
    if hash_hex:
        try:
            content_hash = bytes.fromhex(hash_hex)
        except ValueError:
            pass
    if content_hash is None:
        content_hash_result = hash_message(ciphertext_bytes)
        if isinstance(content_hash_result, (bytes, bytearray)):
            content_hash = bytes(content_hash_result)

    reply_to_id = data.get("reply_to_id")
    if reply_to_id:
        reply_exists = db.query(Message.id).filter(
            Message.id      == reply_to_id,
            Message.room_id == room_id,
            ).first()
        if not reply_exists:
            reply_to_id = None

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

    # ── ACK — подтверждение доставки отправителю ──────────────────────────────
    await manager.send_to_user(room_id, user.id, {
        "type":       "ack",
        "msg_id":     client_msg_id,
        "server_id":  msg.id,
        "created_at": msg.created_at.isoformat(),
    })

    payload = {
        "type":          "message",
        "msg_id":        msg.id,
        "client_msg_id": client_msg_id,
        "sender_id":     user.id,
        "sender":        user.username,
        "display_name":  user.display_name or user.username,
        "avatar_emoji":  user.avatar_emoji,
        "ciphertext":    ciphertext_hex,
        "hash":          hash_hex or (content_hash.hex() if content_hash else None),
        "reply_to_id":   reply_to_id,
        "created_at":    msg.created_at.isoformat(),
    }
    # ── FIX: рассылаем ВСЕМ, включая отправителя — он сам отрендерит своё сообщение ──
    await manager.broadcast_to_room(room_id, payload)


async def _handle_edit_message(room_id: int, user: User, data: dict, db: Session) -> None:
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

    content_hash_result   = hash_message(ciphertext_bytes)
    msg.content_encrypted = ciphertext_bytes
    msg.content_hash      = bytes(content_hash_result) if isinstance(content_hash_result, (bytes, bytearray)) else None
    msg.is_edited         = True
    db.commit()

    await manager.broadcast_to_room(room_id, {
        "type":       "message_edited",
        "msg_id":     msg_id,
        "ciphertext": ciphertext_hex,
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
    for_user_id   = data.get("for_user_id")
    ephemeral_pub = data.get("ephemeral_pub", "")
    ciphertext    = data.get("ciphertext", "")

    if not for_user_id or not validate_ecies_payload({"ephemeral_pub": ephemeral_pub, "ciphertext": ciphertext}):
        await manager.send_to_user(room_id, user.id, {
            "type": "error", "message": "Некорректный key_response формат"
        })
        return

    target_member = db.query(RoomMember).filter(
        RoomMember.room_id == room_id,
        RoomMember.user_id == for_user_id,
        RoomMember.is_banned == False,
        ).first()
    if not target_member:
        return

    from app.models import User as UserModel
    target_user = db.query(UserModel).filter(UserModel.id == for_user_id).first()

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

    db.query(PendingKeyRequest).filter(
        PendingKeyRequest.room_id == room_id,
        PendingKeyRequest.user_id == for_user_id,
        ).delete()

    db.commit()

    delivered = await manager.send_to_user(room_id, for_user_id, {
        "type":          "room_key",
        "room_id":       room_id,
        "ephemeral_pub": ephemeral_pub,
        "ciphertext":    ciphertext,
    })

    logger.info(
        f"Key re-encrypted by {user.username} for user {for_user_id} "
        f"in room {room_id} (ws_delivered={delivered})"
    )


# ══════════════════════════════════════════════════════════════════════════════
# История сообщений
# ══════════════════════════════════════════════════════════════════════════════

async def _send_history(room_id: int, user_id: int, db: Session) -> None:
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

        if m.msg_type in (MessageType.IMAGE, MessageType.FILE, MessageType.VOICE):
            ft = db.query(FileTransfer).filter(
                FileTransfer.room_id       == room_id,
                FileTransfer.original_name == m.file_name,
                FileTransfer.uploader_id   == m.sender_id,
                ).order_by(FileTransfer.created_at.desc()).first()

            if ft:
                entry["download_url"] = f"/api/files/download/{ft.id}"
                entry["mime_type"]    = ft.mime_type
                entry["file_hash"]    = ft.file_hash

        history.append(entry)

    await manager.send_to_user(room_id, user_id, {
        "type":     "history",
        "messages": history,
    })


# ══════════════════════════════════════════════════════════════════════════════
# Загрузка файлов (обычная — не чанкованная)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/api/files/upload/{room_id}")
async def upload_file(
        room_id: int,
        request: Request,
        file:    UploadFile          = File(...),
        u:       User                = Depends(get_current_user),
        db:      Session             = Depends(get_db),
):
    if room_id < 0:
        from app.federation.federation import relay as _fed_relay
        _fed_info = _fed_relay.get_room(room_id)
        if not _fed_info or u.id not in _fed_info.local_user_ids:
            raise HTTPException(403, "Нет доступа к комнате")
    else:
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

    placeholder_encrypted = b"\x00" * 12 + b"\x00" * 16
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
        "file_hash":    file_hash,
    })

    return {"ok": True, "file_id": ft.id, "download_url": download_url, "file_hash": file_hash}


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
        path       = str(path),
        filename   = ft.original_name,
        media_type = ft.mime_type or "application/octet-stream",
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
        FileTransfer.room_id      == room_id,
        FileTransfer.is_available == True,
        ).order_by(FileTransfer.created_at.desc()).limit(100).all()

    return {"files": [{
        "id":           f.id,
        "file_name":    f.original_name,
        "mime_type":    f.mime_type,
        "size_bytes":   f.size_bytes,
        "file_hash":    f.file_hash,
        "uploader":     f.uploader.username if f.uploader else "—",
        "download_url": f"/api/files/download/{f.id}",
        "created_at":   f.created_at.isoformat(),
    } for f in files]}


# ══════════════════════════════════════════════════════════════════════════════
# WebRTC сигнализация (отдельный WS для обычных комнат)
# ══════════════════════════════════════════════════════════════════════════════

_signal_rooms: dict[int, dict[int, WebSocket]] = {}


@router.websocket("/ws/signal/{room_id}")
async def ws_signal(
        websocket: WebSocket,
        room_id:   int,
        token:     Optional[str] = None,
        db:        Session = Depends(get_db),
):
    import json as _json

    raw_token = websocket.cookies.get("access_token") or token
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