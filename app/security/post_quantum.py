"""
Post-Quantum Hybrid Key Exchange — X25519 + Kyber-768 (ML-KEM).

Hybrid approach: combine classical X25519 with post-quantum Kyber-768.
If either algorithm is broken, the other still protects.

Signal uses PQXDH (X25519 + Kyber-768) since September 2023.
iMessage uses PQ3 (X25519 + Kyber-768) since March 2024.
Vortex uses the same hybrid approach.

Key encapsulation flow:
  1. Sender generates X25519 ephemeral pair + Kyber-768 encapsulation
  2. shared_secret = HKDF(X25519_shared || Kyber_shared, info="vortex-pq-session")
  3. Encrypt room key with AES-256-GCM(shared_secret)
  4. Send: {x25519_ephemeral_pub, kyber_ciphertext, aes_ciphertext}

Decapsulation (client-side):
  1. x25519_shared = DH(user_priv, x25519_ephemeral_pub)
  2. kyber_shared = Kyber.Decaps(kyber_sk, kyber_ciphertext)
  3. shared_secret = HKDF(x25519_shared || kyber_shared, info="vortex-pq-session")
  4. room_key = AES-256-GCM-Decrypt(aes_ciphertext, shared_secret)

Performance:
  - Kyber-768 keygen: ~0.03ms
  - Kyber-768 encaps: ~0.05ms
  - Kyber-768 decaps: ~0.07ms
  - Total overhead vs X25519-only: +0.07ms (imperceptible)

Sizes:
  - Kyber-768 public key: 1184 bytes
  - Kyber-768 ciphertext: 1088 bytes
  - Kyber-768 shared secret: 32 bytes
  - Total overhead per key exchange: ~2.3 KB (negligible for messaging)
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ── Try to import kyber from available libraries ─────────────────────────────
_PQ_AVAILABLE = False
_PQ_BACKEND = "none"
_PQ_SIMULATED = False

# Simulation is only allowed when explicitly opted-in (dev/testing only).
# NEVER set VORTEX_PQ_SIMULATE=1 in production — simulation provides NO
# post-quantum security whatsoever (it is SHAKE-256, not Kyber).
_env = os.environ.get("ENVIRONMENT", "development").lower()
_is_prod = (
    _env in ("production", "prod")
    or os.environ.get("IS_PROD", "").lower() in ("1", "true", "yes")
    or os.environ.get("IS_PRODUCTION", "").lower() in ("1", "true", "yes")
)
_SIMULATION_ALLOWED = (
    os.environ.get("VORTEX_PQ_SIMULATE", "").lower() in ("1", "true", "yes")
    and not _is_prod
)
if _is_prod and os.environ.get("VORTEX_PQ_SIMULATE", "").lower() in ("1", "true", "yes"):
    import sys
    print(
        "FATAL: VORTEX_PQ_SIMULATE=1 is set in production environment. "
        "This disables real post-quantum security. Refusing to start.",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    # Primary: liboqs-python — Open Quantum Safe, includes ML-KEM / Kyber-768
    # Ships pre-compiled wheels for Linux/macOS/Windows (pip install liboqs-python)
    import warnings as _warnings
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore", UserWarning)
        import oqs  # noqa: F401
    # Verify oqs is actually functional (shared lib loaded)
    _test_kem = oqs.KeyEncapsulation("Kyber768")
    del _test_kem
    _PQ_AVAILABLE = True
    _PQ_BACKEND = "liboqs"
    logger.info("Post-quantum: liboqs (Kyber-768 / ML-KEM) loaded")
except BaseException as _oqs_err:
    logger.debug("liboqs not usable: %s", _oqs_err)
    try:
        # Fallback: pqcrypto (pip install pqcrypto)
        from pqcrypto.kem.kyber768 import generate_keypair as _kyber_keygen  # noqa: F401
        from pqcrypto.kem.kyber768 import encrypt as _kyber_encaps  # noqa: F401
        from pqcrypto.kem.kyber768 import decrypt as _kyber_decaps  # noqa: F401
        _PQ_AVAILABLE = True
        _PQ_BACKEND = "pqcrypto"
        logger.info("Post-quantum: pqcrypto (Kyber-768) loaded")
    except ImportError:
        # No real PQ library found.
        # _PQ_AVAILABLE stays False — every PQ call will raise RuntimeError
        # unless VORTEX_PQ_SIMULATE=1 is explicitly set (testing only).
        _PQ_SIMULATED = True
        if _SIMULATION_ALLOWED:
            _PQ_AVAILABLE = True   # allow API to function (testing only)
            _PQ_BACKEND = "simulated"
            import platform as _platform
            _system = _platform.system()
            if _system == "Darwin":
                _install = "brew install liboqs && pip install --force-reinstall liboqs-python"
            elif _system == "Linux":
                # Debian/Ubuntu name differs from Arch/Fedora — show the
                # common one first, mention alternatives.
                _install = (
                    "sudo apt install liboqs-dev  (Ubuntu/Debian) "
                    "|  sudo pacman -S liboqs  (Arch) "
                    "|  then: pip install --force-reinstall liboqs-python"
                )
            elif _system == "Windows":
                _install = (
                    "pip install pqcrypto  "
                    "(Windows has no prebuilt liboqs — use the pqcrypto fallback)"
                )
            else:
                _install = "pip install pqcrypto"
            logger.warning(
                "⚠ Post-quantum SIMULATION MODE active. "
                "This is NOT cryptographically secure — SHAKE-256 is not Kyber. "
                "Fix: %s",
                _install,
            )
        else:
            _PQ_BACKEND = "unavailable"
            logger.critical(
                "Post-quantum library not found and VORTEX_PQ_SIMULATE is not set. "
                "Install the required library: pip install liboqs-python\n"
                "All post-quantum operations will raise RuntimeError until fixed.\n"
                "To allow insecure simulation in tests: set VORTEX_PQ_SIMULATE=1"
            )


def _require_real_pq() -> None:
    """Raise if no real PQ backend is available and simulation is not opted-in."""
    if not _PQ_AVAILABLE:
        raise RuntimeError(
            "No post-quantum library available. "
            "Install liboqs-python: pip install liboqs-python\n"
            "To allow simulation in tests (insecure): set VORTEX_PQ_SIMULATE=1"
        )
    if _PQ_BACKEND == "simulated":
        # Called only when VORTEX_PQ_SIMULATE=1 — warn on every operation
        logger.warning("PQ operation running in SIMULATION mode — not real Kyber-768")


def pq_available() -> bool:
    """Check if post-quantum key exchange is available."""
    return _PQ_AVAILABLE


def pq_backend() -> str:
    """Return which PQ backend is active."""
    return _PQ_BACKEND


# ══════════════════════════════════════════════════════════════════════════════
# Kyber-768 abstraction (works with any backend)
# ══════════════════════════════════════════════════════════════════════════════

class Kyber768:
    """Abstraction over Kyber-768 KEM (Key Encapsulation Mechanism)."""

    @staticmethod
    def keygen() -> Tuple[bytes, bytes]:
        """Generate Kyber-768 keypair.

        Returns:
            (public_key, secret_key) — pk is 1184 bytes, sk is 2400 bytes
        """
        _require_real_pq()

        if _PQ_BACKEND == "liboqs":
            import oqs
            kem = oqs.KeyEncapsulation("Kyber768")
            pk = kem.generate_keypair()
            sk = kem.export_secret_key()
            return bytes(pk), bytes(sk)

        elif _PQ_BACKEND == "pqcrypto":
            from pqcrypto.kem.kyber768 import generate_keypair
            pk, sk = generate_keypair()
            return bytes(pk), bytes(sk)

        else:
            # SIMULATION — only reachable when VORTEX_PQ_SIMULATE=1
            seed = os.urandom(32)
            pk = seed + hashlib.shake_256(b"kyber-pk-" + seed).digest(1184 - 32)
            sk = seed + hashlib.shake_256(b"kyber-sk-" + seed).digest(2400 - 32)
            return pk, sk

    @staticmethod
    def encapsulate(public_key: bytes) -> Tuple[bytes, bytes]:
        """Encapsulate: generate shared secret + ciphertext from public key.

        Args:
            public_key: Kyber-768 public key (1184 bytes)

        Returns:
            (ciphertext, shared_secret) — ct is 1088 bytes, ss is 32 bytes
        """
        _require_real_pq()

        if _PQ_BACKEND == "liboqs":
            import oqs
            kem = oqs.KeyEncapsulation("Kyber768")
            ct, ss = kem.encap_secret(public_key)
            return bytes(ct), bytes(ss)

        elif _PQ_BACKEND == "pqcrypto":
            from pqcrypto.kem.kyber768 import encrypt
            ct, ss = encrypt(public_key)
            return bytes(ct), bytes(ss)

        else:
            # SIMULATION — only reachable when VORTEX_PQ_SIMULATE=1
            random_seed = os.urandom(32)
            pk_seed = public_key[:32]
            ss = hashlib.shake_256(b"kyber-ss-" + random_seed + pk_seed).digest(32)
            ct_body = hashlib.shake_256(b"kyber-ct-" + random_seed).digest(1088 - 32)
            ct = random_seed + ct_body
            return ct, ss

    @staticmethod
    def decapsulate(secret_key: bytes, ciphertext: bytes) -> bytes:
        """Decapsulate: recover shared secret from ciphertext + secret key.

        Args:
            secret_key: Kyber-768 secret key (2400 bytes)
            ciphertext: Kyber-768 ciphertext (1088 bytes)

        Returns:
            shared_secret (32 bytes)
        """
        _require_real_pq()

        if _PQ_BACKEND == "liboqs":
            import oqs
            kem = oqs.KeyEncapsulation("Kyber768", secret_key=secret_key)
            ss = kem.decap_secret(ciphertext)
            return bytes(ss)

        elif _PQ_BACKEND == "pqcrypto":
            from pqcrypto.kem.kyber768 import decrypt
            ss = decrypt(secret_key, ciphertext)
            return bytes(ss)

        else:
            # SIMULATION — only reachable when VORTEX_PQ_SIMULATE=1
            random_seed = ciphertext[:32]
            pk_seed = secret_key[:32]
            ss = hashlib.shake_256(b"kyber-ss-" + random_seed + pk_seed).digest(32)
            return ss


# ══════════════════════════════════════════════════════════════════════════════
# Hybrid X25519 + Kyber-768 Key Exchange
# ══════════════════════════════════════════════════════════════════════════════

def hybrid_keygen() -> dict:
    """Generate hybrid X25519 + Kyber-768 keypair.

    Returns:
        {
            "x25519_private": bytes(32),
            "x25519_public": bytes(32),
            "kyber_public": bytes(1184),
            "kyber_secret": bytes(2400),
        }
    """
    from app.security.crypto import generate_x25519_keypair
    x_priv, x_pub = generate_x25519_keypair()
    k_pub, k_sk = Kyber768.keygen()

    return {
        "x25519_private": x_priv,
        "x25519_public": x_pub,
        "kyber_public": k_pub,
        "kyber_secret": k_sk,
    }


def hybrid_encapsulate(recipient_x25519_pub: bytes, recipient_kyber_pub: bytes) -> dict:
    """Hybrid encapsulation: X25519 ECIES + Kyber-768 KEM.

    Combines both shared secrets via HKDF for maximum security.
    If X25519 is broken by quantum → Kyber protects.
    If Kyber has a flaw → X25519 protects.

    Args:
        recipient_x25519_pub: X25519 public key (32 bytes)
        recipient_kyber_pub: Kyber-768 public key (1184 bytes)

    Returns:
        {
            "x25519_ephemeral_pub": hex(32 bytes),
            "kyber_ciphertext": hex(1088 bytes),
            "shared_secret": bytes(32),  ← combined key for AES-256-GCM
        }
    """
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    from app.security.crypto import generate_x25519_keypair, derive_x25519_session_key

    # Classical: X25519 ephemeral DH
    eph_priv, eph_pub = generate_x25519_keypair()
    x25519_shared = derive_x25519_session_key(eph_priv, recipient_x25519_pub)

    # Post-quantum: Kyber-768 KEM
    kyber_ct, kyber_shared = Kyber768.encapsulate(recipient_kyber_pub)

    # Combine both shared secrets via HKDF
    combined = x25519_shared + kyber_shared  # 32 + 32 = 64 bytes
    hybrid_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"vortex-pq-session-v1",
    ).derive(combined)

    return {
        "x25519_ephemeral_pub": eph_pub.hex(),
        "kyber_ciphertext": kyber_ct.hex(),
        "shared_secret": hybrid_key,
    }


def hybrid_decapsulate(
    our_x25519_private: bytes,
    our_kyber_secret: bytes,
    x25519_ephemeral_pub_hex: str,
    kyber_ciphertext_hex: str,
) -> bytes:
    """Hybrid decapsulation: recover shared secret from both key exchanges.

    Args:
        our_x25519_private: Our X25519 private key (32 bytes)
        our_kyber_secret: Our Kyber-768 secret key (2400 bytes)
        x25519_ephemeral_pub_hex: Sender's ephemeral X25519 public key (hex)
        kyber_ciphertext_hex: Kyber-768 ciphertext (hex)

    Returns:
        shared_secret (32 bytes) — same as sender computed
    """
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    from app.security.crypto import derive_x25519_session_key

    eph_pub = bytes.fromhex(x25519_ephemeral_pub_hex)
    kyber_ct = bytes.fromhex(kyber_ciphertext_hex)

    # Classical: X25519 DH
    x25519_shared = derive_x25519_session_key(our_x25519_private, eph_pub)

    # Post-quantum: Kyber-768 decapsulation
    kyber_shared = Kyber768.decapsulate(our_kyber_secret, kyber_ct)

    # Combine via HKDF (same as encapsulation)
    combined = x25519_shared + kyber_shared
    hybrid_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"vortex-pq-session-v1",
    ).derive(combined)

    return hybrid_key


def hybrid_encrypt(plaintext: bytes, recipient_x25519_pub_hex: str,
                   recipient_kyber_pub_hex: str) -> dict:
    """Encrypt plaintext using hybrid X25519 + Kyber-768.

    This is the top-level function for post-quantum ECIES encryption.

    Args:
        plaintext: Data to encrypt (e.g., room key)
        recipient_x25519_pub_hex: X25519 public key (64 hex chars)
        recipient_kyber_pub_hex: Kyber-768 public key (hex)

    Returns:
        {
            "x25519_ephemeral_pub": hex,
            "kyber_ciphertext": hex,
            "ciphertext": hex,  ← AES-256-GCM encrypted plaintext
            "hybrid": True,
        }
    """
    from app.security.crypto import encrypt_message

    x_pub = bytes.fromhex(recipient_x25519_pub_hex)
    k_pub = bytes.fromhex(recipient_kyber_pub_hex)

    result = hybrid_encapsulate(x_pub, k_pub)
    shared_key = result["shared_secret"]

    # AES-256-GCM encrypt with hybrid key
    ct = encrypt_message(plaintext, shared_key)

    return {
        "x25519_ephemeral_pub": result["x25519_ephemeral_pub"],
        "kyber_ciphertext": result["kyber_ciphertext"],
        "ciphertext": ct.hex(),
        "hybrid": True,
    }


def hybrid_decrypt(our_x25519_private: bytes, our_kyber_secret: bytes,
                   encrypted: dict) -> bytes:
    """Decrypt data encrypted with hybrid_encrypt.

    Args:
        our_x25519_private: X25519 private key (32 bytes)
        our_kyber_secret: Kyber-768 secret key
        encrypted: Dict from hybrid_encrypt

    Returns:
        Decrypted plaintext bytes
    """
    from app.security.crypto import decrypt_message

    shared_key = hybrid_decapsulate(
        our_x25519_private,
        our_kyber_secret,
        encrypted["x25519_ephemeral_pub"],
        encrypted["kyber_ciphertext"],
    )

    ct = bytes.fromhex(encrypted["ciphertext"])
    return decrypt_message(ct, shared_key)


def get_pq_status() -> dict:
    """Return post-quantum subsystem status.

    The 'secure' field is the authoritative signal: only True when a real
    cryptographic library (liboqs or pqcrypto) is active.
    """
    secure = _PQ_AVAILABLE and _PQ_BACKEND not in ("simulated", "unavailable", "none")
    return {
        "available": _PQ_AVAILABLE,
        "secure": secure,
        "backend": _PQ_BACKEND,
        "simulated": _PQ_SIMULATED,
        "algorithm": "Kyber-768 (ML-KEM)" if secure else "SHAKE-256 simulation (NOT Kyber)",
        "hybrid": "X25519 + Kyber-768",
        "warning": (
            None if secure else
            "SIMULATION MODE — no real post-quantum protection. "
            "Install liboqs-python: pip install liboqs-python"
        ),
        "key_sizes": {
            "kyber_public_key": "1184 bytes",
            "kyber_ciphertext": "1088 bytes",
            "kyber_shared_secret": "32 bytes",
            "x25519_public_key": "32 bytes",
            "combined_shared_secret": "32 bytes (HKDF)",
        },
        "security_level": (
            "NIST Level 3 (equivalent to AES-192)" if secure else "NONE (simulation)"
        ),
        "performance": {
            "keygen": "~0.03ms",
            "encaps": "~0.05ms",
            "decaps": "~0.07ms",
            "total_overhead": "~0.12ms vs X25519-only",
        },
    }
