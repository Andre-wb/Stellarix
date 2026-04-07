"""
app/chats/channels.py — Broadcast Channels with analytics, comments, scheduling,
                          discovery, reactions, and P2P monetization.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.models_rooms import (
    ChannelDonation, ChannelMonetization, ChannelSubscription,
    Message, MessageType, PostReaction, PostView,
    Room, RoomMember, RoomRole, EncryptedRoomKey,
)
from app.peer.connection_manager import manager
from app.security.auth_jwt import get_current_user
from app.security.blockchain_verify import verify_transaction
from app.security.sealed_sender import compute_sender_pseudo
from app.utilites.utils import generative_invite_code

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/channels", tags=["channels"])


# ── Pydantic Schemas ─────────────────────────────────────────────────────────

class _EncryptedKeyPayload(BaseModel):
    ephemeral_pub: str = Field(..., min_length=64, max_length=64)
    ciphertext:    str = Field(..., min_length=24)


class CreateChannelRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=500)
    is_private: bool = False
    encrypted_room_key: _EncryptedKeyPayload | None = None

class SchedulePostRequest(BaseModel):
    content_encrypted: str
    scheduled_at: str  # ISO datetime

class SetMonetizationRequest(BaseModel):
    wallet_address: str = Field(..., min_length=10, max_length=255)
    currency: str = Field(default="USDT", pattern="^(USDT|TON|BTC|ETH)$")
    network: str = Field(default="trc20")
    price_monthly: int = Field(default=0, ge=0)
    price_display: str = Field(default="Free", max_length=50)
    is_paid: bool = False
    donations_enabled: bool = True

class DonateRequest(BaseModel):
    tx_hash: str = Field(..., max_length=255)
    amount: str = Field(..., max_length=50)  # "5 USDT"
    message: str = Field(default="", max_length=200)

class SubscribeRequest(BaseModel):
    tx_hash: str = Field(..., max_length=255)
    amount: str = Field(default="", max_length=50)

class ReactRequest(BaseModel):
    emoji: str = Field(..., max_length=10)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _channel_dict(c: Room, db: Session, user_id: int | None = None) -> dict:
    count = c.members.count()
    d = {
        "id": c.id, "name": c.name, "description": c.description,
        "is_channel": True, "is_private": c.is_private,
        "invite_code": c.invite_code, "subscriber_count": count,
        "avatar_emoji": c.avatar_emoji, "avatar_url": c.avatar_url,
        "created_at": c.created_at.isoformat() if c.created_at else "",
    }
    # Monetization info
    mon = db.query(ChannelMonetization).filter(ChannelMonetization.room_id == c.id).first()
    if mon:
        d["monetization"] = {
            "is_paid": mon.is_paid, "price_display": mon.price_display,
            "currency": mon.currency, "donations_enabled": mon.donations_enabled,
        }
    return d


# ══════════════════════════════════════════════════════════════════════════════
# CRUD
# ══════════════════════════════════════════════════════════════════════════════

@router.post("", status_code=201)
async def create_channel(body: CreateChannelRequest, u: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    channel = Room(
        name=body.name, description=body.description, creator_id=u.id,
        is_private=body.is_private, invite_code=generative_invite_code(8),
        max_members=100000, is_channel=True,
    )
    db.add(channel)
    db.flush()
    db.add(RoomMember(room_id=channel.id, user_id=u.id, role=RoomRole.OWNER))
    if body.encrypted_room_key:
        db.add(EncryptedRoomKey(
            room_id       = channel.id,
            user_id       = u.id,
            ephemeral_pub = body.encrypted_room_key.ephemeral_pub,
            ciphertext    = body.encrypted_room_key.ciphertext,
            recipient_pub = u.x25519_public_key,
        ))
    db.commit()
    db.refresh(channel)
    d = _channel_dict(channel, db, u.id)
    d["has_key"] = bool(body.encrypted_room_key)
    return d


@router.get("/my")
async def my_channels(u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(RoomMember).filter(RoomMember.user_id == u.id, RoomMember.is_banned == False).all()
    ids = [m.room_id for m in rows]
    role_map = {m.room_id: m.role for m in rows}
    channels = db.query(Room).filter(Room.id.in_(ids), Room.is_channel == True).all()
    result = []
    for c in channels:
        d = _channel_dict(c, db, u.id)
        d["is_owner"] = c.creator_id == u.id
        d["is_admin"] = role_map.get(c.id) in (RoomRole.OWNER, RoomRole.ADMIN)
        result.append(d)
    return {"channels": result}


@router.post("/join/{invite_code}")
async def join_channel(invite_code: str, u: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    channel = db.query(Room).filter(
        Room.invite_code == invite_code.upper(), Room.is_channel == True
    ).first()
    if not channel:
        raise HTTPException(404, "Channel not found")
    existing = db.query(RoomMember).filter(
        RoomMember.room_id == channel.id, RoomMember.user_id == u.id
    ).first()
    if existing:
        if existing.is_banned:
            raise HTTPException(403, "Banned from channel")
        return {"joined": False, "channel": _channel_dict(channel, db, u.id)}
    # Check paywall
    mon = db.query(ChannelMonetization).filter(
        ChannelMonetization.room_id == channel.id, ChannelMonetization.is_paid == True
    ).first()
    if mon:
        sub = db.query(ChannelSubscription).filter(
            ChannelSubscription.room_id == channel.id,
            ChannelSubscription.user_id == u.id,
            ChannelSubscription.expires_at > datetime.now(timezone.utc),
        ).first()
        if not sub:
            return {
                "joined": False,
                "requires_payment": True,
                "price": mon.price_display,
                "wallet": mon.wallet_address,
                "currency": mon.currency,
                "network": mon.network,
            }
    db.add(RoomMember(room_id=channel.id, user_id=u.id, role=RoomRole.MEMBER))
    db.commit()
    return {"joined": True, "channel": _channel_dict(channel, db, u.id)}


# ══════════════════════════════════════════════════════════════════════════════
# 1. Channel Statistics (views, forwards, growth)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/{channel_id}/stats")
async def channel_stats(channel_id: int, u: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """Analytics for channel owner/admin."""
    channel = db.query(Room).filter(Room.id == channel_id, Room.is_channel == True).first()
    if not channel:
        raise HTTPException(404, "Channel not found")
    member = db.query(RoomMember).filter(
        RoomMember.room_id == channel_id, RoomMember.user_id == u.id,
    ).first()
    if not member or member.role not in (RoomRole.OWNER, RoomRole.ADMIN):
        raise HTTPException(403, "Admin access required")

    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    total_subs = channel.members.count()
    total_posts = db.query(func.count(Message.id)).filter(Message.room_id == channel_id).scalar() or 0
    total_views = db.query(func.count(PostView.id)).filter(
        PostView.message_id.in_(
            db.query(Message.id).filter(Message.room_id == channel_id)
        )
    ).scalar() or 0

    # Growth: new members in periods
    new_day = db.query(func.count(RoomMember.id)).filter(
        RoomMember.room_id == channel_id, RoomMember.joined_at >= day_ago
    ).scalar() or 0
    new_week = db.query(func.count(RoomMember.id)).filter(
        RoomMember.room_id == channel_id, RoomMember.joined_at >= week_ago
    ).scalar() or 0
    new_month = db.query(func.count(RoomMember.id)).filter(
        RoomMember.room_id == channel_id, RoomMember.joined_at >= month_ago
    ).scalar() or 0

    # Views in last 24h
    views_today = db.query(func.count(PostView.id)).filter(
        PostView.viewed_at >= day_ago,
        PostView.message_id.in_(
            db.query(Message.id).filter(Message.room_id == channel_id)
        ),
    ).scalar() or 0

    # Reactions count
    total_reactions = db.query(func.count(PostReaction.id)).filter(
        PostReaction.message_id.in_(
            db.query(Message.id).filter(Message.room_id == channel_id)
        )
    ).scalar() or 0

    # Revenue (if monetized)
    total_donations = db.query(func.count(ChannelDonation.id)).filter(
        ChannelDonation.room_id == channel_id
    ).scalar() or 0
    active_subs = db.query(func.count(ChannelSubscription.id)).filter(
        ChannelSubscription.room_id == channel_id,
        ChannelSubscription.expires_at > now,
    ).scalar() or 0

    return {
        "subscribers": {"total": total_subs, "new_24h": new_day, "new_7d": new_week, "new_30d": new_month},
        "posts": {"total": total_posts},
        "views": {"total": total_views, "last_24h": views_today},
        "reactions": {"total": total_reactions},
        "revenue": {"donations": total_donations, "active_subscriptions": active_subs},
        "engagement_rate": round(views_today / max(total_subs, 1) * 100, 1),
    }


@router.post("/{channel_id}/posts/{message_id}/view")
async def record_view(channel_id: int, message_id: int,
                      u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Record that user viewed a post."""
    existing = db.query(PostView).filter(
        PostView.message_id == message_id, PostView.user_id == u.id
    ).first()
    if not existing:
        db.add(PostView(message_id=message_id, user_id=u.id))
        db.commit()
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# 2. Comments (linked discussion)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/{channel_id}/posts/{message_id}/comments")
async def get_comments(channel_id: int, message_id: int,
                       u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get comments on a channel post (thread replies)."""
    comments = db.query(Message).filter(
        Message.room_id == channel_id, Message.thread_id == message_id,
    ).order_by(Message.created_at).limit(200).all()
    return {"comments": [
        {"id": m.id, "sender_pseudo": m.sender_pseudo, "content_encrypted": m.content_encrypted.hex() if m.content_encrypted else "",
         "created_at": m.created_at.isoformat() if m.created_at else ""}
        for m in comments
    ], "count": len(comments)}


@router.post("/{channel_id}/posts/{message_id}/comment")
async def add_comment(channel_id: int, message_id: int,
                      u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Enable comments on a post by creating a linked thread."""
    post = db.query(Message).filter(
        Message.id == message_id, Message.room_id == channel_id
    ).first()
    if not post:
        raise HTTPException(404, "Post not found")
    return {"ok": True, "thread_id": message_id, "comments_enabled": True}


# ══════════════════════════════════════════════════════════════════════════════
# 3. Scheduled Posts
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/{channel_id}/schedule")
async def schedule_post(channel_id: int, body: SchedulePostRequest,
                        u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Schedule a post for later publication."""
    member = db.query(RoomMember).filter(
        RoomMember.room_id == channel_id, RoomMember.user_id == u.id,
    ).first()
    if not member or member.role not in (RoomRole.OWNER, RoomRole.ADMIN):
        raise HTTPException(403, "Only admins can schedule posts")
    try:
        sched_time = datetime.fromisoformat(body.scheduled_at.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, "Invalid datetime format")
    msg = Message(
        room_id=channel_id,
        sender_pseudo=compute_sender_pseudo(channel_id, u.id),
        msg_type=MessageType.TEXT,
        content_encrypted=bytes.fromhex(body.content_encrypted) if body.content_encrypted else b"",
        is_scheduled=True, scheduled_at=sched_time,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return {"ok": True, "message_id": msg.id, "scheduled_at": sched_time.isoformat()}


@router.get("/{channel_id}/scheduled")
async def list_scheduled(channel_id: int, u: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    """List scheduled posts."""
    member = db.query(RoomMember).filter(
        RoomMember.room_id == channel_id, RoomMember.user_id == u.id,
    ).first()
    if not member or member.role not in (RoomRole.OWNER, RoomRole.ADMIN):
        raise HTTPException(403, "Admin access required")
    msgs = db.query(Message).filter(
        Message.room_id == channel_id, Message.is_scheduled == True,
    ).order_by(Message.scheduled_at).all()
    return {"scheduled": [
        {"id": m.id, "scheduled_at": m.scheduled_at.isoformat() if m.scheduled_at else ""}
        for m in msgs
    ]}


# ══════════════════════════════════════════════════════════════════════════════
# 4. Channel Discovery (catalog)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/popular")
async def popular_channels(db: Session = Depends(get_db)):
    """Public channels sorted by subscriber count."""
    channels = db.query(Room).filter(Room.is_channel == True, Room.is_private == False).all()
    result = []
    for c in channels:
        count = c.members.count()
        d = {"id": c.id, "name": c.name, "description": c.description,
             "invite_code": c.invite_code, "subscriber_count": count,
             "avatar_emoji": c.avatar_emoji, "avatar_url": c.avatar_url}
        mon = db.query(ChannelMonetization).filter(ChannelMonetization.room_id == c.id).first()
        if mon:
            d["is_paid"] = mon.is_paid
            d["price_display"] = mon.price_display
        result.append(d)
    result.sort(key=lambda x: x["subscriber_count"], reverse=True)
    return {"channels": result[:100]}


@router.get("/discover")
async def discover_channels(q: str = Query(default="", max_length=100),
                            category: str = Query(default=""),
                            db: Session = Depends(get_db)):
    """Search and discover public channels."""
    query = db.query(Room).filter(Room.is_channel == True, Room.is_private == False)
    if q:
        query = query.filter(Room.name.ilike(f"%{q}%") | Room.description.ilike(f"%{q}%"))
    channels = query.limit(50).all()
    result = []
    for c in channels:
        count = c.members.count()
        result.append({
            "id": c.id, "name": c.name, "description": c.description,
            "invite_code": c.invite_code, "subscriber_count": count,
            "avatar_emoji": c.avatar_emoji,
        })
    result.sort(key=lambda x: x["subscriber_count"], reverse=True)
    return {"channels": result}


# ══════════════════════════════════════════════════════════════════════════════
# 5. Post Reactions (poll-style)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/{channel_id}/posts/{message_id}/react")
async def react_to_post(channel_id: int, message_id: int, body: ReactRequest,
                        u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Add/toggle reaction on a post."""
    existing = db.query(PostReaction).filter(
        PostReaction.message_id == message_id,
        PostReaction.user_id == u.id,
        PostReaction.emoji == body.emoji,
    ).first()
    if existing:
        db.delete(existing)
        db.commit()
        return {"ok": True, "action": "removed"}
    db.add(PostReaction(message_id=message_id, user_id=u.id, emoji=body.emoji))
    db.commit()
    return {"ok": True, "action": "added"}


@router.get("/{channel_id}/posts/{message_id}/reactions")
async def get_reactions(channel_id: int, message_id: int, db: Session = Depends(get_db)):
    """Get reaction counts for a post."""
    reactions = db.query(PostReaction.emoji, func.count(PostReaction.id)).filter(
        PostReaction.message_id == message_id,
    ).group_by(PostReaction.emoji).all()
    return {"reactions": {emoji: count for emoji, count in reactions}}


# ══════════════════════════════════════════════════════════════════════════════
# 6. Monetization (P2P, 0% platform fee)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/{channel_id}/monetization")
async def get_monetization(channel_id: int, db: Session = Depends(get_db)):
    """Get channel monetization settings (public)."""
    mon = db.query(ChannelMonetization).filter(ChannelMonetization.room_id == channel_id).first()
    if not mon:
        return {"is_paid": False, "donations_enabled": False}
    return {
        "is_paid": mon.is_paid, "price_display": mon.price_display,
        "currency": mon.currency, "network": mon.network,
        "wallet_address": mon.wallet_address,
        "donations_enabled": mon.donations_enabled,
    }


@router.put("/{channel_id}/monetization")
async def set_monetization(channel_id: int, body: SetMonetizationRequest,
                           u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Configure monetization (owner only). 0% platform fee — all money goes to author."""
    channel = db.query(Room).filter(Room.id == channel_id, Room.is_channel == True).first()
    if not channel or channel.creator_id != u.id:
        raise HTTPException(403, "Only channel owner can set monetization")
    existing = db.query(ChannelMonetization).filter(ChannelMonetization.room_id == channel_id).first()
    if existing:
        existing.wallet_address = body.wallet_address
        existing.currency = body.currency
        existing.network = body.network
        existing.price_monthly = body.price_monthly
        existing.price_display = body.price_display
        existing.is_paid = body.is_paid
        existing.donations_enabled = body.donations_enabled
    else:
        db.add(ChannelMonetization(
            room_id=channel_id, wallet_address=body.wallet_address,
            currency=body.currency, network=body.network,
            price_monthly=body.price_monthly, price_display=body.price_display,
            is_paid=body.is_paid, donations_enabled=body.donations_enabled,
        ))
    db.commit()
    return {"ok": True}


@router.post("/{channel_id}/subscribe")
async def subscribe_to_paid(channel_id: int, body: SubscribeRequest,
                            u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Subscribe to paid channel after crypto payment.

    Flow:
      1. User sees price + wallet address from /monetization
      2. User sends crypto to wallet directly (P2P)
      3. User submits tx_hash here
      4. Server verifies tx on blockchain (via app.security.blockchain_verify)
      5. User gets access for 30 days
    """
    mon = db.query(ChannelMonetization).filter(
        ChannelMonetization.room_id == channel_id, ChannelMonetization.is_paid == True
    ).first()
    if not mon:
        raise HTTPException(400, "Channel is not paid")

    # Prevent replay: same tx_hash cannot be used twice
    duplicate = db.query(ChannelSubscription).filter(
        ChannelSubscription.tx_hash == body.tx_hash
    ).first()
    if duplicate:
        raise HTTPException(409, "This transaction has already been used")

    # Verify payment on blockchain
    verification = await verify_transaction(
        tx_hash=body.tx_hash,
        wallet_address=mon.wallet_address,
        expected_amount=body.amount or mon.price_display,
        currency=mon.currency,
        network=mon.network,
    )
    if not verification.ok:
        raise HTTPException(402, f"Payment verification failed: {verification.error}")

    sub = ChannelSubscription(
        room_id=channel_id, user_id=u.id,
        tx_hash=body.tx_hash, amount=verification.amount_received or body.amount or mon.price_display,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(sub)
    # Also add as member if not already
    existing = db.query(RoomMember).filter(
        RoomMember.room_id == channel_id, RoomMember.user_id == u.id
    ).first()
    if not existing:
        db.add(RoomMember(room_id=channel_id, user_id=u.id, role=RoomRole.MEMBER))
    db.commit()
    return {"ok": True, "expires_at": sub.expires_at.isoformat()}


@router.post("/{channel_id}/donate")
async def donate_to_channel(channel_id: int, body: DonateRequest,
                            u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Send donation to channel author. All money goes to author's wallet (0% fee)."""
    mon = db.query(ChannelMonetization).filter(
        ChannelMonetization.room_id == channel_id, ChannelMonetization.donations_enabled == True
    ).first()
    if not mon:
        raise HTTPException(400, "Donations not enabled for this channel")

    # Prevent replay: same tx_hash cannot be used twice
    duplicate = db.query(ChannelDonation).filter(
        ChannelDonation.tx_hash == body.tx_hash
    ).first()
    if duplicate:
        raise HTTPException(409, "This transaction has already been used")

    # Verify donation on blockchain
    verification = await verify_transaction(
        tx_hash=body.tx_hash,
        wallet_address=mon.wallet_address,
        expected_amount=body.amount,
        currency=mon.currency,
        network=mon.network,
    )
    if not verification.ok:
        raise HTTPException(402, f"Payment verification failed: {verification.error}")

    don = ChannelDonation(
        room_id=channel_id, user_id=u.id,
        tx_hash=body.tx_hash, amount=verification.amount_received or body.amount,
        message=body.message, currency=mon.currency,
    )
    db.add(don)
    db.commit()
    return {"ok": True, "message": "Thank you for your donation!"}


@router.get("/{channel_id}/donations")
async def list_donations(channel_id: int, u: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    """List donations (owner only)."""
    channel = db.query(Room).filter(Room.id == channel_id).first()
    if not channel or channel.creator_id != u.id:
        raise HTTPException(403, "Owner only")
    dons = db.query(ChannelDonation).filter(
        ChannelDonation.room_id == channel_id
    ).order_by(ChannelDonation.created_at.desc()).limit(100).all()
    return {"donations": [
        {"amount": d.amount, "message": d.message, "tx_hash": d.tx_hash,
         "created_at": d.created_at.isoformat() if d.created_at else ""}
        for d in dons
    ]}


@router.get("/{channel_id}/subscribers")
async def list_subscribers(
    channel_id: int,
    q: str = "",
    offset: int = 0,
    limit: int = 50,
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List channel subscribers with ban/remove capability (admin/owner)."""
    channel = db.query(Room).filter(Room.id == channel_id, Room.is_channel == True).first()
    if not channel:
        raise HTTPException(404, "Channel not found")
    actor = db.query(RoomMember).filter(
        RoomMember.room_id == channel_id, RoomMember.user_id == u.id,
    ).first()
    if not actor or actor.role not in (RoomRole.OWNER, RoomRole.ADMIN):
        raise HTTPException(403, "Admin access required")

    query = db.query(RoomMember).filter(RoomMember.room_id == channel_id)
    if q:
        user_ids = [
            uid for (uid,) in db.query(User.id).filter(
                User.username.ilike(f"%{q}%") | User.display_name.ilike(f"%{q}%")
            ).all()
        ]
        query = query.filter(RoomMember.user_id.in_(user_ids))

    total = query.count()
    members = query.order_by(RoomMember.joined_at.desc()).offset(offset).limit(min(limit, 100)).all()

    result = []
    for m in members:
        user = db.query(User).filter(User.id == m.user_id).first()
        if not user:
            continue
        result.append({
            "user_id": user.id,
            "username": user.username,
            "display_name": user.display_name or user.username,
            "avatar_emoji": user.avatar_emoji,
            "avatar_url": user.avatar_url,
            "role": m.role.value,
            "is_banned": m.is_banned,
            "joined_at": m.joined_at.isoformat() if m.joined_at else "",
        })

    return {"subscribers": result, "total": total, "offset": offset}


@router.post("/{channel_id}/subscribers/{user_id}/ban")
async def ban_subscriber(
    channel_id: int, user_id: int,
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ban a subscriber from channel."""
    channel = db.query(Room).filter(Room.id == channel_id, Room.is_channel == True).first()
    if not channel:
        raise HTTPException(404)
    actor = db.query(RoomMember).filter(
        RoomMember.room_id == channel_id, RoomMember.user_id == u.id,
    ).first()
    if not actor or actor.role not in (RoomRole.OWNER, RoomRole.ADMIN):
        raise HTTPException(403)
    target = db.query(RoomMember).filter(
        RoomMember.room_id == channel_id, RoomMember.user_id == user_id,
    ).first()
    if not target:
        raise HTTPException(404, "Subscriber not found")
    if target.role == RoomRole.OWNER:
        raise HTTPException(403, "Cannot ban owner")
    target.is_banned = True
    db.commit()
    return {"ok": True}


@router.post("/{channel_id}/subscribers/{user_id}/unban")
async def unban_subscriber(
    channel_id: int, user_id: int,
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Unban a subscriber."""
    channel = db.query(Room).filter(Room.id == channel_id, Room.is_channel == True).first()
    if not channel:
        raise HTTPException(404)
    actor = db.query(RoomMember).filter(
        RoomMember.room_id == channel_id, RoomMember.user_id == u.id,
    ).first()
    if not actor or actor.role not in (RoomRole.OWNER, RoomRole.ADMIN):
        raise HTTPException(403)
    target = db.query(RoomMember).filter(
        RoomMember.room_id == channel_id, RoomMember.user_id == user_id,
    ).first()
    if not target:
        raise HTTPException(404)
    target.is_banned = False
    db.commit()
    return {"ok": True}


@router.delete("/{channel_id}/subscribers/{user_id}")
async def remove_subscriber(
    channel_id: int, user_id: int,
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a subscriber from channel."""
    channel = db.query(Room).filter(Room.id == channel_id, Room.is_channel == True).first()
    if not channel:
        raise HTTPException(404)
    actor = db.query(RoomMember).filter(
        RoomMember.room_id == channel_id, RoomMember.user_id == u.id,
    ).first()
    if not actor or actor.role not in (RoomRole.OWNER, RoomRole.ADMIN):
        raise HTTPException(403)
    target = db.query(RoomMember).filter(
        RoomMember.room_id == channel_id, RoomMember.user_id == user_id,
    ).first()
    if not target:
        raise HTTPException(404)
    if target.role == RoomRole.OWNER:
        raise HTTPException(403, "Cannot remove owner")
    db.delete(target)
    # Delete their encrypted key
    db.query(EncryptedRoomKey).filter(
        EncryptedRoomKey.room_id == channel_id,
        EncryptedRoomKey.user_id == user_id,
    ).delete()
    db.commit()
    return {"ok": True}


@router.get("/{channel_id}/banned")
async def list_banned(
    channel_id: int,
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List banned subscribers."""
    channel = db.query(Room).filter(Room.id == channel_id, Room.is_channel == True).first()
    if not channel:
        raise HTTPException(404)
    actor = db.query(RoomMember).filter(
        RoomMember.room_id == channel_id, RoomMember.user_id == u.id,
    ).first()
    if not actor or actor.role not in (RoomRole.OWNER, RoomRole.ADMIN):
        raise HTTPException(403)
    banned = db.query(RoomMember).filter(
        RoomMember.room_id == channel_id, RoomMember.is_banned == True,
    ).all()
    result = []
    for m in banned:
        user = db.query(User).filter(User.id == m.user_id).first()
        if user:
            result.append({
                "user_id": user.id,
                "username": user.username,
                "display_name": user.display_name or user.username,
                "avatar_emoji": user.avatar_emoji,
            })
    return {"banned": result}


@router.get("/{channel_id}/recent-actions")
async def recent_actions(
    channel_id: int,
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Recent admin actions in the last 48 hours (from message log)."""
    channel = db.query(Room).filter(Room.id == channel_id, Room.is_channel == True).first()
    if not channel:
        raise HTTPException(404)
    actor = db.query(RoomMember).filter(
        RoomMember.room_id == channel_id, RoomMember.user_id == u.id,
    ).first()
    if not actor or actor.role not in (RoomRole.OWNER, RoomRole.ADMIN):
        raise HTTPException(403)

    since = datetime.now(timezone.utc) - timedelta(hours=48)

    # Recent joins
    recent_joins = db.query(RoomMember).filter(
        RoomMember.room_id == channel_id,
        RoomMember.joined_at >= since,
    ).all()

    # Recent messages (posts) — edited or deleted
    recent_edits = db.query(Message).filter(
        Message.room_id == channel_id,
        Message.is_edited == True,
        Message.edited_at >= since,
    ).all()

    actions = []
    for m in recent_joins:
        user = db.query(User).filter(User.id == m.user_id).first()
        actions.append({
            "type": "join",
            "user": user.display_name or user.username if user else "?",
            "at": m.joined_at.isoformat() if m.joined_at else "",
        })
    for m in recent_edits:
        user = db.query(User).filter(User.id == m.sender_id).first() if m.sender_id else None
        actions.append({
            "type": "edit",
            "user": user.display_name or user.username if user else "system",
            "message_id": m.id,
            "at": m.edited_at.isoformat() if m.edited_at else "",
        })

    actions.sort(key=lambda a: a.get("at", ""), reverse=True)
    return {"actions": actions[:100]}
