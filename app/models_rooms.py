"""Модели комнат, сообщений, файлов."""
from __future__ import annotations
import enum
from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Integer, LargeBinary, String, Text, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from app.base import Base


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


class Room(Base):
    __tablename__ = "rooms"

    id           = Column(Integer,       primary_key=True, index=True)
    name         = Column(String(100),   nullable=False)
    description  = Column(String(500),   default="")
    creator_id   = Column(Integer,       ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_private   = Column(Boolean,       default=False)
    invite_code  = Column(String(16),    unique=True, nullable=False, index=True)
    max_members  = Column(Integer,       default=200)
    room_key     = Column(LargeBinary(32), nullable=True)   # AES-256 ключ комнаты
    created_at   = Column(DateTime,     default=datetime.utcnow)
    updated_at   = Column(DateTime,     default=datetime.utcnow, onupdate=datetime.utcnow)

    members  = relationship("RoomMember", back_populates="room",
                            cascade="all, delete-orphan", lazy="dynamic")
    messages = relationship("Message",    back_populates="room",
                            cascade="all, delete-orphan", lazy="dynamic")

    def member_count(self) -> int:
        return self.members.count()

    def is_full(self) -> bool:
        return self.member_count() >= self.max_members


class RoomMember(Base):
    __tablename__ = "room_members"

    id        = Column(Integer, primary_key=True, index=True)
    room_id   = Column(Integer, ForeignKey("rooms.id",  ondelete="CASCADE"), nullable=False)
    user_id   = Column(Integer, ForeignKey("users.id",  ondelete="CASCADE"), nullable=False)
    role      = Column(Enum(RoomRole), default=RoomRole.MEMBER, nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)
    is_muted  = Column(Boolean,  default=False)
    is_banned = Column(Boolean,  default=False)

    room = relationship("Room",  back_populates="members")
    user = relationship("User",  back_populates="room_memberships")

    __table_args__ = (
        UniqueConstraint("room_id", "user_id"),
        Index("ix_rm_room_user", "room_id", "user_id"),
    )


class Message(Base):
    __tablename__ = "messages"

    id                = Column(Integer,      primary_key=True, index=True)
    room_id           = Column(Integer,      ForeignKey("rooms.id", ondelete="CASCADE"),
                               nullable=False, index=True)
    sender_id         = Column(Integer,      ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    msg_type          = Column(Enum(MessageType), default=MessageType.TEXT)
    content_encrypted = Column(LargeBinary,  nullable=False)
    content_hash      = Column(LargeBinary(32), nullable=True)   # BLAKE3
    file_name         = Column(String(255),  nullable=True)
    file_size         = Column(Integer,      nullable=True)
    reply_to_id       = Column(Integer,      ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    is_edited         = Column(Boolean,      default=False)
    created_at        = Column(DateTime,     default=datetime.utcnow, index=True)

    room   = relationship("Room",    back_populates="messages")
    sender = relationship("User")
    reply  = relationship("Message", remote_side="Message.id", foreign_keys=[reply_to_id])

    __table_args__ = (Index("ix_msg_room_created", "room_id", "created_at"),)


class FileTransfer(Base):
    __tablename__ = "file_transfers"

    id             = Column(Integer,    primary_key=True, index=True)
    room_id        = Column(Integer,    ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    uploader_id    = Column(Integer,    ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    original_name  = Column(String(255), nullable=False)
    stored_name    = Column(String(255), nullable=False)
    mime_type      = Column(String(128), nullable=True)
    size_bytes     = Column(Integer,    nullable=False)
    file_hash      = Column(String(64), nullable=False)
    is_available   = Column(Boolean,    default=True)
    download_count = Column(Integer,    default=0)
    created_at     = Column(DateTime,   default=datetime.utcnow)

    room     = relationship("Room")
    uploader = relationship("User")