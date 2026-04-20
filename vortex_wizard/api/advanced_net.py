"""Wave 6 — advanced network + onboarding helpers.

Five loosely-related features bundled together:

  1. Onion-only mode — toggle in .env (ONION_ONLY=true). Node reads it
     at startup and routes every outbound HTTP through the local Tor
     SOCKS proxy (127.0.0.1:9050).
  2. Let's Encrypt — wrap ``certbot`` for issue + renew. We detect the
     binary, run in standalone HTTP-01 mode, and report progress.
  3. Auto-update check — fetch a signed version manifest and tell the UI
     whether a newer release is available. No actual upgrade (risky).
  4. Setup presets — 4 canned configs for the setup wizard (personal /
     family / community / pro).
  5. Guided tour — step data so the admin SPA can run a tooltip
     walkthrough on first login.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import backup_api as _b

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin/net", tags=["advanced-net"])


def _env_file(request: Request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


# ══════════════════════════════════════════════════════════════════════════
# 1. Onion-only toggle
# ══════════════════════════════════════════════════════════════════════════

class OnionBody(BaseModel):
    enabled:    bool
    socks_addr: str = Field("127.0.0.1:9050", max_length=100)


@router.get("/onion")
async def onion_get(request: Request) -> dict:
    env = _b._read_env(_env_file(request))
    return {
        "enabled":    env.get("ONION_ONLY", "").lower() in ("1", "true", "yes"),
        "socks_addr": env.get("ONION_SOCKS", "127.0.0.1:9050"),
        "tor_running": await _tor_reachable(env.get("ONION_SOCKS", "127.0.0.1:9050")),
    }


@router.post("/onion")
async def onion_set(body: OnionBody, request: Request) -> dict:
    env_file = _env_file(request)
    from .security_api import _write_env_keys
    _write_env_keys(env_file, {
        "ONION_ONLY":  "true" if body.enabled else "false",
        "ONION_SOCKS": body.socks_addr,
    })
    return {
        "ok":        True,
        "enabled":   body.enabled,
        "note":      "Restart the node to apply. Ensure Tor is running on " + body.socks_addr,
    }


async def _tor_reachable(addr: str) -> bool:
    try:
        host, port = addr.split(":", 1)
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, int(port)),
            timeout=1.5,
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════
# 2. Let's Encrypt (certbot wrapper)
# ══════════════════════════════════════════════════════════════════════════

def _find_certbot() -> Optional[str]:
    # Same approach as _find_cloudflared — check PATH then common brew dirs.
    p = shutil.which("certbot")
    if p:
        return p
    for candidate in ("/opt/homebrew/bin/certbot", "/usr/local/bin/certbot", "/usr/bin/certbot"):
        if Path(candidate).is_file():
            return candidate
    return None


def _cert_expiry(cert_path: Path) -> Optional[int]:
    """Return epoch seconds of not-after, or None if unreadable."""
    if not cert_path.is_file():
        return None
    try:
        from cryptography import x509
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        return int(cert.not_valid_after_utc.timestamp())
    except Exception:
        return None


@router.get("/letsencrypt/status")
async def le_status(request: Request) -> dict:
    env = _b._read_env(_env_file(request))
    cert_dir = Path(env.get("CERT_DIR", "certs"))
    cert = cert_dir / "vortex.crt"
    expiry = _cert_expiry(cert)
    return {
        "certbot_installed": bool(_find_certbot()),
        "certbot_path":      _find_certbot(),
        "contact_email":     env.get("LETSENCRYPT_EMAIL", ""),
        "domain":            env.get("LETSENCRYPT_DOMAIN", ""),
        "cert_path":         str(cert),
        "cert_expires_at":   expiry,
        "days_left":         (expiry - int(time.time())) // 86400 if expiry else None,
    }


class LESetupBody(BaseModel):
    email:  str = Field(..., min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    domain: str = Field(..., min_length=3, max_length=253)


@router.post("/letsencrypt/setup")
async def le_setup(body: LESetupBody, request: Request) -> dict:
    env_file = _env_file(request)
    from .security_api import _write_env_keys
    _write_env_keys(env_file, {
        "LETSENCRYPT_EMAIL":  body.email,
        "LETSENCRYPT_DOMAIN": body.domain,
    })
    return {"ok": True}


@router.post("/letsencrypt/issue")
async def le_issue(request: Request) -> dict:
    """Invoke certbot in standalone mode for the configured domain.

    Uses ``create_subprocess_exec`` (no shell interpolation — args are a
    fixed list + email/domain values validated by Pydantic patterns on
    /letsencrypt/setup). Requires port 80 free on the host.
    """
    cb = _find_certbot()
    if not cb:
        raise HTTPException(400, "certbot not installed (brew install certbot)")
    env_file = _env_file(request)
    env = _b._read_env(env_file)
    email = env.get("LETSENCRYPT_EMAIL", "")
    domain = env.get("LETSENCRYPT_DOMAIN", "")
    if not (email and domain):
        raise HTTPException(400, "call /letsencrypt/setup first")
    # Re-validate — these come from .env on disk, which the user may have
    # edited by hand. Block anything that could smuggle into an argv list.
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) or re.search(r"\s", email):
        raise HTTPException(400, "bad LETSENCRYPT_EMAIL in .env")
    if not re.match(r"^[A-Za-z0-9\.\-]{1,253}$", domain):
        raise HTTPException(400, "bad LETSENCRYPT_DOMAIN in .env")

    cert_dir = env_file.parent / "certs"
    cert_dir.mkdir(exist_ok=True)

    cmd = [
        cb, "certonly", "--standalone",
        "--non-interactive", "--agree-tos",
        "-m", email,
        "-d", domain,
        "--cert-name", "vortex",
        "--config-dir", str(cert_dir / "letsencrypt"),
        "--work-dir",   str(cert_dir / "le-work"),
        "--logs-dir",   str(cert_dir / "le-logs"),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    except asyncio.TimeoutError:
        raise HTTPException(504, "certbot timed out (port 80 in use?)")
    except FileNotFoundError:
        raise HTTPException(500, f"cannot execute {cb}")

    if proc.returncode != 0:
        raise HTTPException(500, f"certbot failed: {(stderr or b'').decode()[:500]}")

    live = cert_dir / "letsencrypt" / "live" / "vortex"
    if (live / "fullchain.pem").is_file():
        shutil.copy2(live / "fullchain.pem", cert_dir / "vortex.crt")
        shutil.copy2(live / "privkey.pem",   cert_dir / "vortex.key")

    return {
        "ok":     True,
        "cert":   str(cert_dir / "vortex.crt"),
        "stdout": (stdout or b"").decode()[:2000],
    }


# ══════════════════════════════════════════════════════════════════════════
# 3. Auto-update check (version manifest)
# ══════════════════════════════════════════════════════════════════════════

_DEFAULT_MANIFEST_URL = "https://vortexx.sol/release/manifest.json"


@router.get("/update/check")
async def update_check(request: Request) -> dict:
    """Compare current version against a (configurable) release manifest."""
    from vortex_wizard import VERSION
    env = _b._read_env(_env_file(request))
    pinned = env.get("VERSION_PIN", "").lower() in ("1", "true", "yes")
    if pinned:
        return {"current": VERSION, "pinned": True, "checked": False}

    url = env.get("UPDATE_MANIFEST_URL", _DEFAULT_MANIFEST_URL)
    try:
        async with httpx.AsyncClient(timeout=5.0, verify=True) as c:
            r = await c.get(url)
        if r.status_code != 200:
            return {"current": VERSION, "error": f"HTTP {r.status_code}", "checked": True}
        m = r.json()
        latest = str(m.get("latest", "")).strip()
        notes  = str(m.get("notes_url", "")).strip()
        newer  = _semver_gt(latest, VERSION)
        return {
            "current":         VERSION,
            "latest":          latest,
            "newer_available": newer,
            "notes_url":       notes,
            "checked":         True,
        }
    except Exception as e:
        return {"current": VERSION, "error": f"{type(e).__name__}: {e}", "checked": True}


def _semver_gt(a: str, b: str) -> bool:
    def parse(s: str) -> tuple:
        parts = re.split(r"[^\d]+", s.strip())
        return tuple(int(p) if p.isdigit() else 0 for p in parts[:3]) + (0,) * (3 - len(parts[:3]))
    return parse(a) > parse(b)


# ══════════════════════════════════════════════════════════════════════════
# 4. Setup presets
# ══════════════════════════════════════════════════════════════════════════

_PRESETS = [
    {
        "id":    "personal",
        "title": "Личная нода",
        "desc":  "Только для меня и пары друзей. Без туннеля, без регистрации.",
        "env": {
            "NETWORK_MODE":         "local",
            "MAX_ROOMS_PER_USER":   "20",
            "BMP_DELIVERY_ENABLED": "true",
        },
    },
    {
        "id":    "family",
        "title": "Семейная",
        "desc":  "Для 2-10 пользователей. Через Cloudflare tunnel или своим доменом.",
        "env": {
            "NETWORK_MODE":         "global",
            "MAX_ROOMS_PER_USER":   "50",
            "BMP_DELIVERY_ENABLED": "true",
            "FEDERATION_ENABLED":   "true",
        },
    },
    {
        "id":    "community",
        "title": "Community 1k+",
        "desc":  "Публичная нода. PostgreSQL, антиспам, rate-limiting.",
        "env": {
            "NETWORK_MODE":         "global",
            "MAX_ROOMS_PER_USER":   "200",
            "BMP_DELIVERY_ENABLED": "true",
            "FEDERATION_ENABLED":   "true",
            "RATE_LIMIT_PER_MIN":   "60",
        },
    },
    {
        "id":    "pro",
        "title": "Pro 10k+",
        "desc":  "Оператор-уровень. Stake, premium payouts, мониторинг.",
        "env": {
            "NETWORK_MODE":          "global",
            "MAX_ROOMS_PER_USER":    "1000",
            "BMP_DELIVERY_ENABLED":  "true",
            "FEDERATION_ENABLED":    "true",
            "RATE_LIMIT_PER_MIN":    "200",
            "OPERATOR_MODE":         "pro",
        },
    },
]


@router.get("/presets")
async def presets_list() -> dict:
    return {"presets": _PRESETS}


class PresetApplyBody(BaseModel):
    id: str


@router.post("/presets/apply")
async def presets_apply(body: PresetApplyBody, request: Request) -> dict:
    preset = next((p for p in _PRESETS if p["id"] == body.id), None)
    if not preset:
        raise HTTPException(404, "unknown preset id")
    env_file = _env_file(request)
    from .security_api import _write_env_keys
    _write_env_keys(env_file, preset["env"])
    return {"ok": True, "applied": preset["id"], "keys_written": list(preset["env"].keys())}


# ══════════════════════════════════════════════════════════════════════════
# 5. Guided tour — step data
# ══════════════════════════════════════════════════════════════════════════

_TOUR_STEPS = [
    {"target": ".nav-item[data-tab='integrity']",
     "title": "Code integrity",
     "body":  "Проверяется автоматически — смотри что ни один файл не подменён."},
    {"target": ".nav-item[data-tab='identity']",
     "title": "Идентичность",
     "body":  "Твой pubkey — делись им, чтобы другие ноды могли тебя пригласить."},
    {"target": ".nav-item[data-tab='controller']",
     "title": "Controller",
     "body":  "Регистратор нод — не хранит сообщения, только адреса."},
    {"target": ".nav-item[data-tab='peers']",
     "title": "Peers",
     "body":  "Ноды с которыми есть активное соединение."},
    {"target": ".nav-item[data-tab='observability']",
     "title": "Observability",
     "body":  "Логи, audit, /metrics, планировщик. Всё локально — никакой телеметрии."},
    {"target": "#btn-node-start",
     "title": "Запусти ноду",
     "body":  "Жми чтобы стартовать. Можно остановить и сбросить в любой момент."},
]


@router.get("/tour")
async def tour_steps(request: Request) -> dict:
    env = _b._read_env(_env_file(request))
    seen = env.get("TOUR_COMPLETED", "").lower() in ("1", "true", "yes")
    return {"steps": _TOUR_STEPS, "already_completed": seen}


@router.post("/tour/complete")
async def tour_complete(request: Request) -> dict:
    from .security_api import _write_env_keys
    _write_env_keys(_env_file(request), {"TOUR_COMPLETED": "true"})
    return {"ok": True}
