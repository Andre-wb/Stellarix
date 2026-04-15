from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Integer, LargeBinary, String, Text, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship

from app.base import Base
from app.models_rooms.enums import MessageType


class Message(Base):
    """
    Сообщение комнаты. Сервер хранит ТОЛЬКО зашифрованный контент.

    Поле content_encrypted содержит:
      - nonce(12) + AES-256-GCM(plaintext, room_key) + tag(16)
    Где room_key известен только клиентам комнаты.

    Сервер передаёт content_encrypted клиентам «как есть» -- не расшифровывая.
    Клиент расшифровывает локально, используя room_key из EncryptedRoomKey.
    """
    __tablename__ = "messages"

    id                = Column(Integer,           primary_key=True, index=True)
    room_id           = Column(Integer,           ForeignKey("rooms.id", ondelete="CASCADE"),
                               nullable=False, index=True)
    sender_id         = Column(Integer,           ForeignKey("users.id", ondelete="SET NULL"),
                               nullable=True)
    # Sealed Sender: per-room pseudonym derived via BLAKE2b(key=secret, room||user).
    # Never expose sender_id to clients — relay only sender_pseudo.
    sender_pseudo     = Column(String(64),         nullable=True, index=True)
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

    # Треды: thread_id ссылается на корневое сообщение треда
    thread_id         = Column(Integer,           ForeignKey("messages.id", ondelete="SET NULL"),
                               nullable=True, index=True)
    # Денормализованный счётчик ответов в треде (только у корневого сообщения)
    thread_count      = Column(Integer,           default=0)

    is_edited         = Column(Boolean,           default=False)
    edited_at         = Column(DateTime,          nullable=True)

    # Пересланное сообщение: имя оригинального отправителя
    forwarded_from    = Column(String(100),       nullable=True)

    # Самоуничтожающиеся сообщения
    expires_at        = Column(DateTime,          nullable=True)

    # Отложенные сообщения (Feature 2: scheduled messages)
    scheduled_at      = Column(DateTime,          nullable=True)  # Когда доставить
    is_scheduled      = Column(Boolean,           default=False)

    created_at        = Column(DateTime,          default=lambda: datetime.now(timezone.utc), index=True)

    room   = relationship("Room",    back_populates="messages", foreign_keys="[Message.room_id]")
    sender = relationship("User")
    reply  = relationship("Message", remote_side="Message.id", foreign_keys=[reply_to_id])
    thread_root = relationship("Message", remote_side="Message.id", foreign_keys=[thread_id])

    __table_args__ = (
        Index("ix_msg_room_created", "room_id", "created_at"),
        Index("ix_msg_thread_id", "thread_id"),
    )

    def to_relay_dict(self) -> dict:
        """
        Формат для relay через WebSocket.
        Никаких расшифрованных данных — только метаданные + зашифрованный payload.
        """
        return {
            "msg_id":        self.id,
            "sender_pseudo": self.sender_pseudo,
            "msg_type":      self.msg_type.value,
            "ciphertext": self.content_encrypted.hex() if self.content_encrypted else None,
            "hash":       self.content_hash.hex()      if self.content_hash      else None,
            "file_name":  self.file_name,
            "file_size":  self.file_size,
            "reply_to_id":    self.reply_to_id,
            "thread_id":      self.thread_id,
            "thread_count":   self.thread_count or 0,
            "is_edited":      self.is_edited,
            "forwarded_from": self.forwarded_from,
            "expires_at":     self.expires_at.isoformat() if self.expires_at else None,
            "created_at":     self.created_at.isoformat(),
        }


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
    created_at     = Column(DateTime,    default=lambda: datetime.now(timezone.utc))

    room     = relationship("Room")
    uploader = relationship("User")


class MessageReaction(Base):
    """Реакция эмодзи на сообщение. Уникальна по (message_id, user_id, emoji)."""
    __tablename__ = "message_reactions"

    id         = Column(Integer,    primary_key=True)
    message_id = Column(Integer,    ForeignKey("messages.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    user_id    = Column(Integer,    ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False)
    emoji      = Column(String(10), nullable=False)
    created_at = Column(DateTime,   default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("message_id", "user_id", "emoji"),
    )


class MessageEditHistory(Base):
    """One row per edit: stores the previous ciphertext before it was overwritten."""
    __tablename__ = "message_edit_history"

    id             = Column(Integer,  primary_key=True, autoincrement=True)
    message_id     = Column(Integer,  ForeignKey("messages.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    ciphertext_hex = Column(Text,     nullable=False)
    edited_at      = Column(DateTime, nullable=False,
                            default=lambda: datetime.now(timezone.utc))
