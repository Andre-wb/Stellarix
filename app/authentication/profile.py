"""Профиль пользователя, статус, аватар и утилиты."""
from __future__ import annotations

import os
import re
import secrets

from fastapi import Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import Config
from app.database import get_db
from app.models import PasswordStrengthRequest, UpdateRichStatusRequest, User
from app.security.auth_jwt import get_current_user
from app.security.security_validate import calculate_password_strength

from app.authentication._helpers import router


# ── /me ───────────────────────────────────────────────────────────────────

@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    return {
        "user_id": current_user.id,
        "phone": current_user.phone,
        "username": current_user.username,
        "display_name": current_user.display_name or current_user.username,
        "avatar_emoji": current_user.avatar_emoji,
        "avatar_url": current_user.avatar_url,
        "email": current_user.email,
        "x25519_public_key": current_user.x25519_public_key,
        "kyber_public_key": current_user.kyber_public_key,
        "network_mode": current_user.network_mode or "local",
        "custom_status": current_user.custom_status,
        "status_emoji": current_user.status_emoji,
        "presence": current_user.presence or "online",
        "created_at": current_user.created_at.isoformat() if current_user.created_at else "",
        "last_seen": current_user.last_seen.isoformat() if current_user.last_seen else "",
        "bio": current_user.bio,
        "birth_date": current_user.birth_date,
        "profile_bg": current_user.profile_bg,
        "profile_icon": current_user.profile_icon,
        "reply_color": current_user.reply_color,
        "reply_icon": current_user.reply_icon,
    }


# ── Profile update ────────────────────────────────────────────────────────

class UpdateProfileBody(BaseModel):
    display_name: str | None = None
    avatar_emoji: str | None = None
    email:        str | None = None
    bio:          str | None = None
    birth_date:   str | None = None
    profile_bg:   str | None = None
    profile_icon: str | None = None
    reply_color:  str | None = None
    reply_icon:   str | None = None
    # Solana wallet (base58) to link for Vortex Premium. Set to empty
    # string to unlink. No on-chain ownership check here — production
    # must require a signed challenge. See premium_check.link_wallet for
    # the upgrade path.
    wallet_pubkey: str | None = None


_BIRTH_RE_NO_YEAR = re.compile(r'^--\d{2}-\d{2}$')
_BIRTH_RE_YEAR = re.compile(r'^\d{4}-\d{2}-\d{2}$')


@router.put("/profile")
async def update_profile(body: UpdateProfileBody, u: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    if body.display_name is not None:
        u.display_name = body.display_name.strip()[:100]
    if body.avatar_emoji is not None:
        u.avatar_emoji = body.avatar_emoji[:10]
    if body.email is not None:
        u.email = body.email.strip()[:255] or None
    if body.bio is not None:
        u.bio = body.bio.strip()[:300] or None
    if body.birth_date is not None:
        bd = body.birth_date.strip()
        if bd == "" or _BIRTH_RE_NO_YEAR.match(bd) or _BIRTH_RE_YEAR.match(bd):
            u.birth_date = bd or None
    if body.profile_bg is not None:
        u.profile_bg = body.profile_bg[:120] or None
    if body.profile_icon is not None:
        u.profile_icon = body.profile_icon[:50] or None
    if body.reply_color is not None:
        u.reply_color = body.reply_color[:20] or None
    if body.reply_icon is not None:
        u.reply_icon = body.reply_icon[:10] or None
    if body.wallet_pubkey is not None:
        # Wallet linking moved to a signed-challenge flow to prove the
        # caller actually controls the wallet. Keeping this field
        # write-through would let anyone "steal" someone else's premium
        # by copying their public address into their own profile.
        raise HTTPException(
            410,
            {
                "error": "wallet_pubkey_linking_moved",
                "message": "Use GET /api/premium/challenge + POST /api/premium/link-wallet.",
                "doc": "Sign the returned challenge with Phantom and POST the signature.",
            },
        )
    db.commit()
    return {
        "ok": True,
        "display_name": u.display_name,
        "avatar_emoji": u.avatar_emoji,
        "avatar_url": u.avatar_url,
        "email": u.email,
        "bio": u.bio,
        "birth_date": u.birth_date,
        "profile_bg": u.profile_bg,
        "profile_icon": u.profile_icon,
        "reply_color": u.reply_color,
    }


# ── Rich status ───────────────────────────────────────────────────────────

@router.put("/status")
async def update_rich_status(body: UpdateRichStatusRequest,
                             u: User = Depends(get_current_user),
                             db: Session = Depends(get_db)):
    if body.custom_status is not None:
        u.custom_status = body.custom_status.strip()[:100] or None
    if body.status_emoji is not None:
        u.status_emoji = body.status_emoji[:10] or None
    if body.presence is not None:
        u.presence = body.presence
    db.commit()
    return {
        "ok": True,
        "custom_status": u.custom_status,
        "status_emoji": u.status_emoji,
        "presence": u.presence or "online",
    }


# ── Avatar upload ─────────────────────────────────────────────────────────

@router.post("/avatar")
async def upload_avatar(file: UploadFile = File(...), u: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    from PIL import Image
    import io

    max_size = 5 * 1024 * 1024
    chunks = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size:
            raise HTTPException(413, "Max 5 MB")
        chunks.append(chunk)
    content = b"".join(chunks)

    try:
        img = Image.open(io.BytesIO(content))
        img = img.convert("RGB")
        img.thumbnail((256, 256))
    except Exception:
        raise HTTPException(400, "Invalid image format")

    os.makedirs("uploads/avatars", exist_ok=True)
    filename = f"{secrets.token_hex(16)}.jpg"
    path = f"uploads/avatars/{filename}"
    img.save(path, "JPEG", quality=85)

    u.avatar_url = f"/uploads/avatars/{filename}"
    db.commit()
    return {"ok": True, "avatar_url": u.avatar_url}


# ── Utility endpoints ─────────────────────────────────────────────────────

@router.post("/password-strength")
async def password_strength(body: PasswordStrengthRequest):
    return calculate_password_strength(body.password)


@router.get("/csrf-token")
async def get_csrf_token(request: Request):
    token = getattr(request.state, "csrf_token", None) or request.cookies.get("csrf_token", "")
    return {"csrf_token": token}


@router.get("/registration-info")
async def registration_info():
    """Возвращает режим регистрации (open/invite/closed)."""
    return {
        "mode": Config.REGISTRATION_MODE,
        "invite_required": Config.REGISTRATION_MODE == "invite",
    }
