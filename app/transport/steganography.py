"""
app/transport/steganography.py — Стеганографический транспорт.

Прячет зашифрованные сообщения внутри изображений (PNG, JPEG, WebP, BMP).
Для DPI трафик выглядит как просмотр фотогалереи.

Метод: Spread-spectrum LSB с HMAC-маркером.

Поддерживаемые форматы:
  - PNG: лучший формат (lossless, сохраняет LSB)
  - WebP lossless: сохраняет LSB, современный формат
  - BMP: lossless, без сжатия
  - JPEG: принимается на входе (конвертируется в lossless для вывода)
  - TIFF: принимается на входе

Защита от стегоанализа (Chi-squared, RS analysis):
  1. Все LSB заполнены случайными битами — нет границы «данные → нули».
  2. Маркер — HMAC-SHA256(key, nonce) вместо статической магии «VX01».
  3. Биты данных распределены по изображению через PRNG seed (не последовательно).
  4. Заголовок зашифрован (XOR с HMAC-потоком), нет plaintext length field.
  5. Сохраняется статистическое распределение LSB ≈ 50/50.

Вместимость:
  - 640×480   → ~115 КБ скрытых данных
  - 1920×1080 → ~777 КБ скрытых данных

Протокол:
  1. Клиент шифрует сообщение (AES-GCM как обычно)
  2. Клиент прячет ciphertext в изображение (spread-spectrum)
  3. POST /api/files/upload → выглядит как загрузка фото
  4. Получатель скачивает «фото»
  5. Извлекает скрытое сообщение, зная shared key
"""
from __future__ import annotations

import hashlib
import hmac
import io
import logging
import os
import struct
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

try:
    import vortex_chat as _vc_rust
    _HAS_RUST_STEG = (hasattr(_vc_rust, "steg_embed_png")
                      and hasattr(_vc_rust, "steg_extract_png"))
except ImportError:
    _HAS_RUST_STEG = False


# ── Shared key for spread-spectrum PRNG ──────────────────────────────────────
# In production: derive from room E2E key.  Fallback: env or random per-process.
_STEG_KEY = os.environ.get("STEG_KEY", "").encode() or os.urandom(32)

# Legacy magic for backward-compatible extraction
_LEGACY_MAGIC = b"VX01"


def can_use_steganography() -> bool:
    """Проверяет доступность PIL для стеганографии."""
    return _PIL_AVAILABLE


# ══════════════════════════════════════════════════════════════════════════════
# Cover image generation
# ══════════════════════════════════════════════════════════════════════════════

# Supported lossless output formats (preserve LSBs)
LOSSLESS_FORMATS = {"PNG", "WEBP", "BMP"}


def _save_lossless(img: "Image.Image", fmt: str = "PNG") -> bytes:
    """Save image in a lossless format that preserves LSB values."""
    buf = io.BytesIO()
    fmt = fmt.upper()
    if fmt == "WEBP":
        img.save(buf, format="WEBP", lossless=True)
    elif fmt == "BMP":
        img.save(buf, format="BMP")
    else:
        img.save(buf, format="PNG")
    return buf.getvalue()


def generate_cover_image(
    width: int = 640, height: int = 480, fmt: str = "PNG",
) -> bytes:
    """
    Генерирует реалистичное изображение-контейнер.
    Все LSB уже рандомизированы — одинаковый statistical profile с/без данных.

    fmt: "PNG" (default), "WEBP", "BMP".
    """
    if not _PIL_AVAILABLE:
        raise RuntimeError("PIL is not available for steganography")

    import random
    img = Image.new("RGB", (width, height))
    pixels = img.load()

    # Базовый градиент + Gaussian-like шум
    for y in range(height):
        for x in range(width):
            base_r = int(40 + 60 * (x / width))
            base_g = int(50 + 40 * (y / height))
            base_b = int(60 + 30 * ((x + y) / (width + height)))
            noise = random.randint(-20, 20)
            r = max(0, min(255, base_r + noise))
            g = max(0, min(255, base_g + noise))
            b = max(0, min(255, base_b + noise))

            # Pre-randomize all LSBs (cover looks same as stego under analysis)
            rnd = os.urandom(1)[0]
            r = (r & 0xFE) | (rnd & 1)
            g = (g & 0xFE) | ((rnd >> 1) & 1)
            b = (b & 0xFE) | ((rnd >> 2) & 1)
            pixels[x, y] = (r, g, b)

    return _save_lossless(img, fmt)


# ══════════════════════════════════════════════════════════════════════════════
# Spread-spectrum helpers
# ══════════════════════════════════════════════════════════════════════════════

def _derive_stream(key: bytes, nonce: bytes, length: int) -> bytes:
    """
    Derive a deterministic pseudo-random byte stream via HMAC-SHA256 counter mode.
    Used for: marker, position permutation, XOR mask.
    """
    out = bytearray()
    ctr = 0
    while len(out) < length:
        block = hmac.new(key, nonce + struct.pack(">I", ctr), hashlib.sha256).digest()
        out.extend(block)
        ctr += 1
    return bytes(out[:length])


def _permuted_indices(key: bytes, nonce: bytes, total: int, count: int) -> list[int]:
    """
    Generate a pseudo-random permutation of `count` unique indices in [0, total).
    Fisher-Yates shuffle seeded by HMAC stream.
    Spreads data bits across the entire image — defeats sequential-scan steganalysis.
    """
    stream = _derive_stream(key, nonce + b"idx", count * 4)
    indices = list(range(total))

    # Partial Fisher-Yates (only first `count` elements)
    for i in range(min(count, total - 1)):
        j_bytes = stream[i * 4:(i + 1) * 4]
        j = i + (int.from_bytes(j_bytes, "big") % (total - i))
        indices[i], indices[j] = indices[j], indices[i]

    return indices[:count]


# ══════════════════════════════════════════════════════════════════════════════
# Embed
# ══════════════════════════════════════════════════════════════════════════════

def embed_data(
    image_bytes: bytes, data: bytes,
    key: bytes | None = None, output_format: str = "PNG",
) -> bytes:
    """
    Прячет данные в изображении — spread-spectrum LSB.

    Принимает любой формат изображения (PNG, JPEG, WebP, BMP, TIFF).
    Выводит в lossless формате (PNG, WebP lossless, BMP) для сохранения LSB.

    Rust реализация даёт ~30× speedup на 1MP изображении (200 мс → 6 мс).
    Python fallback сохраняется для отладки и систем без wheel.
    """
    key = key or _STEG_KEY

    # Rust fast path — bit-compatible со spread-spectrum форматом.
    if _HAS_RUST_STEG and output_format.upper() == "PNG":
        try:
            return _vc_rust.steg_embed_png(image_bytes, data, key)
        except Exception as e:
            logger.debug("rust steg embed failed, falling back to Python: %s", e)

    if not _PIL_AVAILABLE:
        raise RuntimeError("PIL is not available")

    img = Image.open(io.BytesIO(image_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")

    width, height = img.size
    total_bits = width * height * 3
    max_data = total_bits // 8 - 36  # -16 nonce -16 marker -4 length

    if len(data) > max_data:
        raise ValueError(f"Data ({len(data)}B) does not fit in image ({max_data}B max)")

    # ── Build payload ────────────────────────────────────────────────────
    nonce = os.urandom(16)
    marker = hmac.new(key, nonce + b"marker", hashlib.sha256).digest()[:16]
    length_bytes = struct.pack(">I", len(data))

    # Phase 2 payload: marker + length + data  (XOR-masked)
    phase2_raw = marker + length_bytes + data
    xor_mask = _derive_stream(key, nonce + b"xor", len(phase2_raw))
    phase2_masked = bytes(a ^ b for a, b in zip(phase2_raw, xor_mask))

    # ── Convert to bits ──────────────────────────────────────────────────
    def to_bits(data_bytes: bytes) -> list[int]:
        bits = []
        for byte in data_bytes:
            for i in range(7, -1, -1):
                bits.append((byte >> i) & 1)
        return bits

    nonce_bits = to_bits(nonce)        # 128 bits
    phase2_bits = to_bits(phase2_masked)  # (20 + data_len) * 8 bits

    # ── Randomize ALL LSBs first (statistical cover) ─────────────────────
    flat = []
    pixels = img.load()
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            flat.extend([(x, y, 0, r), (x, y, 1, g), (x, y, 2, b)])

    random_bytes = os.urandom((total_bits + 7) // 8)
    for idx in range(total_bits):
        x, y, ch, val = flat[idx]
        rbit = (random_bytes[idx // 8] >> (7 - idx % 8)) & 1
        flat[idx] = (x, y, ch, (val & 0xFE) | rbit)

    # ── Phase 1: Write nonce at fixed-seed positions ─────────────────────
    nonce_perm = _permuted_indices(key, b"\x00" * 16, total_bits, 128)
    used_positions = set(nonce_perm)
    for i, bit in enumerate(nonce_bits):
        pos = nonce_perm[i]
        x, y, ch, val = flat[pos]
        flat[pos] = (x, y, ch, (val & 0xFE) | bit)

    # ── Phase 2: Write rest at nonce-seeded positions (excluding nonce slots)
    available = [i for i in range(total_bits) if i not in used_positions]
    phase2_perm = _permuted_indices(key, nonce, len(available), len(phase2_bits))
    for i, bit in enumerate(phase2_bits):
        real_pos = available[phase2_perm[i]]
        x, y, ch, val = flat[real_pos]
        flat[real_pos] = (x, y, ch, (val & 0xFE) | bit)

    # ── Write back to image ──────────────────────────────────────────────
    for x, y, ch, val in flat:
        px = list(pixels[x, y])
        px[ch] = val
        pixels[x, y] = tuple(px)

    return _save_lossless(img, output_format)


# ══════════════════════════════════════════════════════════════════════════════
# Extract
# ══════════════════════════════════════════════════════════════════════════════

def extract_data(image_bytes: bytes, key: bytes | None = None) -> Optional[bytes]:
    """
    Извлекает скрытые данные из изображения (PNG, WebP, BMP, JPEG*, TIFF).

    *JPEG: данные могут быть утеряны из-за lossy сжатия. Используйте lossless
    форматы для надёжного хранения.

    Возвращает None если данных нет или ключ неверный.

    Двухфазная схема:
      Phase 1: Читаем nonce с фиксированных позиций (key + zeros).
      Phase 2: Читаем marker + length + data с позиций (key + nonce).

    Поддерживает backward compatibility с legacy VX01 формат.
    """
    key = key or _STEG_KEY

    # Rust fast path — returns None if marker doesn't verify (wrong key
    # or no payload), bytes if extracted successfully. Same semantics as
    # the Python version below.
    if _HAS_RUST_STEG:
        try:
            out = _vc_rust.steg_extract_png(image_bytes, key)
            # Only trust Rust if it returned bytes — if it returned None we
            # try Python in case this is a legacy VX01-format image.
            if out is not None:
                return out
        except Exception as e:
            logger.debug("rust steg extract failed, trying Python: %s", e)

    if not _PIL_AVAILABLE:
        return None

    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")

        pixels = img.load()
        width, height = img.size
        total_bits = width * height * 3

        # ── Extract ALL LSBs ─────────────────────────────────────────────
        all_lsb = []
        for y in range(height):
            for x in range(width):
                r, g, b = pixels[x, y]
                all_lsb.append(r & 1)
                all_lsb.append(g & 1)
                all_lsb.append(b & 1)

        # ── Phase 1: Read nonce from fixed-seed positions ────────────────
        nonce_perm = _permuted_indices(key, b"\x00" * 16, total_bits, 128)
        nonce_bits = [all_lsb[p] for p in nonce_perm]
        nonce = _bits_to_bytes(nonce_bits)

        # ── Phase 2: Read marker + length from nonce-seeded positions ────
        used_positions = set(nonce_perm)
        available = [i for i in range(total_bits) if i not in used_positions]

        # Read header: 16B marker + 4B length = 20 bytes = 160 bits
        header_bit_count = 160
        if header_bit_count > len(available):
            return _extract_legacy(all_lsb)

        header_perm = _permuted_indices(key, nonce, len(available), header_bit_count)
        header_bits = [all_lsb[available[header_perm[i]]] for i in range(header_bit_count)]
        header_masked = _bits_to_bytes(header_bits)

        # Unmask
        xor_mask = _derive_stream(key, nonce + b"xor", 20)
        header_raw = bytes(a ^ b for a, b in zip(header_masked, xor_mask))

        # Verify marker
        expected_marker = hmac.new(key, nonce + b"marker", hashlib.sha256).digest()[:16]
        actual_marker = header_raw[:16]
        if not hmac.compare_digest(expected_marker, actual_marker):
            return _extract_legacy(all_lsb)

        data_len = struct.unpack(">I", header_raw[16:20])[0]
        total_phase2_bits = (20 + data_len) * 8
        if total_phase2_bits > len(available):
            return None

        # Read full phase2 payload
        full_perm = _permuted_indices(key, nonce, len(available), total_phase2_bits)
        full_bits = [all_lsb[available[full_perm[i]]] for i in range(total_phase2_bits)]
        full_masked = _bits_to_bytes(full_bits)

        # Unmask all
        full_xor = _derive_stream(key, nonce + b"xor", len(full_masked))
        full_raw = bytes(a ^ b for a, b in zip(full_masked, full_xor))

        return full_raw[20:20 + data_len]

    except Exception as e:
        logger.debug(f"Steg extract error: {e}")
        return None


def _extract_legacy(all_lsb: list[int]) -> Optional[bytes]:
    """Backward-compatible extraction for legacy VX01 sequential LSB format."""
    if len(all_lsb) < 64:
        return None
    header = _bits_to_bytes(all_lsb[:64])
    if header[:4] != _LEGACY_MAGIC:
        return None
    data_len = struct.unpack(">I", header[4:8])[0]
    needed = (8 + data_len) * 8
    if needed > len(all_lsb):
        return None
    all_bytes = _bits_to_bytes(all_lsb[:needed + 8])
    return all_bytes[8:8 + data_len]


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _bits_to_bytes(bits: list[int]) -> bytes:
    """Конвертирует список бит в байты."""
    result = bytearray()
    for i in range(0, len(bits) - 7, 8):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | bits[i + j]
        result.append(byte)
    return bytes(result)
