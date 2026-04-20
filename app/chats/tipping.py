"""DM tipping + per-user donation jar.

On-chain money always requires a client-side signature (the private key
lives in the user's wallet, not on the node). So this module only:

  - Returns the target wallet pubkey + recent payment history
  - Records claimed tips (after the client submits the tx signature)
  - Serves a public /u/{username}/donate page

The node NEVER holds private wallet keys.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.base import Base
from app.database import get_db
from app.models import User
from app.security.auth_jwt import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tipping", tags=["tipping"])


# ── Model (append to the node's SQLite / Postgres on startup) ──────────

class TipEvent(Base):
    """Append-only tip log.

    Written by the client AFTER submitting a Solana transfer — we accept
    the signature as opaque, don't verify on-chain (that's a separate
    indexer task). UI shows them as "pending" / "confirmed" based on
    whether another process later flips the flag.
    """
    __tablename__ = "tip_events"

    id          = Column(Integer, primary_key=True, index=True)
    from_user   = Column(Integer, index=True)           # local user_id
    to_user     = Column(Integer, index=True)           # local user_id (0 if anon donation)
    to_wallet   = Column(String(64), nullable=False)     # Solana pubkey b58
    lamports    = Column(Integer, nullable=False)
    note        = Column(String(200), default="")
    tx_sig      = Column(String(200), index=True)       # base58 sig
    confirmed   = Column(Integer, default=0)            # 0/1
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ── Helpers ─────────────────────────────────────────────────────────────

def _public_profile(u: User) -> dict:
    return {
        "user_id":      u.id,
        "username":     u.username,
        "display_name": u.display_name or u.username,
        "avatar_url":   u.avatar_url,
        "wallet_pubkey": u.wallet_pubkey or "",
        "bio":          (u.bio or "")[:240],
    }


# ── Endpoints (authenticated — DM tipping flow) ─────────────────────────

class TipRecordBody(BaseModel):
    to_user_id: int
    lamports:   int   = Field(..., ge=1, le=1_000_000_000_000)   # up to 1M SOL
    tx_sig:     str   = Field(..., min_length=32, max_length=200)
    note:       str   = Field("", max_length=200)


@router.post("/record")
async def tip_record(
    body: TipRecordBody,
    me:   User = Depends(get_current_user),
    db:   Session = Depends(get_db),
) -> dict:
    """Record a tip after the client has submitted the Solana tx.

    The server stores {from_user, to_user, wallet, lamports, tx_sig}.
    Actual on-chain confirmation can be verified later by any indexer.
    """
    target = db.query(User).filter(User.id == body.to_user_id).first()
    if not target:
        raise HTTPException(404, "target user not found")
    if not target.wallet_pubkey:
        raise HTTPException(400, "target has no wallet_pubkey set")

    ev = TipEvent(
        from_user = me.id,
        to_user   = target.id,
        to_wallet = target.wallet_pubkey,
        lamports  = body.lamports,
        note      = body.note[:200],
        tx_sig    = body.tx_sig,
        confirmed = 0,
    )
    db.add(ev); db.commit(); db.refresh(ev)
    logger.info("tip recorded: %s → %s · %d lamports", me.username, target.username, body.lamports)
    return {
        "ok": True,
        "tip_id":     ev.id,
        "to_wallet":  target.wallet_pubkey,
        "lamports":   body.lamports,
        "amount_sol": body.lamports / 1_000_000_000,
    }


@router.get("/target/{user_id}")
async def tip_target(user_id: int, db: Session = Depends(get_db)) -> dict:
    """Return the wallet info a client needs to send a tip.
    Auth-free so the DM can show the button before opening the thread."""
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(404, "user not found")
    if not u.wallet_pubkey:
        raise HTTPException(400, "user has no wallet pubkey")
    return {
        "user_id":       u.id,
        "username":      u.username,
        "display_name":  u.display_name or u.username,
        "wallet_pubkey": u.wallet_pubkey,
    }


@router.get("/history")
async def tip_history(
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    incoming: bool = True,
    limit: int = 50,
) -> dict:
    limit = max(1, min(limit, 200))
    q = db.query(TipEvent)
    if incoming:
        q = q.filter(TipEvent.to_user == me.id)
    else:
        q = q.filter(TipEvent.from_user == me.id)
    rows = q.order_by(TipEvent.id.desc()).limit(limit).all()
    return {
        "events": [
            {
                "id":         e.id,
                "from_user":  e.from_user,
                "to_user":    e.to_user,
                "to_wallet":  e.to_wallet,
                "lamports":   e.lamports,
                "amount_sol": e.lamports / 1_000_000_000,
                "note":       e.note,
                "tx_sig":     e.tx_sig,
                "confirmed":  bool(e.confirmed),
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in rows
        ]
    }


# ── Public donation jar ─────────────────────────────────────────────────

@router.get("/donate/{username}", response_class=HTMLResponse)
async def donate_page(username: str, db: Session = Depends(get_db)) -> HTMLResponse:
    """Public HTML page with a Donate button. No auth — shareable."""
    u = db.query(User).filter(User.username == username).first()
    if not u or not u.wallet_pubkey:
        raise HTTPException(404, "user not found or no wallet configured")

    # Recent tips — public counts only, no sender usernames.
    recent = (db.query(TipEvent)
              .filter(TipEvent.to_user == u.id, TipEvent.confirmed == 1)
              .order_by(TipEvent.id.desc())
              .limit(10)
              .all())
    total_lamports = sum(e.lamports for e in (db.query(TipEvent)
        .filter(TipEvent.to_user == u.id, TipEvent.confirmed == 1).all()))

    wallet = (u.wallet_pubkey or "").replace("<", "").replace(">", "")
    name   = (u.display_name or u.username).replace("<", "").replace(">", "")
    avatar = u.avatar_url or ""

    # Intentionally minimal HTML — no JS dependencies, zero tracking.
    html = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Donate — {name}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif;
         background: #0b0b0e; color: #eee;
         min-height: 100vh; display: flex; align-items: center; justify-content: center;
         margin: 0; padding: 20px; }}
  .card {{ background: #16161c; border: 1px solid #2a2a33; border-radius: 16px;
          padding: 32px; max-width: 400px; width: 100%; text-align: center; }}
  .avatar {{ width: 84px; height: 84px; border-radius: 50%; background: #333;
            margin: 0 auto 12px; object-fit: cover; }}
  h1 {{ margin: 6px 0; font-size: 22px; font-weight: 600; }}
  .total {{ font-size: 13px; color: #999; margin-bottom: 20px; }}
  .wallet {{ background: #0d0d10; padding: 12px; border-radius: 8px;
            font-family: ui-monospace, Menlo, monospace; font-size: 11px;
            word-break: break-all; border: 1px solid #2a2a33; margin: 16px 0; }}
  .btn-phantom {{ display: inline-block; padding: 14px 22px;
          background: linear-gradient(135deg,#ab9ff2,#5543dd);
          color: #fff; text-decoration: none; border-radius: 10px;
          font-weight: 600; margin: 8px 4px; }}
  .btn-solflare {{ display: inline-block; padding: 14px 22px;
          background: #ff8f00; color: #fff; text-decoration: none;
          border-radius: 10px; font-weight: 600; margin: 8px 4px; }}
  .hint {{ font-size: 11px; color: #666; margin-top: 20px; line-height: 1.5; }}
  .recent {{ margin-top: 24px; text-align: left; font-size: 12px; color: #999; }}
  .recent-row {{ display: flex; justify-content: space-between;
                padding: 6px 0; border-bottom: 1px dashed #2a2a33; }}
</style>
</head><body>
<div class="card">
  <img class="avatar" src="{avatar or '/static/logo-small.png'}" alt="">
  <h1>Donate to {name}</h1>
  <p class="total">Total received: {total_lamports / 1_000_000_000:.4f} SOL</p>

  <div class="wallet">{wallet}</div>

  <a class="btn-phantom"  href="https://phantom.app/ul/v1/solana/transfer?recipient={wallet}">Phantom</a>
  <a class="btn-solflare" href="https://solflare.com/ul/v1/transfer?recipient={wallet}">Solflare</a>

  <div class="recent">
    {"".join(f'<div class="recent-row"><span>{e.created_at.strftime("%Y-%m-%d")}</span><span>{e.lamports/1e9:.3f} SOL</span></div>' for e in recent) or '<em>No donations yet.</em>'}
  </div>

  <p class="hint">
    Powered by <a href="/" style="color:#a78bfa">Vortex</a>. No tracking, no analytics, no cookies.
    Your wallet software handles the transaction — the Vortex server never sees your keys.
  </p>
</div>
</body></html>"""
    return HTMLResponse(content=html)
