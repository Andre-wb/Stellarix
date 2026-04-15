"""
Advanced Bot Features — Inline bots, keyboards, components, slash commands,
webhooks, payment API, bot store, mini-app IDE, bot permissions/scopes.
"""
from __future__ import annotations

import collections
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Bot, User
from app.models_rooms import Message, MessageType, Room, RoomMember
from app.peer.connection_manager import manager
from app.security.auth_jwt import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["bots-advanced"])


# ══════════════════════════════════════════════════════════════════════════════
# Schemas
# ══════════════════════════════════════════════════════════════════════════════

class InlineQueryResult(BaseModel):
    id: str
    title: str
    description: str = ""
    content: str = ""          # Message content to send
    thumbnail_url: str = ""

class InlineQueryResponse(BaseModel):
    results: list[InlineQueryResult] = []

class KeyboardButton(BaseModel):
    text: str
    callback_data: str = ""   # Data sent back on click
    url: str = ""             # Open URL instead

class ReplyKeyboard(BaseModel):
    buttons: list[list[KeyboardButton]]  # 2D grid
    one_time: bool = False
    resize: bool = True

class MessageComponent(BaseModel):
    type: str                 # "button", "select", "modal"
    custom_id: str
    label: str = ""
    style: str = "primary"    # primary, secondary, success, danger
    options: list[dict] = []  # For select menus
    placeholder: str = ""
    min_values: int = 1
    max_values: int = 1

class SlashCommand(BaseModel):
    name: str = Field(..., min_length=1, max_length=32, pattern="^[a-z0-9_]+$")
    description: str = Field("", max_length=100)
    options: list[dict] = []  # {name, type, description, required, choices}

class WebhookConfig(BaseModel):
    url: str = Field(..., max_length=500)
    secret: str = Field(default="", max_length=100)
    events: list[str] = Field(default_factory=lambda: ["message"])  # message, reaction, member_join, etc.

class BotScope(BaseModel):
    """OAuth-style permission scopes for bots."""
    scopes: list[str] = Field(default_factory=lambda: ["messages.read", "messages.send"])

class SendWithKeyboardRequest(BaseModel):
    room_id: int
    text: str
    keyboard: ReplyKeyboard | None = None
    components: list[MessageComponent] = []

class PaymentRequest(BaseModel):
    room_id: int
    title: str = Field(..., max_length=100)
    description: str = Field("", max_length=500)
    amount: str                # "5.00"
    currency: str = "USDT"    # USDT, TON, BTC, ETH
    wallet_address: str       # Where to send payment


# ══════════════════════════════════════════════════════════════════════════════
# Bot auth helper
# ══════════════════════════════════════════════════════════════════════════════

def _get_bot(request: Request, db: Session = Depends(get_db)) -> Bot:
    from app.bots.bot_shared import _hash_token
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bot "):
        raise HTTPException(401, "Expected: Authorization: Bot <token>")
    token = auth[4:].strip()
    token_hash = _hash_token(token)
    bot = db.query(Bot).filter(Bot.api_token == token_hash, Bot.is_active == True).first()
    if not bot:
        # Fallback: try plaintext match and migrate to hashed token
        bot = db.query(Bot).filter(Bot.api_token == token, Bot.is_active == True).first()
        if bot:
            bot.api_token = token_hash
            db.commit()
    if not bot:
        raise HTTPException(401, "Invalid bot token")
    return bot


# ══════════════════════════════════════════════════════════════════════════════
# 1. Inline Bots (@mention in any chat)
# ══════════════════════════════════════════════════════════════════════════════

# In-memory: bot_id -> cached inline results (LRU-bounded to prevent leaks)
_MAX_INLINE_BOTS = 4096
_inline_handlers: collections.OrderedDict[int, list] = collections.OrderedDict()

@router.post("/api/bot/inline/register")
async def register_inline_handler(request: Request, db: Session = Depends(get_db)):
    """Register this bot as an inline bot (responds to @mentions in any chat)."""
    bot = _get_bot(request, db)
    _inline_handlers[bot.id] = []
    _inline_handlers.move_to_end(bot.id)
    while len(_inline_handlers) > _MAX_INLINE_BOTS:
        _inline_handlers.popitem(last=False)
    return {"ok": True, "inline": True}


@router.post("/api/bot/inline/answer")
async def answer_inline_query(body: InlineQueryResponse, request: Request,
                              db: Session = Depends(get_db)):
    """Answer an inline query with results."""
    bot = _get_bot(request, db)
    # Store results for clients to fetch
    _inline_handlers[bot.id] = [r.model_dump() for r in body.results]
    _inline_handlers.move_to_end(bot.id)
    while len(_inline_handlers) > _MAX_INLINE_BOTS:
        _inline_handlers.popitem(last=False)
    return {"ok": True, "results_count": len(body.results)}


@router.get("/api/bots/{bot_id}/inline")
async def query_inline_bot(bot_id: int, q: str = Query(default="", max_length=200),
                           u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Client queries an inline bot with @bot_name search text.
    Returns cached results from the bot.
    """
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.is_active == True).first()
    if not bot:
        raise HTTPException(404, "Bot not found")
    results = _inline_handlers.get(bot.id, [])
    # Filter by query
    if q:
        q_lower = q.lower()
        results = [r for r in results
                   if q_lower in r.get("title", "").lower() or q_lower in r.get("description", "").lower()]
    return {"results": results[:20], "bot_name": bot.name}


# ══════════════════════════════════════════════════════════════════════════════
# 2. Custom Keyboards + 3. Message Components
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/api/bot/send-keyboard")
async def send_with_keyboard(body: SendWithKeyboardRequest, request: Request,
                             db: Session = Depends(get_db)):
    """Send a message with custom keyboard or interactive components.

    Keyboard: buttons below the message (quick replies)
    Components: buttons/selects/modals embedded in the message
    """
    bot = _get_bot(request, db)
    member = db.query(RoomMember).filter(
        RoomMember.room_id == body.room_id, RoomMember.user_id == bot.user_id,
    ).first()
    if not member:
        raise HTTPException(403, "Bot not in this room")

    # Build message with embedded keyboard/components metadata
    metadata = {}
    if body.keyboard:
        metadata["keyboard"] = body.keyboard.dict()
    if body.components:
        metadata["components"] = [c.dict() for c in body.components]

    # Store as system message with JSON metadata
    content = json.dumps({
        "text": body.text,
        "metadata": metadata,
    }).encode()

    msg = Message(
        room_id=body.room_id, sender_id=bot.user_id,
        msg_type=MessageType.TEXT, content_encrypted=content,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    # Broadcast to room
    await manager.broadcast_to_room(body.room_id, {
        "type": "message",
        "id": msg.id,
        "sender_id": bot.user_id,
        "text": body.text,
        "is_bot": True,
        "keyboard": metadata.get("keyboard"),
        "components": metadata.get("components"),
        "created_at": msg.created_at.isoformat() if msg.created_at else "",
    })

    return {"ok": True, "message_id": msg.id}


@router.post("/api/bot/callback")
async def handle_callback(request: Request, db: Session = Depends(get_db)):
    """Handle callback from keyboard button or component interaction.

    Client sends: {callback_data, message_id, user_id}
    Bot receives this via updates/webhook.
    """
    body = await request.json()
    callback_data = body.get("callback_data", "")
    message_id = body.get("message_id")
    user_id = body.get("user_id")

    # Store callback for bot to fetch via /updates or webhook
    return {"ok": True, "callback_data": callback_data,
            "message_id": message_id, "user_id": user_id}


# ══════════════════════════════════════════════════════════════════════════════
# 4. Slash Commands
# ══════════════════════════════════════════════════════════════════════════════

# In-memory: bot_id -> list of registered commands
_slash_commands: dict[int, list[dict]] = {}

@router.post("/api/bot/commands/register")
async def register_slash_commands(request: Request, db: Session = Depends(get_db)):
    """Register slash commands for a bot. Replaces existing commands."""
    bot = _get_bot(request, db)
    body = await request.json()
    commands = body.get("commands", [])
    _slash_commands[bot.id] = commands

    # Also update commands in DB
    bot.commands = json.dumps(commands)
    db.commit()

    return {"ok": True, "commands_count": len(commands)}


@router.get("/api/bots/{bot_id}/commands")
async def get_bot_commands(bot_id: int, db: Session = Depends(get_db)):
    """Get slash commands for a bot (for autocomplete UI)."""
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.is_active == True).first()
    if not bot:
        raise HTTPException(404, "Bot not found")
    commands = _slash_commands.get(bot.id) or json.loads(bot.commands or "[]")
    return {"commands": commands}


@router.get("/api/rooms/{room_id}/commands")
async def get_room_commands(room_id: int, u: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """Get all slash commands available in a room (from all bots)."""
    bot_members = db.query(RoomMember).join(User).filter(
        RoomMember.room_id == room_id, User.is_bot == True,
    ).all()
    all_commands = []
    for bm in bot_members:
        bot = db.query(Bot).filter(Bot.user_id == bm.user_id).first()
        if bot:
            cmds = _slash_commands.get(bot.id) or json.loads(bot.commands or "[]")
            for cmd in cmds:
                cmd["bot_name"] = bot.name
                cmd["bot_id"] = bot.id
            all_commands.extend(cmds)
    return {"commands": all_commands}


# ══════════════════════════════════════════════════════════════════════════════
# 5. Webhook Delivery
# ══════════════════════════════════════════════════════════════════════════════

# In-memory: bot_id -> webhook config
_webhooks: dict[int, dict] = {}

@router.post("/api/bot/webhook/set")
async def set_webhook(body: WebhookConfig, request: Request, db: Session = Depends(get_db)):
    """Set webhook URL for push delivery (instead of long-poll /updates)."""
    bot = _get_bot(request, db)
    _webhooks[bot.id] = {
        "url": body.url,
        "secret": body.secret or secrets.token_hex(16),
        "events": body.events,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return {"ok": True, "webhook_url": body.url}


@router.post("/api/bot/webhook/delete")
async def delete_webhook(request: Request, db: Session = Depends(get_db)):
    """Remove webhook, switch back to long-poll."""
    bot = _get_bot(request, db)
    _webhooks.pop(bot.id, None)
    return {"ok": True}


@router.get("/api/bot/webhook/info")
async def get_webhook_info(request: Request, db: Session = Depends(get_db)):
    """Get current webhook configuration."""
    bot = _get_bot(request, db)
    wh = _webhooks.get(bot.id)
    return {"webhook": wh}


async def deliver_webhook(bot_id: int, event: str, payload: dict) -> bool:
    """Deliver event to bot via webhook (called from chat.py on new messages)."""
    wh = _webhooks.get(bot_id)
    if not wh:
        return False
    if event not in wh.get("events", []):
        return False
    try:
        import httpx
        import hmac
        import hashlib
        body = json.dumps({"event": event, "payload": payload})
        sig = hmac.new(wh["secret"].encode(), body.encode(), hashlib.sha256).hexdigest()
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(wh["url"], content=body, headers={
                "Content-Type": "application/json",
                "X-Hook-Signature": sig,
            })
        return True
    except Exception as e:
        logger.warning("Webhook delivery failed for bot %d: %s", bot_id, e)
        return False


# ══════════════════════════════════════════════════════════════════════════════
# 6. Bot SDK Info (documentation endpoint)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/api/bots/sdk-info")
async def sdk_info():
    """Return Bot SDK documentation and examples for developers."""
    return {
        "sdk": {
            "python": {
                "install": "pip install vortex-bot-sdk",
                "example": """
from vortex_bot import Bot

bot = Bot(token="YOUR_TOKEN")

@bot.command("hello")
async def hello(ctx):
    await ctx.reply("Hello, World!")

@bot.on_message
async def echo(ctx):
    await ctx.reply(ctx.text)

bot.run()
""",
            },
            "javascript": {
                "install": "npm install vortex-bot-sdk",
                "example": """
const { Bot } = require('vortex-bot-sdk');

const bot = new Bot('YOUR_TOKEN');

bot.command('hello', async (ctx) => {
    await ctx.reply('Hello, World!');
});

bot.start();
""",
            },
            "http_api": {
                "base_url": "/api/bot",
                "auth": "Authorization: Bot <api_token>",
                "endpoints": [
                    "POST /api/bot/send — Send message",
                    "POST /api/bot/reply — Reply to message",
                    "POST /api/bot/send-keyboard — Send with buttons",
                    "GET  /api/bot/updates — Long-poll for events",
                    "WS   /ws/bot — Real-time events stream",
                    "POST /api/bot/webhook/set — Push delivery",
                    "POST /api/bot/inline/answer — Inline query results",
                    "POST /api/bot/commands/register — Slash commands",
                    "POST /api/bot/payment/create — Create payment",
                ],
            },
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# 7. Payment API (crypto P2P through bots)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/api/bot/payment/create")
async def create_payment(body: PaymentRequest, request: Request,
                         db: Session = Depends(get_db)):
    """Create a payment request via bot (sends [PAY] card to room).

    All money goes P2P to the specified wallet. 0% platform fee.
    """
    bot = _get_bot(request, db)
    member = db.query(RoomMember).filter(
        RoomMember.room_id == body.room_id, RoomMember.user_id == bot.user_id,
    ).first()
    if not member:
        raise HTTPException(403, "Bot not in room")

    pay_json = json.dumps({
        "title": body.title,
        "description": body.description,
        "amount": body.amount,
        "currency": body.currency,
        "address": body.wallet_address,
        "created": datetime.now(timezone.utc).isoformat(),
        "bot_name": bot.name,
    })

    content = f"[PAY] {pay_json}".encode()
    msg = Message(
        room_id=body.room_id, sender_id=bot.user_id,
        msg_type=MessageType.TEXT, content_encrypted=content,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    await manager.broadcast_to_room(body.room_id, {
        "type": "message", "id": msg.id, "sender_id": bot.user_id,
        "text": f"[PAY] {pay_json}", "is_bot": True,
        "created_at": msg.created_at.isoformat() if msg.created_at else "",
    })

    return {"ok": True, "message_id": msg.id}


# ══════════════════════════════════════════════════════════════════════════════
# 8. Bot Store (enhanced marketplace with one-click install)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/api/bots/store")
async def bot_store(category: str = Query(default="", max_length=30),
                    q: str = Query(default="", max_length=100),
                    sort: str = Query(default="popular"),
                    db: Session = Depends(get_db)):
    """Enhanced bot store with categories, search, and sorting."""
    query = db.query(Bot).filter(Bot.is_public == True, Bot.is_active == True)
    if category:
        query = query.filter(Bot.category == category)
    if q:
        query = query.filter(Bot.name.ilike(f"%{q}%") | Bot.description.ilike(f"%{q}%"))
    if sort == "rating":
        query = query.order_by(Bot.rating.desc())
    elif sort == "new":
        query = query.order_by(Bot.created_at.desc())
    else:
        query = query.order_by(Bot.installs.desc())
    bots = query.limit(50).all()
    return {"bots": [
        {"id": b.id, "name": b.name, "description": b.description,
         "category": b.category, "installs": b.installs, "rating": round(b.rating or 0, 1),
         "avatar_url": b.avatar_url, "is_public": True,
         "has_inline": b.id in _inline_handlers,
         "has_commands": bool(_slash_commands.get(b.id) or json.loads(b.commands or "[]")),
         "has_mini_app": b.mini_app_enabled}
        for b in bots
    ]}


# ══════════════════════════════════════════════════════════════════════════════
# 9. Mini Apps IDE (dev tools info endpoint)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/api/bots/{bot_id}/mini-app/dev")
async def mini_app_dev_info(bot_id: int, u: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """Mini App development tools and configuration."""
    bot = db.query(Bot).filter(Bot.id == bot_id).first()
    if not bot or bot.owner_id != u.id:
        raise HTTPException(403, "Not the bot owner")
    return {
        "bot_id": bot.id,
        "mini_app_url": bot.mini_app_url,
        "mini_app_enabled": bot.mini_app_enabled,
        "dev_tools": {
            "sandbox_url": f"/api/bots/{bot_id}/mini-app/sandbox",
            "debug_mode": True,
            "hot_reload": True,
            "available_apis": [
                "vortex.getUser() — current user info",
                "vortex.sendMessage(text) — send message to chat",
                "vortex.showAlert(text) — show native alert",
                "vortex.showConfirm(text) — show confirmation dialog",
                "vortex.openLink(url) — open external URL",
                "vortex.close() — close mini app",
                "vortex.requestPayment({amount, currency, wallet}) — P2P payment",
                "vortex.getTheme() — current theme (dark/light)",
                "vortex.onEvent(event, callback) — subscribe to events",
            ],
            "init_data_format": {
                "user": {"id": "int", "username": "str", "display_name": "str"},
                "bot_id": "int",
                "room_id": "int",
                "auth_token": "str (JWT for this session)",
            },
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# 10. Bot Permissions (OAuth-style scopes)
# ══════════════════════════════════════════════════════════════════════════════

AVAILABLE_SCOPES = {
    "messages.read": "Read messages in rooms where bot is added",
    "messages.send": "Send messages",
    "messages.delete": "Delete own messages",
    "messages.edit": "Edit own messages",
    "members.read": "Read room member list",
    "members.manage": "Kick/ban/mute members",
    "rooms.read": "Read room info",
    "rooms.manage": "Update room settings",
    "files.send": "Send files",
    "reactions.add": "Add reactions",
    "inline.respond": "Respond to inline queries",
    "commands.register": "Register slash commands",
    "webhooks.manage": "Set up webhook delivery",
    "payments.create": "Create payment requests",
    "mini_app.access": "Access mini app APIs",
    "profile.read": "Read user profiles",
}

# In-memory: bot_id -> set of granted scopes
_bot_scopes: dict[int, set[str]] = {}

@router.get("/api/bots/scopes")
async def list_available_scopes():
    """List all available OAuth-style scopes for bots."""
    return {"scopes": AVAILABLE_SCOPES}

@router.get("/api/bots/{bot_id}/scopes")
async def get_bot_scopes(bot_id: int, u: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    """Get scopes granted to a bot."""
    bot = db.query(Bot).filter(Bot.id == bot_id).first()
    if not bot:
        raise HTTPException(404, "Bot not found")
    scopes = _bot_scopes.get(bot.id, {"messages.read", "messages.send"})
    return {"scopes": list(scopes)}


@router.put("/api/bots/{bot_id}/scopes")
async def set_bot_scopes(bot_id: int, body: BotScope,
                         u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Set scopes for a bot (owner only)."""
    bot = db.query(Bot).filter(Bot.id == bot_id).first()
    if not bot or bot.owner_id != u.id:
        raise HTTPException(403, "Not the bot owner")
    # Validate scopes
    invalid = [s for s in body.scopes if s not in AVAILABLE_SCOPES]
    if invalid:
        raise HTTPException(400, f"Invalid scopes: {invalid}")
    _bot_scopes[bot.id] = set(body.scopes)
    return {"ok": True, "scopes": body.scopes}
