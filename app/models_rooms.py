"""
app/models_rooms.py — Модели комнат, сообщений, файлов и распределённых ключей.

Ключевые изменения для децентрализации:
  ─ Room.room_key УДАЛЁН. Сервер больше не хранит открытый ключ комнаты.
  + EncryptedRoomKey — ключ комнаты, зашифрованный ECIES для каждого участника отдельно.
  + PendingKeyRequest — очередь запросов ключа для участников без активной копии.

Схема распределения ключей:
  1. Создатель комнаты генерирует room_key(32 bytes) НА КЛИЕНТЕ
  2. Клиент делает ECIES(room_key, own_pubkey) → encrypted_key
  3. Клиент отправляет encrypted_key серверу → сохраняется в EncryptedRoomKey
  4. Новый участник подключается → нет EncryptedRoomKey → создаётся PendingKeyRequest
  5. Сервер рассылает online-участникам: {type: "key_request", for_user_id, for_pubkey}
  6. Любой online-участник расшифровывает room_key локально и re-encrypt для нового участника
  7. Участник отправляет: {action: "key_response", for_user_id, ephemeral_pub, ciphertext}
  8. Сервер сохраняет EncryptedRoomKey и доставляет новому участнику: {type: "room_key", ...}
"""
from __future__ import annotations

import enum
from datetime import datetime, timedelta

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Integer, LargeBinary, String, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship

from app.base import Base


# ══════════════════════════════════════════════════════════════════════════════
# Перечисления
# ══════════════════════════════════════════════════════════════════════════════

class RoomRole(str, enum.Enum):
    OWNER  = "owner"
    ADMIN  = "admin"
    MEMBER = "member"


class MessageType(str, enum.Enum):
    TEXT   = "text"
    FILE   = "file"
    IMAGE  = "image"
    VOICE  = "voice"
    SYSTEM = "system"


# ══════════════════════════════════════════════════════════════════════════════
# Комната
# ══════════════════════════════════════════════════════════════════════════════

class Room(Base):
    __tablename__ = "rooms"

    id          = Column(Integer,     primary_key=True, index=True)
    name        = Column(String(100), nullable=False)
    description = Column(String(500), default="")
    creator_id  = Column(Integer,     ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_private  = Column(Boolean,     default=False)
    invite_code = Column(String(16),  unique=True, nullable=False, index=True)
    max_members = Column(Integer,     default=200)

    # ── УДАЛЕНО ──────────────────────────────────────────────────────────────
    # room_key = Column(LargeBinary(32), nullable=True)
    # Причина: сервер не должен хранить открытый ключ шифрования.
    # Вместо этого каждый участник получает room_key, зашифрованный его X25519 pubkey,
    # в таблице encrypted_room_keys. Сервер физически не может расшифровать сообщения.
    # ─────────────────────────────────────────────────────────────────────────

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    members      = relationship("RoomMember",       back_populates="room",
                                cascade="all, delete-orphan", lazy="dynamic")
    messages     = relationship("Message",          back_populates="room",
                                cascade="all, delete-orphan", lazy="dynamic")
    enc_keys     = relationship("EncryptedRoomKey", back_populates="room",
                                cascade="all, delete-orphan")
    pending_keys = relationship("PendingKeyRequest", back_populates="room",
                                cascade="all, delete-orphan")

    def member_count(self) -> int:
        return self.members.count()

    def is_full(self) -> bool:
        return self.member_count() >= self.max_members


# ══════════════════════════════════════════════════════════════════════════════
# Участники комнаты
# ══════════════════════════════════════════════════════════════════════════════

class RoomMember(Base):
    __tablename__ = "room_members"

    id        = Column(Integer,         primary_key=True, index=True)
    room_id   = Column(Integer,         ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    user_id   = Column(Integer,         ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role      = Column(Enum(RoomRole),  default=RoomRole.MEMBER, nullable=False)
    joined_at = Column(DateTime,        default=datetime.utcnow)
    is_muted  = Column(Boolean,         default=False)
    is_banned = Column(Boolean,         default=False)

    room = relationship("Room", back_populates="members")
    user = relationship("User", back_populates="room_memberships")

    __table_args__ = (
        UniqueConstraint("room_id", "user_id"),
        Index("ix_rm_room_user", "room_id", "user_id"),
    )


# ══════════════════════════════════════════════════════════════════════════════
# Зашифрованные ключи комнат (E2E key distribution)
# ══════════════════════════════════════════════════════════════════════════════

class EncryptedRoomKey(Base):
    """
    Ключ комнаты, зашифрованный ECIES для конкретного участника.

    Содержимое (схема ECIES):
      ephemeral_pub — X25519 публичный ключ эфемерной пары (32 bytes → 64 hex chars)
      ciphertext    — nonce(12) + AES-GCM(room_key(32), shared_key) + tag(16)
                      = 60 bytes → 120 hex chars

    Как это работает:
      shared_key = HKDF( DH(ephemeral_priv, user_pub) )
      ciphertext = AES-256-GCM(room_key, shared_key)

    Сервер не может расшифровать это:
      - ему нужен user_priv (приватный ключ пользователя)
      - который никогда не покидает устройство пользователя

    Клиент расшифровывает:
      shared_key = HKDF( DH(user_priv, ephemeral_pub) )   ← тот же shared_key
      room_key   = AES-256-GCM-decrypt(ciphertext, shared_key)
    """
    __tablename__ = "encrypted_room_keys"

    id            = Column(Integer,     primary_key=True, index=True)
    room_id       = Column(Integer,     ForeignKey("rooms.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    user_id       = Column(Integer,     ForeignKey("users.id", ondelete="CASCADE"),
                           nullable=False, index=True)

    # ECIES поля — то что нужно клиенту для расшифровки
    ephemeral_pub = Column(String(64),  nullable=False)    # hex(32 bytes)
    ciphertext    = Column(String(120), nullable=False)    # hex(60 bytes)

    # Для верификации: ключ зашифрован именно для этого pubkey
    recipient_pub = Column(String(64),  nullable=True)

    created_at    = Column(DateTime,    default=datetime.utcnow)
    updated_at    = Column(DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)

    room = relationship("Room", back_populates="enc_keys")

    __table_args__ = (
        UniqueConstraint("room_id", "user_id"),
        Index("ix_erk_room_user", "room_id", "user_id"),
    )

    def to_client_dict(self) -> dict:
        """Формат для отправки клиенту через WebSocket."""
        return {
            "ephemeral_pub": self.ephemeral_pub,
            "ciphertext":    self.ciphertext,
        }


# ══════════════════════════════════════════════════════════════════════════════
# Очередь запросов на получение ключа комнаты
# ══════════════════════════════════════════════════════════════════════════════

class PendingKeyRequest(Base):
    """
    Ожидающий запрос на получение ключа комнаты.

    Создаётся когда:
      - Новый участник подключается через WebSocket
      - У него нет записи в EncryptedRoomKey
      - Ни один владелец ключа не онлайн

    Протокол доставки:
      1. User X joins room → PendingKeyRequest(room_id=R, user_id=X, pubkey=X.pubkey)
      2. Сервер рассылает online-членам: {type: "key_request", for_user_id: X, for_pubkey: "..."}
      3. Любой online-член Y выполняет ECIES(room_key, X.pubkey) на своём клиенте
      4. Y отправляет: {action: "key_response", for_user_id: X, ephemeral_pub: "...", ciphertext: "..."}
      5. Сервер сохраняет EncryptedRoomKey для X, удаляет PendingKeyRequest, доставляет X
      6. Если никто не онлайн: запрос висит до expires_at, очищается через cron/фоновую задачу

    TTL: 48 часов. Если X так и не получил ключ — при следующем подключении
    PendingKeyRequest создаётся заново.
    """
    __tablename__ = "pending_key_requests"

    id          = Column(Integer,    primary_key=True, index=True)
    room_id     = Column(Integer,    ForeignKey("rooms.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    user_id     = Column(Integer,    ForeignKey("users.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    pubkey_hex  = Column(String(64), nullable=False)   # X25519 pubkey ожидающего (64 hex chars)
    created_at  = Column(DateTime,   default=datetime.utcnow)
    expires_at  = Column(DateTime,   nullable=False,
                         default=lambda: datetime.utcnow() + timedelta(hours=48))

    room = relationship("Room", back_populates="pending_keys")

    __table_args__ = (
        UniqueConstraint("room_id", "user_id"),
        Index("ix_pkr_room_user", "room_id", "user_id"),
    )

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at


# ══════════════════════════════════════════════════════════════════════════════
# Сообщения
# ══════════════════════════════════════════════════════════════════════════════

class Message(Base):
    """
    Сообщение комнаты. Сервер хранит ТОЛЬКО зашифрованный контент.

    Поле content_encrypted содержит:
      - nonce(12) + AES-256-GCM(plaintext, room_key) + tag(16)
    Где room_key известен только клиентам комнаты.

    Сервер передаёт content_encrypted клиентам «как есть» — не расшифровывая.
    Клиент расшифровывает локально, используя room_key из EncryptedRoomKey.
    """
    __tablename__ = "messages"

    id                = Column(Integer,           primary_key=True, index=True)
    room_id           = Column(Integer,           ForeignKey("rooms.id", ondelete="CASCADE"),
                               nullable=False, index=True)
    sender_id         = Column(Integer,           ForeignKey("users.id", ondelete="SET NULL"),
                               nullable=True)
    msg_type          = Column(Enum(MessageType), default=MessageType.TEXT)

    # Зашифрованный контент — сервер не знает открытый текст
    content_encrypted = Column(LargeBinary,       nullable=False)

    # BLAKE3(content_encrypted) — для обнаружения дубликатов и проверки целостности
    # Сервер может проверить целостность без расшифровки
    content_hash      = Column(LargeBinary(32),   nullable=True)

    file_name         = Column(String(255),       nullable=True)
    file_size         = Column(Integer,           nullable=True)
    reply_to_id       = Column(Integer,           ForeignKey("messages.id", ondelete="SET NULL"),
                               nullable=True)
    is_edited         = Column(Boolean,           default=False)
    created_at        = Column(DateTime,          default=datetime.utcnow, index=True)

    room   = relationship("Room",    back_populates="messages")
    sender = relationship("User")
    reply  = relationship("Message", remote_side="Message.id", foreign_keys=[reply_to_id])

    __table_args__ = (Index("ix_msg_room_created", "room_id", "created_at"),)

    def to_relay_dict(self) -> dict:
        """
        Формат для relay через WebSocket.
        Никаких расшифрованных данных — только метаданные + зашифрованный payload.
        """
        return {
            "msg_id":     self.id,
            "sender_id":  self.sender_id,
            "msg_type":   self.msg_type.value,
            "ciphertext": self.content_encrypted.hex() if self.content_encrypted else None,
            "hash":       self.content_hash.hex()      if self.content_hash      else None,
            "file_name":  self.file_name,
            "file_size":  self.file_size,
            "reply_to_id":self.reply_to_id,
            "is_edited":  self.is_edited,
            "created_at": self.created_at.isoformat(),
        }


# ══════════════════════════════════════════════════════════════════════════════
# Файлы
# ══════════════════════════════════════════════════════════════════════════════

class FileTransfer(Base):
    """
    Метаданные файлов. Содержимое файла также шифруется клиентом перед загрузкой.
    Для полной E2E клиент должен зашифровать файл room_key перед отправкой на сервер.
    Сервер хранит зашифрованный blob, не может прочитать содержимое.
    """
    __tablename__ = "file_transfers"

    id             = Column(Integer,     primary_key=True, index=True)
    room_id        = Column(Integer,     ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    uploader_id    = Column(Integer,     ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    original_name  = Column(String(255), nullable=False)   # зашифрованное имя (опционально)
    stored_name    = Column(String(255), nullable=False)   # случайное имя на диске
    mime_type      = Column(String(128), nullable=True)    # может быть зашифрован
    size_bytes     = Column(Integer,     nullable=False)
    file_hash      = Column(String(64),  nullable=False)   # SHA-256 зашифрованного контента
    is_available   = Column(Boolean,     default=True)
    download_count = Column(Integer,     default=0)
    created_at     = Column(DateTime,    default=datetime.utcnow)

    room     = relationship("Room")
    uploader = relationship("User")