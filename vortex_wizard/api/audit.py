"""Wizard-local admin audit log.

Records every request to ``/api/wiz/admin/*`` with actor IP, path, HTTP
status, and duration. Kept in a dedicated SQLite file next to the wizard's
``.env`` so audit history survives node crashes and is independent of the
main Vortex DB.

Also surfaces an "unknown IP" alert: if the client IP has never hit the
admin surface before, the row is flagged ``alert=1``. The operator can
see the list in the Audit tab and dismiss false positives.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Awaitable, Callable, Optional

from fastapi import APIRouter, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin/audit", tags=["audit"])


# ── Storage ───────────────────────────────────────────────────────────────

_DB_FILENAME = "wizard_audit.db"
_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            INTEGER NOT NULL,
    method        TEXT    NOT NULL,
    path          TEXT    NOT NULL,
    client_ip     TEXT,
    node_pubkey   TEXT,
    status        INTEGER,
    duration_ms   INTEGER,
    alert         INTEGER DEFAULT 0,
    alert_reason  TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_ts ON audit_entries(ts);
CREATE INDEX IF NOT EXISTS ix_audit_alert ON audit_entries(alert);
CREATE TABLE IF NOT EXISTS audit_known_ips (
    ip          TEXT PRIMARY KEY,
    first_seen  INTEGER NOT NULL,
    trusted     INTEGER DEFAULT 0
);
"""


def _audit_db_path(env_file: Path) -> Path:
    return env_file.parent / _DB_FILENAME


def _conn(env_file: Path) -> sqlite3.Connection:
    p = _audit_db_path(env_file)
    c = sqlite3.connect(str(p), isolation_level=None)
    c.executescript(_SCHEMA)
    c.row_factory = sqlite3.Row
    return c


def _is_known_ip(c: sqlite3.Connection, ip: str) -> bool:
    row = c.execute("SELECT 1 FROM audit_known_ips WHERE ip=?", (ip,)).fetchone()
    return row is not None


def _register_ip(c: sqlite3.Connection, ip: str, ts: int) -> None:
    c.execute(
        "INSERT OR IGNORE INTO audit_known_ips(ip, first_seen, trusted) VALUES (?, ?, 0)",
        (ip, ts),
    )


def _insert_entry(
    env_file: Path,
    *,
    method: str,
    path: str,
    client_ip: str,
    node_pubkey: str,
    status: int,
    duration_ms: int,
) -> None:
    # Strip bearer tokens and anything after "?" to avoid leaking secrets
    # into the audit log.
    safe_path = path.split("?", 1)[0][:512]
    ts = int(time.time())
    try:
        c = _conn(env_file)
    except Exception as e:
        logger.debug("audit: db open failed %s", e)
        return

    alert = 0
    alert_reason: Optional[str] = None
    try:
        # First time we see this IP → flag as unknown. Loopback is always
        # trusted — it's the wizard itself hitting itself.
        if client_ip and client_ip not in ("127.0.0.1", "::1", "localhost"):
            if not _is_known_ip(c, client_ip):
                alert = 1
                alert_reason = "new_ip"
            _register_ip(c, client_ip, ts)

        c.execute(
            "INSERT INTO audit_entries "
            "(ts, method, path, client_ip, node_pubkey, status, duration_ms, alert, alert_reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ts, method, safe_path, client_ip, node_pubkey, status, duration_ms, alert, alert_reason),
        )
    except Exception as e:
        logger.debug("audit: insert failed %s", e)
    finally:
        try: c.close()
        except Exception: pass


def _purge_old(env_file: Path, keep_entries: int = 10_000) -> None:
    """Cap the log at N newest entries so it can't grow unbounded."""
    try:
        c = _conn(env_file)
        c.execute(
            "DELETE FROM audit_entries WHERE id NOT IN "
            "(SELECT id FROM audit_entries ORDER BY id DESC LIMIT ?)",
            (keep_entries,),
        )
        c.close()
    except Exception:
        pass


# ── Middleware ────────────────────────────────────────────────────────────

class AuditMiddleware(BaseHTTPMiddleware):
    """Stamp every /api/wiz/admin/* request with an audit row."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable],
    ):
        path = request.url.path
        # Only the wizard admin surface is interesting. Setup is pre-auth,
        # logs endpoint gets called every 3s by the UI — those would drown
        # the signal. Audit itself is skipped to avoid self-logs.
        if not path.startswith("/api/wiz/admin/"):
            return await call_next(request)
        if path.startswith("/api/wiz/admin/audit"):
            return await call_next(request)
        if path.startswith("/api/wiz/admin/logs"):
            return await call_next(request)
        if path.startswith("/api/wiz/admin/metrics"):
            return await call_next(request)

        env_file = getattr(request.app.state, "env_file", None)
        if env_file is None:
            return await call_next(request)

        t0 = time.monotonic()
        status = 0
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            duration_ms = int((time.monotonic() - t0) * 1000)
            # Pick the best-available client IP. Starlette gives us a
            # Request.client (host, port) tuple if the request made it
            # through the ASGI scope.
            client_ip = ""
            try:
                if request.client:
                    client_ip = request.client.host or ""
                fwd = request.headers.get("x-forwarded-for", "")
                if fwd:
                    # X-Forwarded-For can be a list — the leftmost is the
                    # originating client when the proxy is trusted.
                    client_ip = fwd.split(",", 1)[0].strip() or client_ip
            except Exception:
                client_ip = ""
            node_pubkey = ""
            try:
                sk = getattr(request.app.state, "signing_key", None)
                if sk is not None:
                    node_pubkey = sk.pubkey_hex()
            except Exception:
                pass

            _insert_entry(
                Path(env_file),
                method=request.method,
                path=path,
                client_ip=client_ip,
                node_pubkey=node_pubkey,
                status=status,
                duration_ms=duration_ms,
            )
            # Cheap to call — SQLite's DELETE on indexed id is O(log n).
            _purge_old(Path(env_file))


# ── Endpoints ─────────────────────────────────────────────────────────────

def _env(request: Request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    if p is None:
        raise HTTPException(500, "wizard env not configured")
    return Path(p)


@router.get("")
async def list_audit(
    request: Request,
    limit:      int = 100,
    offset:     int = 0,
    only_alert: bool = False,
) -> dict:
    env_file = _env(request)
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    c = _conn(env_file)
    try:
        if only_alert:
            rows = c.execute(
                "SELECT * FROM audit_entries WHERE alert=1 "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            total = c.execute("SELECT COUNT(*) FROM audit_entries WHERE alert=1").fetchone()[0]
        else:
            rows = c.execute(
                "SELECT * FROM audit_entries ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            total = c.execute("SELECT COUNT(*) FROM audit_entries").fetchone()[0]

        alert_count = c.execute(
            "SELECT COUNT(*) FROM audit_entries WHERE alert=1"
        ).fetchone()[0]
        known_ips = [
            dict(r) for r in c.execute(
                "SELECT ip, first_seen, trusted FROM audit_known_ips ORDER BY first_seen DESC"
            ).fetchall()
        ]
    finally:
        c.close()

    return {
        "total":        int(total),
        "alert_total":  int(alert_count),
        "entries":      [dict(r) for r in rows],
        "known_ips":    known_ips,
    }


@router.post("/trust_ip")
async def trust_ip(request: Request) -> dict:
    """Mark an IP as trusted — clears the alert flag for its past rows."""
    body = await request.json()
    ip = (body.get("ip") or "").strip()
    if not ip:
        raise HTTPException(400, "ip required")
    env_file = _env(request)
    c = _conn(env_file)
    try:
        c.execute(
            "INSERT INTO audit_known_ips(ip, first_seen, trusted) VALUES (?, ?, 1) "
            "ON CONFLICT(ip) DO UPDATE SET trusted=1",
            (ip, int(time.time())),
        )
        c.execute("UPDATE audit_entries SET alert=0 WHERE client_ip=?", (ip,))
    finally:
        c.close()
    return {"ok": True, "ip": ip}


@router.post("/clear")
async def clear_audit(request: Request) -> dict:
    env_file = _env(request)
    c = _conn(env_file)
    try:
        c.execute("DELETE FROM audit_entries")
        c.execute("DELETE FROM audit_known_ips")
    finally:
        c.close()
    return {"ok": True}
