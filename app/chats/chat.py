"""
app/chats/chat.py — WebSocket чат, история сообщений, загрузка файлов.

Используется secure_upload.py с исправленной логикой двойных расширений.
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

# Опасные серверные расширения (для проверки двойных расширений)
_DANGEROUS_EXTS = frozenset({
    '.php', '.php3', '.php4', '.php5', '.phtml',
    '.asp', '.aspx', '.ascx', '.ashx',
    '.jsp', '.jspx', '.jws', '.do',
    '.cgi', '.pl', '.py', '.rb', '.sh', '.bash',
    '.exe', '.dll', '.bat', '.cmd', '.ps1', '.vbs',
})


def _check_double_extension(filename: str) -> bool:
    """
    Правильная проверка двойных расширений.

    Флагирует: shell.php.jpg, virus.exe.png
    НЕ флагирует: фото 2024-01-01 12.34.56.jpg, my.photo.png

    Старый баг: проверял все части включая ПОСЛЕДНЕЕ расширение,
    что флагировало любой файл с точками в имени (скриншоты macOS).
    Исправление: проверяем только ПРОМЕЖУТОЧНЫЕ части на опасные расширения.
    """
    name  = Path(filename).name
    parts = name.split('.')
    if len(parts) <= 2:
        return False
    # Проверяем только промежуточные части (не первую и не последнюю)
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
            elif action == "typing":
                await manager.set_typing(room_id, user.id, bool(data.get("is_typing")))
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

    # Авто-генерация ключа для старых комнат, созданных без него
    if not room.room_key:
        room.room_key = generate_key()
        db.commit()

    encrypted = encrypt_message(text.encode(), room.room_key)
    msg = Message(
        room_id=room_id, sender_id=user.id,
        msg_type=MessageType.TEXT,
        content_encrypted=encrypted,
        content_hash=hash_message(text.encode()),
    )
    db.add(msg); db.commit(); db.refresh(msg)

    await manager.broadcast_to_room(room_id, {
        "type":         "message",
        "msg_id":       msg.id,
        "sender_id":    user.id,
        "sender":       user.username,
        "display_name": user.display_name or user.username,
        "avatar_emoji": user.avatar_emoji,
        "text":         text,
        "msg_type":     "text",
        "created_at":   msg.created_at.isoformat(),
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
        }

        if m.msg_type == MessageType.TEXT and room.room_key:
            try:
                entry["text"] = decrypt_message(m.content_encrypted, room.room_key).decode()
            except Exception:
                entry["text"] = "[ошибка расшифровки]"
        elif m.msg_type in (MessageType.IMAGE, MessageType.FILE):
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
    client_ip = request.client.host if request.client else "unknown"

    # ── 1. Читаем файл ───────────────────────────────────────────────────
    try:
        content, size = await read_file_chunked(file, FileUploadConfig.MAX_FILE_SIZE)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Ошибка чтения файла: {e}")

    # ── 2. Проверяем имя файла ───────────────────────────────────────────
    if FileAnomalyDetector.detect_null_bytes(filename):
        raise HTTPException(400, "Недопустимые символы в имени файла")
    if FileAnomalyDetector.detect_path_traversal(filename):
        raise HTTPException(400, "Недопустимое имя файла")
    # Используем исправленную функцию (не из secure_upload.py — там баг)
    if _check_double_extension(filename):
        raise HTTPException(400, "Недопустимое расширение файла")
    if FileAnomalyDetector.detect_zip_bomb_indicators(content):
        raise HTTPException(400, "Файл имеет признаки архивной бомбы")

    # ── 3. Валидация MIME (magic bytes) ──────────────────────────────────
    mime_ok, mime_result = validate_file_mime_type(content, filename)
    if not mime_ok:
        raise HTTPException(415, mime_result or "Неподдерживаемый тип файла")
    mime_type = mime_result

    # ── 4. Валидация изображения ──────────────────────────────────────────
    is_image = mime_type and mime_type.startswith("image/")
    if is_image:
        img_ok, img_err = await FileAnomalyDetector.validate_image_content(content)
        if not img_ok:
            raise HTTPException(400, img_err or "Неверное содержимое изображения")

    # ── 5. Сохраняем ─────────────────────────────────────────────────────
    ext       = Path(filename).suffix.lower()
    file_hash = calculate_file_hash(content)

    Config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name   = generate_secure_filename(ext)
    stored_path = Config.UPLOAD_DIR / safe_name
    stored_path.write_bytes(content)

    # ── 6. БД ─────────────────────────────────────────────────────────────
    ft = FileTransfer(
        room_id=room_id, uploader_id=u.id,
        original_name=filename, stored_name=safe_name,
        mime_type=mime_type, size_bytes=size, file_hash=file_hash,
    )
    db.add(ft)

    msg_type = MessageType.IMAGE if is_image else MessageType.FILE
    room     = db.query(Room).filter(Room.id == room_id).first()

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

    # ── 7. Бродкаст ───────────────────────────────────────────────────────
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