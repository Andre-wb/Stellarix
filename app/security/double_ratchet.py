"""
app/security/double_ratchet.py — Реализация протокола Double Ratchet (Signal Protocol).

Обеспечивает Perfect Forward Secrecy и Break-in Recovery для E2E шифрования
сообщений между пользователями Vortex.

Компоненты:
  1. X3DH (Extended Triple Diffie-Hellman) — начальный обмен ключами
  2. Double Ratchet — непрерывное обновление ключей шифрования
  3. KDF Chain — цепочка деривации ключей (HKDF-SHA256 + HMAC)
  4. AES-256-GCM — шифрование сообщений с аутентификацией заголовков

Ссылки:
  - Signal Specification: https://signal.org/docs/specifications/doubleratchet/
  - X3DH:                 https://signal.org/docs/specifications/x3dh/
"""
from __future__ import annotations

import hmac
import hashlib
import logging
import struct
from dataclasses import dataclass, field
from typing import Optional, Tuple

from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization

logger = logging.getLogger(__name__)

# Максимальное количество пропущенных ключей сообщений, которые мы храним.
# Защита от DoS: злоумышленник не может заставить нас хранить бесконечно
# много ключей, отправляя сообщения с огромными номерами.
MAX_SKIP = 1000

# Информационная строка для HKDF при деривации корневого и цепного ключей.
_HKDF_INFO_RATCHET = b"vortex-double-ratchet"

# Информационная строка для HKDF при X3DH.
_HKDF_INFO_X3DH = b"vortex-x3dh"

# Байт-префикс 0xFF * 32 — «F» (filler) согласно спецификации X3DH,
# добавляется перед DH-выходами для доменного разделения.
_X3DH_F = b"\xff" * 32


# ══════════════════════════════════════════════════════════════════════════════
# Вспомогательные функции для работы с ключами
# ══════════════════════════════════════════════════════════════════════════════

def _priv_to_bytes(key: X25519PrivateKey) -> bytes:
    """Сериализует X25519 приватный ключ в 32 байта (raw)."""
    return key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )


def _pub_to_bytes(key: X25519PublicKey) -> bytes:
    """Сериализует X25519 публичный ключ в 32 байта (raw)."""
    return key.public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )


def _generate_x25519_pair() -> X25519PrivateKey:
    """Генерирует новую X25519 ключевую пару. Возвращает приватный ключ."""
    return X25519PrivateKey.generate()


def _dh(private: X25519PrivateKey, public: X25519PublicKey) -> bytes:
    """Выполняет X25519 Diffie-Hellman обмен. Возвращает 32 байта shared secret."""
    return private.exchange(public)


# ══════════════════════════════════════════════════════════════════════════════
# Ed25519 подпись для Signed Pre-Key
# ══════════════════════════════════════════════════════════════════════════════

def sign_spk(identity_private: Ed25519PrivateKey, spk_public_bytes: bytes) -> bytes:
    """Подписывает публичный Signed Pre-Key идентификационным ключом Ed25519.

    Args:
        identity_private: Ed25519 приватный ключ идентификации.
        spk_public_bytes: 32 байта публичного Signed Pre-Key (X25519).

    Returns:
        64 байта подписи Ed25519.
    """
    return identity_private.sign(spk_public_bytes)


def verify_spk_signature(
    identity_public: Ed25519PublicKey,
    spk_public_bytes: bytes,
    signature: bytes,
) -> bool:
    """Проверяет подпись Signed Pre-Key.

    Args:
        identity_public:  Ed25519 публичный ключ идентификации.
        spk_public_bytes: 32 байта публичного Signed Pre-Key (X25519).
        signature:        64 байта подписи.

    Returns:
        True если подпись валидна, False иначе.
    """
    try:
        identity_public.verify(signature, spk_public_bytes)
        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# X3DH — Extended Triple Diffie-Hellman Key Agreement
# ══════════════════════════════════════════════════════════════════════════════

def x3dh_initiate(
    ik_private: X25519PrivateKey,
    ik_peer_public: X25519PublicKey,
    spk_peer_public: X25519PublicKey,
    opk_peer_public: Optional[X25519PublicKey] = None,
) -> Tuple[bytes, X25519PrivateKey]:
    """Инициирует X3DH обмен ключами (сторона Alice).

    Вычисляет shared secret из 3 или 4 DH-операций:
      DH1 = DH(IK_A, SPK_B)    — аутентифицирует Alice для Bob
      DH2 = DH(EK_A, IK_B)     — аутентифицирует Bob для Alice
      DH3 = DH(EK_A, SPK_B)    — forward secrecy
      DH4 = DH(EK_A, OPK_B)    — дополнительная forward secrecy (опционально)

    Args:
        ik_private:      X25519 приватный Identity Key Alice.
        ik_peer_public:  X25519 публичный Identity Key Bob.
        spk_peer_public: X25519 публичный Signed Pre-Key Bob.
        opk_peer_public: X25519 публичный One-Time Pre-Key Bob (может отсутствовать).

    Returns:
        Кортеж (shared_secret: 32 bytes, ephemeral_key: X25519PrivateKey).
        ephemeral_key нужен для отправки EK_A.public в первом сообщении.
    """
    ek = _generate_x25519_pair()

    dh1 = _dh(ik_private, spk_peer_public)
    dh2 = _dh(ek, ik_peer_public)
    dh3 = _dh(ek, spk_peer_public)

    km = _X3DH_F + dh1 + dh2 + dh3

    if opk_peer_public is not None:
        dh4 = _dh(ek, opk_peer_public)
        km += dh4

    shared_secret = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"\x00" * 32,
        info=_HKDF_INFO_X3DH,
    ).derive(km)

    logger.debug("X3DH initiated (with OPK: %s)", opk_peer_public is not None)
    return shared_secret, ek


def x3dh_respond(
    ik_private: X25519PrivateKey,
    spk_private: X25519PrivateKey,
    opk_private: Optional[X25519PrivateKey],
    ik_peer_public: X25519PublicKey,
    ek_peer_public: X25519PublicKey,
) -> bytes:
    """Отвечает на X3DH обмен ключами (сторона Bob).

    Зеркальные DH-операции к x3dh_initiate:
      DH1 = DH(SPK_B, IK_A)
      DH2 = DH(IK_B, EK_A)
      DH3 = DH(SPK_B, EK_A)
      DH4 = DH(OPK_B, EK_A)  — если OPK был использован

    Args:
        ik_private:      X25519 приватный Identity Key Bob.
        spk_private:     X25519 приватный Signed Pre-Key Bob.
        opk_private:     X25519 приватный One-Time Pre-Key Bob (None если не использовался).
        ik_peer_public:  X25519 публичный Identity Key Alice.
        ek_peer_public:  X25519 публичный Ephemeral Key Alice.

    Returns:
        shared_secret: 32 bytes — тот же что у Alice.
    """
    dh1 = _dh(spk_private, ik_peer_public)
    dh2 = _dh(ik_private, ek_peer_public)
    dh3 = _dh(spk_private, ek_peer_public)

    km = _X3DH_F + dh1 + dh2 + dh3

    if opk_private is not None:
        dh4 = _dh(opk_private, ek_peer_public)
        km += dh4

    shared_secret = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"\x00" * 32,
        info=_HKDF_INFO_X3DH,
    ).derive(km)

    logger.debug("X3DH responded (with OPK: %s)", opk_private is not None)
    return shared_secret


# ══════════════════════════════════════════════════════════════════════════════
# KDF Chains — деривация ключей
# ══════════════════════════════════════════════════════════════════════════════

try:
    import vortex_chat as _vc_rust
    _HAS_RUST_RATCHET = (hasattr(_vc_rust, "ratchet_kdf_rk")
                         and hasattr(_vc_rust, "ratchet_kdf_ck"))
except ImportError:
    _HAS_RUST_RATCHET = False


def kdf_rk(rk: bytes, dh_out: bytes) -> Tuple[bytes, bytes]:
    """Root Key KDF — HKDF-SHA256(salt=rk, IKM=dh_out, info="vortex-double-ratchet").

    Hot path — called on every DH ratchet step. Rust version ~3 µs vs
    ~80 µs in cryptography's pure-Python HKDF.
    """
    if _HAS_RUST_RATCHET:
        return _vc_rust.ratchet_kdf_rk(rk, dh_out)
    okm = HKDF(
        algorithm=hashes.SHA256(),
        length=64,
        salt=rk,
        info=_HKDF_INFO_RATCHET,
    ).derive(dh_out)
    return okm[:32], okm[32:]


def kdf_ck(ck: bytes) -> Tuple[bytes, bytes]:
    """Chain Key KDF — Signal-standard:
        new_chain_key = HMAC-SHA256(ck, 0x02)
        message_key   = HMAC-SHA256(ck, 0x01)

    Called once per message — the single biggest CPU hotspot after
    AES-GCM. Rust version ~1 µs vs ~40 µs in Python stdlib.
    """
    if _HAS_RUST_RATCHET:
        return _vc_rust.ratchet_kdf_ck(ck)
    new_ck = hmac.new(ck, b"\x02", hashlib.sha256).digest()
    mk = hmac.new(ck, b"\x01", hashlib.sha256).digest()
    return new_ck, mk


# ══════════════════════════════════════════════════════════════════════════════
# Заголовок сообщения
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Header:
    """Заголовок Double Ratchet сообщения.

    Передаётся открыто (не шифруется), но используется как AAD при шифровании
    тела сообщения, что гарантирует его целостность.

    Attributes:
        dh_public:  текущий ratchet публичный ключ отправителя (32 байта).
        prev_count: количество сообщений в предыдущей цепочке отправки.
        msg_number: номер сообщения в текущей цепочке отправки.
    """
    dh_public: bytes     # 32 bytes — текущий ratchet публичный ключ
    prev_count: int      # количество сообщений в предыдущей цепочке
    msg_number: int      # номер сообщения в текущей цепочке

    def serialize(self) -> bytes:
        """Сериализует заголовок в байты для использования как AAD.

        Формат: dh_public (32) + prev_count (4, big-endian) + msg_number (4, big-endian)
        Итого: 40 байт.
        """
        return self.dh_public + struct.pack(">II", self.prev_count, self.msg_number)

    @classmethod
    def deserialize(cls, data: bytes) -> "Header":
        """Десериализует заголовок из байт.

        Args:
            data: 40 байт сериализованного заголовка.

        Returns:
            Экземпляр Header.

        Raises:
            ValueError: если длина данных не равна 40.
        """
        if len(data) != 40:
            raise ValueError(f"Header must be 40 bytes, got {len(data)}")
        dh_pub = data[:32]
        prev_count, msg_number = struct.unpack(">II", data[32:40])
        return cls(dh_public=dh_pub, prev_count=prev_count, msg_number=msg_number)


# ══════════════════════════════════════════════════════════════════════════════
# Состояние Double Ratchet
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class RatchetState:
    """Полное состояние Double Ratchet сессии одной стороны.

    Хранится на клиенте. Сервер НИКОГДА не имеет доступа к этому состоянию.

    Attributes:
        dh_sending:          наш текущий ratchet приватный ключ X25519.
        dh_receiving:        публичный ratchet ключ собеседника (None до получения первого сообщения).
        root_key:            корневой ключ (32 байта) — обновляется при каждом DH ratchet шаге.
        sending_chain_key:   ключ цепочки отправки (32 байта).
        receiving_chain_key: ключ цепочки получения (32 байта).
        send_count:          номер следующего отправляемого сообщения в текущей цепочке.
        recv_count:          номер следующего ожидаемого сообщения в текущей цепочке получения.
        prev_send_count:     количество сообщений в предыдущей цепочке отправки.
        skipped_keys:        кэш ключей для пропущенных (out-of-order) сообщений.
                             Ключ: (ratchet_pub_bytes, msg_number) → message_key.
    """
    dh_sending: X25519PrivateKey
    dh_receiving: Optional[X25519PublicKey]
    root_key: bytes                          # 32 bytes
    sending_chain_key: Optional[bytes]       # 32 bytes
    receiving_chain_key: Optional[bytes]     # 32 bytes
    send_count: int = 0
    recv_count: int = 0
    prev_send_count: int = 0
    skipped_keys: dict = field(default_factory=dict)  # (bytes, int) → bytes


# ══════════════════════════════════════════════════════════════════════════════
# Инициализация Ratchet
# ══════════════════════════════════════════════════════════════════════════════

def ratchet_init_alice(shared_secret: bytes, bob_ratchet_pub: X25519PublicKey) -> RatchetState:
    """Инициализирует Double Ratchet для стороны Alice (инициатор).

    Alice выполняет первый DH ratchet шаг: вычисляет DH с Bob's ratchet public key
    и деривирует первую пару (root_key, sending_chain_key).

    Args:
        shared_secret:  32 байта из X3DH, используется как начальный root_key.
        bob_ratchet_pub: публичный ratchet ключ Bob (обычно его SPK).

    Returns:
        Инициализированное состояние RatchetState для Alice.
    """
    alice_ratchet = _generate_x25519_pair()
    dh_out = _dh(alice_ratchet, bob_ratchet_pub)
    root_key, sending_chain_key = kdf_rk(shared_secret, dh_out)

    return RatchetState(
        dh_sending=alice_ratchet,
        dh_receiving=bob_ratchet_pub,
        root_key=root_key,
        sending_chain_key=sending_chain_key,
        receiving_chain_key=None,
        send_count=0,
        recv_count=0,
        prev_send_count=0,
    )


def ratchet_init_bob(shared_secret: bytes, bob_ratchet_pair: X25519PrivateKey) -> RatchetState:
    """Инициализирует Double Ratchet для стороны Bob (ответчик).

    Bob ещё не получал сообщений от Alice, поэтому у него нет receiving key.
    DH ratchet шаг произойдёт при получении первого сообщения.

    Args:
        shared_secret:    32 байта из X3DH, используется как начальный root_key.
        bob_ratchet_pair: приватный ratchet ключ Bob (обычно его SPK private key).

    Returns:
        Инициализированное состояние RatchetState для Bob.
    """
    return RatchetState(
        dh_sending=bob_ratchet_pair,
        dh_receiving=None,
        root_key=shared_secret,
        sending_chain_key=None,
        receiving_chain_key=None,
        send_count=0,
        recv_count=0,
        prev_send_count=0,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Шифрование / Дешифрование
# ══════════════════════════════════════════════════════════════════════════════

def _encrypt_aes_gcm(message_key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    """Шифрует plaintext с помощью AES-256-GCM.

    Args:
        message_key: 32 байта — ключ шифрования.
        plaintext:   данные для шифрования.
        aad:         Additional Authenticated Data (заголовок сообщения).

    Returns:
        nonce (12 bytes) + ciphertext + tag (16 bytes).
    """
    import secrets
    nonce = secrets.token_bytes(12)
    ct = AESGCM(message_key).encrypt(nonce, plaintext, aad)
    return nonce + ct


def _decrypt_aes_gcm(message_key: bytes, data: bytes, aad: bytes) -> bytes:
    """Дешифрует данные AES-256-GCM.

    Args:
        message_key: 32 байта — ключ шифрования.
        data:        nonce (12 bytes) + ciphertext + tag (16 bytes).
        aad:         Additional Authenticated Data (заголовок сообщения).

    Returns:
        Расшифрованный plaintext.

    Raises:
        cryptography.exceptions.InvalidTag: если данные были изменены.
    """
    if len(data) < 12:
        raise ValueError("Encrypted data too short (missing nonce)")
    nonce = data[:12]
    ct = data[12:]
    return AESGCM(message_key).decrypt(nonce, ct, aad)


def ratchet_encrypt(state: RatchetState, plaintext: bytes) -> Tuple[Header, bytes]:
    """Шифрует сообщение с помощью Double Ratchet.

    Выполняет symmetric ratchet шаг (chain key → message key + next chain key),
    затем шифрует plaintext с полученным message_key.

    Args:
        state:     текущее состояние RatchetState (мутируется!).
        plaintext: данные для шифрования.

    Returns:
        Кортеж (header, ciphertext):
          - header: Header с текущим ratchet public key и счётчиками.
          - ciphertext: nonce + AES-256-GCM(plaintext) с header как AAD.

    Raises:
        RuntimeError: если sending_chain_key не инициализирован.
    """
    if state.sending_chain_key is None:
        raise RuntimeError("Sending chain key not initialized — cannot encrypt")

    # Symmetric ratchet: получаем message_key и обновляем chain_key
    state.sending_chain_key, mk = kdf_ck(state.sending_chain_key)

    # Формируем заголовок
    header = Header(
        dh_public=_pub_to_bytes(state.dh_sending.public_key()),
        prev_count=state.prev_send_count,
        msg_number=state.send_count,
    )

    state.send_count += 1

    # Шифруем с заголовком как AAD (защищает заголовок от подмены)
    ciphertext = _encrypt_aes_gcm(mk, plaintext, header.serialize())

    return header, ciphertext


def _try_skipped_keys(
    state: RatchetState,
    header: Header,
    ciphertext: bytes,
) -> Optional[bytes]:
    """Пытается расшифровать сообщение из кэша пропущенных ключей.

    Args:
        state:      текущее состояние RatchetState.
        header:     заголовок сообщения.
        ciphertext: зашифрованные данные.

    Returns:
        Расшифрованный plaintext или None если ключ не найден.
    """
    key = (header.dh_public, header.msg_number)
    if key in state.skipped_keys:
        mk = state.skipped_keys.pop(key)
        return _decrypt_aes_gcm(mk, ciphertext, header.serialize())
    return None


def _skip_message_keys(state: RatchetState, until: int) -> None:
    """Сохраняет ключи для пропущенных сообщений в текущей цепочке получения.

    Вызывается когда номер полученного сообщения больше ожидаемого —
    значит промежуточные сообщения пришли не по порядку (или будут получены позже).

    Args:
        state: текущее состояние RatchetState (мутируется).
        until: номер сообщения, до которого нужно сохранить ключи (не включительно).

    Raises:
        OverflowError: если количество пропусков превышает MAX_SKIP.
    """
    if state.receiving_chain_key is None:
        return

    if until - state.recv_count > MAX_SKIP:
        raise OverflowError(
            f"Too many skipped messages: {until - state.recv_count} "
            f"(max {MAX_SKIP}). Possible DoS attack."
        )

    dh_pub_bytes = _pub_to_bytes(state.dh_receiving) if state.dh_receiving else b""

    while state.recv_count < until:
        state.receiving_chain_key, mk = kdf_ck(state.receiving_chain_key)
        state.skipped_keys[(dh_pub_bytes, state.recv_count)] = mk
        state.recv_count += 1


def _dh_ratchet_step(state: RatchetState, header: Header) -> None:
    """Выполняет DH ratchet шаг при получении нового ratchet публичного ключа.

    Обновляет receiving chain (для дешифрования входящих сообщений)
    и sending chain (для шифрования исходящих).

    Args:
        state:  текущее состояние RatchetState (мутируется).
        header: заголовок полученного сообщения с новым ratchet public key.
    """
    state.prev_send_count = state.send_count
    state.send_count = 0
    state.recv_count = 0

    state.dh_receiving = X25519PublicKey.from_public_bytes(header.dh_public)

    # Деривируем новый receiving chain
    dh_out = _dh(state.dh_sending, state.dh_receiving)
    state.root_key, state.receiving_chain_key = kdf_rk(state.root_key, dh_out)

    # Генерируем новый ratchet key pair и деривируем sending chain
    state.dh_sending = _generate_x25519_pair()
    dh_out = _dh(state.dh_sending, state.dh_receiving)
    state.root_key, state.sending_chain_key = kdf_rk(state.root_key, dh_out)


def ratchet_decrypt(state: RatchetState, header: Header, ciphertext: bytes) -> bytes:
    """Дешифрует сообщение с помощью Double Ratchet.

    Алгоритм:
      1. Пытается найти message_key в кэше пропущенных ключей.
      2. Если ratchet public key в заголовке отличается от текущего —
         выполняет DH ratchet шаг.
      3. Пропускает ключи для пропущенных сообщений (out-of-order).
      4. Выполняет symmetric ratchet и дешифрует.

    Args:
        state:      текущее состояние RatchetState (мутируется!).
        header:     заголовок сообщения.
        ciphertext: зашифрованные данные.

    Returns:
        Расшифрованный plaintext.

    Raises:
        OverflowError: если слишком много пропущенных сообщений.
        cryptography.exceptions.InvalidTag: если данные повреждены.
    """
    # 1. Попробуем из кэша пропущенных ключей
    plaintext = _try_skipped_keys(state, header, ciphertext)
    if plaintext is not None:
        return plaintext

    # 2. Проверяем нужен ли DH ratchet шаг
    current_dh_pub = (
        _pub_to_bytes(state.dh_receiving)
        if state.dh_receiving is not None
        else None
    )

    if current_dh_pub != header.dh_public:
        # Новый ratchet public key — пропускаем оставшиеся ключи старой цепочки
        _skip_message_keys(state, header.prev_count)
        # Выполняем DH ratchet шаг
        _dh_ratchet_step(state, header)

    # 3. Пропускаем ключи до нужного номера сообщения
    _skip_message_keys(state, header.msg_number)

    # 4. Symmetric ratchet шаг
    state.receiving_chain_key, mk = kdf_ck(state.receiving_chain_key)
    state.recv_count += 1

    # 5. Дешифруем
    return _decrypt_aes_gcm(mk, ciphertext, header.serialize())


# ══════════════════════════════════════════════════════════════════════════════
# Утилиты для сериализации (хранение состояния на клиенте)
# ══════════════════════════════════════════════════════════════════════════════

def serialize_state(state: RatchetState) -> dict:
    """Сериализует RatchetState в словарь для хранения (например, в IndexedDB).

    Все байтовые значения конвертируются в hex-строки. Ключи в skipped_keys
    кодируются как строки «<pub_hex>:<msg_number>».

    Returns:
        Словарь, готовый к JSON-сериализации.
    """
    skipped = {}
    for (pub_bytes, n), mk in state.skipped_keys.items():
        key_str = f"{pub_bytes.hex()}:{n}"
        skipped[key_str] = mk.hex()

    return {
        "dh_sending": _priv_to_bytes(state.dh_sending).hex(),
        "dh_receiving": (
            _pub_to_bytes(state.dh_receiving).hex()
            if state.dh_receiving is not None
            else None
        ),
        "root_key": state.root_key.hex(),
        "sending_chain_key": (
            state.sending_chain_key.hex() if state.sending_chain_key is not None else None
        ),
        "receiving_chain_key": (
            state.receiving_chain_key.hex() if state.receiving_chain_key is not None else None
        ),
        "send_count": state.send_count,
        "recv_count": state.recv_count,
        "prev_send_count": state.prev_send_count,
        "skipped_keys": skipped,
    }


def deserialize_state(data: dict) -> RatchetState:
    """Восстанавливает RatchetState из словаря.

    Args:
        data: словарь, полученный из serialize_state.

    Returns:
        Восстановленное состояние RatchetState.
    """
    skipped = {}
    for key_str, mk_hex in data.get("skipped_keys", {}).items():
        pub_hex, n_str = key_str.rsplit(":", 1)
        skipped[(bytes.fromhex(pub_hex), int(n_str))] = bytes.fromhex(mk_hex)

    dh_recv_hex = data.get("dh_receiving")
    send_ck_hex = data.get("sending_chain_key")
    recv_ck_hex = data.get("receiving_chain_key")

    return RatchetState(
        dh_sending=X25519PrivateKey.from_private_bytes(bytes.fromhex(data["dh_sending"])),
        dh_receiving=(
            X25519PublicKey.from_public_bytes(bytes.fromhex(dh_recv_hex))
            if dh_recv_hex is not None
            else None
        ),
        root_key=bytes.fromhex(data["root_key"]),
        sending_chain_key=bytes.fromhex(send_ck_hex) if send_ck_hex is not None else None,
        receiving_chain_key=bytes.fromhex(recv_ck_hex) if recv_ck_hex is not None else None,
        send_count=data.get("send_count", 0),
        recv_count=data.get("recv_count", 0),
        prev_send_count=data.get("prev_send_count", 0),
        skipped_keys=skipped,
    )
