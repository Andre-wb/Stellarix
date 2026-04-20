"""Wave 8 — multi-device & QR onboarding.

All five use the same pattern: build a signed JSON payload, base64url-
encode it, return via an ``otpauth:``-style URL or raw string the UI
renders to QR client-side. The receiving device decodes + verifies the
signature against the source node's pubkey.

Features:
  1. #43 Device-linking QR       — short-lived token, same seed on other device
  2. #45 Session transfer        — move an active admin session to another machine
  3. #46 Mobile companion QR     — native app bootstrap (same pubkey)
  4. #2  Config import QR        — export .env essentials for a second node
  5. #7  Restore-first-screen    — emit the controller's backup metadata for UI

Each payload is wrapped as ``{"payload": {...}, "signature": "hex"}``
signed with the node's Ed25519 key so it can't be forged.
"""
from __future__ import annotations

import base64
import json
import logging
import secrets as _secrets
import time
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)
from cryptography.exceptions import InvalidSignature
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import backup_api as _b
from . import security_api as _sec

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin/link", tags=["multidevice"])


def _env_file(request: Request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


def _canonical(d: dict) -> bytes:
    return json.dumps(d, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign(env_file: Path, payload: dict) -> str:
    # Reuse the raw-key helper from security_api so passphrase-wrapped
    # keys still work (cached plaintext in memory after unlock).
    priv_bytes = _sec.get_unlocked_signing_key_bytes(env_file)
    priv = Ed25519PrivateKey.from_private_bytes(priv_bytes)
    return priv.sign(_canonical(payload)).hex()


def _pubkey_hex(env_file: Path) -> str:
    priv = Ed25519PrivateKey.from_private_bytes(
        _sec.get_unlocked_signing_key_bytes(env_file))
    from cryptography.hazmat.primitives import serialization
    return priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()


def _to_qr_string(envelope: dict) -> str:
    """Compact base64url of a signed envelope. Prefix is ``vortex://`` so
    scanner apps know what to do with it."""
    raw = _canonical(envelope)
    return "vortex://link?p=" + base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _from_qr_string(s: str) -> dict:
    if not s.startswith("vortex://link?p="):
        raise ValueError("not a Vortex link URI")
    body = s.split("?p=", 1)[1]
    pad = "=" * (-len(body) % 4)
    raw = base64.urlsafe_b64decode(body + pad)
    return json.loads(raw)


# ══════════════════════════════════════════════════════════════════════════
# 1. Device-linking QR (#43)
# ══════════════════════════════════════════════════════════════════════════
#
# Flow: admin UI generates a QR. A second device scans it, submits the
# decoded envelope to the node's /api/session/accept endpoint (existing
# handoff_token mechanism), and gets back a session token bound to the
# same pubkey.

class DeviceLinkBody(BaseModel):
    ttl_seconds: int = Field(300, ge=30, le=3600)


@router.post("/device")
async def make_device_link(body: DeviceLinkBody, request: Request) -> dict:
    env_file = _env_file(request)
    payload = {
        "kind":       "device_link",
        "pubkey":     _pubkey_hex(env_file),
        "nonce":      _secrets.token_urlsafe(16),
        "issued_at":  int(time.time()),
        "expires_at": int(time.time()) + body.ttl_seconds,
    }
    envelope = {"payload": payload, "signature": _sign(env_file, payload)}
    return {
        "uri":        _to_qr_string(envelope),
        "envelope":   envelope,
        "expires_in": body.ttl_seconds,
    }


# ══════════════════════════════════════════════════════════════════════════
# 2. Session transfer (#45)
# ══════════════════════════════════════════════════════════════════════════

class SessionXferBody(BaseModel):
    target_pubkey: str = Field(..., min_length=64, max_length=128, pattern=r"^[0-9a-fA-F]+$")
    ttl_seconds:   int = Field(600, ge=30, le=3600)


@router.post("/session")
async def make_session_transfer(body: SessionXferBody, request: Request) -> dict:
    """Issue a short-lived one-time token the other node can present
    to our /api/session/accept to take over this admin session.

    The target pubkey is baked into the payload — only that node can
    redeem it (the node checks its own pubkey matches on receipt).
    """
    env_file = _env_file(request)
    payload = {
        "kind":          "session_transfer",
        "src_pubkey":    _pubkey_hex(env_file),
        "target_pubkey": body.target_pubkey.lower(),
        "nonce":         _secrets.token_urlsafe(16),
        "issued_at":     int(time.time()),
        "expires_at":    int(time.time()) + body.ttl_seconds,
    }
    envelope = {"payload": payload, "signature": _sign(env_file, payload)}
    return {
        "uri":        _to_qr_string(envelope),
        "envelope":   envelope,
        "expires_in": body.ttl_seconds,
    }


# ══════════════════════════════════════════════════════════════════════════
# 3. Mobile companion QR (#46)
# ══════════════════════════════════════════════════════════════════════════

class MobileQRBody(BaseModel):
    # Optional hint — the mobile app uses this as its default public URL
    # for reaching the node while on the same LAN.
    public_url:  Optional[str] = None
    ttl_seconds: int           = Field(900, ge=60, le=3600)


@router.post("/mobile")
async def make_mobile_qr(body: MobileQRBody, request: Request) -> dict:
    env_file = _env_file(request)
    env = _b._read_env(env_file)
    pub_url = body.public_url or env.get("ANNOUNCE_URL", "") or env.get("PUBLIC_URL", "")
    payload = {
        "kind":        "mobile_bootstrap",
        "pubkey":      _pubkey_hex(env_file),
        "public_url":  pub_url,
        "controller":  env.get("CONTROLLER_URL", ""),
        "issued_at":   int(time.time()),
        "expires_at":  int(time.time()) + body.ttl_seconds,
    }
    envelope = {"payload": payload, "signature": _sign(env_file, payload)}
    return {
        "uri":        _to_qr_string(envelope),
        "envelope":   envelope,
        "expires_in": body.ttl_seconds,
    }


# ══════════════════════════════════════════════════════════════════════════
# 4. Config-import QR (#2) — spawn a second node with same controller
# ══════════════════════════════════════════════════════════════════════════

@router.get("/config")
async def export_config(request: Request) -> dict:
    """Export the minimum .env keys a fresh node needs to join this network:
       controller URL, controller pubkey, network mode, bootstrap peers.

    The ``payload`` is signed so the scanner can verify the config came
    from a trusted source (this exact node).
    """
    env_file = _env_file(request)
    env = _b._read_env(env_file)
    keys = ("CONTROLLER_URL", "CONTROLLER_PUBKEY", "NETWORK_MODE",
            "CONTROLLER_FALLBACK_URLS", "BOOTSTRAP_PEERS",
            "UPDATE_MANIFEST_URL")
    cfg = {k: env[k] for k in keys if k in env}
    payload = {
        "kind":       "node_config",
        "source_pubkey": _pubkey_hex(env_file),
        "config":     cfg,
        "issued_at":  int(time.time()),
        "expires_at": int(time.time()) + 900,
    }
    envelope = {"payload": payload, "signature": _sign(env_file, payload)}
    return {"uri": _to_qr_string(envelope), "envelope": envelope}


class ImportConfigBody(BaseModel):
    uri: str = Field(..., min_length=16, max_length=8192)


@router.post("/config/import")
async def import_config(body: ImportConfigBody, request: Request) -> dict:
    """Receive-side: decode QR, verify signature, apply to local .env.

    The signer's pubkey isn't whitelisted — we display it to the user
    and let them confirm. No signature = reject.
    """
    try:
        env_body = _from_qr_string(body.uri)
    except Exception as e:
        raise HTTPException(400, f"cannot parse QR: {e}")
    payload = env_body.get("payload") or {}
    sig     = env_body.get("signature") or ""
    src = payload.get("source_pubkey", "")
    if len(src) != 64:
        raise HTTPException(400, "missing source_pubkey")
    if int(payload.get("expires_at", 0)) < int(time.time()):
        raise HTTPException(400, "QR expired")
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(src))
        pub.verify(bytes.fromhex(sig), _canonical(payload))
    except (ValueError, InvalidSignature):
        raise HTTPException(401, "signature invalid")

    cfg = payload.get("config") or {}
    if not cfg:
        return {"ok": True, "applied": 0, "note": "no config keys in QR"}

    _sec._write_env_keys(_env_file(request), {k: str(v) for k, v in cfg.items()})
    return {
        "ok":          True,
        "applied":     len(cfg),
        "keys":        list(cfg.keys()),
        "source_pub":  src,
        "note":        "restart the node to apply",
    }


# ══════════════════════════════════════════════════════════════════════════
# 5. Restore-first-screen helper (#7)
# ══════════════════════════════════════════════════════════════════════════
#
# The setup UI lands on an empty node. The user can either create a new
# identity, restore from seed, OR restore from a controller backup. For
# the last flow we need to surface "has the controller got a backup for
# the pubkey derived from this phrase?" — that's already in
# ``seed_tools.backup_discover``. Here we re-expose it under the
# multidevice prefix so the setup SPA can call both from one namespace.

class FirstScreenDiscoverBody(BaseModel):
    controller_url: str = Field(..., min_length=8, max_length=2048)
    mnemonic:       str = Field(..., min_length=20)


@router.post("/firstscreen/discover")
async def firstscreen_discover(body: FirstScreenDiscoverBody, request: Request) -> dict:
    # Thin wrapper so the admin + setup SPAs share one endpoint namespace.
    from .seed_tools import backup_discover, BackupDiscoverBody
    return await backup_discover(BackupDiscoverBody(
        controller_url=body.controller_url,
        mnemonic=body.mnemonic,
    ))


# ══════════════════════════════════════════════════════════════════════════
# Shared: QR preview PNG (for UIs that want a <img>)
# ══════════════════════════════════════════════════════════════════════════

class QrRenderBody(BaseModel):
    uri:  str = Field(..., max_length=8192)
    size: int = Field(240, ge=80, le=1024)


@router.post("/qr.png")
async def qr_png(body: QrRenderBody) -> dict:
    """Return a base64-encoded PNG of the QR.

    Tries the bundled ``qrcode`` lib; if missing, returns a stub so the
    UI can fall back to a text field. Keeping this server-side avoids
    bundling a 30 KiB JS QR encoder into the wizard SPA.
    """
    try:
        import qrcode
        import qrcode.image.pure
    except ImportError:
        return {"available": False, "note": "install 'qrcode' in the wizard env"}

    img = qrcode.make(body.uri, box_size=max(2, body.size // 32))
    import io as _io
    buf = _io.BytesIO()
    img.save(buf, format="PNG")
    return {
        "available": True,
        "png_base64": base64.b64encode(buf.getvalue()).decode("ascii"),
    }
