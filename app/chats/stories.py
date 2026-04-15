"""app/chats/stories.py — E2E Encrypted Stories API (24h ephemeral).

Architecture
~~~~~~~~~~~~
1. Author generates random story_key (AES-256, 32 bytes) on client.
2. Author encrypts media + text + meta with story_key (AES-256-GCM).
3. Author wraps story_key for each contact via ECIES:
      wrap(story_key, contact_pub_key) → {ephemeral_pub, ciphertext}
4. Uploads encrypted blobs + list of wrapped keys to server.
5. Server stores blobs as-is (cannot read); stores wrapped keys per viewer.
6. Viewer fetches story, receives their wrapped key, unwraps locally.
7. Server never sees plaintext content or the story_key.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.models_rooms import Story, StoryKeyEnvelope
from app.security.auth_jwt import get_current_user

router = APIRouter(prefix="/api/stories", tags=["stories"])

UPLOAD_DIR = Path("static/uploads/stories")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_SIZE = 50 * 1024 * 1024  # 50 MB


def _dt(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z" if dt else None


def _story_dict(s: Story, u: User, envelope: StoryKeyEnvelope | None = None) -> dict:
    """Serialize a story for the API response."""
    d = {
        "id": s.id,
        "user_id": s.user_id,
        "username": u.username,
        "display_name": u.display_name or u.username,
        "avatar_emoji": u.avatar_emoji,
        "avatar_url": u.avatar_url,
        "media_type": s.media_type,
        "duration": s.duration or 5,
        "views_count": s.views_count or 0,
        "created_at": _dt(s.created_at),
        "expires_at": _dt(s.expires_at),
        "encrypted": bool(s.encrypted),
    }

    if s.encrypted:
        # E2E encrypted — send ciphertext + key envelope
        d["text_ct"] = s.text_ct
        d["meta_ct"] = s.meta_ct
        d["has_media"] = s.media_blob is not None
        d["has_music"] = s.music_blob is not None
        if envelope:
            d["key_envelope"] = {
                "ephemeral_pub": envelope.ephemeral_pub,
                "ciphertext": envelope.ciphertext,
            }
    else:
        # Legacy plaintext (backward compat)
        d["media_url"] = s.media_url
        d["music_url"] = s.music_url
        d["text"] = s.text
        d["text_color"] = s.text_color
        d["bg_color"] = s.bg_color
        d["music_title"] = s.music_title

    return d


@router.get("")
async def get_stories(u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Active stories grouped by user: self first, then contacts."""
    from app.models.contact import Contact

    now_aware = datetime.now(timezone.utc)
    now_naive = now_aware.replace(tzinfo=None)

    contact_ids = [
        c.contact_id
        for c in db.query(Contact).filter(Contact.owner_id == u.id).all()
    ]
    user_ids = list({u.id} | set(contact_ids))

    try:
        stories = (
            db.query(Story)
            .filter(Story.user_id.in_(user_ids), Story.expires_at > now_aware)
            .order_by(Story.user_id, Story.created_at)
            .all()
        )
    except Exception:
        stories = (
            db.query(Story)
            .filter(Story.user_id.in_(user_ids), Story.expires_at > now_naive)
            .order_by(Story.user_id, Story.created_at)
            .all()
        )

    # Batch-load envelopes for current user
    story_ids = [s.id for s in stories]
    envelopes = {}
    if story_ids:
        for env in (
            db.query(StoryKeyEnvelope)
            .filter(StoryKeyEnvelope.story_id.in_(story_ids), StoryKeyEnvelope.user_id == u.id)
            .all()
        ):
            envelopes[env.story_id] = env

    groups: dict[int, dict] = {}
    for s in stories:
        if s.user_id not in groups:
            su = db.query(User).filter(User.id == s.user_id).first()
            if not su:
                continue
            groups[s.user_id] = {
                "user_id": s.user_id,
                "username": su.username,
                "display_name": su.display_name or su.username,
                "avatar_emoji": su.avatar_emoji,
                "avatar_url": su.avatar_url,
                "is_self": s.user_id == u.id,
                "stories": [],
            }
        su = db.query(User).filter(User.id == s.user_id).first()
        if su:
            envelope = envelopes.get(s.id)
            groups[s.user_id]["stories"].append(_story_dict(s, su, envelope))

    result = list(groups.values())
    result.sort(key=lambda x: (not x["is_self"],))
    return {"story_groups": result}


@router.post("", status_code=201)
async def create_story(
    media_type: str = Form(...),
    # Encrypted content (hex-encoded ciphertext from client)
    text_ct: Optional[str] = Form(None),
    meta_ct: Optional[str] = Form(None),
    duration: int = Form(5),
    # ECIES-wrapped story_key for each contact: JSON array of {user_id, ephemeral_pub, ciphertext}
    key_envelopes: str = Form("[]"),
    # Encrypted media/music blobs
    file: Optional[UploadFile] = File(None),
    music_file: Optional[UploadFile] = File(None),
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import json

    if media_type not in ("photo", "video", "text"):
        raise HTTPException(400, "Invalid media_type")

    # Read encrypted blobs (client already encrypted with story_key)
    media_blob = None
    if file:
        media_blob = await file.read()
        if len(media_blob) > MAX_SIZE:
            raise HTTPException(413, "File too large (max 50 MB)")

    music_blob = None
    if music_file:
        music_blob = await music_file.read()
        if len(music_blob) > MAX_SIZE:
            raise HTTPException(413, "Music file too large")

    story = Story(
        user_id=u.id,
        media_type=media_type,
        media_blob=media_blob,
        music_blob=music_blob,
        text_ct=text_ct,
        meta_ct=meta_ct,
        duration=max(1, min(60, duration)),
        encrypted=True,
    )
    db.add(story)
    db.flush()  # get story.id

    # Store ECIES-wrapped story_keys for each contact
    try:
        envs = json.loads(key_envelopes)
    except (json.JSONDecodeError, TypeError):
        envs = []

    for env in envs:
        uid = env.get("user_id")
        eph = env.get("ephemeral_pub", "")
        ct = env.get("ciphertext", "")
        if uid and eph and ct:
            db.add(StoryKeyEnvelope(
                story_id=story.id,
                user_id=uid,
                ephemeral_pub=eph,
                ciphertext=ct,
            ))

    # Also store envelope for self (author needs to view own stories)
    self_env = None
    for env in envs:
        if env.get("user_id") == u.id:
            self_env = env
            break
    # If author didn't include self envelope, they handle it client-side

    db.commit()
    db.refresh(story)

    # Notify contacts about new story via WebSocket
    from app.peer.connection_manager import manager
    from app.models.contact import Contact
    contact_ids = [
        c.contact_id
        for c in db.query(Contact).filter(Contact.owner_id == u.id).all()
    ]
    for cid in contact_ids:
        await manager.notify_user(cid, {
            "type": "new_story",
            "user_id": u.id,
            "username": u.username,
            "display_name": u.display_name or u.username,
            "avatar_emoji": u.avatar_emoji,
            "story_id": story.id,
        })

    return _story_dict(story, u)


@router.get("/{story_id}/media")
async def get_story_media(
    story_id: int,
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download encrypted media blob. Only accessible to authorized viewers."""
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story or not story.media_blob:
        raise HTTPException(404, "Not found")

    # Check access: author or has key envelope
    if story.user_id != u.id:
        has_key = db.query(StoryKeyEnvelope).filter(
            StoryKeyEnvelope.story_id == story_id,
            StoryKeyEnvelope.user_id == u.id,
        ).first()
        if not has_key:
            raise HTTPException(403, "No access")

    from fastapi.responses import Response
    return Response(
        content=story.media_blob,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename=story_{story_id}.enc"},
    )


@router.get("/{story_id}/music")
async def get_story_music(
    story_id: int,
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download encrypted music blob."""
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story or not story.music_blob:
        raise HTTPException(404, "Not found")

    if story.user_id != u.id:
        has_key = db.query(StoryKeyEnvelope).filter(
            StoryKeyEnvelope.story_id == story_id,
            StoryKeyEnvelope.user_id == u.id,
        ).first()
        if not has_key:
            raise HTTPException(403, "No access")

    from fastapi.responses import Response
    return Response(
        content=story.music_blob,
        media_type="application/octet-stream",
    )


@router.delete("/{story_id}")
async def delete_story(
    story_id: int,
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    story = db.query(Story).filter(Story.id == story_id, Story.user_id == u.id).first()
    if not story:
        raise HTTPException(404, "Story not found")

    # Delete legacy files if any
    for url in (story.media_url, story.music_url):
        if url:
            try:
                fname = Path(url).name
                safe_path = (UPLOAD_DIR / fname).resolve()
                if safe_path.parent == UPLOAD_DIR.resolve() and safe_path.exists():
                    safe_path.unlink()
            except Exception:
                pass

    # Delete key envelopes
    db.query(StoryKeyEnvelope).filter(StoryKeyEnvelope.story_id == story_id).delete()
    db.delete(story)
    db.commit()
    return {"ok": True}


@router.post("/{story_id}/view")
async def view_story(
    story_id: int,
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from sqlalchemy import update as sa_update
    db.execute(
        sa_update(Story)
        .where(Story.id == story_id, Story.user_id != u.id)
        .values(views_count=Story.views_count + 1)
    )
    db.commit()
    return {"ok": True}


@router.post("/{story_id}/react")
async def react_to_story(
    story_id: int,
    emoji: str = Form("❤️"),
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(404, "Story not found")
    if story.user_id == u.id:
        raise HTTPException(400, "Cannot react to own story")

    from app.peer.connection_manager import manager
    await manager.notify_user(story.user_id, {
        "type": "story_reaction",
        "story_id": story_id,
        "emoji": emoji[:10],
        "from_user_id": u.id,
        "from_username": u.username,
        "from_display_name": u.display_name or u.username,
        "from_avatar": u.avatar_emoji,
    })
    return {"ok": True}


@router.post("/{story_id}/reply")
async def reply_to_story(
    story_id: int,
    text: str = Form(...),
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(404, "Story not found")
    if story.user_id == u.id:
        raise HTTPException(400, "Cannot reply to own story")

    from app.peer.connection_manager import manager
    await manager.notify_user(story.user_id, {
        "type": "story_reply",
        "story_id": story_id,
        "text": text[:1000],
        "from_user_id": u.id,
        "from_username": u.username,
        "from_display_name": u.display_name or u.username,
        "from_avatar": u.avatar_emoji,
    })
    return {"ok": True}
