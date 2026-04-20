"""Wave 9 — onboarding extensions.

  1. #1  Quickstart     — one-click fresh node with sensible defaults.
  2. #3  Guest login    — generate a guest credential to try a foreign node.
  3. #10 Setup draft    — persist in-progress setup form between sessions.
  4. #33 DHT seed list  — wizard-kept list of seed peers the node can fall
                          back to when the controller is unreachable.
  5. #38 Telegram import — parse result.json from Telegram's export and
                          stage as pending_telegram_import.json for the
                          node to process on next boot.
"""
from __future__ import annotations

import json
import logging
import os
import secrets as _secrets
import time
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from . import backup_api as _b
from . import security_api as _sec
from . import seed_tools as _seed
from . import advanced_net as _anet

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin/onboard", tags=["onboarding"])


def _env_file(request: Request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


# ══════════════════════════════════════════════════════════════════════════
# 1. Quickstart (#1)
# ══════════════════════════════════════════════════════════════════════════

class QuickstartBody(BaseModel):
    device_name: str = Field(..., min_length=1, max_length=60)


@router.post("/quickstart")
async def quickstart(body: QuickstartBody, request: Request) -> dict:
    """Emit the minimum env for a "just works" local-only node.

    - fresh 24-word seed
    - NETWORK_MODE=local, PORT=9000, BMP on
    - NODE_INITIALIZED=true so the wizard flips into admin mode next boot
    Returns the mnemonic exactly once so the caller can show it to the user.
    """
    env_file = _env_file(request)
    from .seed_derive import generate_mnemonic, derive_identity
    mnemonic = generate_mnemonic()
    ident = derive_identity(mnemonic)

    # Persist the signing key at the same path setup_api would use
    keys_dir = env_file.parent / "keys"
    keys_dir.mkdir(parents=True, exist_ok=True)
    sig_path = keys_dir / "ed25519_signing.bin"
    sig_path.write_bytes(ident.node_priv_raw)
    try: os.chmod(sig_path, 0o600)
    except OSError: pass

    _sec._write_env_keys(env_file, {
        "DEVICE_NAME":          body.device_name,
        "NETWORK_MODE":         "local",
        "HOST":                 "127.0.0.1",
        "PORT":                 "9000",
        "KEYS_DIR":             str(keys_dir),
        "NODE_PUBKEY":          ident.node_pubkey_hex,
        "WALLET_PUBKEY":        ident.wallet_pubkey_base58,
        "BMP_DELIVERY_ENABLED": "true",
        "NODE_INITIALIZED":     "true",
        "JWT_SECRET":           _secrets.token_urlsafe(48),
        "CSRF_SECRET":          _secrets.token_urlsafe(48),
    })
    return {
        "ok":       True,
        "mnemonic": mnemonic,    # one-time display
        "pubkey":   ident.node_pubkey_hex,
        "wallet":   ident.wallet_pubkey_base58,
        "note":     "Write down the mnemonic — it will not be shown again.",
    }


# ══════════════════════════════════════════════════════════════════════════
# 2. Guest login (#3)
# ══════════════════════════════════════════════════════════════════════════

class GuestLoginBody(BaseModel):
    peer_url:     str = Field(..., min_length=8, max_length=2048)
    display_name: str = Field(..., min_length=1, max_length=60)


@router.post("/guest")
async def guest_login(body: GuestLoginBody) -> dict:
    """Proxy to /api/federation/guest-login on another node.

    Lets someone try Vortex without running their own node: the wizard
    generates a throwaway username + X25519 pubkey client-side... ok
    actually generating the client identity requires the browser, not
    the wizard. So we just return the proper URL for the SPA to hit.
    """
    url = body.peer_url.rstrip("/") + "/api/federation/guest-login"
    # Probe the peer's health so we don't send the user to a dead URL.
    try:
        async with httpx.AsyncClient(timeout=4.0, verify=False) as c:
            r = await c.get(body.peer_url.rstrip("/") + "/health")
        alive = r.status_code == 200
    except Exception:
        alive = False
    return {
        "endpoint":      url,
        "peer_alive":    alive,
        "display_name":  body.display_name,
        "note":          "Open the URL in your browser and register as guest.",
    }


# ══════════════════════════════════════════════════════════════════════════
# 3. Setup progress saved draft (#10)
# ══════════════════════════════════════════════════════════════════════════

def _draft_path(env_file: Path) -> Path:
    return env_file.parent / "setup_draft.json"


class DraftBody(BaseModel):
    step:  str
    state: dict


@router.get("/draft")
async def draft_get(request: Request) -> dict:
    p = _draft_path(_env_file(request))
    if not p.is_file():
        return {"exists": False}
    try:
        return {"exists": True, **json.loads(p.read_text())}
    except Exception:
        return {"exists": False}


@router.post("/draft")
async def draft_put(body: DraftBody, request: Request) -> dict:
    p = _draft_path(_env_file(request))
    payload = {
        "step":       body.step,
        "state":      body.state,
        "updated_at": int(time.time()),
    }
    p.write_text(json.dumps(payload, indent=2))
    return {"ok": True}


@router.delete("/draft")
async def draft_delete(request: Request) -> dict:
    p = _draft_path(_env_file(request))
    if p.is_file():
        p.unlink()
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
# 4. DHT seed list (#33)
# ══════════════════════════════════════════════════════════════════════════

def _dht_path(env_file: Path) -> Path:
    return env_file.parent / "dht_seeds.json"


def _load_dht(env_file: Path) -> list[dict]:
    p = _dht_path(env_file)
    if not p.is_file():
        return []
    try: return json.loads(p.read_text()).get("seeds", [])
    except Exception: return []


def _save_dht(env_file: Path, seeds: list[dict]) -> None:
    _dht_path(env_file).write_text(json.dumps({"seeds": seeds}, indent=2))


class DhtAddBody(BaseModel):
    url:    str = Field(..., min_length=8, max_length=2048)
    pubkey: Optional[str] = Field(None, max_length=128, pattern=r"^[0-9a-fA-F]+$")
    note:   Optional[str] = Field(None, max_length=200)


@router.get("/dht/seeds")
async def dht_list(request: Request) -> dict:
    return {"seeds": _load_dht(_env_file(request))}


@router.post("/dht/seeds")
async def dht_add(body: DhtAddBody, request: Request) -> dict:
    env_file = _env_file(request)
    seeds = _load_dht(env_file)
    entry = {
        "url":       body.url.strip(),
        "pubkey":    (body.pubkey or "").lower() or None,
        "note":      body.note or "",
        "added_at":  int(time.time()),
    }
    seeds = [s for s in seeds if s.get("url") != entry["url"]] + [entry]
    _save_dht(env_file, seeds)
    return {"ok": True, "total": len(seeds)}


@router.delete("/dht/seeds")
async def dht_clear(request: Request) -> dict:
    _save_dht(_env_file(request), [])
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
# 5. Telegram import (#38)
# ══════════════════════════════════════════════════════════════════════════
#
# Accept Telegram's ``result.json`` (exported via Settings → Export), count
# chats / messages, save as pending_telegram_import.json. The node — when
# it next boots — reads the staged file and creates matching rooms owned
# by the logged-in user. Actual decryption / re-encryption with new
# room_keys happens on the node side (not yet wired; this module just
# stages).

def _tg_pending_path(env_file: Path) -> Path:
    return env_file.parent / "pending_telegram_import.json"


@router.post("/telegram/upload")
async def telegram_upload(
    request: Request,
    file: UploadFile = File(...),
) -> dict:
    data = await file.read()
    if len(data) > 64 * 1024 * 1024:
        raise HTTPException(413, "Telegram export too large (>64 MiB)")
    try:
        parsed = json.loads(data)
    except Exception:
        raise HTTPException(400, "not valid JSON")

    # Sanity: Telegram exports have `chats.list` (array of chat objects).
    chats_list = []
    if isinstance(parsed, dict):
        chats_obj = parsed.get("chats") or {}
        chats_list = chats_obj.get("list") if isinstance(chats_obj, dict) else chats_obj
        if not isinstance(chats_list, list):
            chats_list = []

    n_chats    = len(chats_list)
    n_messages = 0
    sample = []
    for ch in chats_list:
        msgs = ch.get("messages", []) if isinstance(ch, dict) else []
        n_messages += len(msgs)
        if ch.get("name") and len(sample) < 5:
            sample.append({
                "name":     ch.get("name"),
                "type":     ch.get("type"),
                "msg_count": len(msgs),
            })
    if n_chats == 0:
        raise HTTPException(400, "doesn't look like a Telegram result.json (no chats.list)")

    _tg_pending_path(_env_file(request)).write_bytes(data)
    return {
        "ok":         True,
        "chats":      n_chats,
        "messages":   n_messages,
        "sample":     sample,
        "byte_size":  len(data),
    }


@router.get("/telegram/pending")
async def telegram_pending(request: Request) -> dict:
    p = _tg_pending_path(_env_file(request))
    if not p.is_file():
        return {"pending": False}
    return {
        "pending":     True,
        "byte_size":   p.stat().st_size,
        "uploaded_at": int(p.stat().st_mtime),
    }


@router.delete("/telegram/pending")
async def telegram_pending_delete(request: Request) -> dict:
    p = _tg_pending_path(_env_file(request))
    if p.is_file():
        p.unlink()
    return {"ok": True}
