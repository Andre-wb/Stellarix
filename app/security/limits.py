"""Tiered feature limits (free vs Vortex Premium).

Single source of truth for every numeric limit the app enforces. Endpoints
call ``get_limits_for_user(user)`` (async) and read the field they care
about — they never hard-code ``max_file_mb`` or ``max_big_groups``.

Premium is determined by asking ``premium_check.premium_checker`` for the
user's ``wallet_pubkey`` (a column on User). If the user hasn't linked a
wallet, free-tier limits apply.

Kept in sync with the pricing published on ``vortex_controller/web/`` —
any change here should be mirrored there for user expectations to match.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TierLimits:
    """Immutable snapshot of what a user is allowed to do right now."""

    is_premium: bool

    # Storage / bandwidth
    max_file_mb:             int
    saved_gb:                float   # "Saved Messages" quota (0 = unlimited)

    # Groups and channels
    big_group_threshold:     int     # member count at which a group becomes "big"
    max_big_groups:          int     # groups with > threshold members; 0 = unlimited
    max_channels:            int     # 0 = unlimited

    # Messaging dynamics
    max_scheduled_messages:  int
    max_sticker_packs:       int
    messages_per_minute:     int
    api_requests_per_minute: int

    # Media quality / cover traffic
    max_group_call_size:     int
    max_video_resolution:    str     # "720p" | "1080p"
    cover_traffic_multiplier: float  # Free=1.0, Premium=2.0

    # Economics (operator who is also premium)
    rewards_multiplier:      float   # 1.0 free, 1.2 premium

    # Cosmetic
    animated_avatar:         bool
    premium_badge:           bool

    # Gifting
    can_gift_premium:        bool

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__annotations__.keys()}


# ── Plan tables ───────────────────────────────────────────────────────────

FREE = TierLimits(
    is_premium=False,
    max_file_mb=200,
    saved_gb=0.0,                    # node-decides; no explicit app cap
    big_group_threshold=100,
    max_big_groups=10,
    max_channels=10,
    max_scheduled_messages=3,
    max_sticker_packs=5,
    messages_per_minute=30,
    api_requests_per_minute=600,
    max_group_call_size=4,
    max_video_resolution="720p",
    cover_traffic_multiplier=1.0,
    rewards_multiplier=1.0,
    animated_avatar=False,
    premium_badge=False,
    can_gift_premium=False,
)

PREMIUM = TierLimits(
    is_premium=True,
    max_file_mb=2048,                # 2 GB
    saved_gb=0.0,                    # unlimited (node decides)
    big_group_threshold=100,
    max_big_groups=0,                # unlimited
    max_channels=0,                  # unlimited
    max_scheduled_messages=100,
    max_sticker_packs=100,
    messages_per_minute=300,
    api_requests_per_minute=3000,
    max_group_call_size=50,
    max_video_resolution="1080p",
    cover_traffic_multiplier=2.0,
    rewards_multiplier=1.2,
    animated_avatar=True,
    premium_badge=True,
    can_gift_premium=True,
)


# ── Resolution API ────────────────────────────────────────────────────────


async def get_limits_for_wallet(wallet_pubkey: str) -> TierLimits:
    """Look up on-chain subscription and return the matching tier.

    Never raises — if the RPC is down or the wallet isn't linked, returns
    FREE. The caller doesn't need to guard.
    """
    if not wallet_pubkey:
        return FREE
    try:
        from app.security.premium_check import premium_checker
        status = await premium_checker.get_status(wallet_pubkey)
        return PREMIUM if status.is_premium else FREE
    except Exception as e:
        logger.warning("limits lookup failed for %s: %s — defaulting to FREE",
                       wallet_pubkey, e)
        return FREE


async def get_limits_for_user(user: Any) -> TierLimits:
    """Same as ``get_limits_for_wallet`` but takes a User model instance.

    Reads ``user.wallet_pubkey`` — the optional column that carries the
    linked Solana address. Users who haven't linked a wallet stay on FREE.
    """
    wallet = getattr(user, "wallet_pubkey", "") or ""
    return await get_limits_for_wallet(wallet)


# ── Synchronous snapshot for middleware that can't await ─────────────────


def peek_limits_for_wallet(wallet_pubkey: str) -> TierLimits:
    """Non-blocking best-effort: return cached tier, else FREE.

    Middleware on the hot path (rate limiter) can't do a fresh RPC on
    every request — this helper consults the cache synchronously and
    falls back to FREE when unknown. Accuracy is eventually-consistent
    via the 5-min cache refresh on regular ``get_limits_for_user`` calls.
    """
    if not wallet_pubkey:
        return FREE
    try:
        from app.security.premium_check import premium_checker
        cached = premium_checker._cache.get(wallet_pubkey)  # noqa: SLF001
        if cached and cached.is_premium:
            return PREMIUM
    except Exception:
        pass
    return FREE
