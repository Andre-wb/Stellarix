from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey,
    Integer, LargeBinary, String, Text, Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.base import Base


class PersistedFederatedRoom(Base):
    """
    Персистентная запись о федеративной (виртуальной) комнате.
    Позволяет восстанавливать federated rooms после перезагрузки ноды.
    """
    __tablename__ = "federated_rooms"

    id             = Column(Integer,      primary_key=True, autoincrement=True)
    virtual_id     = Column(Integer,      unique=True, nullable=False, index=True)
    peer_ip        = Column(String(128),  nullable=False)
    peer_port      = Column(Integer,      nullable=False)
    remote_room_id = Column(Integer,      nullable=False)
    remote_jwt     = Column(Text,         nullable=False, default="")
    room_name      = Column(String(255),  nullable=False)
    invite_code    = Column(String(32),   nullable=False)
    is_private     = Column(Boolean,      default=False)
    member_count   = Column(Integer,      default=0)
    created_at     = Column(DateTime,     default=lambda: datetime.now(timezone.utc))
    last_accessed  = Column(DateTime,     nullable=True)


class Story(Base):
    """Ephemeral story -- photo, video, or text. Expires in 24 hours.
    E2E encrypted: media/text are AES-256-GCM ciphertext.  The per-story
    random key is wrapped for each viewer in StoryKeyEnvelope.
    """
    __tablename__ = "stories"

    id          = Column(Integer,     primary_key=True, index=True)
    user_id     = Column(Integer,     ForeignKey("users.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    media_type  = Column(String(20),  nullable=False)   # 'photo' | 'video' | 'text'
    # ── Encrypted fields (hex-encoded nonce+ciphertext) ──
    media_blob  = Column(LargeBinary, nullable=True)     # AES-GCM(story_key, media)
    text_ct     = Column(Text,        nullable=True)     # hex of AES-GCM(story_key, text)
    meta_ct     = Column(Text,        nullable=True)     # hex of AES-GCM(story_key, JSON{text_color, bg_color, music_title})
    music_blob  = Column(LargeBinary, nullable=True)     # AES-GCM(story_key, music)
    # ── Plaintext metadata (non-sensitive) ──
    duration    = Column(Integer,     default=5)
    views_count = Column(Integer,     default=0)
    created_at  = Column(DateTime,    default=lambda: datetime.now(timezone.utc))
    expires_at  = Column(DateTime,    default=lambda: datetime.now(timezone.utc) + timedelta(hours=24))
    encrypted   = Column(Boolean,     default=True)      # False for legacy unencrypted stories

    # Legacy plaintext fields (kept for backward compat, unused for new stories)
    media_url   = Column(String(500), nullable=True)
    music_url   = Column(String(500), nullable=True)
    text        = Column(Text,        nullable=True)
    text_color  = Column(String(30),  default="#ffffff")
    bg_color    = Column(String(100), default="linear-gradient(135deg,#667eea 0%,#764ba2 100%)")
    music_title = Column(String(100), nullable=True)


class StoryKeyEnvelope(Base):
    """Per-viewer wrapped story key.
    story_key is encrypted via ECIES for each contact who should see it.
    """
    __tablename__ = "story_key_envelopes"
    __table_args__ = (UniqueConstraint("story_id", "user_id"),)

    id            = Column(Integer,     primary_key=True, index=True)
    story_id      = Column(Integer,     ForeignKey("stories.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    user_id       = Column(Integer,     ForeignKey("users.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    ephemeral_pub = Column(String(128), nullable=False)   # hex X25519 ephemeral pub
    ciphertext    = Column(String(256), nullable=False)   # hex nonce+AES-GCM(story_key)
