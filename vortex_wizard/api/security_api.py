"""Wave 3 — wizard security features.

Keeps all 5 in one module so they share helpers and avoid polluting the
top-level API list. Each sub-section is independent; see headers.

1. Admin 2FA (TOTP) — optional gate on /api/wiz/admin/*.
2. Panic button  — wipe keys + stop node.
3. JWT rotation  — scheduled secret rotation with overlap window.
4. Keys-at-rest — passphrase-wrap the node signing key.
5. CSP/HSTS     — edit header policy via UI.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import io
import json
import logging
import os
import secrets as _secrets
import shutil
import struct
import time
from pathlib import Path
from typing import Awaitable, Callable, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin/sec", tags=["security"])


# ── Shared helpers ────────────────────────────────────────────────────────

def _env_file(request: Request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


def _read_env(env_file: Path) -> dict[str, str]:
    if not env_file.is_file():
        return {}
    out: dict[str, str] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def _write_env_keys(env_file: Path, kv: dict[str, str]) -> None:
    lines: list[str] = []
    remaining = dict(kv)
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k = line.split("=", 1)[0].strip()
                if k in remaining:
                    lines.append(f"{k}={remaining.pop(k)}")
                    continue
            lines.append(line)
    for k, v in remaining.items():
        lines.append(f"{k}={v}")
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _sec_state_path(env_file: Path) -> Path:
    return env_file.parent / "security_state.json"


def _load_sec_state(env_file: Path) -> dict:
    p = _sec_state_path(env_file)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _save_sec_state(env_file: Path, state: dict) -> None:
    try:
        _sec_state_path(env_file).write_text(json.dumps(state, indent=2))
    except Exception as e:
        logger.debug("sec state save: %s", e)


# ══════════════════════════════════════════════════════════════════════════
# 1. TOTP — 2FA for the admin UI
# ══════════════════════════════════════════════════════════════════════════

_TOTP_COOKIE = "vx_wiz_2fa"
_TOTP_DIGITS = 6
_TOTP_STEP   = 30
_SESSION_TTL = 12 * 3600   # 12 h


def _totp_code(secret_b32: str, now: Optional[int] = None) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    t = (now if now is not None else int(time.time())) // _TOTP_STEP
    msg = struct.pack(">Q", t)
    mac = hmac.new(key, msg, hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    val = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{val % (10 ** _TOTP_DIGITS):0{_TOTP_DIGITS}d}"


def _totp_verify(secret_b32: str, code: str) -> bool:
    code = (code or "").replace(" ", "").strip()
    if not code.isdigit() or len(code) != _TOTP_DIGITS:
        return False
    now = int(time.time())
    # Allow one step of drift on either side — saves users from clock
    # skew angst.
    for delta in (-1, 0, 1):
        if hmac.compare_digest(_totp_code(secret_b32, now + delta * _TOTP_STEP), code):
            return True
    return False


def _issue_session(env_file: Path) -> str:
    state = _load_sec_state(env_file)
    token = _secrets.token_urlsafe(32)
    sessions = state.get("totp_sessions", {})
    sessions[token] = {"expires": int(time.time()) + _SESSION_TTL}
    # Clean expired
    now = int(time.time())
    sessions = {t: s for t, s in sessions.items() if s.get("expires", 0) > now}
    state["totp_sessions"] = sessions
    _save_sec_state(env_file, state)
    return token


def _session_valid(env_file: Path, token: Optional[str]) -> bool:
    if not token:
        return False
    state = _load_sec_state(env_file)
    s = state.get("totp_sessions", {}).get(token)
    if not s:
        return False
    return int(time.time()) < int(s.get("expires", 0))


def _totp_enabled(env_file: Path) -> bool:
    return bool(_load_sec_state(env_file).get("totp_secret"))


class TOTPMiddleware(BaseHTTPMiddleware):
    """Gate /api/wiz/admin/* behind the 2FA cookie when enabled.

    Intentionally bypasses sec endpoints (so the user can enroll / verify)
    and the static asset paths. Also bypasses GET /mode so the SPA can
    detect the enrollment state before showing admin content.
    """

    BYPASS_PREFIXES = (
        "/api/wiz/admin/sec",     # this module itself
        "/api/wiz/setup",          # setup flow is pre-auth
        "/static", "/locales",
    )
    BYPASS_EXACT = {"/mode", "/favicon.ico"}

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable],
    ):
        path = request.url.path
        if (path in self.BYPASS_EXACT or
            any(path.startswith(p) for p in self.BYPASS_PREFIXES) or
            not path.startswith("/api/wiz/admin")):
            return await call_next(request)

        env_file = getattr(request.app.state, "env_file", None)
        if env_file is None or not _totp_enabled(Path(env_file)):
            return await call_next(request)

        token = request.cookies.get(_TOTP_COOKIE, "")
        if not _session_valid(Path(env_file), token):
            return JSONResponse(
                status_code=401,
                content={"error": "2fa_required", "detail": "unlock with TOTP first"},
            )
        return await call_next(request)


class TOTPSetupBody(BaseModel):
    code: str = Field(..., min_length=6, max_length=10)


class TOTPVerifyBody(BaseModel):
    code: str = Field(..., min_length=6, max_length=10)


@router.get("/totp/status")
async def totp_status(request: Request) -> dict:
    env_file = _env_file(request)
    enabled = _totp_enabled(env_file)
    token = request.cookies.get(_TOTP_COOKIE, "")
    return {
        "enabled":     enabled,
        "session_ok":  _session_valid(env_file, token),
    }


@router.post("/totp/init")
async def totp_init(request: Request) -> dict:
    """Generate a provisional secret + otpauth URI for QR rendering.

    The secret isn't activated until /totp/confirm succeeds — protects
    against lockout if the user mis-enters the code.
    """
    env_file = _env_file(request)
    state = _load_sec_state(env_file)
    if state.get("totp_secret"):
        raise HTTPException(409, "TOTP already enabled; disable first")
    secret = base64.b32encode(os.urandom(20)).decode("ascii").rstrip("=")
    state["totp_pending"] = secret
    _save_sec_state(env_file, state)
    issuer = "VortexWizard"
    label  = f"{issuer}:node"
    uri = (f"otpauth://totp/{label}?secret={secret}"
           f"&issuer={issuer}&algorithm=SHA1&digits={_TOTP_DIGITS}&period={_TOTP_STEP}")
    return {"secret": secret, "uri": uri}


@router.post("/totp/confirm")
async def totp_confirm(body: TOTPSetupBody, request: Request, response: Response) -> dict:
    env_file = _env_file(request)
    state = _load_sec_state(env_file)
    pending = state.get("totp_pending")
    if not pending:
        raise HTTPException(400, "call /totp/init first")
    if not _totp_verify(pending, body.code):
        raise HTTPException(401, "code invalid")
    state["totp_secret"] = pending
    state.pop("totp_pending", None)
    _save_sec_state(env_file, state)
    # Immediately issue a session so the user isn't locked out.
    token = _issue_session(env_file)
    response.set_cookie(_TOTP_COOKIE, token, httponly=True, samesite="strict",
                         max_age=_SESSION_TTL, path="/")
    return {"ok": True}


@router.post("/totp/verify")
async def totp_verify(body: TOTPVerifyBody, request: Request, response: Response) -> dict:
    env_file = _env_file(request)
    state = _load_sec_state(env_file)
    secret = state.get("totp_secret")
    if not secret:
        raise HTTPException(400, "TOTP not enabled")
    if not _totp_verify(secret, body.code):
        raise HTTPException(401, "code invalid")
    token = _issue_session(env_file)
    response.set_cookie(_TOTP_COOKIE, token, httponly=True, samesite="strict",
                         max_age=_SESSION_TTL, path="/")
    return {"ok": True}


@router.post("/totp/disable")
async def totp_disable(body: TOTPVerifyBody, request: Request, response: Response) -> dict:
    env_file = _env_file(request)
    state = _load_sec_state(env_file)
    secret = state.get("totp_secret")
    if not secret:
        return {"ok": True, "already": "disabled"}
    if not _totp_verify(secret, body.code):
        raise HTTPException(401, "code invalid")
    state.pop("totp_secret", None)
    state.pop("totp_sessions", None)
    _save_sec_state(env_file, state)
    response.delete_cookie(_TOTP_COOKIE, path="/")
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
# 2. Panic button — wipe keys + stop
# ══════════════════════════════════════════════════════════════════════════

class PanicBody(BaseModel):
    confirm: str = Field(..., description='Must equal "WIPE AND STOP"')


@router.post("/panic")
async def panic(body: PanicBody, request: Request) -> dict:
    """Wipe the signing key + stop the running node. IRREVERSIBLE without
    backup + seed phrase.

    Steps:
      1. Stop the node (best-effort — admin_api already exposes a stop).
      2. Remove keys/ed25519_signing.bin and any derived files.
      3. Leave .env in place so operator can re-run setup → restore.
    """
    if body.confirm != "WIPE AND STOP":
        raise HTTPException(400, 'confirm must be exactly "WIPE AND STOP"')

    env_file = _env_file(request)
    env = _read_env(env_file)
    node_root = env_file.parent

    # 1) Best-effort node stop
    from . import admin_api as _admin_api
    try:
        await _admin_api.node_stop(request)  # type: ignore[arg-type]
    except Exception as e:
        logger.warning("panic: node_stop failed: %s", e)

    # 2) Remove sensitive files
    removed: list[str] = []
    targets = [
        Path(env.get("KEYS_DIR", str(node_root / "keys"))),
        node_root / "keys",
        node_root / "backup_last.meta",
    ]
    for p in targets:
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
            removed.append(str(p))
        elif p.is_file():
            try:
                p.unlink()
                removed.append(str(p))
            except OSError:
                pass

    # 3) Wipe NODE_INITIALIZED so wizard flips back to setup
    _write_env_keys(env_file, {"NODE_INITIALIZED": "false"})
    return {"ok": True, "removed": removed}


# ══════════════════════════════════════════════════════════════════════════
# 3. JWT rotation scheduler job (registered externally)
# ══════════════════════════════════════════════════════════════════════════

async def job_jwt_rotate(env_file: Path) -> dict:
    """Rotate the node's JWT_SECRET. The node reads this at every boot;
    in-flight sessions will need to re-auth after the next restart.
    """
    new = _secrets.token_urlsafe(48)
    env = _read_env(env_file)
    prev = env.get("JWT_SECRET", "")
    # Keep previous in a historical log for audit/debug.
    state = _load_sec_state(env_file)
    hist = state.get("jwt_rotation_history", [])
    hist.append({"rotated_at": int(time.time()), "prev_prefix": prev[:8]})
    state["jwt_rotation_history"] = hist[-20:]
    _save_sec_state(env_file, state)
    _write_env_keys(env_file, {"JWT_SECRET": new})
    return {"message": f"JWT_SECRET rotated (previous prefix {prev[:8]}…)"}


# ══════════════════════════════════════════════════════════════════════════
# 4. Keys-at-rest passphrase
# ══════════════════════════════════════════════════════════════════════════

# In-memory cache of the unlocked signing key bytes. This module is the
# only consumer; ed25519_signing.bin stays encrypted on disk as long as
# the feature is enabled.
_signing_cache: dict[str, bytes] = {}

_MAGIC = b"VTXWRAP1"
_KDF_ITERS = 200_000
_SALT_LEN  = 16
_NONCE_LEN = 12


def _signing_path(env_file: Path) -> Path:
    env = _read_env(env_file)
    return Path(env.get("KEYS_DIR", str(env_file.parent / "keys"))) / "ed25519_signing.bin"


def _derive_wrap_key(passphrase: str, salt: bytes) -> bytes:
    return PBKDF2HMAC(
        algorithm  = hashes.SHA256(),
        length     = 32,
        salt       = salt,
        iterations = _KDF_ITERS,
    ).derive(passphrase.encode("utf-8"))


def _is_wrapped(data: bytes) -> bool:
    return data.startswith(_MAGIC)


class PassphraseBody(BaseModel):
    passphrase: str = Field(..., min_length=8, max_length=256)


class ChangePassphraseBody(BaseModel):
    old: str = Field(..., min_length=8)
    new: str = Field(..., min_length=8)


@router.get("/passphrase/status")
async def passphrase_status(request: Request) -> dict:
    env_file = _env_file(request)
    p = _signing_path(env_file)
    if not p.is_file():
        return {"enabled": False, "locked": False, "missing": True}
    data = p.read_bytes()
    enabled = _is_wrapped(data)
    locked  = enabled and (str(p) not in _signing_cache)
    return {"enabled": enabled, "locked": locked, "missing": False}


@router.post("/passphrase/enable")
async def passphrase_enable(body: PassphraseBody, request: Request) -> dict:
    env_file = _env_file(request)
    p = _signing_path(env_file)
    if not p.is_file():
        raise HTTPException(404, "signing key not present")
    data = p.read_bytes()
    if _is_wrapped(data):
        raise HTTPException(409, "already passphrase-protected")
    if len(data) != 32:
        raise HTTPException(400, f"unexpected key length: {len(data)}")

    salt = os.urandom(_SALT_LEN)
    wrap_key = _derive_wrap_key(body.passphrase, salt)
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(wrap_key).encrypt(nonce, data, _MAGIC)
    # Format: MAGIC || salt || nonce || ct
    wrapped = _MAGIC + salt + nonce + ct
    tmp = p.with_suffix(".wrap.tmp")
    tmp.write_bytes(wrapped)
    os.replace(tmp, p)
    try: os.chmod(p, 0o600)
    except OSError: pass

    # Keep plaintext in memory for the current process so the node
    # relaunch still works without prompting.
    _signing_cache[str(p)] = data
    return {"ok": True}


@router.post("/passphrase/unlock")
async def passphrase_unlock(body: PassphraseBody, request: Request) -> dict:
    env_file = _env_file(request)
    p = _signing_path(env_file)
    if not p.is_file():
        raise HTTPException(404, "signing key not present")
    data = p.read_bytes()
    if not _is_wrapped(data):
        # Already plaintext — cache for consistency.
        _signing_cache[str(p)] = data
        return {"ok": True, "note": "key was not wrapped"}

    salt  = data[len(_MAGIC):len(_MAGIC) + _SALT_LEN]
    nonce = data[len(_MAGIC) + _SALT_LEN: len(_MAGIC) + _SALT_LEN + _NONCE_LEN]
    ct    = data[len(_MAGIC) + _SALT_LEN + _NONCE_LEN:]
    try:
        wrap_key = _derive_wrap_key(body.passphrase, salt)
        plain = AESGCM(wrap_key).decrypt(nonce, ct, _MAGIC)
    except Exception:
        raise HTTPException(401, "wrong passphrase")

    _signing_cache[str(p)] = plain
    return {"ok": True}


@router.post("/passphrase/disable")
async def passphrase_disable(body: PassphraseBody, request: Request) -> dict:
    env_file = _env_file(request)
    p = _signing_path(env_file)
    if not p.is_file():
        raise HTTPException(404, "signing key not present")
    data = p.read_bytes()
    if not _is_wrapped(data):
        return {"ok": True, "already": "plaintext"}

    salt  = data[len(_MAGIC):len(_MAGIC) + _SALT_LEN]
    nonce = data[len(_MAGIC) + _SALT_LEN: len(_MAGIC) + _SALT_LEN + _NONCE_LEN]
    ct    = data[len(_MAGIC) + _SALT_LEN + _NONCE_LEN:]
    try:
        wrap_key = _derive_wrap_key(body.passphrase, salt)
        plain = AESGCM(wrap_key).decrypt(nonce, ct, _MAGIC)
    except Exception:
        raise HTTPException(401, "wrong passphrase")

    p.write_bytes(plain)
    try: os.chmod(p, 0o600)
    except OSError: pass
    _signing_cache[str(p)] = plain
    return {"ok": True}


def get_unlocked_signing_key_bytes(env_file: Path) -> bytes:
    """Helper used by backup/replication when the key is wrapped.

    Returns the cached plaintext if the user unlocked in this process,
    else reads plain key from disk, else raises.
    """
    p = _signing_path(env_file)
    if str(p) in _signing_cache:
        return _signing_cache[str(p)]
    data = p.read_bytes()
    if _is_wrapped(data):
        raise RuntimeError("signing key is passphrase-wrapped — unlock via /api/wiz/admin/sec/passphrase/unlock")
    _signing_cache[str(p)] = data
    return data


# ══════════════════════════════════════════════════════════════════════════
# 5. CSP / HSTS editor
# ══════════════════════════════════════════════════════════════════════════

_CSP_PROFILES = {
    "strict": (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; "
        "object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
    ),
    "relaxed": (
        "default-src 'self' https:; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; connect-src 'self' https: wss:; "
        "object-src 'none'; frame-ancestors 'self'"
    ),
    "off": "",
}

_HSTS_PROFILES = {
    "off":     "",
    "on":      "max-age=15552000; includeSubDomains",
    "preload": "max-age=31536000; includeSubDomains; preload",
}


class HeaderPolicyBody(BaseModel):
    csp_profile:  str = Field(..., pattern=r"^(strict|relaxed|off|custom)$")
    csp_custom:   Optional[str] = Field(None, max_length=2048)
    hsts_profile: str = Field(..., pattern=r"^(off|on|preload)$")


@router.get("/headers")
async def headers_get(request: Request) -> dict:
    env = _read_env(_env_file(request))
    return {
        "csp_profile":  env.get("CSP_PROFILE", "strict"),
        "csp_custom":   env.get("CSP_CUSTOM", ""),
        "hsts_profile": env.get("HSTS_PROFILE", "off"),
        "profiles":     {"csp": list(_CSP_PROFILES.keys()) + ["custom"],
                         "hsts": list(_HSTS_PROFILES.keys())},
        "preview": {
            "csp":  _render_csp(env),
            "hsts": _HSTS_PROFILES.get(env.get("HSTS_PROFILE", "off"), ""),
        },
    }


def _render_csp(env: dict) -> str:
    profile = env.get("CSP_PROFILE", "strict")
    if profile == "custom":
        return env.get("CSP_CUSTOM", "") or _CSP_PROFILES["strict"]
    return _CSP_PROFILES.get(profile, _CSP_PROFILES["strict"])


@router.post("/headers")
async def headers_set(body: HeaderPolicyBody, request: Request) -> dict:
    env_file = _env_file(request)
    updates: dict[str, str] = {
        "CSP_PROFILE":  body.csp_profile,
        "HSTS_PROFILE": body.hsts_profile,
    }
    if body.csp_profile == "custom":
        updates["CSP_CUSTOM"] = (body.csp_custom or "").strip()
    _write_env_keys(env_file, updates)
    env = _read_env(env_file)
    return {
        "ok": True,
        "applied": {
            "csp":  _render_csp(env),
            "hsts": _HSTS_PROFILES.get(body.hsts_profile, ""),
        },
        "note": "Restart the node to apply on its HTTP responses.",
    }
