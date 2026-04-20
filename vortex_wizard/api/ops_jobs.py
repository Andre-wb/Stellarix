"""Scheduled maintenance jobs + public uptime badge.

Each job is a ``async def job(env_file: Path) -> dict`` consumed by the
scheduler in ``scheduler.py``. Jobs are deliberately tolerant — a failure
is logged into the job's last_msg, it doesn't kill the loop.
"""
from __future__ import annotations

import asyncio
import gzip
import json
import logging
import os
import resource
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import audit as _audit
from . import backup_api as _backup_api
from . import scheduler as _sched

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin/ops", tags=["ops"])


# ── Tunables (override via .env when needed) ──────────────────────────────

_RES_DISK_FREE_PCT_WARN = 10     # warn if free disk < 10%
_RES_MEM_RSS_MB_WARN    = 2048   # warn if RSS > 2 GB
_RES_CPU_SECONDS_WINDOW = 300    # cpu-seconds observed in last 5 min
_RES_CPU_WARN_SEC       = 250    # >250 cpu-seconds / 5 min → ~80% saturated
_PRUNE_FILES_OLDER_DAYS = 30
_UPTIME_WINDOW_DAYS     = 30


# ── Job: cron backup ──────────────────────────────────────────────────────

async def job_cron_backup(env_file: Path) -> dict:
    """Invoke the same path as the /backup/upload endpoint.

    We call the function directly rather than HTTP to avoid loopback
    roundtrip and auth complications.
    """
    env = _backup_api._read_env(env_file)
    if not env.get("CONTROLLER_URL"):
        return {"skipped": True, "message": "CONTROLLER_URL unset"}

    is_sq, db_path = _backup_api._is_sqlite(env, _backup_api._node_root(env_file))
    if not is_sq or not db_path or not db_path.is_file():
        return {"skipped": True, "message": "sqlite file not present"}

    # Reuse the handler internals.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    import base64 as _b64
    import hashlib as _h

    priv_bytes = _backup_api._signing_key_bytes(env_file)
    priv = Ed25519PrivateKey.from_private_bytes(priv_bytes)
    pub = _backup_api._node_pubkey_hex(priv)
    blob_key = _backup_api._derive_blob_key(priv_bytes)

    plaintext = _backup_api._sqlite_snapshot(db_path)
    blob      = _backup_api._encrypt_blob(plaintext, blob_key)
    sha       = _h.sha256(blob).hexdigest()

    payload = {
        "action":    "put",
        "pubkey":    pub,
        "sha256":    sha,
        "byte_size": len(blob),
        "blob_b64":  _b64.b64encode(blob).decode("ascii"),
        "timestamp": int(time.time()),
    }
    ctrl_url = env.get("CONTROLLER_URL", "").rstrip("/")
    res = await _backup_api._post_signed(ctrl_url, "/v1/backup", payload, priv)

    # Drop the marker file the Prometheus exporter reads.
    try:
        (env_file.parent / "backup_last.meta").write_text(json.dumps({
            "updated_at": res.get("updated_at") or int(time.time()),
            "byte_size":  len(blob),
            "sha256":     sha,
        }))
    except Exception:
        pass

    return {
        "message":   f"uploaded {len(blob)} B (plaintext {len(plaintext)} B)",
        "byte_size": len(blob),
        "sha256":    sha,
    }


# ── Job: auto-prune + VACUUM ──────────────────────────────────────────────

async def job_prune(env_file: Path) -> dict:
    root = env_file.parent
    env = _backup_api._read_env(env_file)
    actions: list[str] = []

    # 1. Prune uploaded files older than N days from <root>/uploads
    uploads = root / "uploads"
    if uploads.is_dir():
        cutoff = time.time() - _PRUNE_FILES_OLDER_DAYS * 86400
        removed = 0
        for p in uploads.rglob("*"):
            try:
                if p.is_file() and p.stat().st_mtime < cutoff:
                    p.unlink()
                    removed += 1
            except OSError:
                continue
        if removed:
            actions.append(f"pruned {removed} old upload(s)")

    # 2. VACUUM the SQLite db (offline when possible, otherwise VACUUM INTO)
    is_sq, db_path = _backup_api._is_sqlite(env, root)
    if is_sq and db_path and db_path.is_file():
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute("VACUUM")
                conn.commit()
                actions.append(f"VACUUM {db_path.name}")
            finally:
                conn.close()
        except sqlite3.OperationalError as e:
            # Typical when the node holds a write lock — note and skip.
            actions.append(f"VACUUM skipped ({e})")

    # 3. Also prune old scheduler log if it grew huge
    sched_state = root / "scheduler_state.json"
    if sched_state.is_file() and sched_state.stat().st_size > 512 * 1024:
        try:
            sched_state.unlink()
            actions.append("pruned scheduler_state.json")
        except OSError:
            pass

    return {"message": "; ".join(actions) or "nothing to prune", "actions": actions}


# ── Job: resource watchdog ────────────────────────────────────────────────

_last_cpu_sec = 0.0


async def job_resource_watchdog(env_file: Path) -> dict:
    global _last_cpu_sec
    root = env_file.parent

    # Disk free %
    du = shutil.disk_usage(str(root))
    free_pct = (du.free / du.total) * 100 if du.total else 0

    # CPU seconds over this tick — compare to last
    ru = resource.getrusage(resource.RUSAGE_SELF)
    cpu_now = ru.ru_utime + ru.ru_stime
    cpu_delta = cpu_now - _last_cpu_sec
    _last_cpu_sec = cpu_now

    # RSS (Darwin is bytes, Linux is KB)
    rss = ru.ru_maxrss
    if sys.platform != "darwin":
        rss *= 1024
    rss_mb = rss // (1024 * 1024)

    alerts: list[str] = []
    if free_pct < _RES_DISK_FREE_PCT_WARN:
        alerts.append(f"disk_free_pct={free_pct:.1f}<{_RES_DISK_FREE_PCT_WARN}")
    if rss_mb > _RES_MEM_RSS_MB_WARN:
        alerts.append(f"rss_mb={rss_mb}>{_RES_MEM_RSS_MB_WARN}")
    if cpu_delta > _RES_CPU_WARN_SEC:
        alerts.append(f"cpu_sec_delta={cpu_delta:.0f}>{_RES_CPU_WARN_SEC}")

    # Any alert → write as audit row with alert flag so the operator sees
    # it in the Observability tab too.
    if alerts:
        try:
            _audit._insert_entry(
                env_file,
                method="JOB",
                path="resource_watchdog",
                client_ip="",
                node_pubkey="",
                status=0,
                duration_ms=0,
            )
            # Override the reason via a direct row update — simpler than
            # threading another function through _insert_entry.
            c = _audit._conn(env_file)
            try:
                c.execute(
                    "UPDATE audit_entries SET alert=1, alert_reason=? "
                    "WHERE id = (SELECT MAX(id) FROM audit_entries)",
                    ("; ".join(alerts),),
                )
            finally:
                c.close()
        except Exception:
            pass

        # Fan out to configured alert channels (email / Slack / etc.)
        try:
            from . import alerts as _alerts
            severity = "critical" if free_pct < 2 else "warning"
            await _alerts.dispatch(
                env_file,
                severity=severity,   # type: ignore[arg-type]
                title="Vortex resource watchdog",
                body="; ".join(alerts) + f"\ndisk_free_pct={free_pct:.1f}"
                     f"\nrss_mb={rss_mb}\ncpu_sec_delta={cpu_delta:.0f}",
                tags=["resource_watchdog"],
            )
        except Exception as e:
            logger.debug("alerts dispatch failed: %s", e)

    return {
        "message":        "; ".join(alerts) or "ok",
        "disk_free_pct":  round(free_pct, 1),
        "rss_mb":         rss_mb,
        "cpu_sec_delta":  round(cpu_delta, 1),
        "alerts":         alerts,
    }


# ── Job: uptime ping (updates rolling window) ─────────────────────────────

def _uptime_path(env_file: Path) -> Path:
    return env_file.parent / "uptime.ndjson"


async def job_uptime_ping(env_file: Path) -> dict:
    """Self-ping the node and append the result to uptime.ndjson.

    Rolling window — old rows pruned automatically.
    """
    env = _backup_api._read_env(env_file)
    host = env.get("HOST", "127.0.0.1")
    if host == "0.0.0.0":
        host = "127.0.0.1"
    try:
        port = int(env.get("PORT", "9000"))
    except ValueError:
        port = 9000
    proto = "https" if (Path("certs") / "vortex.crt").is_file() else "http"
    url = f"{proto}://{host}:{port}/health"

    up = 0
    try:
        async with httpx.AsyncClient(timeout=3.0, verify=False) as c:
            r = await c.get(url)
            up = 1 if r.status_code == 200 else 0
    except Exception:
        up = 0

    ts = int(time.time())
    line = json.dumps({"ts": ts, "up": up}) + "\n"

    p = _uptime_path(env_file)
    try:
        with p.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass

    # Trim file once it gets past ~2*window
    try:
        cutoff = ts - _UPTIME_WINDOW_DAYS * 86400 - 3600
        _trim_uptime(p, cutoff)
    except Exception:
        pass

    return {"message": "up" if up else "down", "up": up}


def _trim_uptime(p: Path, cutoff: int) -> None:
    if not p.is_file():
        return
    if p.stat().st_size < 64 * 1024:
        return      # too small to bother — rewrite is wasteful
    keep_lines = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
                if int(rec.get("ts", 0)) >= cutoff:
                    keep_lines.append(line)
            except Exception:
                continue
    p.write_text("".join(keep_lines), encoding="utf-8")


def _uptime_percent(env_file: Path, window_sec: int = _UPTIME_WINDOW_DAYS * 86400) -> tuple[float, int, int]:
    """Compute (uptime_pct, total_samples, up_samples) over the window."""
    p = _uptime_path(env_file)
    if not p.is_file():
        return 100.0, 0, 0
    now = int(time.time())
    total = up = 0
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
                if int(rec.get("ts", 0)) < now - window_sec:
                    continue
                total += 1
                up += int(rec.get("up", 0))
            except Exception:
                continue
    if total == 0:
        return 100.0, 0, 0
    return round(100.0 * up / total, 2), total, up


# ── Lifecycle hook (called from server.py at startup) ─────────────────────

def install_default_jobs(env_file: Path) -> None:
    s = _sched.get(env_file)
    s.register("cron_backup",       job_cron_backup,       default_interval="daily")
    s.register("prune",             job_prune,             default_interval="weekly")
    s.register("resource_watchdog", job_resource_watchdog, default_interval="hourly")
    s.register("uptime_ping",       job_uptime_ping,       default_interval="hourly")
    # JWT rotation — default off; operator opts in by flipping interval.
    from . import security_api as _sec
    s.register("jwt_rotate",        _sec.job_jwt_rotate,   default_interval="off")

    # Wave-10 jobs (mirror backup, autocompound candidate staging)
    try:
        from . import operator as _op
        _op.install_jobs(env_file)
    except Exception as e:
        logger.warning("operator jobs install failed: %s", e)

    # Monitoring — custom alert rules (W2)
    try:
        from . import monitoring as _mon
        _mon.install_monitoring_jobs(env_file)
    except Exception as e:
        logger.warning("monitoring jobs install failed: %s", e)

    # DB operations — PITR snapshots (W3)
    try:
        from . import db_ops as _dbo
        _dbo.install_dbops_jobs(env_file)
    except Exception as e:
        logger.warning("dbops jobs install failed: %s", e)

    # Peer advanced — blacklist expiry (W4)
    try:
        from . import peer_advanced as _pa
        _pa.install_peer_adv_jobs(env_file)
    except Exception as e:
        logger.warning("peer_advanced jobs install failed: %s", e)

    # Secrets — expiry reminder (W5)
    try:
        from . import secrets_mgr as _sm
        _sm.install_secrets_jobs(env_file)
    except Exception as e:
        logger.warning("secrets_mgr jobs install failed: %s", e)

    # Backup plus — multi-controller + integrity check (W6)
    try:
        from . import backup_plus as _bp
        _bp.install_backup_plus_jobs(env_file)
    except Exception as e:
        logger.warning("backup_plus jobs install failed: %s", e)

    s.start()


# ── Endpoints ─────────────────────────────────────────────────────────────

class IntervalBody(BaseModel):
    interval: str = Field(..., pattern=r"^(off|hourly|daily|weekly)$")


def _env_file(request: Request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


@router.get("/jobs")
async def list_jobs(request: Request) -> dict:
    s = _sched.get(_env_file(request))
    return {
        "jobs":      s.jobs(),
        "presets":   list(_sched.INTERVAL_PRESETS.keys()),
        "tick_sec":  s._tick_sec,
    }


@router.patch("/jobs/{name}")
async def patch_job(name: str, body: IntervalBody, request: Request) -> dict:
    s = _sched.get(_env_file(request))
    try:
        s.set_interval(name, body.interval)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "name": name, "interval": body.interval}


@router.post("/jobs/{name}/run")
async def run_job(name: str, request: Request) -> dict:
    s = _sched.get(_env_file(request))
    try:
        res = await s.run_once(name)
    except KeyError:
        raise HTTPException(404, "unknown job")
    return {"ok": True, "name": name, "result": res}


# Uptime badge — public-readable SVG so operators can embed on a website.
@router.get("/uptime/badge.svg")
async def uptime_badge(request: Request) -> Response:
    pct, total, up = _uptime_percent(_env_file(request))
    color = "#22c55e" if pct >= 99 else ("#eab308" if pct >= 95 else "#ef4444")
    label = "uptime"
    value = f"{pct}% ({total}s)"
    # shields.io-style flat SVG, width auto-ish based on text length.
    w_left = 6 + 6 * len(label)
    w_right = 6 + 6 * len(value)
    total_w = w_left + w_right
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="20">
  <linearGradient id="b" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <mask id="a"><rect width="{total_w}" height="20" rx="3" fill="#fff"/></mask>
  <g mask="url(#a)">
    <path fill="#555" d="M0 0h{w_left}v20H0z"/>
    <path fill="{color}" d="M{w_left} 0h{w_right}v20H{w_left}z"/>
    <path fill="url(#b)" d="M0 0h{total_w}v20H0z"/>
  </g>
  <g fill="#fff" text-anchor="middle"
     font-family="Verdana,Geneva,sans-serif" font-size="11">
    <text x="{w_left/2}" y="14">{label}</text>
    <text x="{w_left + w_right/2}" y="14">{value}</text>
  </g>
</svg>"""
    return Response(content=svg, media_type="image/svg+xml", headers={
        "Cache-Control": "public, max-age=60",
    })


@router.get("/uptime")
async def uptime_stats(request: Request) -> dict:
    pct, total, up = _uptime_percent(_env_file(request))
    return {
        "uptime_pct":   pct,
        "total_samples": total,
        "up_samples":    up,
        "window_days":   _UPTIME_WINDOW_DAYS,
    }


# Version pinning — simple flag in .env.
class VersionPinBody(BaseModel):
    pinned: bool


@router.get("/version")
async def version_info(request: Request) -> dict:
    from vortex_wizard import VERSION
    env_file = _env_file(request)
    env = _backup_api._read_env(env_file)
    return {
        "version": VERSION,
        "pinned":  env.get("VERSION_PIN", "").lower() in ("1", "true", "yes"),
    }


@router.post("/version/pin")
async def set_version_pin(body: VersionPinBody, request: Request) -> dict:
    env_file = _env_file(request)
    lines: list[str] = []
    found = False
    target = "true" if body.pinned else "false"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("VERSION_PIN="):
                lines.append(f"VERSION_PIN={target}")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"VERSION_PIN={target}")
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "pinned": body.pinned}
