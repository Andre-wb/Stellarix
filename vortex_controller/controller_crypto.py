"""Ed25519 signing for the controller and for node-supplied registrations.

Two sides:
    - Controller keypair: signs outbound responses (entries, node list).
      Loaded from CONTROLLER_KEYS_DIR, generated on first run.
    - Node verification: nodes sign their registration/heartbeat with their
      own ed25519 key; we verify that signature to prove pubkey ownership.

Payload canonicalization is JSON with sort_keys=True and separators=(",",":").
Both sides MUST use this form to produce identical bytes.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.exceptions import InvalidSignature


# ── Canonical JSON encoding ─────────────────────────────────────────────────

try:
    import vortex_chat as _vc_rust
    _HAS_RUST_CJSON = hasattr(_vc_rust, "canonical_json")
except ImportError:
    _HAS_RUST_CJSON = False


def canonical_json(data: Any) -> bytes:
    """Deterministic JSON bytes for signing.

    Must match the node side byte-for-byte — otherwise signatures won't
    verify. Rust path (~3 µs) preferred on controllers under load;
    Python fallback preserved for deploys without the compiled wheel.
    """
    if _HAS_RUST_CJSON:
        return _vc_rust.canonical_json(data)
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


# ── Controller keypair (persistent) ─────────────────────────────────────────

class ControllerKey:
    """Controller's persistent Ed25519 keypair."""

    def __init__(self, priv: Ed25519PrivateKey):
        self._priv = priv

    @classmethod
    def load_or_create(cls, keys_dir: Path) -> "ControllerKey":
        keys_dir.mkdir(parents=True, exist_ok=True)
        key_path = keys_dir / "controller.key"
        if key_path.exists():
            raw = key_path.read_bytes()
            priv = Ed25519PrivateKey.from_private_bytes(raw)
            return cls(priv)

        priv = Ed25519PrivateKey.generate()
        raw = priv.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_path.write_bytes(raw)
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
        return cls(priv)

    def pubkey_hex(self) -> str:
        pub = self._priv.public_key()
        raw = pub.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return raw.hex()

    def sign(self, payload: Any) -> str:
        """Sign canonical JSON of payload; return hex signature."""
        data = canonical_json(payload)
        sig = self._priv.sign(data)
        return sig.hex()

    def sign_bytes(self, data: bytes) -> str:
        return self._priv.sign(data).hex()


# ── Verification helpers ────────────────────────────────────────────────────

def verify_signature(pubkey_hex: str, signature_hex: str, payload: Any) -> bool:
    """Verify a signature over canonical JSON of payload.

    Hot path — called on every registration, heartbeat, backup, and
    federation envelope. Prefers Rust ed25519-dalek (~30 µs/verify) over
    cryptography's PyOpenSSL path (~300 µs/verify).
    """
    try:
        pub_bytes = bytes.fromhex(pubkey_hex)
        sig_bytes = bytes.fromhex(signature_hex)
    except ValueError:
        return False
    if _HAS_RUST_CJSON and hasattr(_vc_rust, "verify_signature"):
        try:
            return bool(_vc_rust.verify_signature(pub_bytes, canonical_json(payload), sig_bytes))
        except Exception:
            return False
    try:
        pub = Ed25519PublicKey.from_public_bytes(pub_bytes)
        pub.verify(sig_bytes, canonical_json(payload))
        return True
    except (ValueError, InvalidSignature):
        return False


def sign_response(controller_key: ControllerKey, data: Any) -> dict:
    """Wrap `data` in a signed envelope.

    Client reads `payload` + `signature`, verifies with pinned controller pubkey.
    """
    return {
        "payload": data,
        "signature": controller_key.sign(data),
        "signed_by": controller_key.pubkey_hex(),
    }


# ── Utility: base64 helpers for misc use ────────────────────────────────────

def b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)
