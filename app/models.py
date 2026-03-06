"""
app/models.py — Модели пользователей.

Ключевые изменения для децентрализации:
  - RegisterRequest теперь требует x25519_public_key от клиента
    (ключ генерируется на устройстве, сервер не генерирует его за пользователя)
  - Добавлен KeyLoginRequest для беспарольного входа через X25519 challenge-response
"""
from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from app.base import Base
from app.security.crypto import hash_password, verify_password

_PHONE_RE = re.compile(r"^\+?[1-9]\d{9,14}$")
_USER_RE  = re.compile(r"^[a-zA-Z0-9_]{3,30}$")


# ══════════════════════════════════════════════════════════════════════════════
# SQLAlchemy модели
# ══════════════════════════════════════════════════════════════════════════════

class User(Base):
    __tablename__ = "users"

    id               = Column(Integer,     primary_key=True, index=True)
    phone            = Column(String(20),  unique=True, nullable=False, index=True)
    username         = Column(String(50),  unique=True, nullable=False, index=True)
    password_hash    = Column(String(512), nullable=False)
    display_name     = Column(String(100), nullable=True)
    avatar_emoji     = Column(String(10),  default="👤")

    # X25519 публичный ключ пользователя — генерируется НА КЛИЕНТЕ при регистрации.
    # Сервер никогда не видит приватный ключ.
    # Используется для:
    #   1. Шифрования ключей комнат (ECIES) при вступлении в комнату
    #   2. Challenge-response аутентификации (опционально)
    #   3. Обмена публичными ключами между участниками для E2E сессий
    x25519_public_key = Column(String(64), nullable=True, index=True)  # hex(32 bytes)

    is_active   = Column(Boolean,  default=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    last_seen   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    room_memberships = relationship(
        "RoomMember", back_populates="user", cascade="all, delete-orphan"
    )

    def set_password(self, password: str) -> None:
        self.password_hash = hash_password(password)

    def check_password(self, password: str) -> bool:
        return verify_password(password, self.password_hash)

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username}>"


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id          = Column(Integer,     primary_key=True)
    user_id     = Column(Integer,     nullable=False, index=True)
    token_hash  = Column(String(64),  unique=True, nullable=False)
    expires_at  = Column(DateTime,    nullable=False)
    revoked_at  = Column(DateTime,    nullable=True)
    created_at  = Column(DateTime,    default=datetime.utcnow)
    ip_address  = Column(String(45),  nullable=True)
    user_agent  = Column(String(512), nullable=True)


# ══════════════════════════════════════════════════════════════════════════════
# Pydantic схемы
# ══════════════════════════════════════════════════════════════════════════════

class RegisterRequest(BaseModel):
    phone:             str = Field(..., min_length=10, max_length=20)
    username:          str = Field(..., min_length=3,  max_length=30)
    password:          str = Field(..., min_length=8,  max_length=128)
    display_name:      str = Field("",  max_length=100)
    avatar_emoji:      str = Field("👤", max_length=10)

    # ── Ключевое поле для децентрализации ────────────────────────────────────
    # Клиент генерирует X25519 ключевую пару ЛОКАЛЬНО и передаёт только публичный ключ.
    # Приватный ключ никогда не отправляется на сервер.
    #
    # JavaScript (клиент):
    #   // Используем @noble/curves или TweetNaCl:
    #   import { x25519 } from "@noble/curves/ed25519";
    #   const priv = crypto.getRandomValues(new Uint8Array(32));
    #   const pub  = x25519.getPublicKey(priv);
    #   // priv — сохранить в localStorage / IndexedDB (зашифровав паролем)
    #   // pub  — отправить в этом поле как hex
    x25519_public_key: str = Field(..., min_length=64, max_length=64,
                                   description="X25519 публичный ключ клиента в hex (32 bytes = 64 chars)")

    @field_validator("phone")
    @classmethod
    def v_phone(cls, v: str) -> str:
        c = re.sub(r"[\s\-\(\)]", "", v)
        if not _PHONE_RE.match(c):
            raise ValueError("Неверный формат номера телефона")
        return c

    @field_validator("username")
    @classmethod
    def v_username(cls, v: str) -> str:
        if not _USER_RE.match(v):
            raise ValueError("Только буквы, цифры и _ (3–30 символов)")
        return v.lower()

    @field_validator("x25519_public_key")
    @classmethod
    def v_pubkey(cls, v: str) -> str:
        try:
            key_bytes = bytes.fromhex(v)
            if len(key_bytes) != 32:
                raise ValueError("Ключ должен быть 32 bytes")
        except ValueError as e:
            raise ValueError(f"x25519_public_key: {e}") from e
        return v.lower()


class LoginRequest(BaseModel):
    phone_or_username: str = Field(..., min_length=3, max_length=128)
    password:          str = Field(..., min_length=1, max_length=128)


class KeyLoginRequest(BaseModel):
    """
    Беспарольный вход через X25519 challenge-response.

    Протокол:
      1. GET /api/authentication/challenge?identifier=<phone_or_username>
         → {challenge_id, challenge_hex, server_pubkey_hex}
      2. Клиент вычисляет:
           shared = X25519-DH(client_priv, server_pub)
           proof  = HMAC-SHA256(key=shared, msg=challenge_bytes).hexdigest()
      3. POST /api/authentication/login-key с этой схемой
    """
    challenge_id: str = Field(..., min_length=32, max_length=32)
    pubkey:       str = Field(..., min_length=64, max_length=64,
                              description="X25519 публичный ключ клиента в hex")
    proof:        str = Field(..., min_length=64, max_length=64,
                              description="HMAC-SHA256(shared_secret, challenge) в hex")

    @field_validator("pubkey", "proof")
    @classmethod
    def v_hex(cls, v: str) -> str:
        try:
            bytes.fromhex(v)
        except ValueError:
            raise ValueError("Поле должно быть hex строкой")
        return v.lower()


class UpdateProfileRequest(BaseModel):
    """Обновление профиля пользователя."""
    display_name:  str | None = Field(None, max_length=100)
    avatar_emoji:  str | None = Field(None, max_length=10)
    # При смене устройства пользователь может обновить публичный ключ,
    # но это инвалидирует все EncryptedRoomKey — требует re-distribution
    x25519_public_key: str | None = Field(None, min_length=64, max_length=64)


class PasswordStrengthRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=128)