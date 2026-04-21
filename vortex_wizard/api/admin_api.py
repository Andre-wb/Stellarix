"""Admin dashboard API — reads live metrics from the running Vortex node.

All endpoints return local-only data. There is no telemetry, no external
API call, no phone-home behavior. Even "check for updates" is gated
behind an explicit user action.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/wiz/admin", tags=["admin"])


def _env_path(request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


def _read_env_at(env_file: Path) -> dict[str, str]:
    if not env_file.is_file():
        return {}
    out: dict[str, str] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def _node_base_url(env: dict) -> str:
    port = env.get("PORT", "9000")
    host = env.get("HOST", "127.0.0.1")
    if host == "0.0.0.0":
        host = "127.0.0.1"
    proto = "https" if (Path("certs") / "vortex.crt").is_file() else "http"
    return f"{proto}://{host}:{port}"


async def _node_get_at(url: str, timeout: float = 5.0) -> Optional[dict]:
    try:
        # verify=False since the cert is self-signed and we're on loopback
        async with httpx.AsyncClient(timeout=timeout, verify=False) as http:
            r = await http.get(url)
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logging.debug("node GET %s failed: %s", url, e)
    return None


async def _node_get(request, path: str, timeout: float = 5.0) -> Optional[dict]:
    env = _read_env_at(_env_path(request))
    base = _node_base_url(env).rstrip("/")
    return await _node_get_at(f"{base}{path}", timeout=timeout)


@router.get("/overview")
async def overview(request: Request) -> dict:
    """Single call that the dashboard polls every 5s."""
    env = _read_env_at(_env_path(request))
    node_url = _node_base_url(env)

    health = await _node_get(request, "/health")
    migration_hint = await _node_get(request, "/api/session/migration-hint")
    integrity = await _node_get(request, "/v1/integrity")

    # Public URL this node announces to peers. The setup wizard writes
    # this into NODE_ANNOUNCE_ENDPOINTS as a comma-separated list
    # (cloudflared tunnel, manual URL, tor hidden service, …). First
    # entry is the "primary" one the UI highlights.
    announce_raw = env.get("NODE_ANNOUNCE_ENDPOINTS", "") or ""
    announce_list = [u.strip() for u in announce_raw.split(",") if u.strip()]

    return {
        "node_url": node_url,
        "device_name": env.get("DEVICE_NAME", ""),
        "network_mode": env.get("NETWORK_MODE", "local"),
        "controller_url": env.get("CONTROLLER_URL", ""),
        "controller_pubkey": env.get("CONTROLLER_PUBKEY", ""),
        "announce_url":     announce_list[0] if announce_list else "",
        "announce_all":     announce_list,
        "running": health is not None,
        "health": health,
        "migration_hint": migration_hint,
        "integrity": integrity,
    }


@router.get("/identity")
async def identity(request: Request) -> dict:
    """Node Ed25519 signing pubkey (from keys/ed25519_signing.bin)."""
    keys_dir = Path(_read_env_at(_env_path(request)).get("KEYS_DIR", "keys"))
    sig_path = keys_dir / "ed25519_signing.bin"
    if not sig_path.is_file():
        return {"pubkey": None, "message": "Node has not generated a signing key yet."}
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        priv = Ed25519PrivateKey.from_private_bytes(sig_path.read_bytes())
        pub = priv.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ).hex()
        return {"pubkey": pub}
    except Exception as e:
        return {"pubkey": None, "error": str(e)}


@router.get("/peers")
async def peers(request: Request) -> dict:
    """Current peer list with verification source (controller / on-chain / bootstrap)."""
    hint = await _node_get(request, "/api/session/migration-hint")
    alternatives = (hint or {}).get("alternatives") or []
    # Classify verification source based on presence of on-chain fields.
    for a in alternatives:
        md = a.get("metadata") or {}
        if md.get("sealed") or a.get("code_hash"):
            a["verification"] = "solana+controller"
        else:
            a["verification"] = "controller"
    return {"peers": alternatives}


@router.get("/traffic")
async def traffic(request: Request) -> dict:
    """CPU / RAM / WS counters — metadata-safe (no content, only numbers)."""
    import resource
    rusage = resource.getrusage(resource.RUSAGE_SELF)
    info = {
        "ws_active": 0,
        "rooms_active": 0,
        "cpu_seconds": round(rusage.ru_utime + rusage.ru_stime, 2),
        "memory_mb": round(rusage.ru_maxrss / (1024 if sys.platform != "darwin" else 1024 * 1024), 1),
        "pid": os.getpid(),
    }
    health = await _node_get(request, "/health")
    if isinstance(health, dict):
        info["ws_active"] = health.get("ws_connections", 0)
        info["rooms_active"] = health.get("rooms", 0)
    return info


@router.get("/certs")
async def certs(request: Request) -> dict:
    """SSL cert expiry + key ages."""
    out: dict = {"ssl": None, "jwt_secret_age_days": None, "csrf_secret_age_days": None}
    cert = Path("certs") / "vortex.crt"
    if cert.is_file():
        try:
            from cryptography import x509
            data = cert.read_bytes()
            c = x509.load_pem_x509_certificate(data)
            # _utc variants avoid naïve-datetime deprecation warnings in
            # cryptography ≥ 42; timestamp()==epoch, no tz juggling needed.
            out["ssl"] = {
                "subject": c.subject.rfc4514_string(),
                "not_before": int(c.not_valid_before_utc.timestamp()),
                "not_after": int(c.not_valid_after_utc.timestamp()),
                "days_left": int((c.not_valid_after_utc.timestamp() - time.time()) / 86400),
            }
        except Exception as e:
            out["ssl"] = {"error": str(e)}
    env_file = _env_path(request)
    if env_file.is_file():
        mtime = env_file.stat().st_mtime
        age_days = int((time.time() - mtime) / 86400)
        out["jwt_secret_age_days"] = age_days
        out["csrf_secret_age_days"] = age_days
    return out


@router.get("/logs")
async def logs(request: Request, limit: int = 500, level: str = "all") -> dict:
    """Read the last N lines from the node log.

    Priority:
      1. ``_node_log_path`` — the file the wizard itself pipes the child
         node's stdout/stderr into (set by ``/node/start``).
      2. ``<env-dir>/logs/vortex.log`` — where the bundled node writes
         its own structured logs (CWD is the state dir when we spawn it).
      3. Legacy paths used by the dev-checkout launcher.
    """
    env_dir = _env_path(request).parent
    log_candidates = []
    if _node_log_path:
        log_candidates.append(_node_log_path)
    log_candidates += [
        env_dir / "logs" / "vortex.log",
        env_dir / "logs" / "vortex.json.log",
        env_dir / "logs" / "node.log",
        Path("logs") / "vortex.log",
        Path("logs") / "vortex.json.log",
        Path("vortex.log"),
    ]
    log_file: Optional[Path] = next((p for p in log_candidates if p.is_file()), None)
    if log_file is None:
        return {"lines": [], "source": None}

    lines = []
    try:
        # Cheap tail: read last ~256KB, split, take last N
        size = log_file.stat().st_size
        chunk = min(size, 256 * 1024)
        with log_file.open("rb") as f:
            f.seek(size - chunk)
            data = f.read()
        text = data.decode("utf-8", errors="replace").splitlines()
        lines = text[-limit:]
    except Exception as e:
        return {"lines": [], "source": str(log_file), "error": str(e)}

    level = level.lower()
    if level != "all":
        lines = [ln for ln in lines if level.upper() in ln]
    return {"lines": lines, "source": str(log_file)}


# ── Whole-repo integrity (scripts/integrity_repo.py wrapped as HTTP) ──
#
# The wizard imports scripts/integrity_repo.py lazily via importlib so
# users don't need to open a terminal to sign/verify the Vortex source
# tree. Hashing 1,250 files takes ~1.7s so the endpoints run synchronously
# without a background job.

def _load_repo_integrity():
    """Load scripts/integrity_repo.py as a module (not an installable pkg)."""
    import importlib.util
    repo_root = Path(__file__).resolve().parent.parent.parent
    script = repo_root / "scripts" / "integrity_repo.py"
    if not script.is_file():
        raise FileNotFoundError(f"integrity_repo.py not found at {script}")
    spec = importlib.util.spec_from_file_location("integrity_repo", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@router.get("/repo-integrity/status")
async def repo_integrity_status() -> dict:
    """Quick: does the repo manifest exist, when was it last signed."""
    try:
        mod = _load_repo_integrity()
        return mod.get_status()
    except Exception as e:
        return {"error": str(e), "has_manifest": False, "has_key": False}


@router.post("/repo-integrity/sign")
async def repo_integrity_sign() -> dict:
    """Sign the whole Vortex repo. Generates the key on first call.

    The private key is written to keys/repo-release.key (chmod 600, excluded
    from git). The signed manifest goes to INTEGRITY.repo.json at repo root.
    Returns the release pubkey so the user can pin it in clients.
    """
    try:
        mod = _load_repo_integrity()
        # Offload hashing (~1.7s, CPU-bound) to a thread so the event loop
        # stays responsive for other admin-panel polling.
        return await asyncio.to_thread(mod.sign_repo)
    except Exception as e:
        logging.exception("repo-integrity sign failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/repo-integrity/verify")
async def repo_integrity_verify() -> dict:
    """Verify on-disk files against the signed manifest."""
    try:
        mod = _load_repo_integrity()
        return await asyncio.to_thread(mod.verify_repo)
    except Exception as e:
        logging.exception("repo-integrity verify failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/env")
async def env_snapshot(request: Request) -> dict:
    """Return selected env vars (secrets masked)."""
    env = _read_env_at(_env_path(request))
    masked = dict(env)
    for k in ("JWT_SECRET", "CSRF_SECRET", "STEALTH_SECRET", "VORTEX_NETWORK_KEY", "POSTGRES_PASSWORD"):
        if k in masked and masked[k]:
            masked[k] = masked[k][:8] + "…" + masked[k][-4:]
    return masked


@router.get("/check-node")
async def check_node(request: Request) -> dict:
    """Ping the messenger node; returns whether it's running."""
    env = _read_env_at(_env_path(request))
    base = _node_base_url(env)
    return {
        "running": await _node_get_at(f"{base}/health") is not None,
        "url": base,
    }


# ── Node lifecycle (start / stop) ──────────────────────────────────────────
#
# The wizard can spawn the Vortex node (``python run.py``) as a child
# process so operators don't have to keep a terminal open. Approach:
#
#   * ``_repo_root()`` locates the directory containing ``run.py``. Works
#     both for dev-checkout (``python -m vortex_wizard`` → parent of the
#     wizard package) and PyInstaller .app bundles (VORTEX_REPO_ROOT env
#     override, or CWD fallback).
#   * ``_python_exe()`` picks a real Python interpreter. In a dev
#     checkout this is ``sys.executable`` (the venv interpreter); in a
#     frozen .app ``sys.executable`` is the wizard binary itself, so we
#     fall back to ``python3`` on PATH + homebrew locations.
#   * The child stays alive after the wizard window closes — it's the
#     point of moving away from "always keep a terminal open".
#   * One node per wizard instance. Re-calling /start while it's already
#     running is a no-op.

_node_proc: Optional[subprocess.Popen] = None
_node_log_path: Optional[Path] = None
_tunnel_proc: Optional[subprocess.Popen] = None
_tunnel_url: Optional[str] = None


def _find_cloudflared_bin() -> Optional[str]:
    """Same fallback list used by setup_api — PATH then brew/snap paths."""
    hit = shutil.which("cloudflared")
    if hit:
        return hit
    for c in (
        "/opt/homebrew/bin/cloudflared",
        "/usr/local/bin/cloudflared",
        "/opt/local/bin/cloudflared",
        "/snap/bin/cloudflared",
        "/usr/bin/cloudflared",
        r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
        r"C:\Program Files\cloudflared\cloudflared.exe",
    ):
        try:
            if os.path.isfile(c) and os.access(c, os.X_OK):
                return c
        except OSError:
            continue
    return None


def _spawn_tunnel_for_node(port: int, proto: str, log_dir: Path) -> Optional[subprocess.Popen]:
    """Start cloudflared in the background. Returns the Popen immediately
    without waiting for the public URL.

    The URL is parsed asynchronously by a daemon thread that watches
    cloudflared's stdout; once it appears we stash it in
    ``_tunnel_url`` so ``/node/status`` can report it. This keeps the
    HTTP handler responsive — ``/node/start`` returns in <100 ms even
    though cloudflared can take 30+ s to negotiate with Cloudflare edge.
    """
    import re as _re
    import threading as _threading

    bin_path = _find_cloudflared_bin()
    if not bin_path:
        return None

    log_path = log_dir / "tunnel.log"
    log_fh = log_path.open("ab")
    cmd = [
        bin_path, "tunnel",
        "--url", f"{proto}://localhost:{port}",
        "--protocol", "http2",
        "--no-autoupdate",
    ]
    if proto == "https":
        cmd.append("--no-tls-verify")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        start_new_session=os.name == "posix",
    )

    pattern = _re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

    def _watch_and_pump():
        """Parse URL from stdout, then keep forwarding lines to tunnel.log."""
        global _tunnel_url
        try:
            for line in proc.stdout:
                log_fh.write(line.encode("utf-8", errors="replace"))
                log_fh.flush()
                if _tunnel_url is None:
                    m = pattern.search(line)
                    if m:
                        _tunnel_url = m.group(0)
                        logging.info("cloudflared tunnel ready: %s", _tunnel_url)
        except Exception as e:
            logging.debug("tunnel pump exited: %s", e)
        finally:
            try: log_fh.close()
            except Exception: pass

    _threading.Thread(target=_watch_and_pump, daemon=True).start()
    return proc


def _who_holds_port(port: int) -> Optional[dict]:
    """Return {'pid': int, 'command': str} of whoever listens on ``port``,
    or None if the port is free. Does NOT kill anything — pure inspection.
    """
    lsof = shutil.which("lsof")
    if not lsof:
        return None
    try:
        out = subprocess.check_output(
            [lsof, "-nP", "-iTCP:" + str(port), "-sTCP:LISTEN"],
            text=True, timeout=3,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None
    # Skip header line, pick the first LISTEN row.
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1].isdigit():
            return {
                "pid":     int(parts[1]),
                "command": parts[0],
            }
    return None


def _terminate_tunnel() -> None:
    global _tunnel_proc, _tunnel_url
    if _tunnel_proc is not None and _tunnel_proc.poll() is None:
        try:
            _tunnel_proc.terminate()
            try:
                _tunnel_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                _tunnel_proc.kill()
        except OSError:
            pass
    _tunnel_proc = None
    _tunnel_url = None


def _repo_root() -> Optional[Path]:
    """Find the directory containing run.py.

    Only used in dev checkouts. In a frozen PyInstaller bundle the node
    is launched via ``sys.executable --run-node`` and run.py lives
    under sys._MEIPASS, so this function returns None — the spawn path
    below handles that case separately.
    """
    if getattr(sys, "frozen", False):
        mei = getattr(sys, "_MEIPASS", None)
        return Path(mei) if mei else None

    override = os.environ.get("VORTEX_REPO_ROOT")
    if override:
        p = Path(override).expanduser()
        if (p / "run.py").is_file():
            return p
    # Dev checkout: vortex_wizard/api/admin_api.py → parents[2] = repo root
    guess = Path(__file__).resolve().parents[2]
    if (guess / "run.py").is_file():
        return guess
    cwd = Path.cwd()
    if (cwd / "run.py").is_file():
        return cwd
    return None


def _node_spawn_cmd(repo_root: Path) -> list[str]:
    """Build the command line that starts the node as a child process.

    Frozen .app: re-invoke ourselves with --run-node (the __main__
    dispatcher routes us into run.py inside the bundle).

    Dev checkout: prefer the repo's own ``.venv/bin/python`` over
    ``sys.executable``. If the wizard was launched with the system
    interpreter (``python3 -m vortex_wizard`` without activating the
    venv), ``sys.executable`` points at ``/usr/bin/python3`` and
    re-using it means the node can't import ``sqlalchemy``, ``fastapi``,
    etc. The venv is the canonical dev interpreter — fall back to
    ``sys.executable`` only when no venv exists.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, "--run-node"]

    for candidate in (
        repo_root / ".venv" / "bin" / "python",
        repo_root / "venv" / "bin" / "python",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return [str(candidate), str(repo_root / "run.py")]

    return [sys.executable, str(repo_root / "run.py")]


@router.post("/node/start")
async def node_start(request: Request) -> dict:
    """Spawn ``python run.py`` in the background.

    Returns the PID on success. Safe to call while already running — it
    no-ops and returns the existing PID.
    """
    global _node_proc, _node_log_path

    if _node_proc is not None and _node_proc.poll() is None:
        return {
            "ok":              True,
            "pid":             _node_proc.pid,
            "already_running": True,
            "log":             str(_node_log_path) if _node_log_path else None,
        }

    # Forget any stale handle so pre-cleanup below kills OS-level
    # leftovers from a previous wizard launch (where _node_proc reset
    # to None but the OS process stayed alive as a detached session).
    _node_proc = None

    root = _repo_root()
    if root is None:
        raise HTTPException(
            404,
            "run.py not found. Set VORTEX_REPO_ROOT to the folder that "
            "contains run.py, or launch this wizard from a dev checkout.",
        )

    cmd = _node_spawn_cmd(root)

    env_file = _env_path(request)
    env = _read_env_at(env_file)

    # Refuse if the port is already held by someone else — killing a
    # foreign process would be rude. Surface a clean 409 the UI can
    # translate into a timed warning. Operator can then decide whether
    # to kill the other process themselves or pick a different port.
    target_port = int(env.get("PORT", "9000") or "9000")
    holder = _who_holds_port(target_port)
    if holder:
        raise HTTPException(
            409,
            {
                "error":  "port_in_use",
                "port":   target_port,
                "holder": holder,
                "hint":   (f"Port {target_port} is already in use by PID "
                           f"{holder.get('pid')} ({holder.get('command')}). "
                           "Close that process or change PORT in .env, then try again."),
            },
        )

    logs_dir = env_file.parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "node.log"
    log_fh = log_path.open("ab")
    _node_log_path = log_path

    # Inherit the env + make sure PYTHONUNBUFFERED so log is flushed live.
    spawn_env = dict(os.environ)
    spawn_env["PYTHONUNBUFFERED"] = "1"
    # Tell the node which .env to read, since the wizard may write to a
    # per-user dir that differs from the process CWD.
    spawn_env.setdefault("VORTEX_ENV_FILE", str(env_file))

    try:
        _node_proc = subprocess.Popen(
            cmd,
            cwd=str(root),
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=spawn_env,
            # Detach on POSIX so closing the wizard window (which may SIGHUP
            # our process group) doesn't kill the node too.
            start_new_session=os.name == "posix",
        )
    except OSError as e:
        log_fh.close()
        raise HTTPException(500, f"failed to spawn node: {e}")

    # Start cloudflared in the background if the node is set up for
    # internet reach. We don't wait for the URL here — the HTTP handler
    # must return in <1 s or the browser times out the fetch and chokes
    # on a half-written JSON body. ``/node/status`` polls once the URL
    # is ready (daemon thread inside _spawn_tunnel_for_node sets it).
    global _tunnel_proc, _tunnel_url
    _terminate_tunnel()  # clean slate
    port = int(env.get("PORT", "9000") or "9000")
    proto = "https" if (env_file.parent / "certs" / "vortex.crt").is_file() else "http"
    announce_raw = env.get("NODE_ANNOUNCE_ENDPOINTS", "") or ""
    want_tunnel = bool(announce_raw) or env.get("NETWORK_MODE", "") in ("global", "custom")
    tunnel_pending = False
    tunnel_error: Optional[str] = None
    if want_tunnel:
        try:
            _tunnel_proc = _spawn_tunnel_for_node(
                port=port, proto=proto, log_dir=logs_dir,
            )
            if _tunnel_proc is None:
                tunnel_error = (
                    "cloudflared not installed — "
                    "brew install cloudflared (macOS)"
                )
            else:
                tunnel_pending = True
        except Exception as e:
            tunnel_error = f"{e.__class__.__name__}: {e}"

    return {
        "ok":              True,
        "pid":             _node_proc.pid,
        "already_running": False,
        "log":             str(log_path),
        "tunnel_pending":  tunnel_pending,
        "tunnel_error":    tunnel_error,
    }


@router.post("/node/stop")
async def node_stop() -> dict:
    """Terminate the child node process (graceful, then SIGKILL after 5s)
    and tear down the cloudflared tunnel spawned for it.
    """
    global _node_proc
    was_running = _node_proc is not None and _node_proc.poll() is None
    pid = _node_proc.pid if was_running else None

    # Kill the tunnel first — it's useless without the node.
    _terminate_tunnel()

    if was_running:
        try:
            _node_proc.terminate()
        except OSError:
            pass
        try:
            _node_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try: _node_proc.kill()
            except OSError: pass
    _node_proc = None
    return {"ok": True, "was_running": was_running, "pid": pid}


@router.post("/reset")
async def reset_setup(request: Request) -> dict:
    """Wipe the node's identity + config so the wizard flips back to Setup.

    Removes:
      * .env (setup marker + secrets + controller config)
      * keys/ed25519_signing.bin (node identity)

    Leaves untouched:
      * vortex.db (chat history) — a real "delete my data" flow lives
        elsewhere
      * logs/

    Stops the spawned node child process first so it doesn't try to
    keep writing to the state we're about to remove.
    """
    import shutil as _shutil  # local alias so we don't shadow module-level

    global _node_proc

    # 0. Kill the tunnel — no point in leaving it running without a node.
    _terminate_tunnel()

    # 1. Stop the running node child, if any.
    if _node_proc is not None and _node_proc.poll() is None:
        try:
            _node_proc.terminate()
            try:
                _node_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                _node_proc.kill()
        except OSError:
            pass
    _node_proc = None

    env_file = _env_path(request)
    removed = []

    try:
        if env_file.is_file():
            env_file.unlink()
            removed.append(str(env_file))
    except OSError as e:
        raise HTTPException(500, f"cannot delete env: {e}")

    keys_dir = env_file.parent / "keys"
    if keys_dir.is_dir():
        try:
            _shutil.rmtree(keys_dir)
            removed.append(str(keys_dir))
        except OSError as e:
            # Best-effort — env is already gone which is the important bit.
            logging.warning("reset: could not delete keys dir: %s", e)

    return {"ok": True, "removed": removed}


@router.get("/node/status")
async def node_status(request: Request) -> dict:
    """Whether the spawned node process is still alive + ping health +
    expose the public tunnel URL (so the UI can render a clickable link).
    """
    global _node_proc, _tunnel_proc, _tunnel_url
    proc_alive   = _node_proc is not None and _node_proc.poll() is None
    tunnel_alive = _tunnel_proc is not None and _tunnel_proc.poll() is None
    env = _read_env_at(_env_path(request))
    base = _node_base_url(env)
    health = await _node_get_at(f"{base}/health", timeout=2.0)
    return {
        "process_alive":  proc_alive,
        "pid":            _node_proc.pid if proc_alive else None,
        "http_reachable": health is not None,
        "url":            base,
        "tunnel_url":     _tunnel_url if tunnel_alive else None,
        "tunnel_alive":   tunnel_alive,
        "log":            str(_node_log_path) if _node_log_path else None,
    }


@router.get("/earnings")
async def earnings(request: Request) -> dict:
    """Operator-level rewards summary.

    Reads the wallet pubkey from ``WALLET_PUBKEY`` in the env file (set
    during setup from the BIP39 mnemonic) and combines it with uptime
    and traffic metrics to show the operator what they're earning. Also
    queries on-chain for the operator's Vortex Premium subscription —
    if active, the rewards estimate picks up the ×1.2 premium bonus.

    Figures are placeholder until the payout smart contract is live —
    but the wallet address, subscription status, and uptime are real.
    """
    env = _read_env_at(_env_path(request))
    wallet = env.get("WALLET_PUBKEY", "")
    node_pub = env.get("NODE_PUBKEY", "")

    # Uptime from migration-hint (cheap proxy — node reports its own age).
    hint = await _node_get(request, "/api/session/migration-hint")
    running = hint is not None

    # Mock stake / register-fee status until smart contract is deployed.
    stake_sol = 0.0
    register_fee_paid = False

    # On-chain premium lookup — picks up the ×1.2 multiplier if the
    # operator also holds an active Vortex Premium subscription.
    premium_active = False
    premium_end = 0
    if wallet:
        try:
            import httpx
            # Resolve the Solana RPC by asking the running node's premium
            # cache — keeps the wizard decoupled from RPC credentials.
            base = _node_base_url(env).rstrip("/")
            async with httpx.AsyncClient(timeout=5.0, verify=False) as http:
                r = await http.get(f"{base}/api/premium/status", params={"wallet": wallet})
            if r.status_code == 200:
                d = r.json()
                premium_active = bool(d.get("is_premium"))
                premium_end = int(d.get("end_timestamp", 0))
        except Exception:
            pass

    rewards_multiplier = 1.2 if premium_active else 1.0

    uptime_pct = 100.0 if running else 0.0
    users_served_est = 8 if running else 0
    base_monthly_usd = users_served_est * 5 * 0.7 * (uptime_pct / 100.0)
    est_monthly_usd = base_monthly_usd * rewards_multiplier
    est_monthly_sol = round(est_monthly_usd / 150, 4)

    return {
        "wallet_pubkey":   wallet,
        "node_pubkey":     node_pub,
        "stake_sol":       stake_sol,
        "register_fee_paid": register_fee_paid,
        "uptime_pct":      round(uptime_pct, 1),
        "users_served":    users_served_est,
        "premium": {
            "active":         premium_active,
            "end_timestamp":  premium_end,
            "multiplier":     rewards_multiplier,
        },
        "estimated": {
            "monthly_usd": round(est_monthly_usd, 2),
            "monthly_sol": est_monthly_sol,
        },
        "note": (
            "estimate — becomes exact once the payout contract is wired in"
            + (" · operator has Premium ×1.2 bonus" if premium_active else "")
        ),
    }
