"""
Криптографический модуль.

Приоритет: Rust (vortex_chat) → Python (cryptography + hashlib)

Что на Rust (cpu-intensive):
  - AES-256-GCM шифрование/дешифрование
  - BLAKE3 хеширование сообщений
  - Argon2 хеширование паролей
  - SHA-256 хеширование токенов (constant-time)
  - X25519 Diffie-Hellman (E2E ключи)
  - Генерация AES ключей

Что на Python:
  - Управление ключами X25519 (файловая система)
  - JWT (PyJWT HMAC-HS256)
  - Все что не является узким местом производительности
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ── Загрузка Rust модуля ────────────────────────────────────────────────────

try:
    import vortex_chat as _vc
    _RUST = True
    logger.info(f"✅ vortex_chat {_vc.VERSION} (Rust) загружен")
except ImportError:
    _RUST = False
    logger.warning("⚠️  vortex_chat не найден — Python fallback активен")
    logger.warning("   Скомпилируйте: cd rust_src && maturin develop --release")


# ══════════════════════════════════════════════════════════════════════════════
# Python fallbacks
# ══════════════════════════════════════════════════════════════════════════════

def _py_generate_key() -> bytes:
    return secrets.token_bytes(32)


def _py_encrypt(plaintext: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, None)


def _py_decrypt(data: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if len(data) < 12:
        raise ValueError("Зашифрованные данные слишком короткие")
    return AESGCM(key).decrypt(data[:12], data[12:], None)


def _py_hash(data: bytes) -> bytes:
    return hashlib.blake2b(data, digest_size=32).digest()


def _py_hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 310_000, dklen=32)
    return f"pbkdf2:sha256:310000:{salt}:{dk.hex()}"


def _py_verify_password(pw: str, h: str) -> bool:
    try:
        _, _, iters, salt, stored = h.split(":")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), int(iters), dklen=32)
        return secrets.compare_digest(dk.hex(), stored)
    except Exception:
        return False


def _py_hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _py_verify_token(token: str, expected_hash: str) -> bool:
    computed = _py_hash_token(token)
    return secrets.compare_digest(computed, expected_hash)


def _py_generate_keypair() -> Tuple[bytes, bytes]:
    """X25519 ключевая пара через cryptography."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    priv = X25519PrivateKey.generate()
    pub  = priv.public_key()
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption
    priv_bytes = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pub_bytes  = pub.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return priv_bytes, pub_bytes


def _py_derive_session_key(private_bytes: bytes, peer_public_bytes: bytes) -> bytes:
    """X25519 DH + HKDF-SHA256."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    priv = X25519PrivateKey.from_private_bytes(private_bytes)
    pub  = X25519PublicKey.from_public_bytes(peer_public_bytes)
    shared = priv.exchange(pub)
    hkdf  = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                 info=b"vortex-session")
    return hkdf.derive(shared)


# ══════════════════════════════════════════════════════════════════════════════
# Публичный API — единый для Rust и Python
# ══════════════════════════════════════════════════════════════════════════════

def generate_key() -> bytes:
    """Генерирует 32-байтный AES ключ."""
    if _RUST:
        return bytes(_vc.generate_key())
    return _py_generate_key()


def encrypt_message(plaintext: bytes, key: bytes) -> bytes:
    """AES-256-GCM шифрование. Возвращает nonce(12) + ciphertext."""
    if _RUST:
        return bytes(_vc.encrypt_message(plaintext, key))
    return _py_encrypt(plaintext, key)


def decrypt_message(data: bytes, key: bytes) -> bytes:
    """AES-256-GCM дешифрование."""
    if _RUST:
        return bytes(_vc.decrypt_message(data, key))
    return _py_decrypt(data, key)


def hash_message(data: bytes) -> bytes:
    """BLAKE3 хеш (32 байта). Rust path — очень быстро."""
    if _RUST:
        return bytes(_vc.hash_message(data))
    return _py_hash(data)


def hash_password(pw: str) -> str:
    """Argon2id хеш пароля. Rust path — безопасно и быстро."""
    if _RUST:
        return _vc.hash_password(pw)
    return _py_hash_password(pw)


def verify_password(pw: str, h: str) -> bool:
    """Проверка пароля (constant-time)."""
    if _RUST:
        return bool(_vc.verify_password(pw, h))
    return _py_verify_password(pw, h)


def hash_token(token: str) -> str:
    """SHA-256 хеш токена для хранения в БД."""
    if _RUST:
        return _vc.hash_token(token)
    return _py_hash_token(token)


def verify_token_hash(token: str, expected_hash: str) -> bool:
    """Constant-time проверка токена."""
    if _RUST:
        return bool(_vc.verify_token(token, expected_hash))
    return _py_verify_token(token, expected_hash)


def generate_x25519_keypair() -> Tuple[bytes, bytes]:
    """Генерирует X25519 ключевую пару (private, public), 32 байта каждый."""
    if _RUST:
        priv, pub = _vc.generate_keypair()
        return bytes(priv), bytes(pub)
    return _py_generate_keypair()


def derive_x25519_session_key(private_bytes: bytes, peer_public_bytes: bytes) -> bytes:
    """X25519 DH + HKDF → 32-байтный AES ключ для E2E сессии."""
    if _RUST:
        return bytes(_vc.derive_session_key(list(private_bytes), list(peer_public_bytes)))
    return _py_derive_session_key(private_bytes, peer_public_bytes)


def rust_available() -> bool:
    return _RUST


# ══════════════════════════════════════════════════════════════════════════════
# X25519 ключи узла (хранятся на диске)
# ══════════════════════════════════════════════════════════════════════════════

_node_priv: Optional[bytes] = None
_node_pub:  Optional[bytes] = None


def load_or_create_node_keypair(keys_dir: Path) -> Tuple[bytes, bytes]:
    """
    Загружает или создаёт X25519 ключевую пару этого узла.
    Приватный ключ хранится в keys/x25519_private.bin (бинарный, 32 байта)
    Публичный ключ в keys/x25519_public.bin
    """
    global _node_priv, _node_pub
    if _node_priv and _node_pub:
        return _node_priv, _node_pub

    keys_dir = Path(keys_dir)
    keys_dir.mkdir(parents=True, exist_ok=True)

    priv_path = keys_dir / "x25519_private.bin"
    pub_path  = keys_dir / "x25519_public.bin"

    if priv_path.exists() and pub_path.exists():
        _node_priv = priv_path.read_bytes()
        _node_pub  = pub_path.read_bytes()
        logger.info("X25519 ключи узла загружены")
    else:
        _node_priv, _node_pub = generate_x25519_keypair()
        priv_path.write_bytes(_node_priv)
        pub_path.write_bytes(_node_pub)
        # Устанавливаем права только для владельца
        os.chmod(priv_path, 0o600)
        logger.info("X25519 ключи узла сгенерированы и сохранены")

    return _node_priv, _node_pub


def get_node_public_key_hex(keys_dir: Path) -> str:
    """Возвращает публичный ключ узла в hex для хранения в БД и передачи пирам."""
    _, pub = load_or_create_node_keypair(keys_dir)
    return pub.hex()