"""Модели пользователей. Идентификатор = номер телефона."""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, LargeBinary, String, Text
from sqlalchemy.orm import relationship
from app.database import Base
from app.security.crypto import hash_password, verify_password
from pydantic import BaseModel, Field, field_validator
import re

_PHONE_RE = re.compile(r"^\+?[1-9]\d{9,14}$")
_USER_RE  = re.compile(r"^[a-zA-Z0-9_]{3,30}$")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(20),  unique=True, nullable=False, index=True)
    username = Column(String(50),  unique=True, nullable=False, index=True)
    password_hash = Column(String(512), nullable=False)
    display_name = Column(String(100), nullable=True)
    avatar_emoji = Column(String(10),  default="👤")
    x25519_public_key = Column(String(64),  nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    room_memberships = relationship(
        "RoomMember", back_populates="user", cascade="all, delete-orphan"
    )

    def set_password(self, password: str) -> None:
        self.password_hash = hash_password(password)

    def check_password(self, password: str) -> bool:
        return verify_password(password, self.password_hash)

    def __repr__(self) -> str:
        return f"<User id={self.id} phone={self.phone} username={self.username}>"


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer,    primary_key=True)
    user_id = Column(Integer,    nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False)
    expires_at = Column(DateTime,   nullable=False)
    revoked_at = Column(DateTime,   nullable=True)
    created_at = Column(DateTime,   default=datetime.utcnow)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(512), nullable=True)

class RegisterRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=20)
    username: str = Field(..., min_length=3,  max_length=30)
    password: str = Field(..., min_length=8,  max_length=128)
    display_name: str = Field("", max_length=100)
    avatar_emoji: str = Field("👤", max_length=10)

    @field_validator("phone")
    @classmethod
    def v_phone(cls, v):
        c = re.sub(r"[\s\-\(\)]", "", v)
        if not _PHONE_RE.match(c):
            raise ValueError("Неверный формат номера телефона")
        return c

    @field_validator("username")
    @classmethod
    def v_username(cls, v):
        if not _USER_RE.match(v):
            raise ValueError("Только буквы, цифры и _ (3–30 символов)")
        return v.lower()


class LoginRequest(BaseModel):
    phone_or_username: str = Field(..., min_length=3, max_length=128)
    password: str = Field(..., min_length=1, max_length=128)


class PasswordStrengthRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=128)