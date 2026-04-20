"""
app/security/sealed_sender.py — Sealed Sender: per-room pseudonyms for social-graph protection.

Problem: messages.sender_id stored as a plain FK on users.id — anyone who reads
the DB can reconstruct who communicates with whom (social graph).

Solution: instead of broadcasting sender_id to clients, compute a per-room
sender pseudonym using a server-side BLAKE2b keyed hash.

Properties:
  • No FK exposed to clients — relay layer never sends users.id
  • Per-room: one user has a different pseudonym in each room → cross-room
    correlation is impossible for clients/passive observers
  • One-way without the server secret: BLAKE2b keyed hash cannot be
    inverted without SEALED_SENDER_SECRET
  • Deterministic: the same (room_id, user_id) pair always yields the
    same pseudo in a single server deployment
  • Audited resolution: resolve_pseudo() emits a structured audit log entry
    and is rate-limited — bulk social-graph reconstruction is detectable

Algorithm:
  BLAKE2b(
      data   = room_id_bytes(8, big-endian) || user_id_bytes(8, big-endian),
      key    = SEALED_SENDER_SECRET  (32 bytes),
      digest = 32 bytes,
  ).hex()  →  64-char lowercase hex string

Secret derivation (priority):
  1. env SEALED_SENDER_SECRET — explicit 64-char hex (32 bytes)
     For production: load from HashiCorp Vault / AWS Secrets Manager / HSM
     so the secret is never on the same disk as the DB.
     Example (Vault):
       export SEALED_SENDER_SECRET=$(vault kv get -field=value secret/vortex/sealed_sender)
  2. env SECRET_KEY — stretched with BLAKE2b + personalization tag
  3. os.urandom(32) — per-process ephemeral (warns, safe for dev only)

Threat model:
  • DB dump only  → pseudos are unresolvable (no secret)
  • Server + DB   → operator can resolve via resolve_pseudo(); every call is
                    logged to the audit log; rate-limiting prevents bulk attack
  • Full compromise + secret → social graph recoverable (use HSM to mitigate)
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import logging
import os
import threading
import time
import warnings


_SECRET: bytes | None = None
_audit_logger = logging.getLogger("vortex.sealed_sender.audit")

# ── Resolution rate-limiter ──────────────────────────────────────────────────
# Prevents an attacker (or compromised admin account) from bulk-resolving
# the entire social graph in a single burst.
#
# Config (env):
#   SEALED_SENDER_RESOLVE_LIMIT  — max resolutions per window  (default: 100)
#   SEALED_SENDER_RESOLVE_WINDOW — window size in seconds       (default: 60)
#
_RESOLVE_LIMIT  = int(os.environ.get("SEALED_SENDER_RESOLVE_LIMIT",  "100"))
_RESOLVE_WINDOW = int(os.environ.get("SEALED_SENDER_RESOLVE_WINDOW", "60"))
_resolve_counter: list[float] = []   # timestamps of recent resolve calls
_resolve_lock = threading.Lock()


def _check_resolve_rate() -> bool:
    """Return True if the call is within rate limit, False if exceeded."""
    now = time.monotonic()
    with _resolve_lock:
        # Drop timestamps outside the window
        cutoff = now - _RESOLVE_WINDOW
        while _resolve_counter and _resolve_counter[0] < cutoff:
            _resolve_counter.pop(0)
        if len(_resolve_counter) >= _RESOLVE_LIMIT:
            return False
        _resolve_counter.append(now)
    return True


# ── Secret loading ────────────────────────────────────────────────────────────

def _get_secret() -> bytes:
    global _SECRET
    if _SECRET is None:
        raw = os.environ.get("SEALED_SENDER_SECRET", "")
        if len(raw) >= 64:
            try:
                _SECRET = bytes.fromhex(raw[:64])
            except ValueError:
                pass
        if _SECRET is None:
            sk = os.environ.get("SECRET_KEY", "")
            if sk:
                _SECRET = hashlib.blake2b(
                    sk.encode(),
                    digest_size=32,
                    person=b"sealedsndr\x00\x00\x00\x00\x00\x00",
                ).digest()
            else:
                # Auto-generate and persist to .env
                from app.config import _auto_secret
                generated = _auto_secret("SEALED_SENDER_SECRET")
                try:
                    _SECRET = bytes.fromhex(generated[:64])
                except ValueError:
                    _SECRET = os.urandom(32)
    return _SECRET


# ── Core functions ────────────────────────────────────────────────────────────

try:
    import vortex_chat as _vc_rust
    _HAS_RUST_PSEUDO = hasattr(_vc_rust, "compute_sender_pseudo")
except ImportError:
    _HAS_RUST_PSEUDO = False


def compute_sender_pseudo(room_id: int, user_id: int) -> str:
    """
    Compute a per-room pseudonym for user_id.

    Same (room_id, user_id) → same pseudo within a deployment. Different
    rooms yield unrelated pseudonyms. Returns 64-char lowercase hex.

    Hot path — called for every outgoing message. Prefers Rust
    (blake2 crate, ~1 µs) with a Python fallback that preserves byte-
    for-byte output.
    """
    key = _get_secret()
    if _HAS_RUST_PSEUDO:
        return _vc_rust.compute_sender_pseudo(key, room_id, user_id)
    data = room_id.to_bytes(8, "big") + user_id.to_bytes(8, "big")
    return hashlib.blake2b(data, key=key, digest_size=32).digest().hex()


def verify_sender_pseudo(room_id: int, user_id: int, pseudo: str) -> bool:
    """
    Verify that *pseudo* matches (room_id, user_id).
    Uses constant-time comparison to prevent timing attacks.
    """
    try:
        expected = compute_sender_pseudo(room_id, user_id)
        return _hmac.compare_digest(expected, pseudo.lower())
    except Exception:
        return False


def resolve_pseudo(
    room_id: int,
    candidate_ids: list[int],
    pseudo: str,
    *,
    caller: str = "unknown",
) -> int | None:
    """
    Resolve sender_pseudo → user_id by checking all room members.

    Used server-side for moderation and panic-wipe.

    Every call is written to the audit log (vortex.sealed_sender.audit).
    Rate-limited to SEALED_SENDER_RESOLVE_LIMIT calls per
    SEALED_SENDER_RESOLVE_WINDOW seconds — bulk social-graph reconstruction
    is detectable and throttled.

    Args:
        room_id:       The room the pseudo belongs to.
        candidate_ids: Member user_ids to check (bounded search space).
        pseudo:        The sender_pseudo value to resolve.
        caller:        Free-form label for the audit log (e.g. "moderation",
                       "panic_wipe", "admin:{admin_id}").

    Returns: matching user_id, or None if not found / rate-limited.
    """
    if not _check_resolve_rate():
        _audit_logger.warning(
            "resolve_pseudo RATE_LIMITED room_id=%s pseudo=%s… caller=%s",
            room_id, pseudo[:8], caller,
        )
        return None

    result = None
    for uid in candidate_ids:
        if verify_sender_pseudo(room_id, uid, pseudo):
            result = uid
            break

    _audit_logger.info(
        "resolve_pseudo room_id=%s pseudo=%s… caller=%s resolved=%s",
        room_id, pseudo[:8], caller, result,
    )
    return result
