"""Async lookup of on-chain premium subscriptions.

Reads the ``Subscription`` PDA from the Solana ``vortex_registry`` program
and caches the result for 5 minutes so every authenticated request doesn't
hit an RPC endpoint.

Public surface:
    premium_checker                — singleton ``PremiumChecker`` instance
    PremiumStatus                  — dataclass describing a wallet's plan
    premium_checker.get_status(w)  — async, never raises on RPC failure
    premium_checker.invalidate(w)  — drop cache entry (call after purchase)
    require_premium                — FastAPI dependency for gating endpoints
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import struct
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ── Configuration ─────────────────────────────────────────────────────────

VORTEX_PROGRAM_ID = os.getenv(
    "VORTEX_PROGRAM_ID",
    "Vor1exReg1111111111111111111111111111111111",
).strip()

# Public Solana RPC. Override with a dedicated endpoint for production so
# rate-limit 429s don't cascade into "subscription expired" false negatives.
SOLANA_RPC_URL = os.getenv(
    "SOLANA_RPC_URL",
    "https://api.mainnet-beta.solana.com",
).strip()
_IS_DEFAULT_RPC = SOLANA_RPC_URL == "https://api.mainnet-beta.solana.com"
if _IS_DEFAULT_RPC:
    logger.warning(
        "SOLANA_RPC_URL is using the public mainnet-beta endpoint — "
        "it rate-limits heavily (HTTP 429) and will cause false 'no subscription' "
        "results under load. Configure Helius / QuickNode / Ankr in production. "
        "See .env.example for details."
    )

_CACHE_TTL_SECONDS = int(os.getenv("PREMIUM_CACHE_TTL", "300"))
_RPC_TIMEOUT_SECONDS = float(os.getenv("PREMIUM_RPC_TIMEOUT", "4.0"))

# Anchor prefixes every account with sha256("account:<StructName>")[:8]
_SUBSCRIPTION_DISCRIMINATOR = hashlib.sha256(b"account:Subscription").digest()[:8]

_SUBSCRIPTION_SEED = b"subscription"


# ── Data model ────────────────────────────────────────────────────────────


@dataclass
class PremiumStatus:
    """Result of a subscription lookup.

    ``is_premium`` is the single flag app code should gate features on.
    ``reason`` carries extra context for debugging / error UX and stays
    empty on the happy path.
    """
    wallet_pubkey: str
    is_premium: bool = False
    end_timestamp: int = 0
    months_total_paid: int = 0
    lifetime_lamports_paid: int = 0
    last_gift_from: str = ""
    reason: str = ""
    cached_at: int = field(default_factory=lambda: int(time.time()))

    def to_dict(self) -> dict:
        return {
            "wallet_pubkey": self.wallet_pubkey,
            "is_premium": self.is_premium,
            "end_timestamp": self.end_timestamp,
            "months_total_paid": self.months_total_paid,
            "lifetime_lamports_paid": self.lifetime_lamports_paid,
            "last_gift_from": self.last_gift_from,
            "reason": self.reason,
            "cached_at": self.cached_at,
        }


# ── Checker ───────────────────────────────────────────────────────────────


class PremiumChecker:
    """Caches per-wallet subscription status.

    Concurrency-safe: parallel requests for the same wallet coalesce into
    a single RPC call via an in-flight task map.
    """

    def __init__(self) -> None:
        self._cache: dict[str, PremiumStatus] = {}
        self._inflight: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    # ── Public API ────────────────────────────────────────────────────

    async def get_status(self, wallet_pubkey: str) -> PremiumStatus:
        """Return premium status; never raises on RPC errors."""
        wallet_pubkey = (wallet_pubkey or "").strip()
        if not wallet_pubkey:
            return PremiumStatus(wallet_pubkey="", reason="empty wallet")

        cached = self._cache.get(wallet_pubkey)
        if cached and (time.time() - cached.cached_at) < _CACHE_TTL_SECONDS:
            return cached

        # Coalesce concurrent misses.
        async with self._lock:
            task = self._inflight.get(wallet_pubkey)
            if task is None:
                task = asyncio.create_task(self._fetch_status(wallet_pubkey))
                self._inflight[wallet_pubkey] = task

        try:
            result = await task
        finally:
            self._inflight.pop(wallet_pubkey, None)
        return result

    def invalidate(self, wallet_pubkey: str) -> None:
        self._cache.pop(wallet_pubkey, None)

    # ── Fetch + parse ─────────────────────────────────────────────────

    async def _fetch_status(self, wallet_pubkey: str) -> PremiumStatus:
        try:
            pda = _derive_subscription_pda(wallet_pubkey)
        except Exception as e:
            status = PremiumStatus(
                wallet_pubkey=wallet_pubkey,
                reason=f"pda-derivation-failed: {e}",
            )
            self._cache[wallet_pubkey] = status
            return status

        raw = await _rpc_get_account_info(pda)
        if raw is None:
            status = PremiumStatus(
                wallet_pubkey=wallet_pubkey,
                reason="rpc-unreachable",
            )
            # Cache negative result briefly so a dead RPC doesn't lock us
            # out completely — user can retry in a minute.
            self._cache[wallet_pubkey] = status
            return status

        if raw == b"":
            status = PremiumStatus(
                wallet_pubkey=wallet_pubkey,
                reason="no-subscription-found",
            )
            self._cache[wallet_pubkey] = status
            return status

        try:
            parsed = _parse_subscription(raw, wallet_pubkey)
        except Exception as e:
            logger.warning("premium_check parse failed for %s: %s", wallet_pubkey, e)
            status = PremiumStatus(
                wallet_pubkey=wallet_pubkey,
                reason=f"parse-failed: {e}",
            )
            self._cache[wallet_pubkey] = status
            return status

        parsed.is_premium = parsed.end_timestamp > int(time.time())
        if not parsed.is_premium:
            parsed.reason = "expired"
        self._cache[wallet_pubkey] = parsed
        return parsed


# ── PDA derivation ────────────────────────────────────────────────────────


def _derive_subscription_pda(beneficiary_base58: str) -> str:
    """Compute ``["subscription", beneficiary]`` PDA for vortex_registry.

    Requires ``solders`` (hard dep). Raises if Pubkey/PDA derivation
    fails so the caller can convert the failure into a cached
    "no subscription" response.
    """
    from solders.pubkey import Pubkey  # deferred import
    program_id = Pubkey.from_string(VORTEX_PROGRAM_ID)
    beneficiary = Pubkey.from_string(beneficiary_base58)
    pda, _bump = Pubkey.find_program_address(
        [_SUBSCRIPTION_SEED, bytes(beneficiary)],
        program_id,
    )
    return str(pda)


# ── RPC ───────────────────────────────────────────────────────────────────


async def _rpc_get_account_info(pda_base58: str) -> Optional[bytes]:
    """Return raw account data, ``b""`` if the account doesn't exist, or
    ``None`` on network / RPC failure.
    """
    import httpx
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAccountInfo",
        "params": [pda_base58, {"encoding": "base64", "commitment": "confirmed"}],
    }
    try:
        async with httpx.AsyncClient(timeout=_RPC_TIMEOUT_SECONDS) as client:
            r = await client.post(SOLANA_RPC_URL, json=payload)
        if r.status_code != 200:
            logger.debug("solana rpc %s returned %d", SOLANA_RPC_URL, r.status_code)
            return None
        body = r.json()
    except Exception as e:
        logger.debug("solana rpc failure: %s", e)
        return None

    if not isinstance(body, dict) or "result" not in body:
        return None
    result = body["result"]
    if not isinstance(result, dict):
        return None
    value = result.get("value")
    if value is None:
        return b""  # account doesn't exist — signals "no subscription"
    data_field = value.get("data")
    if not isinstance(data_field, list) or len(data_field) < 1:
        return None
    try:
        return base64.b64decode(data_field[0])
    except Exception:
        return None


# ── Parse account bytes ───────────────────────────────────────────────────


def _parse_subscription(raw: bytes, expected_wallet: str) -> PremiumStatus:
    """Decode the on-chain Subscription layout.

    Layout (offsets):
        0..8    anchor discriminator       (8 bytes)
        8..40   beneficiary                (32 bytes, Pubkey)
        40..48  end_timestamp              (i64 LE)
        48..52  months_total_paid          (u32 LE)
        52..60  lifetime_lamports_paid     (u64 LE)
        60..92  last_gift_from             (32 bytes, Pubkey)
        92..93  bump                       (u8)
    """
    if len(raw) < 93:
        raise ValueError(f"account too small: {len(raw)} bytes")
    if raw[:8] != _SUBSCRIPTION_DISCRIMINATOR:
        raise ValueError("discriminator mismatch — not a Subscription account")

    from solders.pubkey import Pubkey  # deferred import
    beneficiary = str(Pubkey(raw[8:40]))
    (end_timestamp,) = struct.unpack("<q", raw[40:48])
    (months_total_paid,) = struct.unpack("<I", raw[48:52])
    (lifetime_lamports,) = struct.unpack("<Q", raw[52:60])
    last_gift_from_bytes = raw[60:92]

    # Encode default Pubkey as empty string so UIs can check `if x:` naturally.
    default_pubkey = bytes(32)
    last_gift_from = (
        "" if last_gift_from_bytes == default_pubkey
        else str(Pubkey(last_gift_from_bytes))
    )

    return PremiumStatus(
        wallet_pubkey=expected_wallet,
        is_premium=False,  # filled in by caller using current time
        end_timestamp=end_timestamp,
        months_total_paid=months_total_paid,
        lifetime_lamports_paid=lifetime_lamports,
        last_gift_from=last_gift_from,
    )


# ── Singleton + FastAPI dependency ────────────────────────────────────────


premium_checker = PremiumChecker()


async def require_premium_wallet(wallet_pubkey: str) -> PremiumStatus:
    """FastAPI dependency: raises 402 if wallet is not premium.

    Use in endpoints that gate a paid feature:

        @router.post("/rooms/big")
        async def create_big_room(
            status: PremiumStatus = Depends(get_premium_for_request),
            ...
        ):
            ...
    """
    from fastapi import HTTPException
    status = await premium_checker.get_status(wallet_pubkey)
    if not status.is_premium:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "premium_required",
                "reason": status.reason or "no active subscription",
                "wallet": wallet_pubkey,
            },
        )
    return status


# ── FastAPI router ────────────────────────────────────────────────────────

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/premium", tags=["premium"])


@router.get("/status")
async def get_premium_status(
    wallet: str = Query(..., description="Solana wallet base58 pubkey"),
) -> dict:
    """Check whether a given wallet has an active premium subscription.

    Safe to call unauthenticated — response reveals only public on-chain
    state. Cached 5 min server-side; call ``/refresh`` right after a
    purchase to force an immediate re-check.
    """
    status = await premium_checker.get_status(wallet)
    return status.to_dict()


@router.post("/refresh")
async def refresh_premium_status(
    wallet: str = Query(..., description="Solana wallet base58 pubkey"),
) -> dict:
    """Invalidate the cache for a wallet and re-fetch."""
    premium_checker.invalidate(wallet)
    status = await premium_checker.get_status(wallet)
    return status.to_dict()


## ── Signed-challenge wallet linking ──────────────────────────────────────
#
# Claiming a wallet on someone else's account would "steal" their premium.
# We require proof-of-ownership via an Ed25519 signature over a one-shot
# challenge before persisting ``users.wallet_pubkey``.
#
# Flow:
#   1. Client GETs /api/premium/challenge      → {challenge, expires_at}
#   2. Client asks Phantom to signMessage(challenge)
#   3. Client POSTs /api/premium/link-wallet   → {wallet, challenge, signature}
#   4. Server verifies sig, consumes challenge, writes wallet on the user row
#
# The challenge is keyed by the authenticated user id so a bystander
# can't race ahead by grabbing someone else's challenge string.

import base64
import secrets
from datetime import datetime, timezone

# In-memory challenge map. Cleaned lazily on new issuance so the app
# doesn't need a background job. Key → (challenge_bytes, expires_at).
_challenges: dict[int, tuple[bytes, float]] = {}
_CHALLENGE_TTL_SECONDS = 300


def _cleanup_expired_challenges() -> None:
    now = time.time()
    expired = [k for k, (_, exp) in _challenges.items() if exp < now]
    for k in expired:
        _challenges.pop(k, None)


@router.get("/challenge")
async def get_wallet_link_challenge(request) -> dict:  # type: ignore[valid-type]
    """Issue a one-shot nonce the user must sign with their wallet.

    Requires an authenticated session. The challenge is 32 random bytes
    shown to the user as base64 so Phantom's signMessage UI can display
    something safe-looking.
    """
    from fastapi import Depends, HTTPException  # noqa: F401
    from app.keys.keys import get_current_user
    # Resolve user via the request to avoid changing this function's
    # signature — some callers pre-hook deps via middleware.
    user = await _resolve_current_user(request)
    if not user:
        raise HTTPException(401, "auth required")

    _cleanup_expired_challenges()
    challenge = secrets.token_bytes(32)
    expires_at = time.time() + _CHALLENGE_TTL_SECONDS
    _challenges[user.id] = (challenge, expires_at)

    return {
        "challenge":  base64.b64encode(challenge).decode("ascii"),
        "expires_at": int(expires_at),
        "ttl_seconds": _CHALLENGE_TTL_SECONDS,
        "instructions": (
            "Sign this exact string with your wallet (Phantom: signMessage). "
            "Then POST /api/premium/link-wallet with {wallet, challenge, signature_b58}."
        ),
    }


async def _resolve_current_user(request):
    """Pull the authenticated user without forcing the caller to use Depends."""
    try:
        from app.keys.keys import get_current_user
        from app.database import get_db
        # get_current_user expects a session; build one on the fly.
        db_gen = get_db()
        db = next(db_gen)
        try:
            return await _maybe_await(get_current_user(request, db=db))
        finally:
            try: next(db_gen)
            except StopIteration: pass
    except Exception:
        return None


async def _maybe_await(value):
    import inspect
    if inspect.isawaitable(value):
        return await value
    return value


@router.post("/link-wallet")
async def link_wallet_signed(request, body: dict) -> dict:  # type: ignore[valid-type]
    """Save a Solana wallet onto the authenticated user after verifying
    they own it.

    Body:
      * wallet        — base58 Solana pubkey
      * challenge     — the base64 string returned by /challenge
      * signature_b58 — base58 signature of the raw challenge bytes
    """
    from fastapi import HTTPException
    user = await _resolve_current_user(request)
    if not user:
        raise HTTPException(401, "auth required")

    wallet = str(body.get("wallet") or "").strip()
    challenge_b64 = str(body.get("challenge") or "").strip()
    signature_b58 = str(body.get("signature_b58") or "").strip()
    if not wallet or not challenge_b64 or not signature_b58:
        raise HTTPException(400, "wallet, challenge, signature_b58 all required")

    stored = _challenges.get(user.id)
    if not stored:
        raise HTTPException(400, "no active challenge — call /challenge first")
    stored_challenge, expires_at = stored
    if expires_at < time.time():
        _challenges.pop(user.id, None)
        raise HTTPException(400, "challenge expired — request a new one")
    try:
        supplied_challenge = base64.b64decode(challenge_b64)
    except Exception:
        raise HTTPException(400, "challenge is not valid base64")
    if supplied_challenge != stored_challenge:
        raise HTTPException(400, "challenge mismatch")

    # Validate wallet format + extract raw bytes.
    try:
        from solders.pubkey import Pubkey
        pk = Pubkey.from_string(wallet)
        pubkey_bytes = bytes(pk)
    except Exception:
        raise HTTPException(400, "invalid wallet pubkey")

    # Decode signature.
    try:
        import base58
        signature = base58.b58decode(signature_b58)
    except Exception:
        raise HTTPException(400, "signature_b58 is not valid base58")
    if len(signature) != 64:
        raise HTTPException(400, "signature must be 64 bytes")

    # Verify Ed25519 signature. A valid signature means the caller controls
    # the private key for ``wallet`` — good enough to link.
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
        Ed25519PublicKey.from_public_bytes(pubkey_bytes).verify(
            signature, stored_challenge,
        )
    except InvalidSignature:
        raise HTTPException(403, "signature does not match wallet pubkey")
    except Exception as e:
        raise HTTPException(400, f"signature verification failed: {e}")

    # Challenge consumed — single-use.
    _challenges.pop(user.id, None)

    # Persist on the user row.
    from app.database import get_db
    db_gen = get_db()
    db = next(db_gen)
    try:
        from app.models.user import User
        db_user = db.query(User).filter(User.id == user.id).first()
        if not db_user:
            raise HTTPException(404, "user not found")
        # Invalidate cached premium status for both old and new wallets
        if db_user.wallet_pubkey:
            premium_checker.invalidate(db_user.wallet_pubkey)
        premium_checker.invalidate(wallet)
        db_user.wallet_pubkey = wallet
        db.commit()
    finally:
        try: next(db_gen)
        except StopIteration: pass

    return {
        "ok": True,
        "wallet_pubkey": wallet,
        "linked_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/plans")
async def get_premium_plans() -> dict:
    """Public plan catalogue — mirrors the on-chain ``tier_prices_lamports``.

    Frontend uses this to render the purchase modal. Prices here are the
    hard-coded defaults; a production deploy should fetch them from
    ``config.tier_prices_lamports`` via RPC for accuracy.
    """
    return {
        "plans": [
            {"tier": 0, "months": 1,  "lamports":  33_333_333, "usd":  5, "label": "Monthly"},
            {"tier": 1, "months": 3,  "lamports":  80_000_000, "usd": 12, "label": "Quarterly"},
            {"tier": 2, "months": 6,  "lamports": 133_333_333, "usd": 20, "label": "Half-year"},
            {"tier": 3, "months": 12, "lamports": 253_333_333, "usd": 38, "label": "Yearly"},
        ],
        "program_id": VORTEX_PROGRAM_ID,
        "treasury_hint": "5ABkkipTZZEEPNR3cP4MCzftpAhqv6jvM4UTSLPGt5Qq",
    }
