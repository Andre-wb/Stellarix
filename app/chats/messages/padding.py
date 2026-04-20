"""Metadata length padding for encrypted payloads.

Applied to every outbound ciphertext so a passive observer can't
distinguish a 5-byte ACK from a 500-byte file reference. Bucket sizes
are log-spaced to minimize per-bucket traffic-analysis leakage.

Format of a padded buffer (before encryption):

    [ u16 BE plaintext_len ] [ plaintext_bytes ] [ random_padding ]
    └─ 2 bytes ─────────── ─┘ ─────── plaintext_len ─────┘ ──── bucket-len ─┘

On the way back, the u16 prefix tells us how many bytes are real.

Rust implementation (`vortex_chat.pad_to_bucket`) does the crypto-
quality random fill in ~2 µs; pure Python version here is 20-40 µs. At
10K msg/s this is ~300 ms/s CPU recovered.

Controlled by Config.METADATA_PADDING — when disabled we return the
plaintext verbatim (no prefix) so legacy deploys stay compatible.
"""
from __future__ import annotations

import logging
import os
import struct
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import vortex_chat as _vc_rust
    _HAS_RUST_PAD = (hasattr(_vc_rust, "pad_to_bucket")
                     and hasattr(_vc_rust, "unpad_from_bucket"))
except ImportError:
    _HAS_RUST_PAD = False


BUCKETS = (64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536)


def _enabled() -> bool:
    # Lazy import to avoid app-boot circular dependency.
    try:
        from app.config import Config
        return bool(getattr(Config, "METADATA_PADDING", True))
    except Exception:
        return os.getenv("METADATA_PADDING", "true").lower() in ("1", "true", "yes")


def pad(plaintext: bytes) -> bytes:
    """Return a bucket-sized buffer with length prefix + random fill."""
    if not _enabled():
        return plaintext
    if _HAS_RUST_PAD:
        try:
            return _vc_rust.pad_to_bucket(plaintext)
        except Exception as e:
            logger.debug("rust pad_to_bucket failed, Python fallback: %s", e)
    # Pure-Python fallback
    n = len(plaintext)
    if n > 65534:
        raise ValueError("plaintext exceeds 64 KiB padding limit")
    needed = n + 2
    bucket = next((b for b in BUCKETS if b >= needed), 65536)
    return (
        struct.pack(">H", n)
        + plaintext
        + os.urandom(bucket - n - 2)
    )


def unpad(padded: bytes) -> bytes:
    """Strip the length prefix + padding, return original plaintext."""
    if not _enabled():
        return padded
    if _HAS_RUST_PAD:
        try:
            return _vc_rust.unpad_from_bucket(padded)
        except Exception as e:
            logger.debug("rust unpad_from_bucket failed, Python fallback: %s", e)
    if len(padded) < 2:
        raise ValueError("padded buffer too short")
    (n,) = struct.unpack(">H", padded[:2])
    if 2 + n > len(padded):
        raise ValueError("declared plaintext length exceeds buffer")
    return padded[2 : 2 + n]


def bucket_for(plaintext_len: int) -> int:
    """Expose bucket calculation for analytics / UI."""
    if _HAS_RUST_PAD:
        try:
            return _vc_rust.pad_bucket_for(plaintext_len)
        except Exception:
            pass
    needed = plaintext_len + 2
    return next((b for b in BUCKETS if b >= needed), 65536)
