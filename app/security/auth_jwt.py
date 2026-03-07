"""
JWT аутентификация — HMAC-HS256 с локальным секретом.
X25519 используется для E2E шифрования между устройствами, не для JWT.
Никаких RSA, никаких внешних CA.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import Config
from app.security.crypto import hash_token, verify_token_hash
from app.database import get_db
from app.models import RefreshToken, User

logger = logging.getLogger(__name__)

_JWT_ALG = "HS256"


# ══════════════════════════════════════════════════════════════════════════════
# Access Token (JWT HS256)
# ══════════════════════════════════════════════════════════════════════════════

def create_access_token(user_id: int, phone: str, username: str) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=Config.ACCESS_TOKEN_EXPIRE_MIN)
    payload: dict[str, Any] = {
        "sub":      str(user_id),
        "phone":    phone,
        "username": username,
        "iat":      now,
        "exp":      exp,
        "jti":      secrets.token_hex(16),
        "typ":      "access",
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm=_JWT_ALG)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            Config.JWT_SECRET,
            algorithms=[_JWT_ALG],
            options={"verify_aud": False, "require": ["sub", "exp", "jti"]},
            leeway=30,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Токен истёк")
    except jwt.InvalidTokenError as e:
        raise HTTPException(401, f"Неверный токен: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Refresh Token (opaque, SHA-256 hash в БД через Rust)
# ══════════════════════════════════════════════════════════════════════════════

def create_refresh_token(
        user_id: int, db: Session,
        ip: str | None = None,
        ua: str | None = None,
) -> tuple[str, datetime]:
    # Чистим просроченные
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.expires_at < datetime.now(timezone.utc),
        ).delete()

    raw = secrets.token_urlsafe(64)
    exp = datetime.now(timezone.utc) + timedelta(days=Config.REFRESH_TOKEN_EXPIRE_DAYS)

    # hash_token → SHA-256 через Rust (constant-time)
    db.add(RefreshToken(
        user_id=user_id,
        token_hash=hash_token(raw),
        expires_at=exp,
        ip_address=ip,
        user_agent=ua,
    ))
    db.commit()
    return raw, exp


def verify_refresh_token(raw: str, db: Session) -> User:
    token_hash = hash_token(raw)
    rec = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.revoked_at.is_(None),
        RefreshToken.expires_at > datetime.now(timezone.utc),
        ).first()
    if not rec:
        raise HTTPException(401, "Refresh-токен недействителен или истёк")
    user = db.query(User).filter(User.id == rec.user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(401, "Пользователь не найден")
    rec.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return user


# ══════════════════════════════════════════════════════════════════════════════
# FastAPI Dependencies
# ══════════════════════════════════════════════════════════════════════════════

async def get_current_user(
        request: Request,
        db: Session = Depends(get_db),
) -> User:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(401, "Не авторизован")
    payload = decode_access_token(token)
    user = db.query(User).filter(
        User.id == int(payload["sub"]),
        User.is_active == True,
        ).first()
    if not user:
        raise HTTPException(401, "Пользователь не найден")
    return user


async def get_user_ws(token: str, db: Session) -> User:
    """Для WebSocket — токен передаётся как query-параметр."""
    payload = decode_access_token(token)
    user = db.query(User).filter(
        User.id == int(payload["sub"]),
        User.is_active == True,
        ).first()
    if not user:
        raise HTTPException(401, "Пользователь не найден")
    return user