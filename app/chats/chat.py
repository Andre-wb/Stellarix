"""
app/chats/chat.py — WebSocket чат, история сообщений, загрузка файлов.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from app.config import Config
from app.database import get_db
from app.models import User
from app.models_rooms import FileTransfer, Message, MessageType, Room, RoomMember
from app.peer.connection_manager import manager
from app.security.auth_jwt import get_current_user, get_user_ws
from app.security.secure_upload import (
    FileAnomalyDetector,
    FileUploadConfig,
    calculate_file_hash,
    generate_secure_filename,
    read_file_chunked,
    validate_file_mime_type,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

_DANGEROUS_EXTS = frozenset({
    '.php', '.php3', '.php4', '.php5', '.phtml',
    '.asp', '.aspx', '.ascx', '.ashx',
    '.jsp', '.jspx', '.jws', '.do',
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
# WebSocket чат
# ══════════════════════════════════════════════════════════════════════════════

@router.websocket("/ws/{room_id}")
async def ws_chat(
        websocket: WebSocket,
        room_id: int,
        token: Optional[str] = None,
        db: Session = Depends(get_db),
):
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
        room = db.query(Room).filter(Room.id == room_id).first()
        if room:
            await manager.send_to_user(room_id, user.id, {
                "type":       "node_pubkey",
                "pubkey_hex": user.x25519_public_key,
            })
            await _send_history(room_id, user.id, db)

        await manager.send_to_user(room_id, user.id, {
            "type":  "online",
            "users": manager.get_online_users(room_id),
        })

        while True:
            data   = await websocket.receive_json()
            action = data.get("action", "")

            if action == "message":
                await _handle_text_message(room_id, user, data, db)

            elif action == "edit_message":
                await _handle_edit_message(room_id, user, data, db)

            elif action == "delete_message":
                await _handle_delete_message(room_id, user, data, db)

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
        logger.warning(f"WS error user={user.username}: {e}")
    finally:
        await manager.disconnect(room_id, user.id)


async def _handle_text_message(room_id: int, user: User, data: dict, db: Session):
    text = (data.get("text") or "").strip()
    if not text or len(text) > 4096:
        return

    from app.security.crypto import encrypt_message, hash_message, generate_key
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        return

    if not room.room_key:
        room.room_key = generate_key()
        db.commit()

    reply_to_id   = data.get("reply_to_id")
    reply_to_text = None
    reply_to_sender = None

    if reply_to_id:
        replied = db.query(Message).filter(
            Message.id == reply_to_id,
            Message.room_id == room_id,
            ).first()
        if replied:
            if replied.msg_type == MessageType.TEXT and room.room_key:
                try:
                    from app.security.crypto import decrypt_message
                    reply_to_text = decrypt_message(replied.content_encrypted, room.room_key).decode()
                except Exception:
                    reply_to_text = "[сообщение]"
            else:
                reply_to_text = replied.file_name or "[файл]"

            if replied.sender:
                reply_to_sender = replied.sender.display_name or replied.sender.username
        else:
            reply_to_id = None

    encrypted = encrypt_message(text.encode(), room.room_key)
    msg = Message(
        room_id=room_id,
        sender_id=user.id,
        msg_type=MessageType.TEXT,
        content_encrypted=encrypted,
        content_hash=hash_message(text.encode()),
        reply_to_id=reply_to_id,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    payload = {
        "type":         "message",
        "msg_id":       msg.id,
        "sender_id":    user.id,
        "sender":       user.username,
        "display_name": user.display_name or user.username,
        "avatar_emoji": user.avatar_emoji,
        "text":         text,
        "msg_type":     "text",
        "created_at":   msg.created_at.isoformat(),
    }
    if reply_to_id:
        payload["reply_to_id"]     = reply_to_id
        payload["reply_to_text"]   = reply_to_text
        payload["reply_to_sender"] = reply_to_sender

    await manager.broadcast_to_room(room_id, payload)


async def _handle_edit_message(room_id: int, user: User, data: dict, db: Session):
    msg_id   = data.get("msg_id")
    new_text = (data.get("text") or "").strip()
    if not msg_id or not new_text or len(new_text) > 4096:
        return

    msg = db.query(Message).filter(
        Message.id == msg_id,
        Message.room_id == room_id,
        Message.sender_id == user.id,
        Message.msg_type == MessageType.TEXT,
    ).first()

    if not msg:
        return

    room = db.query(Room).filter(Room.id == room_id).first()
    if not room or not room.room_key:
        return

    from app.security.crypto import encrypt_message, hash_message
    msg.content_encrypted = encrypt_message(new_text.encode(), room.room_key)
    msg.content_hash      = hash_message(new_text.encode())
    msg.is_edited         = True
    db.commit()

    await manager.broadcast_to_room(room_id, {
        "type":      "message_edited",
        "msg_id":    msg_id,
        "text":      new_text,
        "is_edited": True,
    })


async def _handle_delete_message(room_id: int, user: User, data: dict, db: Session):
    msg_id = data.get("msg_id")
    if not msg_id:
        return

    msg = db.query(Message).filter(
        Message.id == msg_id,
        Message.room_id == room_id,
        Message.sender_id == user.id,   # только своё
    ).first()

    if not msg:
        return

    db.delete(msg)
    db.commit()

    await manager.broadcast_to_room(room_id, {
        "type":   "message_deleted",
        "msg_id": msg_id,
    })


async def _send_history(room_id: int, user_id: int, db: Session):
    from app.security.crypto import decrypt_message

    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        return

    messages = (
        db.query(Message)
        .filter(Message.room_id == room_id)
        .order_by(Message.created_at.desc())
        .limit(50).all()
    )[::-1]

    history = []
    for m in messages:
        entry = {
            "type":         "history_msg",
            "msg_id":       m.id,
            "sender_id":    m.sender_id,
            "sender":       m.sender.username if m.sender else "—",
            "display_name": (m.sender.display_name or m.sender.username) if m.sender else "—",
            "avatar_emoji": m.sender.avatar_emoji if m.sender else "👤",
            "msg_type":     m.msg_type.value,
            "created_at":   m.created_at.isoformat(),
            "file_name":    m.file_name,
            "file_size":    m.file_size,
            "is_edited":    m.is_edited,
        }

        # Данные цитируемого сообщения
        if m.reply_to_id and m.reply:
            entry["reply_to_id"] = m.reply_to_id
            if m.reply.msg_type == MessageType.TEXT and room.room_key:
                try:
                    entry["reply_to_text"] = decrypt_message(
                        m.reply.content_encrypted, room.room_key
                    ).decode()
                except Exception:
                    entry["reply_to_text"] = "[сообщение]"
            else:
                entry["reply_to_text"] = m.reply.file_name or "[файл]"

            if m.reply.sender:
                entry["reply_to_sender"] = (
                        m.reply.sender.display_name or m.reply.sender.username
                )

        if m.msg_type == MessageType.TEXT and room.room_key:
            try:
                entry["text"] = decrypt_message(m.content_encrypted, room.room_key).decode()
            except Exception:
                entry["text"] = "[ошибка расшифровки]"

        elif m.msg_type in (MessageType.IMAGE, MessageType.FILE, MessageType.VOICE):
            ft = db.query(FileTransfer).filter(
                FileTransfer.room_id == room_id,
                FileTransfer.original_name == m.file_name,
                FileTransfer.uploader_id == m.sender_id,
                ).order_by(FileTransfer.created_at.desc()).first()

            if ft:
                entry["download_url"] = f"/api/files/download/{ft.id}"
                entry["mime_type"]    = ft.mime_type
                entry["text"]         = f"[file:{ft.id}:{m.file_name}]"
            else:
                entry["text"] = f"[file:?:{m.file_name}]"
        else:
            entry["text"] = m.file_name or ""

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
        file: UploadFile = File(...),
        u: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    member = db.query(RoomMember).filter(
        RoomMember.room_id == room_id, RoomMember.user_id == u.id,
        RoomMember.is_banned == False,
        ).first()
    if not member:
        raise HTTPException(403, "Нет доступа к комнате")

    filename  = file.filename or "file"

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
    safe_name   = generate_secure_filename(ext)
    stored_path = Config.UPLOAD_DIR / safe_name
    stored_path.write_bytes(content)

    ft = FileTransfer(
        room_id=room_id, uploader_id=u.id,
        original_name=filename, stored_name=safe_name,
        mime_type=mime_type, size_bytes=size, file_hash=file_hash,
    )
    db.add(ft)

    is_voice   = filename.startswith("voice_") and mime_type and mime_type.startswith("audio/")
    msg_type   = MessageType.VOICE if is_voice else (MessageType.IMAGE if is_image else MessageType.FILE)
    room       = db.query(Room).filter(Room.id == room_id).first()

    if room and room.room_key:
        from app.security.crypto import encrypt_message, hash_message
        placeholder = f"[file:0:{filename}]".encode()
        encrypted   = encrypt_message(placeholder, room.room_key)
        msg = Message(
            room_id=room_id, sender_id=u.id,
            msg_type=msg_type,
            content_encrypted=encrypted,
            content_hash=hash_message(placeholder),
            file_name=filename, file_size=size,
        )
        db.add(msg)

    db.commit()
    db.refresh(ft)

    download_url = f"/api/files/download/{ft.id}"

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
        u: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    ft = db.query(FileTransfer).filter(
        FileTransfer.id == file_id, FileTransfer.is_available == True,
        ).first()
    if not ft:
        raise HTTPException(404, "Файл не найден")

    member = db.query(RoomMember).filter(
        RoomMember.room_id == ft.room_id, RoomMember.user_id == u.id,
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
        path=str(path),
        filename=ft.original_name,
        media_type=ft.mime_type or "application/octet-stream",
    )


@router.get("/api/files/room/{room_id}")
async def list_room_files(
        room_id: int,
        u: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    member = db.query(RoomMember).filter(
        RoomMember.room_id == room_id, RoomMember.user_id == u.id,
        RoomMember.is_banned == False,
        ).first()
    if not member:
        raise HTTPException(403, "Нет доступа")

    files = db.query(FileTransfer).filter(
        FileTransfer.room_id == room_id,
        FileTransfer.is_available == True,
        ).order_by(FileTransfer.created_at.desc()).limit(100).all()

    return {
        "files": [{
            "id":           f.id,
            "file_name":    f.original_name,
            "mime_type":    f.mime_type,
            "size_bytes":   f.size_bytes,
            "uploader":     f.uploader.username if f.uploader else "—",
            "download_url": f"/api/files/download/{f.id}",
            "created_at":   f.created_at.isoformat(),
        } for f in files]
    }


# ══════════════════════════════════════════════════════════════════════════════
# WebRTC сигнализация
# ══════════════════════════════════════════════════════════════════════════════

_signal_rooms: dict[int, dict[int, WebSocket]] = {}


@router.websocket("/ws/signal/{room_id}")
async def ws_signal(
        websocket: WebSocket,
        room_id: int,
        db: Session = Depends(get_db),
):
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
    logger.info(f"Signal WS: {user.username} → room {room_id}")

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
        logger.info(f"Signal WS closed: {user.username}")