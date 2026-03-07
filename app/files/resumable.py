"""
app/files/resumable.py — Протокол возобновляемой загрузки файлов.

Архитектура:
  1. POST /api/files/upload-init          — инициализация сессии, возвращает upload_id
  2. PUT  /api/files/upload-chunk/{id}    — загрузка одного чанка (chunk_index, data, sha256)
  3. GET  /api/files/upload-status/{id}   — список полученных чанков (для возобновления)
  4. POST /api/files/upload-complete/{id} — сборка, проверка хеша, сохранение
  5. DELETE /api/files/upload-cancel/{id} — отмена сессии

Каждый чанк:
  - имеет порядковый номер (0-based)
  - сопровождается SHA-256 хешем для контроля целостности
  - хранится во временной директории до финальной сборки

Сессии хранятся в памяти (dict) + фоновая задача очистки протухших.
Хранение в памяти обнуляется при рестарте — клиент должен обрабатывать этот случай
через /upload-status или повторную инициализацию через /upload-init.

Подключение в main.py:
    from app.files.resumable import router as resumable_router, cleanup_sessions_loop
    app.include_router(resumable_router)

    # В lifespan:
    asyncio.create_task(cleanup_sessions_loop())
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import Config
from app.database import get_db
from app.models import User
from app.models_rooms import FileTransfer, Message, MessageType, RoomMember
from app.peer.connection_manager import manager
from app.security.auth_jwt import get_current_user
from app.security.secure_upload import (
    FileAnomalyDetector,
    FileUploadConfig,
    generate_secure_filename,
    validate_file_mime_type,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["resumable-upload"])

# ── Константы ──────────────────────────────────────────────────────────────────
DEFAULT_CHUNK_SIZE = 1 * 1024 * 1024        # 1 МБ
MIN_CHUNK_SIZE     = 64 * 1024              # 64 КБ
MAX_CHUNK_SIZE     = 10 * 1024 * 1024       # 10 МБ
MAX_CHUNKS         = 10_240                 # ≈ 10 ГБ при 1МБ-чанках
SESSION_TTL        = 24 * 3600             # TTL сессии (24 часа)
TEMP_DIR           = Config.UPLOAD_DIR / "_chunks"


# ══════════════════════════════════════════════════════════════════════════════
# Модель сессии загрузки
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class UploadSession:
    """
    In-memory запись активной сессии возобновляемой загрузки.

    Поля:
        upload_id      — уникальный токен сессии (URL-safe, 32 символа).
        room_id        — ID комнаты, в которую загружается файл.
        user_id        — ID пользователя-загрузчика.
        file_name      — оригинальное имя файла (от клиента).
        file_size      — ожидаемый полный размер в байтах.
        total_chunks   — ceil(file_size / chunk_size).
        file_hash      — SHA-256 всего файла (hex, нижний регистр).
        received       — множество индексов уже принятых чанков.
        created_at     — монотонное время создания сессии (time.monotonic()).
        chunk_dir      — временная папка для хранения чанков до сборки.
    """
    upload_id:    str
    room_id:      int
    user_id:      int
    file_name:    str
    file_size:    int
    total_chunks: int
    file_hash:    str
    received:     Set[int] = field(default_factory=set)
    created_at:   float    = field(default_factory=time.monotonic)
    chunk_dir:    Path     = field(default=None)  # type: ignore

    # ── Методы состояния ───────────────────────────────────────────────────────

    def is_expired(self) -> bool:
        return (time.monotonic() - self.created_at) > SESSION_TTL

    def is_complete(self) -> bool:
        return len(self.received) >= self.total_chunks

    def missing_chunks(self) -> List[int]:
        return sorted(set(range(self.total_chunks)) - self.received)

    def progress_pct(self) -> float:
        if self.total_chunks == 0:
            return 100.0
        return round(len(self.received) / self.total_chunks * 100, 1)


# ══════════════════════════════════════════════════════════════════════════════
# Хранилище сессий (in-memory, потокобезопасное через asyncio.Lock)
# ══════════════════════════════════════════════════════════════════════════════

class SessionStore:
    """
    Асинхронное хранилище сессий загрузки.

    Все операции защищены asyncio.Lock. Протухшие сессии удаляются при
    обращении и в фоновой задаче cleanup_sessions_loop().
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, UploadSession] = {}
        self._lock = asyncio.Lock()

    async def create(self, **kwargs) -> UploadSession:
        session = UploadSession(**kwargs)
        async with self._lock:
            self._sessions[session.upload_id] = session
        return session

    async def get(self, upload_id: str) -> Optional[UploadSession]:
        async with self._lock:
            session = self._sessions.get(upload_id)
            if session is None:
                return None
            if session.is_expired():
                # Удаляем без ожидания (внутри lock нельзя await нелиниейно)
                self._sessions.pop(upload_id, None)
                asyncio.create_task(self._cleanup_dir(session.chunk_dir))
                return None
            return session

    async def delete(self, upload_id: str) -> None:
        async with self._lock:
            session = self._sessions.pop(upload_id, None)
        if session:
            await self._cleanup_dir(session.chunk_dir)

    @staticmethod
    async def _cleanup_dir(chunk_dir: Optional[Path]) -> None:
        """Удаляет временную директорию чанков."""
        if not chunk_dir:
            return
        try:
            import shutil
            if chunk_dir.exists():
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: shutil.rmtree(chunk_dir, ignore_errors=True)
                )
        except Exception as exc:
            logger.warning(f"Chunk dir cleanup failed ({chunk_dir}): {exc}")

    async def cleanup_expired(self) -> int:
        """Удаляет все протухшие сессии. Возвращает количество удалённых."""
        async with self._lock:
            expired = [
                uid for uid, s in self._sessions.items() if s.is_expired()
            ]
            dirs_to_clean = []
            for uid in expired:
                s = self._sessions.pop(uid)
                dirs_to_clean.append(s.chunk_dir)

        for d in dirs_to_clean:
            await self._cleanup_dir(d)

        return len(expired)

    def active_count(self) -> int:
        return len(self._sessions)


# Глобальный экземпляр хранилища
_store = SessionStore()


# ══════════════════════════════════════════════════════════════════════════════
# Вспомогательные функции
# ══════════════════════════════════════════════════════════════════════════════

def _validate_hex_hash(value: str, field_name: str = "hash") -> str:
    """Проверяет, что строка является корректным SHA-256 hex (64 символа)."""
    value = value.strip().lower()
    if len(value) != 64:
        raise HTTPException(400, f"{field_name}: ожидается 64 hex-символа, получено {len(value)}")
    try:
        bytes.fromhex(value)
    except ValueError:
        raise HTTPException(400, f"{field_name}: некорректный hex")
    return value


def _check_room_access(room_id: int, user_id: int, db: Session) -> None:
    """Бросает 403 если пользователь не является участником комнаты."""
    if room_id >= 0:
        member = db.query(RoomMember).filter(
            RoomMember.room_id == room_id,
            RoomMember.user_id == user_id,
            RoomMember.is_banned == False,
            ).first()
        if not member:
            raise HTTPException(403, "Нет доступа к комнате")


# ══════════════════════════════════════════════════════════════════════════════
# 1. Инициализация сессии
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/api/files/upload-init")
async def upload_init(
        room_id:    int     = Form(...),
        file_name:  str     = Form(...),
        file_size:  int     = Form(...),
        file_hash:  str     = Form(...),
        chunk_size: int     = Form(DEFAULT_CHUNK_SIZE),
        u:          User    = Depends(get_current_user),
        db:         Session = Depends(get_db),
):
    """
    Инициализация сессии возобновляемой загрузки.

    Клиент передаёт:
      - room_id    — ID комнаты
      - file_name  — оригинальное имя файла
      - file_size  — полный размер в байтах
      - file_hash  — SHA-256 полного файла (64 hex-символа)
      - chunk_size — размер одного чанка (64КБ–10МБ, по умолчанию 1МБ)

    Ответ:
      - upload_id    — токен сессии для последующих запросов
      - total_chunks — ожидаемое количество чанков
      - chunk_size   — итоговый (скорректированный) размер чанка
      - received     — список уже принятых чанков (пусто для новой сессии)
    """
    _check_room_access(room_id, u.id, db)

    # Валидация размера файла
    if file_size <= 0 or file_size > FileUploadConfig.MAX_FILE_SIZE:
        raise HTTPException(
            400,
            f"Недопустимый размер файла: {file_size}. "
            f"Максимум: {FileUploadConfig.MAX_FILE_SIZE // 1024 // 1024} МБ"
        )

    # Валидация имени файла
    if FileAnomalyDetector.detect_null_bytes(file_name):
        raise HTTPException(400, "Недопустимые символы в имени файла")
    if FileAnomalyDetector.detect_path_traversal(file_name):
        raise HTTPException(400, "Недопустимое имя файла")

    # Валидация хеша
    file_hash = _validate_hex_hash(file_hash, "file_hash")

    # Нормализация chunk_size
    chunk_size    = max(MIN_CHUNK_SIZE, min(chunk_size, MAX_CHUNK_SIZE))
    total_chunks  = (file_size + chunk_size - 1) // chunk_size

    if total_chunks > MAX_CHUNKS:
        raise HTTPException(
            400,
            f"Слишком много чанков: {total_chunks} (максимум {MAX_CHUNKS}). "
            f"Увеличьте chunk_size."
        )

    # Создаём временную директорию
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    upload_id = secrets.token_urlsafe(24)
    chunk_dir = TEMP_DIR / upload_id
    chunk_dir.mkdir(parents=True, exist_ok=True)

    await _store.create(
        upload_id    = upload_id,
        room_id      = room_id,
        user_id      = u.id,
        file_name    = file_name,
        file_size    = file_size,
        total_chunks = total_chunks,
        file_hash    = file_hash,
        chunk_dir    = chunk_dir,
    )

    logger.info(
        f"[UploadInit] user={u.username} room={room_id} "
        f"file={file_name!r} size={file_size} chunks={total_chunks} id={upload_id}"
    )

    return {
        "upload_id":    upload_id,
        "total_chunks": total_chunks,
        "chunk_size":   chunk_size,
        "received":     [],
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2. Загрузка чанка
# ══════════════════════════════════════════════════════════════════════════════

@router.put("/api/files/upload-chunk/{upload_id}")
async def upload_chunk(
        upload_id:   str,
        chunk_index: int        = Form(...),
        chunk_hash:  str        = Form(...),
        data:        UploadFile = File(...),
        u:           User       = Depends(get_current_user),
):
    """
    Загрузка одного чанка.

    Клиент передаёт:
      - chunk_index — порядковый номер чанка (0-based)
      - chunk_hash  — SHA-256 данного чанка (для верификации)
      - data        — бинарные данные чанка

    Операция идемпотентна: если чанк с таким индексом уже принят,
    сервер возвращает OK без повторной записи.
    """
    session = await _store.get(upload_id)
    if not session:
        raise HTTPException(404, "Сессия загрузки не найдена или истекла. Начните заново.")
    if session.user_id != u.id:
        raise HTTPException(403, "Нет доступа к сессии загрузки")

    if not (0 <= chunk_index < session.total_chunks):
        raise HTTPException(400, f"Недопустимый номер чанка: {chunk_index} "
                                 f"(ожидается 0–{session.total_chunks - 1})")

    # Идемпотентность: чанк уже принят
    if chunk_index in session.received:
        return {
            "ok":             True,
            "chunk_index":    chunk_index,
            "already_received": True,
            "progress":       session.progress_pct(),
        }

    # Читаем данные
    raw = await data.read()
    if not raw:
        raise HTTPException(400, f"Пустой чанк {chunk_index}")

    # Проверяем хеш чанка
    chunk_hash    = _validate_hex_hash(chunk_hash, "chunk_hash")
    actual_hash   = hashlib.sha256(raw).hexdigest()
    if actual_hash != chunk_hash:
        raise HTTPException(
            400,
            f"Хеш чанка {chunk_index} не совпадает. "
            f"Ожидался: {chunk_hash[:16]}…, получен: {actual_hash[:16]}…"
        )

    # Атомарная запись: сначала во временный файл, потом rename
    chunk_path = session.chunk_dir / f"{chunk_index:06d}.chunk"
    tmp_path   = chunk_path.with_suffix(".tmp")
    tmp_path.write_bytes(raw)
    tmp_path.rename(chunk_path)

    session.received.add(chunk_index)

    logger.debug(
        f"[Chunk] {chunk_index}/{session.total_chunks - 1} "
        f"upload={upload_id} progress={session.progress_pct()}%"
    )

    return {
        "ok":          True,
        "chunk_index": chunk_index,
        "progress":    session.progress_pct(),
        "missing":     len(session.missing_chunks()),
        "complete":    session.is_complete(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 3. Статус сессии
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/api/files/upload-status/{upload_id}")
async def upload_status(
        upload_id: str,
        u:         User = Depends(get_current_user),
):
    """
    Возвращает список принятых чанков и прогресс.

    Клиент использует этот эндпоинт при возобновлении загрузки после
    разрыва соединения или перезагрузки страницы.
    """
    session = await _store.get(upload_id)
    if not session:
        raise HTTPException(404, "Сессия загрузки не найдена или истекла")
    if session.user_id != u.id:
        raise HTTPException(403, "Нет доступа к сессии загрузки")

    return {
        "upload_id":    upload_id,
        "file_name":    session.file_name,
        "file_size":    session.file_size,
        "total_chunks": session.total_chunks,
        "received":     sorted(session.received),
        "missing":      session.missing_chunks(),
        "progress":     session.progress_pct(),
        "complete":     session.is_complete(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 4. Финализация (сборка файла)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/api/files/upload-complete/{upload_id}")
async def upload_complete(
        upload_id: str,
        u:         User    = Depends(get_current_user),
        db:        Session = Depends(get_db),
):
    """
    Финализация загрузки: сборка чанков → проверка SHA-256 → сохранение.

    Последовательность:
      1. Проверить что все чанки получены.
      2. Собрать файл в памяти (stream по чанкам).
      3. Проверить SHA-256 против file_hash из init.
      4. Прогнать MIME-валидацию и проверки аномалий.
      5. Записать в Config.UPLOAD_DIR, создать FileTransfer + Message в БД.
      6. Broadcast в WebSocket комнаты.
      7. Удалить сессию и временные файлы.
    """
    session = await _store.get(upload_id)
    if not session:
        raise HTTPException(404, "Сессия загрузки не найдена или истекла")
    if session.user_id != u.id:
        raise HTTPException(403, "Нет доступа к сессии загрузки")

    missing = session.missing_chunks()
    if missing:
        raise HTTPException(
            400,
            {
                "error":   "Загрузка не завершена — есть незагруженные чанки",
                "missing": missing[:20],
                "count":   len(missing),
            }
        )

    # ── Сборка файла ──────────────────────────────────────────────────────────
    assembled = bytearray()
    for idx in range(session.total_chunks):
        chunk_path = session.chunk_dir / f"{idx:06d}.chunk"
        if not chunk_path.exists():
            # Это не должно произойти, но защищаемся
            raise HTTPException(500, f"Чанк {idx} отсутствует на диске — повторите загрузку")
        assembled.extend(chunk_path.read_bytes())

    content = bytes(assembled)
    del assembled

    # ── Проверка итогового хеша ───────────────────────────────────────────────
    actual_hash = hashlib.sha256(content).hexdigest()
    if actual_hash != session.file_hash:
        await _store.delete(upload_id)
        raise HTTPException(
            400,
            f"Хеш файла не совпадает. "
            f"Ожидался: {session.file_hash[:16]}…, получен: {actual_hash[:16]}…"
        )

    # ── Проверки безопасности ─────────────────────────────────────────────────
    if FileAnomalyDetector.detect_zip_bomb_indicators(content):
        await _store.delete(upload_id)
        raise HTTPException(400, "Файл имеет признаки архивной бомбы")

    mime_ok, mime_result = validate_file_mime_type(content, session.file_name)
    if not mime_ok:
        await _store.delete(upload_id)
        raise HTTPException(415, mime_result or "Неподдерживаемый тип файла")
    mime_type = mime_result

    is_image = mime_type and mime_type.startswith("image/")
    if is_image:
        img_ok, img_err = await FileAnomalyDetector.validate_image_content(content)
        if not img_ok:
            await _store.delete(upload_id)
            raise HTTPException(400, img_err or "Неверное содержимое изображения")

    # ── Сохранение файла ──────────────────────────────────────────────────────
    ext        = Path(session.file_name).suffix.lower()
    safe_name  = generate_secure_filename(ext)
    Config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_path = Config.UPLOAD_DIR / safe_name
    stored_path.write_bytes(content)

    # ── Запись в БД ───────────────────────────────────────────────────────────
    ft = FileTransfer(
        room_id       = session.room_id,
        uploader_id   = u.id,
        original_name = session.file_name,
        stored_name   = safe_name,
        mime_type     = mime_type,
        size_bytes    = len(content),
        file_hash     = actual_hash,
    )
    db.add(ft)
    db.commit()
    db.refresh(ft)

    download_url = f"/api/files/download/{ft.id}"

    is_voice = (
            session.file_name.startswith("voice_")
            and mime_type
            and mime_type.startswith("audio/")
    )
    msg_type = (
        MessageType.VOICE if is_voice
        else MessageType.IMAGE if is_image
        else MessageType.FILE
    )

    placeholder_encrypted = b"\x00" * 12 + b"\x00" * 16
    msg = Message(
        room_id           = session.room_id,
        sender_id         = u.id,
        msg_type          = msg_type,
        content_encrypted = placeholder_encrypted,
        file_name         = session.file_name,
        file_size         = len(content),
    )
    db.add(msg)
    db.commit()

    # ── WebSocket broadcast ───────────────────────────────────────────────────
    await manager.broadcast_to_room(session.room_id, {
        "type":         "file",
        "sender_id":    u.id,
        "sender":       u.username,
        "display_name": u.display_name or u.username,
        "avatar_emoji": u.avatar_emoji,
        "file_name":    session.file_name,
        "file_size":    len(content),
        "mime_type":    mime_type,
        "download_url": download_url,
        "msg_type":     msg_type.value,
        "created_at":   ft.created_at.isoformat(),
        "file_hash":    actual_hash,
    })

    logger.info(
        f"[UploadComplete] user={u.username} file={session.file_name!r} "
        f"size={len(content)} room={session.room_id} upload_id={upload_id}"
    )

    # ── Очистка сессии ────────────────────────────────────────────────────────
    await _store.delete(upload_id)

    return {
        "ok":          True,
        "file_id":     ft.id,
        "download_url": download_url,
        "file_hash":   actual_hash,
        "size_bytes":  len(content),
        "mime_type":   mime_type,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 5. Отмена сессии
# ══════════════════════════════════════════════════════════════════════════════

@router.delete("/api/files/upload-cancel/{upload_id}")
async def upload_cancel(
        upload_id: str,
        u:         User = Depends(get_current_user),
):
    """
    Отменяет сессию загрузки и удаляет временные файлы чанков.
    Безопасно вызывать даже если сессия уже завершена или истекла.
    """
    session = await _store.get(upload_id)
    if not session:
        return {"ok": True, "message": "Сессия не найдена (уже завершена или истекла)"}
    if session.user_id != u.id:
        raise HTTPException(403, "Нет доступа к сессии загрузки")

    await _store.delete(upload_id)
    logger.info(f"[UploadCancel] user={u.username} upload_id={upload_id}")
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# Фоновая задача очистки протухших сессий
# ══════════════════════════════════════════════════════════════════════════════

async def cleanup_sessions_loop(interval_sec: int = 3600) -> None:
    """
    Периодически удаляет протухшие сессии загрузки.

    Запускать как asyncio background task в lifespan приложения:

        asyncio.create_task(cleanup_sessions_loop())
    """
    while True:
        await asyncio.sleep(interval_sec)
        try:
            n = await _store.cleanup_expired()
            if n:
                logger.info(f"[ResumableCleanup] Удалено {n} протухших сессий")
        except Exception as exc:
            logger.error(f"[ResumableCleanup] Ошибка очистки: {exc}")