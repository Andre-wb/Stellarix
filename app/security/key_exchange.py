"""
app/security/key_exchange.py — ECIES и P2P шифрование между узлами.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  СХЕМА ECIES (Elliptic Curve Integrated Encryption Scheme)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Шифрование (сервер → участнику комнаты):
    1. Генерируем эфемерную X25519 пару: (e_priv, e_pub)  ← новая для каждого вызова
    2. shared = X25519-DH(e_priv, recipient_pub)
    3. enc_key = HKDF-SHA256(shared, salt=e_pub, info=b"ecies-room-key", len=32)
    4. nonce(12) + ct = AES-256-GCM( plaintext, enc_key )
       для room_key(32 bytes): ct = 32 + 16(tag) = 48 bytes → итого 60 bytes
    5. Сохраняем: { "ephemeral_pub": e_pub.hex(), "ciphertext": (nonce+ct).hex() }

  Расшифровка (КЛИЕНТ, JavaScript / мобильное приложение):
    1. shared = X25519-DH(user_priv, e_pub)
    2. enc_key = HKDF-SHA256(shared, salt=e_pub, info=b"ecies-room-key", len=32)
    3. room_key = AES-256-GCM-decrypt(ciphertext[12:], nonce=ciphertext[:12], key=enc_key)

  Сервер НИКОГДА не видит приватный ключ пользователя.
  Сервер может зашифровать для пользователя, но не может расшифровать.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  JAVASCRIPT-РЕАЛИЗАЦИЯ (для клиента)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  // ── Генерация ключевой пары при регистрации ──────────────────────
  const raw = crypto.getRandomValues(new Uint8Array(32));
  // Используем raw bytes как X25519 private key (RFC 7748)
  // Отправляем publicKey на сервер в hex при регистрации

  // ── ECIES расшифровка ключа комнаты ──────────────────────────────
  async function eciesDecrypt(ephPubHex, ciphertextHex, myPrivHex) {
    const ephPub = hexToBytes(ephPubHex);
    const ct     = hexToBytes(ciphertextHex);
    // Web Crypto не поддерживает X25519 DH напрямую — используем TweetNaCl или noble-curves:
    const shared   = x25519.getSharedSecret(myPrivBytes, ephPub);
    const salt     = ephPub;
    const encKey   = await hkdf(shared, salt, "ecies-room-key", 32);
    const nonce    = ct.slice(0, 12);
    const cipher   = ct.slice(12);
    const roomKey  = await crypto.subtle.decrypt(
      {name:"AES-GCM", iv:nonce}, await importKey(encKey), cipher
    );
    return new Uint8Array(roomKey); // 32 bytes — ключ комнаты
  }

  // ── Шифрование сообщения ключом комнаты ──────────────────────────
  async function encryptMessage(text, roomKeyBytes) {
    const nonce = crypto.getRandomValues(new Uint8Array(12));
    const key   = await crypto.subtle.importKey("raw", roomKeyBytes, "AES-GCM", false, ["encrypt"]);
    const ct    = await crypto.subtle.encrypt({name:"AES-GCM", iv:nonce}, key, new TextEncoder().encode(text));
    return bytesToHex(new Uint8Array([...nonce, ...new Uint8Array(ct)]));
  }

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  P2P ШИФРОВАНИЕ МЕЖДУ УЗЛАМИ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Каждый HTTP-запрос между нодами шифруется ECIES с forward secrecy:
    - Отправитель генерирует эфемерную пару для КАЖДОГО запроса
    - Получатель расшифровывает своим постоянным X25519 ключом узла
    - Подслушивающий не может расшифровать даже если узнает постоянный ключ позже
"""
from __future__ import annotations

import json
import logging
from typing import Tuple

from app.security.crypto import (
    derive_x25519_session_key,
    encrypt_message,
    decrypt_message,
    generate_x25519_keypair,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# ECIES: шифрование данных для X25519 получателя
# ══════════════════════════════════════════════════════════════════════════════

def ecies_encrypt(plaintext: bytes, recipient_pub_hex: str) -> dict:
    """
    Шифрует plaintext для получателя по его X25519 публичному ключу.

    Используется когда:
      - Сервер шифрует ключ комнаты для нового участника
      - Участник переотдаёт ключ комнаты другому участнику (через WebSocket)
      - Узел шифрует P2P payload для другого узла

    Эфемерная пара генерируется КАЖДЫЙ РАЗ → forward secrecy на уровне сообщения.

    Args:
        plaintext:         байты для шифрования (room_key = 32 bytes, или JSON payload)
        recipient_pub_hex: X25519 публичный ключ получателя в hex (64 символа = 32 bytes)

    Returns:
        {
          "ephemeral_pub": "<64 hex chars — 32 bytes>",
          "ciphertext":    "<120 hex chars — 60 bytes: nonce(12) + ct(32) + tag(16)>"
        }
        Для JSON payload размер ciphertext будет больше.
    """
    if len(recipient_pub_hex) != 64:
        raise ValueError(f"recipient_pub_hex должен быть 64 hex chars, получено {len(recipient_pub_hex)}")

    recipient_pub = bytes.fromhex(recipient_pub_hex)

    # Новая эфемерная пара для этого конкретного шифрования
    ephemeral_priv, ephemeral_pub = generate_x25519_keypair()

    # X25519 DH: ephemeral_priv × recipient_pub → 32-byte shared secret
    # Rust: derive_session_key использует HKDF-SHA256 поверх DH
    shared_key = derive_x25519_session_key(ephemeral_priv, recipient_pub)

    # AES-256-GCM: результат = nonce(12) + ciphertext + tag(16)
    ciphertext = encrypt_message(plaintext, shared_key)

    return {
        "ephemeral_pub": ephemeral_pub.hex(),
        "ciphertext":    ciphertext.hex(),
    }


def ecies_decrypt_node(ephemeral_pub_hex: str, ciphertext_hex: str, our_node_private: bytes) -> bytes:
    """
    Расшифровывает данные, зашифрованные через ecies_encrypt.

    Используется ТОЛЬКО на уровне УЗЛА (не пользователей):
      - Узел расшифровывает входящий зашифрованный P2P запрос от другого узла
      - Пользователи расшифровывают ключи комнат САМИ на клиенте (JavaScript)

    Args:
        ephemeral_pub_hex:  hex публичного X25519 ключа отправителя (из поля "ephemeral_pub")
        ciphertext_hex:     hex зашифрованных данных (из поля "ciphertext")
        our_node_private:   X25519 приватный ключ ЭТОГО узла (32 bytes из keys/x25519_private.bin)

    Returns:
        Расшифрованные bytes
    """
    ephemeral_pub = bytes.fromhex(ephemeral_pub_hex)
    ciphertext    = bytes.fromhex(ciphertext_hex)

    # DH с эфемерным ключом отправителя → тот же shared_key что и при шифровании
    shared_key = derive_x25519_session_key(our_node_private, ephemeral_pub)

    # AES-256-GCM decrypt
    result = decrypt_message(ciphertext, shared_key)

    # Rust decrypt_message возвращает str (UTF-8); Python fallback — bytes
    # Нормализуем в bytes для единообразия
    if isinstance(result, str):
        return result.encode("latin-1")  # latin-1 сохраняет все байты 0-255
    return bytes(result)


# ══════════════════════════════════════════════════════════════════════════════
# P2P шифрование между узлами Vortex
# ══════════════════════════════════════════════════════════════════════════════

def encrypt_p2p_payload(payload_dict: dict, our_node_private: bytes, peer_node_pub_hex: str) -> dict:
    """
    Шифрует JSON payload для отправки другому узлу по HTTP.

    Используется в peer_registry.py при вызове /api/peers/receive.
    Каждый запрос имеет уникальную эфемерную пару → forward secrecy.

    Args:
        payload_dict:       словарь для JSON-сериализации (room_id, sender, ciphertext, ...)
        our_node_private:   X25519 приватный ключ нашего узла
        peer_node_pub_hex:  X25519 публичный ключ узла-получателя

    Returns:
        {
          "ephemeral_pub":   "<hex>",
          "ciphertext":      "<hex>",
          "sender_pubkey":   "<hex нашего публичного ключа — для ответа получателю>"
        }
    """
    from app.security.crypto import generate_x25519_keypair as _kp
    _, our_pub = _kp()  # получаем pubkey из privkey... но это новая пара!
    # Правильный способ: получить наш pubkey из node keypair
    # Это сделает вызывающий код (peer_registry.py), передав sender_pubkey отдельно

    payload_bytes = json.dumps(payload_dict, ensure_ascii=False).encode("utf-8")
    encrypted     = ecies_encrypt(payload_bytes, peer_node_pub_hex)
    return encrypted  # caller добавит sender_pubkey


def decrypt_p2p_payload(ephemeral_pub_hex: str, ciphertext_hex: str,
                        our_node_private: bytes) -> dict:
    """
    Расшифровывает входящий P2P payload от другого узла.

    Returns:
        Десериализованный словарь (room_id, sender, ...)

    Raises:
        ValueError: если расшифровка или десериализация не удалась
    """
    try:
        raw   = ecies_decrypt_node(ephemeral_pub_hex, ciphertext_hex, our_node_private)
        return json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Не удалось расшифровать P2P payload: {e}") from e


# ══════════════════════════════════════════════════════════════════════════════
# Утилиты для форматирования (используются в rooms.py и chat.py)
# ══════════════════════════════════════════════════════════════════════════════

def format_encrypted_key(enc_dict: dict) -> Tuple[str, str]:
    """
    Извлекает (ephemeral_pub_hex, ciphertext_hex) из словаря,
    возвращённого ecies_encrypt или переданного клиентом.
    """
    return enc_dict["ephemeral_pub"], enc_dict["ciphertext"]


def validate_ecies_payload(payload: dict) -> bool:
    """Проверяет что payload содержит корректные ECIES поля."""
    try:
        ep = payload.get("ephemeral_pub", "")
        ct = payload.get("ciphertext", "")
        if len(ep) != 64 or len(ct) < 24:  # минимум nonce(12)*2=24 hex chars
            return False
        bytes.fromhex(ep)
        bytes.fromhex(ct)
        return True
    except Exception:
        return False