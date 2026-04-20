"""
app/chats/chat_messages.py — E2E message handlers: send, thread reply, edit, delete.

Extracted from chat.py for maintainability.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func as sa_func, update as sa_update
from sqlalchemy.orm import Session

from app.models import User
from app.models_rooms import (
    Message, MessageType, Room, RoomMember, RoomRole,
)
from app.peer.connection_manager import manager
from app.security.crypto import hash_message

from app.chats.messages._router import utc_iso as _utc_iso, parse_client_ts as _parse_client_ts
from app.chats.messages.flood import check_flood as _check_flood, _FLOOD_THRESHOLD
from app.chats.messages.push import send_web_push as _send_web_push
from app.federation.replication import maybe_replicate as _maybe_replicate
from app.security.sealed_sender import compute_sender_pseudo, verify_sender_pseudo, resolve_pseudo
from app.transport.blind_mailbox import deposit_envelope

logger = logging.getLogger(__name__)


async def _bmp_deposit(room_id: int, payload: dict):
    """Deposit message payload into BMP mailbox for the room (hybrid mode)."""
    from app.config import Config
    if not Config.BMP_DELIVERY_ENABLED:
        return
    try:
        import json
        await deposit_envelope(room_id, json.dumps(payload))
    except Exception as e:
        logger.debug("[BMP] Deposit failed for room %d: %s", room_id, e)


# ══════════════════════════════════════════════════════════════════════════════
# E2E message
# ══════════════════════════════════════════════════════════════════════════════

async def handle_e2e_message(room_id: int, user: User, data: dict, db: Session) -> None:
    # ── Global mute check (platform-level, before room-level checks) ─────────
    if user.global_muted_until and user.global_muted_until > datetime.now(timezone.utc):
        remaining = user.global_muted_until - datetime.now(timezone.utc)
        days = remaining.days
        hours = remaining.seconds // 3600
        if days > 0:
            time_str = f"{days}d {hours}h"
        elif hours > 0:
            time_str = f"{hours}h {remaining.seconds % 3600 // 60}m"
        else:
            time_str = f"{remaining.seconds // 60}m"
        await manager.send_to_user(room_id, user.id, {
            "type":    "error",
            "message": f"You are muted on the platform. Remaining: {time_str}",
            "code":    "global_muted",
        })
        return

    # ── Rate limiting (Token Bucket) ─────────────────────────────────────────
    if not manager.check_rate_limit(room_id, user.id):
        await manager.send_to_user(room_id, user.id, {
            "type":    "error",
            "message": "Too many messages. Please wait.",
            "code":    "rate_limited",
        })
        return

    # ── Flood auto-mute check (skipped for DMs and if antispam disabled) ────
    room_obj = db.query(Room).filter(Room.id == room_id).first()
    _is_dm = room_obj and room_obj.is_dm
    _antispam = room_obj.antispam_enabled if (room_obj and room_obj.antispam_enabled is not None) else True

    if _antispam and not _is_dm:
        from app.bots.antispam_bot import (
            get_antispam_config, get_antispam_bot_user_id,
            check_repeat_spam, check_link_spam, check_caps_spam,
        )

        # Skip antispam for the bot itself
        _bot_uid = get_antispam_bot_user_id()
        _is_antispam_bot = _bot_uid and user.id == _bot_uid

        if not _is_antispam_bot:
            member_flood = db.query(RoomMember).filter(
                RoomMember.room_id == room_id,
                RoomMember.user_id == user.id,
            ).first()
            if member_flood and member_flood.muted_until and member_flood.muted_until > datetime.now(timezone.utc):
                remaining = int((member_flood.muted_until - datetime.now(timezone.utc)).total_seconds())
                await manager.send_to_user(room_id, user.id, {
                    "type":    "error",
                    "message": f"You are muted. Remaining: {remaining} sec.",
                    "code":    "flood_muted",
                })
                return

            # Use configurable threshold from room settings
            _cfg = get_antispam_config(room_obj) if room_obj else {}
            _threshold = _cfg.get("threshold", _FLOOD_THRESHOLD)
            if await _check_flood(room_id, user, db, threshold_override=_threshold):
                return

            # ── Enhanced antispam checks (use plaintext hint from client) ──────
            _plaintext = data.get("plaintext_command", "") or data.get("plaintext_hint", "")
            if _plaintext and isinstance(_plaintext, str):
                _member_role = member_flood.role if member_flood else RoomRole.MEMBER

                if _cfg.get("block_repeats", True):
                    if await check_repeat_spam(room_id, user, _plaintext, db):
                        return

                if _cfg.get("block_links", True):
                    if await check_link_spam(room_id, user, _plaintext, _member_role, db):
                        return

                if await check_caps_spam(room_id, user, _plaintext, db):
                    return

    # ── Проверка прав на отправку в канале ────────────────────────────────────
    if room_obj and room_obj.is_channel:
        member = db.query(RoomMember).filter(
            RoomMember.room_id == room_id,
            RoomMember.user_id == user.id,
        ).first()
        if not member or member.role not in (RoomRole.OWNER, RoomRole.ADMIN):
            await manager.send_to_user(room_id, user.id, {
                "type": "error", "message": "Only admins can post in channels"
            })
            return

    # ── Slow mode (Feature 4) ─────────────────────────────────────────────────
    if room_obj and room_obj.slow_mode_seconds and room_obj.slow_mode_seconds > 0 and not room_obj.is_dm:
        member_sm = db.query(RoomMember).filter(
            RoomMember.room_id == room_id,
            RoomMember.user_id == user.id,
        ).first()
        if member_sm and member_sm.role == RoomRole.MEMBER:
            _user_pseudo = compute_sender_pseudo(room_id, user.id)
            last_msg = db.query(Message).filter(
                Message.room_id == room_id,
                Message.sender_pseudo == _user_pseudo,
            ).order_by(Message.created_at.desc()).first()
            if last_msg:
                elapsed = (datetime.now(timezone.utc) - last_msg.created_at).total_seconds()
                if elapsed < room_obj.slow_mode_seconds:
                    remaining = int(room_obj.slow_mode_seconds - elapsed)
                    await manager.send_to_user(room_id, user.id, {
                        "type": "error",
                        "message": f"Please wait {remaining} sec (slow mode)",
                        "code": "slow_mode",
                    })
                    return

    ciphertext_hex = data.get("ciphertext", "").strip()
    client_msg_id  = data.get("msg_id", "")   # идентификатор от клиента

    if not ciphertext_hex:
        return

    if len(ciphertext_hex) < 48:
        await manager.send_to_user(room_id, user.id, {
            "type": "error", "message": "Ciphertext too short"
        })
        return

    # ── Deduplication by client_msg_id ─────────────────────────────────────────
    if client_msg_id:
        dedup_key = f"msg:{room_id}:{client_msg_id}"
        if await manager.is_duplicate_message(dedup_key):
            # Повторная отправка — шлём ACK без сохранения
            await manager.send_to_user(room_id, user.id, {
                "type":       "ack",
                "msg_id":     client_msg_id,
                "duplicate":  True,
            })
            return

    try:
        ciphertext_bytes = bytes.fromhex(ciphertext_hex)
    except ValueError:
        await manager.send_to_user(room_id, user.id, {
            "type": "error", "message": "Ciphertext is not valid hex"
        })
        return

    content_hash = None
    hash_hex     = data.get("hash", "")
    if hash_hex:
        try:
            content_hash = bytes.fromhex(hash_hex)
        except ValueError:
            pass
    if content_hash is None:
        content_hash_result = hash_message(ciphertext_bytes)
        if isinstance(content_hash_result, (bytes, bytearray)):
            content_hash = bytes(content_hash_result)

    reply_to_id = data.get("reply_to_id")
    if reply_to_id is not None:
        try:
            reply_to_id = int(reply_to_id)
        except (ValueError, TypeError):
            reply_to_id = None
    if reply_to_id:
        reply_exists = db.query(Message.id).filter(
            Message.id      == reply_to_id,
            Message.room_id == room_id,
        ).first()
        if not reply_exists:
            reply_to_id = None

    # ── @mention usernames (client-detected, since E2E encrypted) ────────────
    mentioned_usernames: list[str] = data.get("mentioned_usernames") or []
    # Sanitize: keep only valid short strings
    mentioned_usernames = [u.lower().strip() for u in mentioned_usernames[:20] if isinstance(u, str) and 3 <= len(u) <= 30]

    # ── Disappearing messages per-chat (Feature 3) ──────────────────────────
    auto_expire = None
    if room_obj and room_obj.auto_delete_seconds and room_obj.auto_delete_seconds > 0:
        auto_expire = datetime.now(timezone.utc) + timedelta(seconds=room_obj.auto_delete_seconds)

    client_created_at = _parse_client_ts(data.get("client_ts"))

    msg = Message(
        room_id           = room_id,
        sender_pseudo     = compute_sender_pseudo(room_id, user.id),
        msg_type          = MessageType.TEXT,
        content_encrypted = ciphertext_bytes,
        content_hash      = content_hash,
        reply_to_id       = reply_to_id,
        expires_at        = auto_expire,
    )
    if client_created_at:
        msg.created_at = client_created_at
    db.add(msg)
    try:
        # Update room's updated_at for sorting
        _room_obj = db.query(Room).filter(Room.id == room_id).first()
        if _room_obj:
            _room_obj.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(msg)
    except Exception as e:
        db.rollback()
        logger.error("Failed to save message in room %s: %s", room_id, e)
        await manager.send_to_user(room_id, user.id, {
            "type": "error", "message": "Failed to save message",
        })
        return

    # ── ACK — подтверждение доставки отправителю ──────────────────────────────
    await manager.send_to_user(room_id, user.id, {
        "type":       "ack",
        "msg_id":     client_msg_id,
        "server_id":  msg.id,
        "created_at": _utc_iso(msg.created_at),
    })

    # Fetch sender's tag in this room
    _sender_member = db.query(RoomMember).filter(
        RoomMember.room_id == room_id, RoomMember.user_id == user.id,
    ).first()

    payload = {
        "type":          "message",
        "msg_id":        msg.id,
        "client_msg_id": client_msg_id,
        "sender_id":     user.id,
        "sender_pseudo": msg.sender_pseudo,
        "sender":        user.username,
        "display_name":  user.display_name or user.username,
        "avatar_emoji":  user.avatar_emoji,
        "avatar_url":    user.avatar_url,
        "is_bot":        bool(user.is_bot),
        "tag":           getattr(_sender_member, 'tag', None) if _sender_member else None,
        "tag_color":     getattr(_sender_member, 'tag_color', None) if _sender_member else None,
        "reply_color":   user.reply_color,
        "reply_icon":    user.reply_icon,
        "ciphertext":    ciphertext_hex,
        "hash":          hash_hex or (content_hash.hex() if content_hash else None),
        "reply_to_id":   reply_to_id,
        "reply_quote":   data.get("reply_quote"),
        "status":        "sent",
        "forwarded_from": msg.forwarded_from,
        "expires_at":    _utc_iso(msg.expires_at),
        "created_at":    _utc_iso(msg.created_at),
    }
    # ── Собираем ID участников комнаты для pending delivery queue ──────────
    _room_member_ids = [
        rm.user_id for rm in db.query(RoomMember.user_id).filter(
            RoomMember.room_id == room_id,
            RoomMember.is_banned == False,
        ).all()
    ]

    # ── Delivery: BMP-only (zero metadata leakage) ─────────────────────────
    # WS broadcast removed — server no longer reveals who receives what.
    # Messages are deposited into anonymous BMP mailboxes.
    # Pending queue still works for offline users (fallback via WS on reconnect).
    await _bmp_deposit(room_id, payload)
    # Keep pending queue for offline delivery (BMP TTL = 2h, pending = 7d)
    await manager.enqueue_pending(room_id, payload, member_ids=_room_member_ids)

    # ── Cross-node replication (federated rooms only, owner opt-in) ────────
    # No-op unless `room.replication_mode == 'federated'`. Metadata leak is
    # intentional and surfaced to users via the warning banner; content
    # stays E2E-encrypted.
    if _room_obj is not None:
        try:
            _sender_ts = int(msg.created_at.timestamp()) if msg.created_at else 0
        except Exception:
            _sender_ts = 0
        await _maybe_replicate(_room_obj, payload, _sender_ts)

    # ── Bot command forwarding ─────────────────────────────────────────────
    # Client may include plaintext_command when text starts with '/'
    # (server can't see E2E-encrypted text, so client provides the hint)
    _bot_cmd_text = data.get("plaintext_command", "")
    if _bot_cmd_text and isinstance(_bot_cmd_text, str) and _bot_cmd_text.startswith("/"):
        # Handle built-in antispam bot commands
        _cmd_lower = _bot_cmd_text.strip().split()[0].lower()
        if _cmd_lower in ("/antispam_status", "/antispam_help"):
            try:
                from app.bots.antispam_bot import handle_antispam_command
                await handle_antispam_command(room_id, _cmd_lower, db)
            except Exception as e:
                logger.warning(f"Antispam command error: {e}")

        try:
            from app.bots.bot_api import notify_bots_in_room
            await notify_bots_in_room(
                room_id=room_id,
                sender_id=user.id,
                text=_bot_cmd_text,
                msg_id=msg.id,
                sender_username=user.username,
                sender_display_name=user.display_name or user.username,
                db=db,
            )
        except Exception as e:
            logger.warning(f"Bot notification error: {e}")

    # ── Уведомления для участников, не подключённых к WS комнаты ──────────
    room_obj = db.query(Room).filter(Room.id == room_id).first()
    is_dm = room_obj.is_dm if room_obj else False

    # Определяем кому был reply (для отображения @ mention)
    reply_to_user_id = None
    if reply_to_id:
        reply_msg = db.query(Message).filter(Message.id == reply_to_id).first()
        if reply_msg:
            if reply_msg.sender_id:
                reply_to_user_id = reply_msg.sender_id
            elif reply_msg.sender_pseudo:
                _rm_ids = [rm.user_id for rm in db.query(RoomMember).filter(
                    RoomMember.room_id == room_id).with_entities(RoomMember.user_id).all()]
                reply_to_user_id = resolve_pseudo(room_id, _rm_ids, reply_msg.sender_pseudo, caller="reply_notify")

    # Build set of mentioned user ids (from @username list sent by client)
    _mentioned_user_ids: set[int] = set()
    if mentioned_usernames:
        mentioned_users = db.query(User.id).filter(
            sa_func.lower(User.username).in_(mentioned_usernames)
        ).all()
        _mentioned_user_ids = {u.id for u in mentioned_users}

    room_members_full = db.query(RoomMember).filter(
        RoomMember.room_id == room_id,
        RoomMember.is_banned == False,
    ).all()
    # BMP mode: notifications go through BMP deposit (already done above).
    # Anonymous push proxy handles wake signals (Phase 6).
    # No targeted notify_user — zero metadata leakage.
    # Web Push via anonymous push proxy category signal:
    from app.config import Config
    if Config.BMP_DELIVERY_ENABLED:
        pass  # BMP deposit already sends wake signal via _emit_wake_signal
    else:
        # Legacy fallback for non-BMP mode
        online_in_room = set(manager._rooms.get(room_id, {}).keys())
        for rm in room_members_full:
            member_id = rm.user_id
            if member_id not in online_in_room and member_id != user.id:
                if rm.is_muted:
                    continue
                is_mention = (reply_to_user_id == member_id) or (member_id in _mentioned_user_ids)
                delivered = await manager.notify_user(member_id, {
                    "type":             "notification",
                    "room_id":          room_id,
                    "room_name":        room_obj.name if room_obj else "",
                    "is_dm":            is_dm,
                    "sender_pseudo":    msg.sender_pseudo,
                    "sender_username":  user.username,
                    "sender_display_name": user.display_name or user.username,
                    "sender_avatar":    user.avatar_emoji,
                    "sender_avatar_url": user.avatar_url,
                    "is_mention":       is_mention,
                    "created_at":       _utc_iso(msg.created_at),
                })

                if not delivered:
                    await _send_web_push(
                        member_id,
                        user.display_name or user.username,
                        room_id,
                    is_dm,
                    db,
                )


# ══════════════════════════════════════════════════════════════════════════════
# Thread reply
# ══════════════════════════════════════════════════════════════════════════════

async def handle_thread_reply(room_id: int, user: User, data: dict, db: Session) -> None:
    """Обработка ответа в треде: создаёт сообщение с thread_id и обновляет thread_count."""
    thread_id      = data.get("thread_id")
    ciphertext_hex = data.get("ciphertext", "").strip()
    client_msg_id  = data.get("msg_id", "")

    if not thread_id or not ciphertext_hex:
        return

    if len(ciphertext_hex) < 48:
        await manager.send_to_user(room_id, user.id, {
            "type": "error", "message": "Ciphertext too short"
        })
        return

    # ── Global mute check (platform-level) ───────────────────────────────────
    if user.global_muted_until and user.global_muted_until > datetime.now(timezone.utc):
        remaining = user.global_muted_until - datetime.now(timezone.utc)
        days = remaining.days
        hours = remaining.seconds // 3600
        if days > 0:
            time_str = f"{days}d {hours}h"
        elif hours > 0:
            time_str = f"{hours}h {remaining.seconds % 3600 // 60}m"
        else:
            time_str = f"{remaining.seconds // 60}m"
        await manager.send_to_user(room_id, user.id, {
            "type":    "error",
            "message": f"You are muted on the platform. Remaining: {time_str}",
            "code":    "global_muted",
        })
        return

    # Rate limiting
    if not manager.check_rate_limit(room_id, user.id):
        await manager.send_to_user(room_id, user.id, {
            "type": "error", "message": "Too many messages. Please wait.", "code": "rate_limited",
        })
        return

    # Flood auto-mute check (skipped for DMs and if antispam disabled)
    _room_for_flood = db.query(Room).filter(Room.id == room_id).first()
    _is_dm2 = _room_for_flood and _room_for_flood.is_dm
    _antispam2 = _room_for_flood.antispam_enabled if (_room_for_flood and _room_for_flood.antispam_enabled is not None) else True
    if _antispam2 and not _is_dm2:
        from app.bots.antispam_bot import get_antispam_config as _get_as_cfg2, get_antispam_bot_user_id as _get_bot_uid2
        _bot_uid2 = _get_bot_uid2()
        if not (_bot_uid2 and user.id == _bot_uid2):
            member_flood = db.query(RoomMember).filter(
                RoomMember.room_id == room_id, RoomMember.user_id == user.id,
            ).first()
            if member_flood and member_flood.muted_until and member_flood.muted_until > datetime.now(timezone.utc):
                remaining = int((member_flood.muted_until - datetime.now(timezone.utc)).total_seconds())
                await manager.send_to_user(room_id, user.id, {
                    "type": "error", "message": f"You are muted. Remaining: {remaining} sec.", "code": "flood_muted",
                })
                return
            _cfg2 = _get_as_cfg2(_room_for_flood) if _room_for_flood else {}
            _thr2 = _cfg2.get("threshold", _FLOOD_THRESHOLD)
            if await _check_flood(room_id, user, db, threshold_override=_thr2):
                return

    # Проверяем что корневое сообщение существует в этой комнате
    root_msg = db.query(Message).filter(
        Message.id == thread_id, Message.room_id == room_id,
    ).first()
    if not root_msg:
        await manager.send_to_user(room_id, user.id, {
            "type": "error", "message": "Thread root message not found"
        })
        return

    # Дедупликация
    if client_msg_id:
        dedup_key = f"msg:{room_id}:{client_msg_id}"
        if await manager.is_duplicate_message(dedup_key):
            await manager.send_to_user(room_id, user.id, {
                "type": "ack", "msg_id": client_msg_id, "duplicate": True,
            })
            return

    try:
        ciphertext_bytes = bytes.fromhex(ciphertext_hex)
    except ValueError:
        await manager.send_to_user(room_id, user.id, {
            "type": "error", "message": "Ciphertext is not valid hex"
        })
        return

    content_hash = None
    hash_hex = data.get("hash", "")
    if hash_hex:
        try:
            content_hash = bytes.fromhex(hash_hex)
        except ValueError:
            pass
    if content_hash is None:
        content_hash_result = hash_message(ciphertext_bytes)
        if isinstance(content_hash_result, (bytes, bytearray)):
            content_hash = bytes(content_hash_result)

    reply_to_id = data.get("reply_to_id")

    msg = Message(
        room_id           = room_id,
        sender_pseudo     = compute_sender_pseudo(room_id, user.id),
        msg_type          = MessageType.TEXT,
        content_encrypted = ciphertext_bytes,
        content_hash      = content_hash,
        reply_to_id       = reply_to_id,
        thread_id         = thread_id,
    )
    db.add(msg)

    # Атомарно инкрементируем thread_count на корневом сообщении (избегаем race condition)
    db.execute(
        sa_update(Message).where(Message.id == root_msg.id).values(
            thread_count=Message.thread_count + 1
        )
    )
    try:
        db.commit()
        db.refresh(msg)
        db.refresh(root_msg)
    except Exception as e:
        db.rollback()
        logger.error("Failed to save thread reply in room %s: %s", room_id, e)
        await manager.send_to_user(room_id, user.id, {
            "type": "error", "message": "Failed to save thread reply",
        })
        return

    # ACK отправителю
    await manager.send_to_user(room_id, user.id, {
        "type":       "ack",
        "msg_id":     client_msg_id,
        "server_id":  msg.id,
        "created_at": _utc_iso(msg.created_at),
    })

    # Собираем member_ids для pending delivery
    _thread_member_ids = [
        rm.user_id for rm in db.query(RoomMember.user_id).filter(
            RoomMember.room_id == room_id,
            RoomMember.is_banned == False,
        ).all()
    ]

    # Рассылаем сообщение в тред всем в комнате
    payload = {
        "type":          "thread_message",
        "msg_id":        msg.id,
        "client_msg_id": client_msg_id,
        "sender_pseudo": msg.sender_pseudo,
        "sender":        user.username,
        "display_name":  user.display_name or user.username,
        "avatar_emoji":  user.avatar_emoji,
        "avatar_url":    user.avatar_url,
        "ciphertext":    ciphertext_hex,
        "hash":          hash_hex or (content_hash.hex() if content_hash else None),
        "reply_to_id":   reply_to_id,
        "reply_quote":   data.get("reply_quote"),
        "thread_id":     thread_id,
        "status":        "sent",
        "created_at":    _utc_iso(msg.created_at),
    }
    # BMP-only delivery (WS broadcast removed)
    await _bmp_deposit(room_id, payload)
    await manager.enqueue_pending(room_id, payload, member_ids=_thread_member_ids)

    # Cross-node replication (same opt-in flag as regular messages)
    _room_obj2 = db.query(Room).filter(Room.id == room_id).first()
    if _room_obj2 is not None:
        try:
            _sender_ts2 = int(msg.created_at.timestamp()) if msg.created_at else 0
        except Exception:
            _sender_ts2 = 0
        await _maybe_replicate(_room_obj2, payload, _sender_ts2)

    # Обновляем badge thread_count для всех
    await manager.broadcast_to_room(room_id, {
        "type":         "thread_update",
        "msg_id":       thread_id,
        "thread_count": root_msg.thread_count,
    })


# ══════════════════════════════════════════════════════════════════════════════
# Edit message
# ══════════════════════════════════════════════════════════════════════════════

async def handle_edit_message(room_id: int, user: User, data: dict, db: Session) -> None:
    msg_id         = data.get("msg_id")
    ciphertext_hex = data.get("ciphertext", "").strip()

    if not msg_id or not ciphertext_hex or len(ciphertext_hex) < 48:
        return

    try:
        ciphertext_bytes = bytes.fromhex(ciphertext_hex)
    except ValueError:
        return

    msg = db.query(Message).filter(
        Message.id       == msg_id,
        Message.room_id  == room_id,
        Message.msg_type == MessageType.TEXT,
    ).first()
    if not msg:
        return
    # Ownership check: prefer sender_pseudo (sealed sender), fall back to sender_id
    _is_owner = (
        (msg.sender_pseudo and verify_sender_pseudo(room_id, user.id, msg.sender_pseudo))
        or (msg.sender_pseudo is None and msg.sender_id == user.id)
    )
    if not _is_owner:
        return

    from app.models_rooms import MessageEditHistory

    # Сохранить предыдущую версию в историю
    if msg.content_encrypted:
        history_entry = MessageEditHistory(
            message_id=msg.id,
            ciphertext_hex=msg.content_encrypted.hex() if isinstance(msg.content_encrypted, (bytes, bytearray)) else str(msg.content_encrypted),
            edited_at=datetime.now(timezone.utc),
        )
        db.add(history_entry)

    content_hash_result   = hash_message(ciphertext_bytes)
    msg.content_encrypted = ciphertext_bytes
    msg.content_hash      = bytes(content_hash_result) if isinstance(content_hash_result, (bytes, bytearray)) else None
    msg.is_edited         = True
    msg.edited_at         = datetime.now(timezone.utc)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to edit message %s: %s", msg_id, e)
        return

    _edit_payload = {
        "type":       "message_edited",
        "msg_id":     msg_id,
        "ciphertext": ciphertext_hex,
        "is_edited":  True,
    }
    await manager.broadcast_to_room(room_id, _edit_payload)


# ══════════════════════════════════════════════════════════════════════════════
# Delete message
# ══════════════════════════════════════════════════════════════════════════════

async def handle_delete_message(room_id: int, user: User, data: dict, db: Session) -> None:
    msg_id = data.get("msg_id")
    if not msg_id:
        return

    msg = db.query(Message).filter(
        Message.id      == msg_id,
        Message.room_id == room_id,
    ).first()
    if not msg:
        return
    # Ownership check OR admin/owner role in room
    _is_owner = (
        (msg.sender_pseudo and verify_sender_pseudo(room_id, user.id, msg.sender_pseudo))
        or (msg.sender_pseudo is None and msg.sender_id == user.id)
    )
    if not _is_owner:
        from app.models_rooms import RoomMember, RoomRole
        member = db.query(RoomMember).filter(
            RoomMember.room_id == room_id,
            RoomMember.user_id == user.id,
        ).first()
        if not member or member.role not in (RoomRole.OWNER, RoomRole.ADMIN):
            return

    db.delete(msg)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to delete message %s: %s", msg_id, e)
        return

    _del_payload = {"type": "message_deleted", "msg_id": msg_id}
    await manager.broadcast_to_room(room_id, _del_payload)
