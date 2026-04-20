"""Setup mode API — first-run node configuration."""
from __future__ import annotations

import logging
import os
import secrets
import socket
import traceback
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/wiz/setup", tags=["setup"])

logger = logging.getLogger(__name__)


def _env_path(request: Request) -> Path:
    """Pick the env file for this request (app.state override > default)."""
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


class SetupConfig(BaseModel):
    device_name: str
    port: int = Field(9000, ge=1024, le=65535)
    host: str = "0.0.0.0"
    network_mode: str = Field("local", pattern="^(local|global|custom)$")
    registration_mode: str = Field("open", pattern="^(open|invite|closed)$")
    invite_code: str = ""
    controller_url: str = ""
    controller_pubkey: str = ""
    announce_endpoints: str = ""
    max_file_mb: int = Field(100, ge=1, le=10000)
    # 24-word BIP39 mnemonic that derives both the node identity (Ed25519
    # signing key) and the Solana wallet for rewards. Required on every
    # save() call — clients either generate a fresh one via /generate-seed
    # or paste a backup.
    mnemonic: str = ""


class MnemonicBody(BaseModel):
    mnemonic: str


class SystemInfo(BaseModel):
    hostname: str
    platform: str
    local_ips: list[str]
    env_exists: bool


@router.get("/system", response_model=SystemInfo)
async def system_info(request: Request) -> SystemInfo:
    """OS info for pre-populating fields."""
    import platform
    ips = _detect_local_ips()
    return SystemInfo(
        hostname=socket.gethostname(),
        platform=platform.system(),
        local_ips=ips,
        env_exists=_env_path(request).is_file(),
    )


# ── Seed-phrase identity ──────────────────────────────────────────────────


@router.get("/generate-seed")
async def generate_seed() -> dict:
    """Generate a fresh 24-word BIP39 mnemonic + derived pubkeys.

    Returned mnemonic is ephemeral — it is NOT written to disk here. The
    client shows it to the user, waits for a "I saved it" confirmation,
    and then calls ``/save`` with the same words so the wizard writes the
    derived private key to ``keys/ed25519_signing.bin``.
    """
    from . import seed_derive
    phrase = seed_derive.generate_mnemonic()
    ident = seed_derive.derive_identity(phrase)
    return {
        "mnemonic":        phrase,
        "words":           phrase.split(),
        "node_pubkey":     ident.node_pubkey_hex,
        "wallet_pubkey":   ident.wallet_pubkey_base58,
    }


@router.post("/validate-seed")
async def validate_seed(body: MnemonicBody) -> dict:
    """Validate a user-supplied 24-word phrase and return derived pubkeys.

    Used by the Restore-from-seed flow to show the operator exactly what
    address they're recovering before committing.
    """
    from . import seed_derive
    phrase = seed_derive.normalize_mnemonic(body.mnemonic)
    if len(phrase.split()) != 24:
        return {"ok": False, "error": "must be 24 words"}
    if not seed_derive.validate_mnemonic(phrase):
        return {"ok": False, "error": "checksum fails — words are wrong or mis-spelled"}
    ident = seed_derive.derive_identity(phrase)
    return {
        "ok":              True,
        "node_pubkey":     ident.node_pubkey_hex,
        "wallet_pubkey":   ident.wallet_pubkey_base58,
    }


@router.post("/save")
async def save_config(cfg: SetupConfig, request: Request) -> dict:
    """Write the supplied config to .env atomically.

    Any exception here turns into a clean 500 + JSON body with the message
    instead of letting the default FastAPI handler emit an HTML-looking
    error (which would break the client's JSON.parse).
    """
    if not cfg.device_name.strip():
        return {"ok": False, "error": "device_name required"}

    # Seed phrase is required — it drives both the node identity and the
    # operator's reward wallet. Without it we cannot persist a signing key.
    from . import seed_derive
    phrase = seed_derive.normalize_mnemonic(cfg.mnemonic)
    if len(phrase.split()) != 24 or not seed_derive.validate_mnemonic(phrase):
        raise HTTPException(400, "valid 24-word mnemonic required")
    ident = seed_derive.derive_identity(phrase)

    env_file = _env_path(request)
    try:
        # Ensure the parent directory exists (~/.vortex, AppData, etc.)
        env_file.parent.mkdir(parents=True, exist_ok=True)

        existing = _read_env(env_file)
        jwt_secret = existing.get("JWT_SECRET") or secrets.token_hex(32)
        csrf_secret = existing.get("CSRF_SECRET") or secrets.token_hex(32)
        stealth_secret = existing.get("STEALTH_SECRET") or secrets.token_hex(32)
        network_key = existing.get("VORTEX_NETWORK_KEY") or secrets.token_hex(32)

        # Write the derived node signing key (raw 32 bytes) next to the
        # env file, in a ``keys/`` sibling directory the node already
        # knows to read from (see KEYS_DIR below).
        keys_dir = env_file.parent / "keys"
        keys_dir.mkdir(parents=True, exist_ok=True)
        sig_path = keys_dir / "ed25519_signing.bin"
        sig_path.write_bytes(ident.node_priv_raw)
        try:
            os.chmod(sig_path, 0o600)
        except OSError:
            pass

        announce = _normalize_endpoints(cfg.announce_endpoints)

        lines = [
            "# VORTEX Node Configuration",
            "# (managed by vortex-wizard — don't hand-edit secrets)",
            "",
            "# Security",
            f"JWT_SECRET={jwt_secret}",
            f"CSRF_SECRET={csrf_secret}",
            f"STEALTH_SECRET={stealth_secret}",
            f"VORTEX_NETWORK_KEY={network_key}",
            "",
            "# Server",
            f"HOST={cfg.host}",
            f"PORT={cfg.port}",
            f"DEVICE_NAME={cfg.device_name}",
            "",
            "# Storage",
            "DB_PATH=vortex.db",
            "UPLOAD_DIR=uploads",
            f"KEYS_DIR={keys_dir}",
            f"MAX_FILE_MB={cfg.max_file_mb}",
            "",
            "# Identity — derived from 24-word seed (mnemonic NOT stored)",
            f"NODE_PUBKEY={ident.node_pubkey_hex}",
            f"WALLET_PUBKEY={ident.wallet_pubkey_base58}",
            "",
            "# Network mode",
            f"NETWORK_MODE={cfg.network_mode}",
            f"REGISTRATION_MODE={cfg.registration_mode}",
        ]
        if cfg.invite_code:
            lines.append(f"INVITE_CODE_NODE={cfg.invite_code}")

        if cfg.network_mode in ("global", "custom"):
            lines += [
                "",
                "# Controller",
                f"CONTROLLER_URL={cfg.controller_url}",
                f"CONTROLLER_PUBKEY={cfg.controller_pubkey}",
                f"NODE_ANNOUNCE_ENDPOINTS={announce}",
                "CONTROLLER_HEARTBEAT_SEC=60",
            ]

        # Final marker — only when this line is present does the wizard
        # consider setup "complete" and jump straight into the admin UI on
        # subsequent launches.
        lines += ["", "# Wizard completion marker", "NODE_INITIALIZED=true"]

        # Write + fsync so the NODE_INITIALIZED marker is definitely on
        # disk before we return. Without fsync, the browser's reload
        # might hit _current_mode() microseconds too early and read an
        # unsynced .env that still lacks the marker → SPA falls back to
        # setup, looking like "setup keeps looping".
        payload = "\n".join(lines) + "\n"
        with open(env_file, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            try: os.fsync(f.fileno())
            except OSError: pass
        try:
            os.chmod(env_file, 0o600)
        except OSError:
            pass
        # Sanity — re-read and confirm the marker made it. If not, fail
        # loudly so the caller knows the mode won't flip.
        try:
            written = env_file.read_text(encoding="utf-8")
            if "NODE_INITIALIZED=true" not in written:
                raise RuntimeError("NODE_INITIALIZED=true not found in .env after write")
        except Exception as e:
            logger.exception("save: post-write verification failed")
            raise HTTPException(500, f"env write verification failed: {e}")
    except PermissionError as e:
        logger.exception("save: permission denied at %s", env_file)
        raise HTTPException(500, f"cannot write to {env_file}: permission denied")
    except OSError as e:
        logger.exception("save: OS error at %s", env_file)
        raise HTTPException(500, f"cannot write to {env_file}: {e.__class__.__name__}: {e}")
    except Exception as e:
        logger.exception("save: unexpected failure")
        raise HTTPException(500, f"internal error: {e.__class__.__name__}: {e}")

    # Auto-start the node right after save so the operator never has to
    # open a second terminal. Delegates to the admin_api lifecycle
    # handler — any spawn error is reported back but doesn't block the
    # save itself (config is still written).
    node_started = False
    node_error: Optional[str] = None
    try:
        from . import admin_api
        resp = await admin_api.node_start(request)
        node_started = bool(resp.get("ok"))
    except HTTPException as e:
        node_error = e.detail if isinstance(e.detail, str) else str(e.detail)
    except Exception as e:
        node_error = f"{e.__class__.__name__}: {e}"
        logger.exception("save: autostart failed")

    return {
        "ok":           True,
        "path":         str(env_file),
        "node_started": node_started,
        "node_error":   node_error,
    }


@router.get("/resolve-sns")
async def resolve_sns(domain: str = "vortexx.sol") -> dict:
    """Resolve a ``.sol`` domain to its controller URL + pubkey via Bonfida SNS.

    The frontend calls this when the user picks Global mode so there's no
    need to paste the URL and pubkey by hand — they're read directly off
    the Solana Name Service on-chain record.
    """
    domain = (domain or "").strip().lower()
    if not domain.endswith(".sol"):
        return {"ok": False, "error": "not a .sol domain"}

    try:
        import httpx

        async def _fetch(record: str) -> str:
            url = f"https://sns-api.bonfida.com/v2/record/{domain}/{record}"
            async with httpx.AsyncClient(timeout=10) as http:
                r = await http.get(url)
            if r.status_code != 200:
                return ""
            try:
                data = r.json()
            except ValueError:
                return ""
            result = data.get("result", data) if isinstance(data, dict) else data
            if isinstance(result, dict):
                val = result.get("content") or result.get("value") or result.get("deserialized")
            else:
                val = result
            return (val or "").strip() if isinstance(val, str) else ""

        import asyncio
        url_val, txt_val = await asyncio.gather(_fetch("URL"), _fetch("TXT"))
    except Exception as e:
        return {"ok": False, "domain": domain, "error": str(e)}

    if url_val and not url_val.startswith(("http://", "https://")):
        url_val = "https://" + url_val

    pubkey = None
    mirrors: list[str] = []
    if txt_val:
        for part in txt_val.replace("\n", ";").split(";"):
            part = part.strip()
            if "=" not in part:
                continue
            k, _, v = part.partition("=")
            k = k.strip().lower()
            v = v.strip()
            if k == "pubkey" and v:
                pubkey = v
            elif k == "mirrors" and v:
                mirrors.extend(m.strip() for m in v.split(",") if m.strip())

    return {
        "ok": bool(url_val),
        "domain": domain,
        "url": url_val,
        "pubkey": pubkey,
        "mirrors": mirrors,
    }


# ── Cloudflare tunnel lifecycle ──────────────────────────────────────────
# A Global-mode node is typically behind a home NAT and needs a public URL
# to receive traffic. The wizard spawns a long-lived `cloudflared tunnel`
# child process and parses its stdout for the assigned trycloudflare.com
# URL. All args are literals or numeric, so subprocess is launched with
# `create_subprocess_exec` (no shell invocation, no injection surface).

import asyncio as _asyncio
import re as _re
import shutil as _shutil

_tunnel_proc: Optional["_asyncio.subprocess.Process"] = None
_tunnel_url: Optional[str] = None
_tunnel_lock: Optional[_asyncio.Lock] = None


def _get_tunnel_lock() -> _asyncio.Lock:
    global _tunnel_lock
    if _tunnel_lock is None:
        _tunnel_lock = _asyncio.Lock()
    return _tunnel_lock


def _find_cloudflared() -> Optional[str]:
    """Locate the cloudflared binary even when PATH is stripped.

    PyInstaller-built .app bundles launched from Finder inherit a bare
    ``PATH=/usr/bin:/bin:/usr/sbin:/sbin``. Homebrew lives under
    ``/opt/homebrew/bin`` (Apple Silicon) or ``/usr/local/bin`` (Intel
    Mac), neither of which is in that default path — so the usual
    ``shutil.which`` misses a perfectly good install.

    We first try the normal PATH lookup, then fall back to the handful
    of well-known install locations for each platform.
    """
    hit = _shutil.which("cloudflared")
    if hit:
        return hit
    candidates = [
        "/opt/homebrew/bin/cloudflared",      # Homebrew on Apple Silicon
        "/usr/local/bin/cloudflared",         # Homebrew on Intel, generic /usr/local
        "/opt/local/bin/cloudflared",         # MacPorts
        "/snap/bin/cloudflared",              # Linux snap
        "/usr/bin/cloudflared",               # apt / dnf / pacman
        # Windows winget default — also handled by shutil.which normally but
        # a stripped-cmd environment can miss it.
        r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
        r"C:\Program Files\cloudflared\cloudflared.exe",
    ]
    for c in candidates:
        try:
            if os.path.isfile(c) and os.access(c, os.X_OK):
                return c
        except OSError:
            continue
    return None


@router.get("/tunnel-status")
async def tunnel_status() -> dict:
    """Whether cloudflared is installed and if there's a live tunnel."""
    return {
        "installed": bool(_find_cloudflared()),
        "url": _tunnel_url,
        "running": _tunnel_proc is not None and _tunnel_proc.returncode is None,
    }


@router.post("/start-tunnel")
async def start_tunnel(body: dict) -> dict:
    """Spawn cloudflared and return the issued public URL."""
    global _tunnel_proc, _tunnel_url

    port = int(body.get("port", 9000))
    if not (1024 <= port <= 65535):
        raise HTTPException(400, "port out of range")

    bin_path = _find_cloudflared()
    if not bin_path:
        return {
            "ok": False,
            "error": "cloudflared is not installed",
            "install_hint": (
                "macOS: brew install cloudflared\n"
                "Linux: https://pkg.cloudflare.com/index.html\n"
                "Windows: winget install Cloudflare.cloudflared"
            ),
        }

    async with _get_tunnel_lock():
        if _tunnel_proc and _tunnel_proc.returncode is None:
            _tunnel_proc.terminate()
            try:
                await _asyncio.wait_for(_tunnel_proc.wait(), timeout=3)
            except _asyncio.TimeoutError:
                _tunnel_proc.kill()
        _tunnel_url = None

        # Pick http vs https to match how the node is actually bound —
        # the node launcher switches to HTTPS when a cert file is present,
        # and cloudflared must forward with the same scheme or the origin
        # drops the connection and we get a 502 at the edge.
        origin_scheme = "https" if (Path("certs") / "vortex.crt").is_file() else "http"
        cloudflared_args = [
            bin_path, "tunnel",
            "--url", f"{origin_scheme}://localhost:{port}",
            # http2 avoids QUIC — more robust through NAT/firewall
            "--protocol", "http2",
            "--no-autoupdate",
        ]
        if origin_scheme == "https":
            # Node uses a self-signed cert; skip TLS verification so the
            # tunnel actually connects. The outer Cloudflare-to-client
            # leg stays genuinely TLS-terminated.
            cloudflared_args.append("--no-tls-verify")

        _tunnel_proc = await _asyncio.create_subprocess_exec(
            *cloudflared_args,
            stdout=_asyncio.subprocess.PIPE,
            stderr=_asyncio.subprocess.STDOUT,
        )

        pattern = _re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
        deadline = _asyncio.get_event_loop().time() + 30.0
        while _asyncio.get_event_loop().time() < deadline:
            if _tunnel_proc.returncode is not None:
                return {"ok": False, "error": "cloudflared exited before producing a URL"}
            try:
                line = await _asyncio.wait_for(_tunnel_proc.stdout.readline(), timeout=1.5)
            except _asyncio.TimeoutError:
                continue
            if not line:
                continue
            m = pattern.search(line.decode("utf-8", errors="replace"))
            if m:
                _tunnel_url = m.group(0)
                logger.info("cloudflared tunnel ready: %s", _tunnel_url)
                return {"ok": True, "url": _tunnel_url}

        return {"ok": False, "error": "timed out waiting for tunnel URL"}


@router.post("/stop-tunnel")
async def stop_tunnel() -> dict:
    global _tunnel_proc, _tunnel_url
    async with _get_tunnel_lock():
        if _tunnel_proc and _tunnel_proc.returncode is None:
            _tunnel_proc.terminate()
            try:
                await _asyncio.wait_for(_tunnel_proc.wait(), timeout=3)
            except _asyncio.TimeoutError:
                _tunnel_proc.kill()
        _tunnel_proc = None
        _tunnel_url = None
    return {"ok": True}


@router.post("/check-port/{port}")
async def check_port(port: int) -> dict:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", port))
        s.close()
        return {"ok": True}
    except OSError as e:
        return {"ok": False, "error": str(e)}


# ── Helpers ───────────────────────────────────────────────────────────────


def _detect_local_ips() -> list[str]:
    ips: list[str] = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for target in ("192.168.1.1", "10.0.0.1", "8.8.8.8"):
            try:
                s.connect((target, 80))
                ip = s.getsockname()[0]
                if not ip.startswith("127."):
                    ips.append(ip)
                    break
            except Exception:
                continue
        s.close()
    except Exception:
        pass
    return ips


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


def _normalize_endpoints(raw: str) -> str:
    if not raw:
        return ""
    parts = [p.strip() for p in raw.replace("\n", ",").split(",")]
    return ",".join(p for p in parts if p)
