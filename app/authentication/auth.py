"""
app/authentication/auth.py — Аутентификация с поддержкой X25519 challenge-response.

Два метода входа:
  1. Password login    — классический, для совместимости
  2. Key login         — беспарольный, через X25519 DH challenge-response

Регистрация:
  - Клиент генерирует X25519 keypair ЛОКАЛЬНО
  - Отправляет только публичный ключ (x25519_public_key в RegisterRequest)
  - Сервер НИКОГДА не генерирует и не видит приватный ключ пользователя

X25519 Challenge-Response (беспарольный вход):
  ┌──────────────┐                              ┌──────────────┐
  │    Клиент    │                              │    Сервер    │
  └──────┬───────┘                              └──────┬───────┘
         │  GET /challenge?identifier=alice            │
         │ ─────────────────────────────────────────► │
         │                                             │ генерирует challenge(32 bytes)
         │  {challenge_id, challenge_hex,              │ сохраняет (60s TTL)
         │   server_pubkey_hex}                        │
         │ ◄───────────────────────────────────────── │
         │                                             │
         │  shared = DH(client_priv, server_pub)       │
         │  proof  = HMAC-SHA256(shared, challenge)    │
         │                                             │
         │  POST /login-key {challenge_id,             │
         │                   pubkey, proof}            │
         │ ─────────────────────────────────────────► │
         │                                             │ shared = DH(server_priv, client_pub)
         │                                             │ expected = HMAC(shared, stored_challenge)
         │                                             │ if proof == expected → OK
         │  {ok: true, ...} + JWT cookies              │
         │ ◄───────────────────────────────────────── │

Безопасность:
  - Приватный ключ клиента никогда не отправляется
  - Challenge одноразовый, 60-секундный TTL
  - HMAC вычисляется от shared secret → доказывает владение приватным ключом
  - Constant-time сравнение proof → защита от timing attacks
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import Config
from app.database import get_db
from app.models import (
    KeyLoginRequest, LoginRequest, PasswordStrengthRequest,
    RegisterRequest, User,
)
from app.security.auth_jwt import (
    create_access_token, create_refresh_token,
    get_current_user, verify_refresh_token,
)
from app.security.crypto import (
    derive_x25519_session_key, load_or_create_node_keypair, verify_password,
)
from app.security.security_vaidate import (
    calculate_password_strength, validate_password_with_context,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/authentication", tags=["authentication"])


# ══════════════════════════════════════════════════════════════════════════════
# In-memory хранилище challenge'ов
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class _Challenge:
    """Одноразовый challenge для X25519 аутентификации."""
    challenge:  bytes   # 32 случайных байта
    user_id:    int
    pubkey_hex: str     # ожидаемый публичный ключ клиента
    expires_at: float   # time.monotonic()


_challenges: dict[str, _Challenge] = {}
_challenges_lock = threading.Lock()
_CHALLENGE_TTL = 60  # секунд


def _cleanup_expired_challenges() -> None:
    """Удаляет просроченные challenge'ы (вызывается при каждом GET /challenge)."""
    now = time.monotonic()
    with _challenges_lock:
        expired = [cid for cid, ch in _challenges.items() if now > ch.expires_at]
        for cid in expired:
            del _challenges[cid]


# ══════════════════════════════════════════════════════════════════════════════
# Вспомогательные функции
# ══════════════════════════════════════════════════════════════════════════════

def _set_auth_cookies(response: Response, user: User, db: Session, request: Request) -> None:
    """Устанавливает access_token и refresh_token как HttpOnly cookies."""
    ip  = request.client.host if request.client else None
    ua  = request.headers.get("user-agent")
    access_token, _    = create_access_token(user.id, user.phone, user.username), None
    raw_refresh, _exp  = create_refresh_token(user.id, db, ip, ua)

    for name, val, max_age in [
        ("access_token",  access_token, 3600),
        ("refresh_token", raw_refresh,  86400 * 30),
    ]:
        response.set_cookie(
            name, val,
            httponly=True,
            secure=Config.IS_PRODUCTION,
            samesite="Lax",
            max_age=max_age,
            path="/",
        )


# ══════════════════════════════════════════════════════════════════════════════
# Регистрация
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/register", status_code=201)
async def register(body: RegisterRequest, request: Request,
                   db: Session = Depends(get_db)):
    """
    Регистрация нового пользователя.

    Клиент ОБЯЗАН передать x25519_public_key — X25519 публичный ключ, сгенерированный
    на устройстве. Приватный ключ никогда не отправляется и не должен покидать устройство.

    Публичный ключ используется для:
      - Шифрования ключей комнат при вступлении (ECIES)
      - Опционального беспарольного входа
      - E2E ключевого обмена между участниками комнаты
    """
    import asyncio

    # Проверка уникальности
    if db.query(User).filter(User.phone == body.phone).first():
        raise HTTPException(409, "Номер телефона уже занят")
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(409, "Имя пользователя уже занято")
    if db.query(User).filter(User.x25519_public_key == body.x25519_public_key).first():
        raise HTTPException(409, "Публичный ключ уже зарегистрирован")

    # Валидация пароля
    ok, msg = validate_password_with_context(body.password, body.username)
    if not ok:
        raise HTTPException(422, msg)

    # Создание пользователя
    # x25519_public_key берётся от КЛИЕНТА — сервер не генерирует ключи за пользователя
    user = User(
        phone             = body.phone,
        username          = body.username,
        display_name      = body.display_name or body.username,
        avatar_emoji      = body.avatar_emoji,
        x25519_public_key = body.x25519_public_key,  # ← от клиента, не от сервера
    )

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, user.set_password, body.password)

    db.add(user)
    try:
        await loop.run_in_executor(None, db.commit)
    except Exception:
        db.rollback()
        logger.exception("Register commit failed")
        raise HTTPException(500, "Ошибка базы данных")

    db.refresh(user)
    logger.info(f"Registered: {user.username} pubkey={user.x25519_public_key[:16]}...")

    data = {
        "ok":          True,
        "user_id":     user.id,
        "username":    user.username,
        "phone":       user.phone,
        "display_name":user.display_name,
        "avatar_emoji":user.avatar_emoji,
        "x25519_pubkey": user.x25519_public_key,
    }
    response = JSONResponse(status_code=201, content=data)
    _set_auth_cookies(response, user, db, request)
    return response


# ══════════════════════════════════════════════════════════════════════════════
# Парольный вход
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/login")
async def login(body: LoginRequest, request: Request,
                db: Session = Depends(get_db)):
    """Классический вход по паролю."""
    cred = body.phone_or_username.strip()
    user = (
            db.query(User).filter(User.phone == cred).first()
            or db.query(User).filter(User.username == cred.lower()).first()
    )

    if not user:
        try:
            verify_password(body.password, "$argon2id$v=19$m=65536,t=3,p=4$dummydummy$dummydummy")
        except Exception:
            pass
        raise HTTPException(401, "Неверный телефон/имя или пароль")

    if not user.check_password(body.password):
        raise HTTPException(401, "Неверный телефон/имя или пароль")
    if not user.is_active:
        raise HTTPException(403, "Аккаунт заблокирован")

    user.last_seen = datetime.now(timezone.utc)
    db.commit()

    data = {
        "ok":          True,
        "user_id":     user.id,
        "username":    user.username,
        "phone":       user.phone,
        "display_name":user.display_name or user.username,
        "avatar_emoji":user.avatar_emoji,
        "x25519_pubkey": user.x25519_public_key,
    }
    response = JSONResponse(content=data)
    _set_auth_cookies(response, user, db, request)
    return response


# ══════════════════════════════════════════════════════════════════════════════
# X25519 Challenge-Response (беспарольный вход)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/challenge")
async def get_challenge(identifier: str, db: Session = Depends(get_db)):
    """
    Шаг 1 беспарольного X25519 входа.
    Возвращает challenge и публичный ключ сервера.

    Клиент использует их для вычисления proof:
      shared = X25519-DH(client_priv, server_pub)
      proof  = HMAC-SHA256(key=shared, msg=challenge_bytes).hexdigest()
    """
    _cleanup_expired_challenges()

    user = (
            db.query(User).filter(User.phone == identifier).first()
            or db.query(User).filter(User.username == identifier.lower()).first()
    )

    # Если пользователь не найден — отвечаем dummy данными (timing attack prevention)
    if not user or not user.x25519_public_key:
        return {
            "challenge_id":    secrets.token_hex(16),
            "challenge":       secrets.token_hex(32),
            "server_pubkey":   "0" * 64,
            "expires_in":      _CHALLENGE_TTL,
        }

    # Публичный ключ этого узла (X25519)
    _, server_pub = load_or_create_node_keypair(Config.KEYS_DIR)

    challenge_bytes = secrets.token_bytes(32)
    challenge_id    = secrets.token_hex(16)

    with _challenges_lock:
        _challenges[challenge_id] = _Challenge(
            challenge  = challenge_bytes,
            user_id    = user.id,
            pubkey_hex = user.x25519_public_key,
            expires_at = time.monotonic() + _CHALLENGE_TTL,
        )

    return {
        "challenge_id":  challenge_id,
        "challenge":     challenge_bytes.hex(),
        "server_pubkey": server_pub.hex(),
        "expires_in":    _CHALLENGE_TTL,
    }


@router.post("/login-key")
async def login_with_key(body: KeyLoginRequest, request: Request,
                         db: Session = Depends(get_db)):
    """
    Шаг 2 беспарольного X25519 входа.
    Клиент доказывает владение приватным ключом через HMAC challenge-response.

    Проверка на сервере:
      server_priv, _ = load_node_keypair()
      shared         = X25519-DH(server_priv, client_pub)   ← симметрично DH клиента
      expected_proof = HMAC-SHA256(key=shared, msg=stored_challenge).hexdigest()
      assert constant_time_equal(body.proof, expected_proof)
    """
    # Извлекаем и сразу удаляем challenge (одноразовый)
    with _challenges_lock:
        ch = _challenges.pop(body.challenge_id, None)

    if not ch:
        raise HTTPException(401, "Challenge не найден или уже использован")
    if time.monotonic() > ch.expires_at:
        raise HTTPException(401, "Challenge истёк (60 секунд)")
    if not secrets.compare_digest(ch.pubkey_hex, body.pubkey):
        raise HTTPException(401, "Публичный ключ не совпадает с зарегистрированным")

    # Вычисляем expected proof на сервере
    server_priv, _ = load_or_create_node_keypair(Config.KEYS_DIR)
    client_pub     = bytes.fromhex(body.pubkey)

    try:
        # X25519 DH(server_priv, client_pub) = DH(client_priv, server_pub) — одинаковый результат
        shared = derive_x25519_session_key(server_priv, client_pub)
        if isinstance(shared, list):
            shared = bytes(shared)
    except Exception as e:
        logger.warning(f"Key derivation failed: {e}")
        raise HTTPException(401, "Ошибка вычисления общего секрета")

    expected_proof = hmac.new(shared, ch.challenge, hashlib.sha256).hexdigest()

    if not secrets.compare_digest(body.proof, expected_proof):
        raise HTTPException(401, "Неверный proof — возможно неверный приватный ключ")

    user = db.query(User).filter(
        User.id == ch.user_id, User.is_active == True
    ).first()
    if not user:
        raise HTTPException(401, "Пользователь не найден или деактивирован")

    user.last_seen = datetime.now(timezone.utc)
    db.commit()

    logger.info(f"Key-login: {user.username}")

    data = {
        "ok":          True,
        "user_id":     user.id,
        "username":    user.username,
        "phone":       user.phone,
        "display_name":user.display_name or user.username,
        "avatar_emoji":user.avatar_emoji,
        "x25519_pubkey": user.x25519_public_key,
    }
    response = JSONResponse(content=data)
    _set_auth_cookies(response, user, db, request)
    return response


# ══════════════════════════════════════════════════════════════════════════════
# Refresh, Logout, Me
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/refresh")
async def refresh(request: Request, db: Session = Depends(get_db)):
    raw = request.cookies.get("refresh_token")
    if not raw:
        raise HTTPException(401, "Нет refresh-токена")
    user = verify_refresh_token(raw, db)
    response = JSONResponse(content={"ok": True})
    _set_auth_cookies(response, user, db, request)
    return response


@router.post("/logout")
async def logout():
    r = JSONResponse({"ok": True})
    r.delete_cookie("access_token",  path="/")
    r.delete_cookie("refresh_token", path="/")
    return r


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    return {
        "user_id":       current_user.id,
        "phone":         current_user.phone,
        "username":      current_user.username,
        "display_name":  current_user.display_name or current_user.username,
        "avatar_emoji":  current_user.avatar_emoji,
        "x25519_pubkey": current_user.x25519_public_key,
        "created_at":    current_user.created_at.isoformat(),
        "last_seen":     current_user.last_seen.isoformat(),
    }


@router.post("/password-strength")
async def password_strength(body: PasswordStrengthRequest):
    return calculate_password_strength(body.password)


@router.get("/csrf-token")
async def get_csrf_token(request: Request):
    return {"csrf_token": request.cookies.get("csrf_token", "")}