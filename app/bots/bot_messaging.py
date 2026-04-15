"""
app/bots/bot_messaging.py — Bot HTTP API & WebSocket (for bots, authenticated via api_token).

Send/reply messages, long-poll for updates, WebSocket streaming,
and the notify_bots_in_room helper called from chat.py.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Bot, User
from app.models_rooms import Message, MessageType, Room, RoomMember
from app.peer.connection_manager import manager

from app.bots.bot_shared import (
    router,
    _get_bot_by_token,
    _get_or_create_queue,
    enqueue_bot_update,
    BotSendRequest,
    BotReplyRequest,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Bot HTTP API (for bots, authenticated via api_token)
# ══════════════════════════════════════════════════════════════════════════════

def _store_bot_message(
    bot: Bot, room_id: int, text: str, db: Session,
    reply_to_id: int | None = None,
) -> Message:
    """
    Store a bot message as plaintext. Bot messages are NOT encrypted
    because bots are server-side entities without E2E keys.

    The text is stored as raw bytes in content_encrypted (same column,
    but unencrypted for bot messages). The is_bot flag on the sender User
    tells the client to render it as plaintext.
    """
    # Verify bot is a member of the room
    member = db.query(RoomMember).filter(
        RoomMember.room_id == room_id,
        RoomMember.user_id == bot.user_id,
    ).first()
    if not member:
        raise HTTPException(403, "Bot is not a member of this room")

    if reply_to_id:
        reply_exists = db.query(Message.id).filter(
            Message.id == reply_to_id,
            Message.room_id == room_id,
        ).first()
        if not reply_exists:
            reply_to_id = None

    msg = Message(
        room_id=room_id,
        sender_id=bot.user_id,
        msg_type=MessageType.TEXT,
        content_encrypted=text.encode("utf-8"),  # plaintext for bot messages
        reply_to_id=reply_to_id,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


async def _broadcast_bot_message(bot: Bot, msg: Message, db: Session) -> None:
    """Broadcast a bot message to all room members via WS."""
    bot_user = db.query(User).filter(User.id == bot.user_id).first()

    payload = {
        "type":         "message",
        "msg_id":       msg.id,
        "sender_id":    bot.user_id,
        "sender":       bot_user.username if bot_user else bot.name,
        "display_name": bot.name,
        "avatar_emoji": "🤖",
        "avatar_url":   bot.avatar_url,
        "is_bot":       True,
        "bot_id":       bot.id,
        "bot_name":     bot.name,
        "plaintext":    msg.content_encrypted.decode("utf-8"),
        "msg_type":     "text",
        "reply_to_id":  msg.reply_to_id,
        "status":       "sent",
        "created_at":   msg.created_at.isoformat(),
    }
    await manager.broadcast_to_room(msg.room_id, payload)


@router.post("/api/bot/send")
async def bot_send_message(
    body: BotSendRequest,
    bot: Bot = Depends(_get_bot_by_token),
    db: Session = Depends(get_db),
):
    """Bot sends a plaintext message to a room."""
    msg = _store_bot_message(bot, body.room_id, body.text, db)
    await _broadcast_bot_message(bot, msg, db)

    return {
        "ok": True,
        "msg_id": msg.id,
        "created_at": msg.created_at.isoformat(),
    }


@router.post("/api/bot/reply")
async def bot_reply_message(
    body: BotReplyRequest,
    bot: Bot = Depends(_get_bot_by_token),
    db: Session = Depends(get_db),
):
    """Bot replies to a specific message in a room."""
    msg = _store_bot_message(bot, body.room_id, body.text, db, reply_to_id=body.reply_to_id)
    await _broadcast_bot_message(bot, msg, db)

    return {
        "ok": True,
        "msg_id": msg.id,
        "created_at": msg.created_at.isoformat(),
    }


@router.get("/api/bot/updates")
async def bot_get_updates(
    timeout: int = Query(30, ge=1, le=60),
    bot: Bot = Depends(_get_bot_by_token),
    db: Session = Depends(get_db),
):
    """
    Long-poll for new messages/commands directed at the bot.
    Blocks for up to `timeout` seconds waiting for updates.
    Returns a list of updates (messages from rooms the bot is in).
    """
    q = await _get_or_create_queue(bot.user_id)
    updates = []

    # Drain any already-queued updates first
    while not q.empty():
        try:
            updates.append(q.get_nowait())
        except asyncio.QueueEmpty:
            break

    if updates:
        return {"ok": True, "updates": updates}

    # Long-poll: wait for up to `timeout` seconds
    try:
        update = await asyncio.wait_for(q.get(), timeout=timeout)
        updates.append(update)
        # Drain any more that arrived
        while not q.empty():
            try:
                updates.append(q.get_nowait())
            except asyncio.QueueEmpty:
                break
    except asyncio.TimeoutError:
        logger.debug("Bot long-poll timeout after %ss, returning %d updates", timeout, len(updates))

    return {"ok": True, "updates": updates}


@router.get("/api/bot/me")
async def bot_me(
    bot: Bot = Depends(_get_bot_by_token),
    db: Session = Depends(get_db),
):
    """Returns bot info (for the bot itself to verify its token works)."""
    return {
        "bot_id": bot.id,
        "bot_user_id": bot.user_id,
        "name": bot.name,
        "description": bot.description,
        "is_active": bot.is_active,
        "commands": json.loads(bot.commands or "[]"),
        "mini_app_url": bot.mini_app_url,
        "mini_app_enabled": bot.mini_app_enabled or False,
    }


@router.get("/api/bot/rooms")
async def bot_list_rooms(
    bot: Bot = Depends(_get_bot_by_token),
    db: Session = Depends(get_db),
):
    """List rooms the bot is a member of."""
    memberships = db.query(RoomMember).filter(RoomMember.user_id == bot.user_id).all()
    rooms = []
    for m in memberships:
        room = db.query(Room).filter(Room.id == m.room_id).first()
        if room:
            rooms.append({
                "room_id": room.id,
                "name": room.name,
                "description": room.description,
                "member_count": room.member_count(),
            })
    return {"rooms": rooms}


# ══════════════════════════════════════════════════════════════════════════════
# Bot WebSocket (alternative to HTTP long-polling)
# ══════════════════════════════════════════════════════════════════════════════

@router.websocket("/ws/bot")
async def ws_bot(
    websocket: WebSocket,
    token: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Bot WebSocket. Connect with ?token=<api_token>.
    Receives all messages from rooms the bot is a member of.
    Bot can also send messages through this WebSocket.

    Incoming format (from bot):
        {"action": "send", "room_id": 123, "text": "Hello!"}
        {"action": "reply", "room_id": 123, "reply_to_id": 456, "text": "response"}

    Outgoing format (to bot):
        {"type": "message", "room_id": 123, "sender_id": 1, "sender": "alice",
         "text": "Hello bot!", "msg_id": 789, ...}
        {"type": "command", "room_id": 123, "sender_id": 1, "command": "/help",
         "args": "some args", "msg_id": 789, ...}
    """
    if not token:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Missing token query parameter"})
        await websocket.close(code=4401)
        return

    from app.bots.bot_shared import _hash_token
    token_hash = _hash_token(token)
    bot = db.query(Bot).filter(Bot.api_token == token_hash, Bot.is_active == True).first()
    if not bot:
        # Fallback: try plaintext match and migrate to hashed token
        bot = db.query(Bot).filter(Bot.api_token == token, Bot.is_active == True).first()
        if bot:
            bot.api_token = token_hash
            db.commit()
    if not bot:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Invalid or inactive bot token"})
        await websocket.close(code=4401)
        return

    await websocket.accept()
    logger.info(f"Bot WS+ {bot.name} (user_id={bot.user_id})")

    # Create/get the update queue
    q = await _get_or_create_queue(bot.user_id)

    # Send initial connected event
    await websocket.send_json({
        "type": "connected",
        "bot_id": bot.id,
        "bot_user_id": bot.user_id,
        "name": bot.name,
    })

    async def _reader():
        """Read messages from bot and process them."""
        while True:
            try:
                data = await websocket.receive_json()
            except WebSocketDisconnect:
                return
            except Exception:
                return

            action = data.get("action", "")

            if action == "send":
                room_id = data.get("room_id")
                text = data.get("text", "").strip()
                if room_id and text:
                    try:
                        msg = _store_bot_message(bot, room_id, text, db)
                        await _broadcast_bot_message(bot, msg, db)
                        await websocket.send_json({
                            "type": "ack",
                            "msg_id": msg.id,
                            "room_id": room_id,
                        })
                    except HTTPException as e:
                        await websocket.send_json({
                            "type": "error",
                            "message": e.detail,
                        })

            elif action == "reply":
                room_id = data.get("room_id")
                reply_to_id = data.get("reply_to_id")
                text = data.get("text", "").strip()
                if room_id and text:
                    try:
                        msg = _store_bot_message(bot, room_id, text, db, reply_to_id=reply_to_id)
                        await _broadcast_bot_message(bot, msg, db)
                        await websocket.send_json({
                            "type": "ack",
                            "msg_id": msg.id,
                            "room_id": room_id,
                        })
                    except HTTPException as e:
                        await websocket.send_json({
                            "type": "error",
                            "message": e.detail,
                        })

            elif action == "ping":
                await websocket.send_json({"type": "pong"})

    async def _writer():
        """Push updates from queue to bot WebSocket."""
        while True:
            try:
                update = await q.get()
                await websocket.send_json(update)
            except Exception:
                return

    # Run reader and writer concurrently
    reader_task = asyncio.create_task(_reader())
    writer_task = asyncio.create_task(_writer())

    try:
        done, pending = await asyncio.wait(
            [reader_task, writer_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
    except Exception:
        reader_task.cancel()
        writer_task.cancel()
    finally:
        logger.info(f"Bot WS- {bot.name} (user_id={bot.user_id})")


# ══════════════════════════════════════════════════════════════════════════════
# Helper: route messages to bots in a room (called from chat.py)
# ══════════════════════════════════════════════════════════════════════════════

async def notify_bots_in_room(
    room_id: int, sender_id: int, text: str,
    msg_id: int, sender_username: str, sender_display_name: str,
    db: Session,
) -> None:
    """
    Called after a message is saved in a room. Checks if any bots are members
    and enqueues the message as an update for them.

    If the text starts with '/', it's treated as a command and the update
    includes parsed command and args.
    """
    # Find all bot members in this room
    bot_members = (
        db.query(RoomMember.user_id)
        .join(User, User.id == RoomMember.user_id)
        .filter(
            RoomMember.room_id == room_id,
            User.is_bot == True,
        )
        .all()
    )

    if not bot_members:
        return

    # Build update payload
    is_command = text.startswith("/")
    command = None
    args = ""
    if is_command:
        parts = text.split(None, 1)
        command = parts[0]  # e.g. "/help"
        args = parts[1] if len(parts) > 1 else ""

    for (bot_user_id,) in bot_members:
        if bot_user_id == sender_id:
            continue  # Don't notify bot about its own messages

        update = {
            "type":             "command" if is_command else "message",
            "room_id":          room_id,
            "msg_id":           msg_id,
            "sender_id":        sender_id,
            "sender":           sender_username,
            "sender_display_name": sender_display_name,
            "text":             text,
        }
        if is_command:
            update["command"] = command
            update["args"] = args

        await enqueue_bot_update(bot_user_id, update)

        # Fallback: Constructor bot responds from saved commands
        if is_command:
            await _constructor_bot_respond(bot_user_id, room_id, command, sender_display_name, db)


async def _constructor_bot_respond(bot_user_id, room_id, command, sender_name, db):
    """
    If a bot was created via Constructor (commands stored as JSON),
    respond automatically without Gravitix runtime.
    """
    import json as _json
    from app.bots.bot_crud import Bot
    from app.models_rooms import Message, MessageType
    from app.peer.connection_manager import manager

    bot = db.query(Bot).filter(Bot.user_id == bot_user_id).first()
    if not bot or not bot.commands:
        return

    cmds = bot.commands
    if isinstance(cmds, str):
        try:
            cmds = _json.loads(cmds)
        except Exception:
            return

    if not isinstance(cmds, list):
        return

    # Find matching command
    cmd_lower = command.lower().strip()
    response = None
    for c in cmds:
        if isinstance(c, dict) and c.get("command", "").lower() == cmd_lower:
            response = c.get("response") or c.get("description") or c.get("command")
            break

    if not response:
        return

    # Replace template variables
    response = response.replace("{ctx.first_name}", sender_name or "User")

    # Send as bot message (plaintext — bots don't use E2E)
    try:
        msg = Message(
            room_id=room_id,
            sender_id=bot_user_id,
            msg_type=MessageType.TEXT,
            content_encrypted=b"\x00" * 28,
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)

        await manager.broadcast_to_room(room_id, {
            "type": "message",
            "msg_id": msg.id,
            "sender_id": bot_user_id,
            "sender": bot.name,
            "display_name": bot.name,
            "is_bot": True,
            "plaintext": response,
            "created_at": msg.created_at.isoformat() if msg.created_at else "",
        })
    except Exception as e:
        logger.warning(f"Constructor bot respond error: {e}")
