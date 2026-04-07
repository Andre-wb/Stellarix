from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Integer, String, Text, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship

from app.base import Base
from app.models_rooms.enums import RoomRole


class Room(Base):
    __tablename__ = "rooms"

    id          = Column(Integer,     primary_key=True, index=True)
    name        = Column(String(100), nullable=False)
    description = Column(String(500), default="")
    creator_id  = Column(Integer,     ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_private  = Column(Boolean,     default=False)
    invite_code = Column(String(16),  unique=True, nullable=False, index=True)
    max_members = Column(Integer,     default=100000)
    is_dm       = Column(Boolean,     default=False)
    is_channel  = Column(Boolean,     default=False)
    is_voice    = Column(Boolean,     default=False)
    is_forum    = Column(Boolean,     default=False)   # Forum mode (Reddit-like threads)
    subscriber_count = Column(Integer, default=0)
    discussion_enabled = Column(Boolean, default=False)  # Enable comments under channel posts

    # Channel-specific settings
    reactions_type      = Column(String(20), default="all")    # "all", "selected", "off"
    allowed_reactions   = Column(Text, default="")             # comma-separated emojis if reactions_type=selected
    admin_signatures    = Column(Boolean, default=False)       # Show admin name under posts
    copy_protection     = Column(Boolean, default=False)       # Disable copy/forward/screenshots
    silent_default      = Column(Boolean, default=False)       # Posts are silent by default (no notification sound)
    join_approval       = Column(Boolean, default=False)       # Require admin approval for join requests
    hashtags_enabled    = Column(Boolean, default=True)        # Enable clickable hashtags in channel

    # Привязка к пространству (Space)
    space_id    = Column(Integer, ForeignKey("spaces.id", ondelete="SET NULL"),
                         nullable=True, index=True)
    category_id = Column(Integer, ForeignKey("space_categories.id", ondelete="SET NULL"),
                         nullable=True)
    order_idx   = Column(Integer, default=0)

    # Закреплённое сообщение
    pinned_message_id = Column(Integer, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)

    # Автоудаление сообщений (Feature 3: disappearing messages per-chat)
    auto_delete_seconds = Column(Integer, nullable=True)  # 0/None = disabled, 30, 300, 3600, 86400

    # Медленный режим (Feature 4: slow mode for groups)
    slow_mode_seconds = Column(Integer, default=0)  # 0 = disabled

    # Аватар комнаты
    avatar_emoji = Column(String(10), default="\U0001f4ac")
    avatar_url   = Column(String(255), nullable=True)

    # Антиспам (flood detection) — можно отключить для конкретной комнаты
    antispam_enabled = Column(Boolean, default=True)

    # JSON-конфиг антиспам-бота: {threshold, action, block_repeats, block_links}
    antispam_config = Column(Text, default='{}')

    # Per-room theme: JSON {"wallpaper": "stars|aurora|...", "accent": "#hex", "dark_mode": bool}
    theme_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    members      = relationship("RoomMember",       back_populates="room",
                                cascade="all, delete-orphan", lazy="dynamic")
    messages     = relationship("Message",          back_populates="room",
                                cascade="all, delete-orphan", lazy="dynamic",
                                foreign_keys="[Message.room_id]")
    enc_keys     = relationship("EncryptedRoomKey", back_populates="room",
                                cascade="all, delete-orphan")
    pending_keys = relationship("PendingKeyRequest", back_populates="room",
                                cascade="all, delete-orphan")

    def member_count(self) -> int:
        cached = getattr(self, "_cached_member_count", None)
        if cached is not None:
            return cached
        try:
            from sqlalchemy import func
            from sqlalchemy.orm import Session, object_session
            sess: Session | None = object_session(self)
            if sess is not None:
                count = sess.query(func.count(RoomMember.id)).filter(
                    RoomMember.room_id == self.id
                ).scalar() or 0
            else:
                count = 0
        except Exception:
            count = 0
        self._cached_member_count = count
        return count

    def is_full(self) -> bool:
        return self.member_count() >= self.max_members


class RoomMember(Base):
    __tablename__ = "room_members"

    id        = Column(Integer,         primary_key=True, index=True)
    room_id   = Column(Integer,         ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    user_id   = Column(Integer,         ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role      = Column(Enum(RoomRole),  default=RoomRole.MEMBER, nullable=False)
    joined_at = Column(DateTime,        default=lambda: datetime.now(timezone.utc))
    is_muted  = Column(Boolean,         default=False)
    is_banned = Column(Boolean,         default=False)
    muted_until = Column(DateTime,     nullable=True)   # flood auto-mute expiry

    # ID последнего прочитанного сообщения (для серверного подсчёта непрочитанных)
    last_read_message_id = Column(Integer, nullable=True)

    room = relationship("Room", back_populates="members")
    user = relationship("User", back_populates="room_memberships")

    __table_args__ = (
        UniqueConstraint("room_id", "user_id"),
        Index("ix_rm_room_user", "room_id", "user_id"),
    )
