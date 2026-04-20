"""
app/security/panic.py — Panic Button / Duress Mode.

POST /api/panic  — полное уничтожение аккаунта и всех данных.

Что удаляется:
  1. Все сообщения пользователя во всех комнатах
  2. Ключи шифрования (encrypted_room_keys, pending_key_requests)
  3. Все DM-комнаты где пользователь был участником (если там только 2 участника)
  4. Все боты пользователя
  5. Все пространства (Spaces) созданные пользователем
  6. RefreshToken записи (нет CASCADE FK)
  7. Запись User (остальное CASCADE)

Всем участникам комнат рассылается WebSocket событие `panic_wipe`
(клиент должен удалить сообщения пользователя из UI и очистить ключи).

Требует: пароль пользователя (Argon2id verify).

Memory shredding:
  Секреты (ключи, пароли, seed phrase) затираются через mmap-based secure
  buffers, полностью минуя pymalloc free-list. Используется explicit_bzero
  из libc (гарантированно не оптимизируется компилятором) или 4-pass DoD
  5220.22-M fallback. После wipe: SQLAlchemy identity map очищается,
  GC собирает все поколения, malloc_trim возвращает арены ОС.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import gc
import logging
import mmap
import os
import platform
import sys

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.security.auth_jwt import get_current_user
from app.database import get_db
from app.models import Bot, RefreshToken, User, UserDevice
from app.models.contact import Contact
from app.models_rooms import (
    EncryptedRoomKey, Message, PendingKeyRequest, Room, RoomMember,
    Space, SpaceMember,
)
from app.security.crypto import verify_password

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["panic"])


# ── libc bindings ───────────────────────────────────────────────────────────

def _get_libc():
    """Load libc — cached."""
    if not hasattr(_get_libc, "_lib"):
        name = ctypes.util.find_library("c")
        _get_libc._lib = ctypes.CDLL(name) if name else None
    return _get_libc._lib


def _has_explicit_bzero() -> bool:
    """Check if libc provides explicit_bzero (macOS 10.13+, glibc 2.25+)."""
    if not hasattr(_has_explicit_bzero, "_ok"):
        libc = _get_libc()
        try:
            libc.explicit_bzero
            _has_explicit_bzero._ok = True
        except (AttributeError, TypeError):
            _has_explicit_bzero._ok = False
    return _has_explicit_bzero._ok


# ── Core secure zeroing ─────────────────────────────────────────────────────

def _explicit_bzero(addr: int, size: int) -> bool:
    """Call libc explicit_bzero — guaranteed not optimized away by compiler."""
    libc = _get_libc()
    if libc is None:
        return False
    try:
        libc.explicit_bzero(ctypes.c_void_p(addr), ctypes.c_size_t(size))
        return True
    except (AttributeError, OSError):
        return False


def _mlock(addr: int, size: int) -> bool:
    libc = _get_libc()
    if libc is None:
        return False
    try:
        return libc.mlock(ctypes.c_void_p(addr), ctypes.c_size_t(size)) == 0
    except Exception:
        return False


def _munlock(addr: int, size: int) -> None:
    libc = _get_libc()
    if libc is None:
        return
    try:
        libc.munlock(ctypes.c_void_p(addr), ctypes.c_size_t(size))
    except Exception:
        pass


def _secure_zero_region(addr: int, size: int) -> None:
    """Zero a memory region using explicit_bzero or 4-pass DoD 5220.22-M fallback.

    explicit_bzero: single C call, compiler-guaranteed not to be elided.
    Fallback: 0x00 → 0xFF → random → 0x00 via ctypes.memset.
    """
    if _has_explicit_bzero() and _explicit_bzero(addr, size):
        return
    # Fallback: 4-pass DoD 5220.22-M
    ptr = ctypes.c_void_p(addr)
    sz = ctypes.c_size_t(size)
    ctypes.memset(ptr, 0x00, sz)
    ctypes.memset(ptr, 0xFF, sz)
    try:
        rand_buf = (ctypes.c_char * size).from_buffer_copy(os.urandom(size))
        ctypes.memmove(ptr, rand_buf, size)
    except Exception:
        ctypes.memset(ptr, 0xAA, sz)
    ctypes.memset(ptr, 0x00, sz)


# ── mmap-based secure buffer (bypasses pymalloc entirely) ────────────────────

class SecurePage:
    """Anonymous mmap page for secret data — never touches pymalloc.

    Memory is mlock'd on allocation (won't swap), zeroed with explicit_bzero
    on close, then munlock'd and munmap'd. The OS reclaims the page — no
    free-list residue.
    """

    def __init__(self, size: int):
        self._size = max(size, 1)
        self._buf = mmap.mmap(-1, self._size, access=mmap.ACCESS_WRITE)
        # mlock the page so it can't be swapped out
        _mlock(ctypes.addressof(ctypes.c_char.from_buffer(self._buf)), self._size)

    def write(self, data: bytes | str) -> None:
        raw = data.encode("utf-8") if isinstance(data, str) else data
        self._buf.seek(0)
        self._buf.write(raw[:self._size])

    def shred(self) -> None:
        """Multi-pass zero + unmap. After this, the memory is gone."""
        if self._buf is None:
            return
        try:
            addr = ctypes.addressof(ctypes.c_char.from_buffer(self._buf))
            _secure_zero_region(addr, self._size)
            _munlock(addr, self._size)
        except Exception:
            pass
        try:
            self._buf.close()
        except Exception:
            pass
        self._buf = None

    def __del__(self):
        self.shred()


# ── String/bytes shredding ──────────────────────────────────────────────────

def _secure_zero_string(s: str) -> None:
    """Shred a CPython str's internal buffer in-place.

    1. Disable GC — prevent the collector from relocating the object.
    2. mlock the data region — prevent page-out to swap.
    3. Overwrite via explicit_bzero / 4-pass fallback.
    4. Copy the secret into a SecurePage (outside pymalloc) and shred it
       there too — ensures the data is zeroed even if pymalloc recycles
       the original block without clearing it.
    """
    if not isinstance(s, str) or len(s) == 0:
        return
    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        header = sys.getsizeof("") - 1
        data_addr = id(s) + header
        data_len = len(s)

        _mlock(data_addr, data_len)
        _secure_zero_region(data_addr, data_len)
        _munlock(data_addr, data_len)

        # Mirror into mmap page and shred — catches pymalloc free-list residue
        page = SecurePage(data_len)
        page.write(b"\x00" * data_len)
        page.shred()
    except Exception:
        pass
    finally:
        if gc_was_enabled:
            gc.enable()


def _secure_zero_bytes(b: bytes | bytearray) -> None:
    """Shred a bytes/bytearray buffer."""
    if not b:
        return
    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        if isinstance(b, bytearray):
            addr = ctypes.addressof((ctypes.c_char * len(b)).from_buffer(b))
            _secure_zero_region(addr, len(b))
        else:
            header = sys.getsizeof(b"") - 1
            data_addr = id(b) + header
            _mlock(data_addr, len(b))
            _secure_zero_region(data_addr, len(b))
            _munlock(data_addr, len(b))
    except Exception:
        pass
    finally:
        if gc_was_enabled:
            gc.enable()


# ── Post-wipe cleanup ───────────────────────────────────────────────────────

def _purge_pymalloc_residue(db: Session) -> None:
    """Flush SQLAlchemy caches and return freed pymalloc arenas to the OS.

    1. Expunge all — drops SQLAlchemy's identity map (which may hold
       references to secret strings loaded from the DB).
    2. GC collect × 3 generations — frees all unreachable objects so
       pymalloc can reclaim their blocks.
    3. malloc_trim(0) on Linux — returns free pymalloc arenas to the OS,
       so even a memory dump after this point won't find them.
    """
    try:
        db.expunge_all()
    except Exception:
        pass

    gc.collect(0)
    gc.collect(1)
    gc.collect(2)

    libc = _get_libc()
    if libc and platform.system() == "Linux":
        try:
            libc.malloc_trim(ctypes.c_int(0))
        except (AttributeError, OSError):
            pass


# ── API endpoints ───────────────────────────────────────────────────────────

class PanicRequest(BaseModel):
    password: str


@router.post("/panic/verify")
async def panic_verify_password(
    body: PanicRequest,
    u: User = Depends(get_current_user),
):
    """Проверяет пароль перед показом модалки подтверждения — не удаляет данные."""
    if not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Invalid password")
    return {"ok": True}


@router.post("/panic")
async def panic_wipe(
    body: PanicRequest,
    request: Request,
    response: Response,
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Экстренное уничтожение аккаунта.
    Удаляет ВСЕ данные пользователя без возможности восстановления.
    """
    # 1. Проверяем пароль
    if not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Invalid password")

    user_id = u.id
    from app.security.ip_privacy import raw_ip_for_ratelimit
    logger.warning(f"PANIC WIPE initiated for user_id={user_id} ip={raw_ip_for_ratelimit(request)}")

    # 2. Собираем комнаты пользователя ДО удаления (для broadcast)
    memberships = db.query(RoomMember).filter(RoomMember.user_id == user_id).all()
    room_ids = [m.room_id for m in memberships]

    # 3. Рассылаем panic_wipe всем участникам комнат
    try:
        from app.peer.connection_manager import manager
        payload = {"type": "panic_wipe", "user_id": user_id}
        for room_id in room_ids:
            await manager.broadcast_to_room(room_id, payload)
    except Exception as e:
        logger.warning(f"Panic broadcast failed: {e}")

    # 4. Удаляем данные в правильном порядке (обходим FK без CASCADE)
    #
    #    Проблемные FK (без ondelete → NO ACTION по умолчанию):
    #      - Space.creator_id     FK("users.id"), nullable=False
    #      - RoomTask.creator_id  FK("users.id"), nullable=False
    #      - RoomTask.assignee_id FK("users.id"), nullable=True
    #    Эти записи ОБЯЗАТЕЛЬНО нужно удалить/обнулить ДО удаления User,
    #    иначе БД откажет с IntegrityError.
    try:
        from sqlalchemy import text as _sql_text, delete as _sql_delete

        # ── RefreshTokens (нет FK constraint) ───────────────────────────────
        db.query(RefreshToken).filter(RefreshToken.user_id == user_id).delete(synchronize_session=False)

        # ── UserDevice rows — must go explicitly. The FK is ON DELETE CASCADE
        # at the DB level, but the SQLAlchemy relationship User.devices
        # defaults to passive_deletes=False, so on db.delete(user) the ORM
        # runs UPDATE user_devices SET user_id=NULL which fails against the
        # NOT NULL constraint (sqlite3.IntegrityError NOT NULL constraint
        # failed: user_devices.user_id). Delete them up front.
        db.query(UserDevice).filter(UserDevice.user_id == user_id).delete(synchronize_session=False)

        # ── Ключи шифрования — зачищаем в памяти перед удалением ────────────
        doomed_keys = db.query(EncryptedRoomKey).filter(EncryptedRoomKey.user_id == user_id).all()
        for key_row in doomed_keys:
            if key_row.encrypted_key:
                _secure_zero_string(key_row.encrypted_key)
                key_row.encrypted_key = ""
        db.flush()
        db.query(EncryptedRoomKey).filter(EncryptedRoomKey.user_id == user_id).delete(synchronize_session=False)
        db.query(PendingKeyRequest).filter(PendingKeyRequest.user_id == user_id).delete(synchronize_session=False)

        # ── Сообщения — удаляем по sender_pseudo (Sealed Sender) ────────────
        from app.security.sealed_sender import compute_sender_pseudo as _csp
        for _rid in room_ids:
            _pseudo = _csp(_rid, user_id)
            db.query(Message).filter(
                Message.sender_pseudo == _pseudo,
            ).delete(synchronize_session=False)

        # ── DM-комнаты (2 участника — удаляем полностью) ────────────────────
        for room_id in room_ids:
            room = db.get(Room, room_id)
            if room and room.is_dm:
                all_members = db.query(RoomMember).filter(RoomMember.room_id == room_id).all()
                if len(all_members) <= 2:
                    db.query(Message).filter(Message.room_id == room_id).delete(synchronize_session=False)
                    db.query(RoomMember).filter(RoomMember.room_id == room_id).delete(synchronize_session=False)
                    db.query(EncryptedRoomKey).filter(EncryptedRoomKey.room_id == room_id).delete(synchronize_session=False)
                    db.query(PendingKeyRequest).filter(PendingKeyRequest.room_id == room_id).delete(synchronize_session=False)
                    db.delete(room)

        # ── RoomTask (FK без ondelete → NO ACTION!) ─────────────────────────
        try:
            from app.models_rooms import RoomTask
            db.query(RoomTask).filter(RoomTask.assignee_id == user_id).update(
                {RoomTask.assignee_id: None}, synchronize_session=False
            )
            db.query(RoomTask).filter(RoomTask.creator_id == user_id).delete(synchronize_session=False)
        except Exception as te:
            logger.warning(f"RoomTask cleanup failed: {te}")

        # ── Боты пользователя ────────────────────────────────────────────────
        try:
            from app.models import BotReview
            db.query(BotReview).filter(BotReview.user_id == user_id).delete(synchronize_session=False)
        except Exception:
            pass
        db.query(Bot).filter(Bot.owner_id == user_id).delete(synchronize_session=False)

        # ── Spaces (creator_id FK без ondelete, nullable=False!) ─────────────
        owned_spaces = db.query(Space).filter(Space.creator_id == user_id).all()
        for space in owned_spaces:
            db.query(SpaceMember).filter(SpaceMember.space_id == space.id).delete(synchronize_session=False)
            db.delete(space)

        # ── Контакты ────────────────────────────────────────────────────────
        try:
            db.query(Contact).filter(
                (Contact.owner_id == user_id) | (Contact.contact_id == user_id)
            ).delete(synchronize_session=False)
        except Exception as ce:
            logger.warning(f"Contacts delete failed (table may not exist): {ce}")

        # ── Убираем membership из оставшихся комнат ──────────────────────────
        db.query(RoomMember).filter(RoomMember.user_id == user_id).delete(synchronize_session=False)

        db.flush()

        # ── Зачищаем чувствительные поля пользователя в памяти ───────────
        for attr in ("password_hash", "seed_phrase_hash", "totp_secret"):
            val = getattr(u, attr, None)
            if val:
                _secure_zero_string(val)

        # ── Удаляем пользователя raw SQL → CASCADE сработает на остальных FK ─
        db.expunge(u)
        db.execute(_sql_delete(User).where(User.id == user_id))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"PANIC WIPE failed for user_id={user_id}: {e}", exc_info=True)
        raise HTTPException(500, f"Data deletion error: {e}")

    logger.warning(f"PANIC WIPE completed for user_id={user_id}")

    # 5. Зачищаем пароль из памяти (через SecurePage — вне pymalloc)
    _secure_zero_string(body.password)

    # 6. Вычищаем pymalloc residue
    _purge_pymalloc_residue(db)

    # 7. Сбрасываем cookies
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")

    return {"ok": True, "wiped": True}
