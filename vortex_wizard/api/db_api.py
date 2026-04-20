"""Wizard-managed PostgreSQL lifecycle.

Goal: operator clicks one button, types a password, gets a working
Postgres 17 cluster living under ``state_root/pgdata`` with a role and
database both named ``vortex``. Wizard writes ``DATABASE_URL`` into the
same ``.env`` the node reads, so the next node start-up uses Postgres
automatically.

Approach:
  * Detect ``initdb`` / ``pg_ctl`` / ``createdb`` / ``createuser`` on
    PATH + brew / linux standard prefixes.
  * If missing and we're on macOS with Homebrew available, offer to run
    ``brew install postgresql@17``. No silent installs — everything is
    reported back through streaming progress.
  * Cluster + logs live under the per-user state dir. The wizard never
    touches system-wide Postgres installs (``/Library/PostgreSQL/*``,
    ``/var/lib/postgresql``, etc.).
  * All destructive operations require a JSON body — no query-string
    triggers.

Endpoints exposed (prefix ``/api/wiz/admin/db``):

    GET  /status    → detection + cluster + running state
    POST /setup     → install + initdb + start + role + db + .env
    POST /start     → pg_ctl start (idempotent)
    POST /stop      → pg_ctl stop -m fast
    POST /uninstall → drop cluster + rewrite .env back to SQLite

The endpoints do not stream — they do the work inline and return when
each stage finishes. For big brew installs the caller keeps the browser
busy; UI shows a spinner.
"""
from __future__ import annotations

import logging
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/wiz/admin/db", tags=["db"])

logger = logging.getLogger(__name__)

# Pinned major version — we want deterministic initdb -> pg_ctl behaviour
# across machines. If the operator already has another major version on
# PATH we happily use that instead.
_PREFERRED_PG_MAJOR = "17"


# ── Path resolution ────────────────────────────────────────────────────────


def _env_path(request: Request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


def _pgdata(request: Request) -> Path:
    return _env_path(request).parent / "pgdata"


def _pglog(request: Request) -> Path:
    logs = _env_path(request).parent / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs / "postgres.log"


# ── Binary discovery ──────────────────────────────────────────────────────


_BREW_PREFIXES = (
    "/opt/homebrew",             # Apple Silicon
    "/usr/local",                # Intel / Linux brew
)


def _find_pg_bin(name: str) -> Optional[str]:
    """Find a Postgres binary by name, preferring the pinned major version."""
    # Prefer the versioned brew install (keeps us on a known dialect).
    for prefix in _BREW_PREFIXES:
        cand = f"{prefix}/opt/postgresql@{_PREFERRED_PG_MAJOR}/bin/{name}"
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    # Then any recent Postgres that brew laid into /opt/.../bin.
    for prefix in _BREW_PREFIXES:
        cand = f"{prefix}/bin/{name}"
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    # Fall back to system PATH.
    hit = shutil.which(name)
    if hit:
        return hit
    # Linux common paths
    for cand in (
        f"/usr/lib/postgresql/{_PREFERRED_PG_MAJOR}/bin/{name}",
        f"/usr/pgsql-{_PREFERRED_PG_MAJOR}/bin/{name}",
        f"/usr/bin/{name}",
    ):
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def _find_brew() -> Optional[str]:
    hit = shutil.which("brew")
    if hit:
        return hit
    for p in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew"):
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


# ── Running state ──────────────────────────────────────────────────────────


def _pg_is_running(pgdata: Path) -> bool:
    """True if pg_ctl status on our cluster says it's up."""
    pg_ctl = _find_pg_bin("pg_ctl")
    if not pg_ctl or not pgdata.is_dir():
        return False
    try:
        r = subprocess.run(
            [pg_ctl, "status", "-D", str(pgdata)],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _pick_free_pg_port(start: int = 5432, tries: int = 10) -> int:
    """Find a free port for postgres (fallback if 5432 is taken)."""
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    # Last resort — let the kernel assign
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _read_env_at(env_file: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not env_file.is_file():
        return out
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def _write_env_keys(env_file: Path, updates: dict[str, Optional[str]]) -> None:
    """Overwrite / delete specific keys in .env without disturbing the rest."""
    lines: list[str] = []
    seen: set[str] = set()
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k = stripped.split("=", 1)[0].strip()
                if k in updates:
                    seen.add(k)
                    new = updates[k]
                    if new is None:
                        continue           # drop the key entirely
                    lines.append(f"{k}={new}")
                    continue
            lines.append(line)
    for k, v in updates.items():
        if k in seen or v is None:
            continue
        lines.append(f"{k}={v}")
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(env_file, 0o600)
    except OSError:
        pass


# ── Status ─────────────────────────────────────────────────────────────────


@router.get("/status")
async def db_status(request: Request) -> dict:
    """Report everything the UI needs to decide whether to show Setup."""
    env = _read_env_at(_env_path(request))
    database_url = env.get("DATABASE_URL", "")
    uses_postgres = database_url.startswith("postgresql://") or database_url.startswith("postgres://")

    pg_ctl  = _find_pg_bin("pg_ctl")
    initdb  = _find_pg_bin("initdb")
    brew    = _find_brew()
    pgdata  = _pgdata(request)
    running = _pg_is_running(pgdata)

    return {
        "installed":     pg_ctl is not None and initdb is not None,
        "pg_ctl":        pg_ctl,
        "initdb":        initdb,
        "cluster_inited": pgdata.is_dir() and (pgdata / "PG_VERSION").is_file(),
        "pgdata":        str(pgdata),
        "running":       running,
        "brew":          brew,
        "preferred_major": _PREFERRED_PG_MAJOR,
        "env_uses_postgres": uses_postgres,
        "current_database_url_masked":
            (database_url[:30] + "…") if database_url else "",
    }


# ── Setup (the big button) ────────────────────────────────────────────────


class SetupBody(BaseModel):
    password: str = Field(
        ...,
        min_length=8,
        description="Password for the new 'vortex' Postgres role",
    )
    port: int = Field(
        0, ge=0, le=65535,
        description="Bind port (0 = auto-pick, default 5432 if free)",
    )
    force_install: bool = Field(
        False,
        description="Run 'brew install postgresql@N' even if Postgres is on PATH",
    )


@router.post("/setup")
async def db_setup(body: SetupBody, request: Request) -> dict:
    """Install (if needed), init cluster, start, create role+db, write .env."""
    env_file = _env_path(request)
    pgdata   = _pgdata(request)
    pglog    = _pglog(request)
    steps: list[dict] = []

    def _step(name: str, **kv) -> None:
        steps.append({"name": name, **kv})
        logger.info("db_setup %s: %s", name, kv)

    # 1. Install postgres via brew if we don't find the binaries.
    if body.force_install or not _find_pg_bin("pg_ctl") or not _find_pg_bin("initdb"):
        brew = _find_brew()
        if not brew:
            raise HTTPException(
                500,
                "Homebrew not found. Either install Homebrew "
                "(https://brew.sh) so the wizard can 'brew install "
                "postgresql', OR install PostgreSQL 17 yourself (e.g. "
                "https://postgresapp.com) and try again.",
            )
        pkg = f"postgresql@{_PREFERRED_PG_MAJOR}"
        _step("brew_install_start", pkg=pkg)
        try:
            r = subprocess.run(
                [brew, "install", pkg],
                capture_output=True, text=True, timeout=900,
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(500, "brew install timed out after 15 min")
        if r.returncode != 0:
            raise HTTPException(500, f"brew install failed: {r.stderr[:800]}")
        _step("brew_install_done", stdout_tail=r.stdout[-200:])

        # Make sure our lookups pick it up next call.
        if not _find_pg_bin("pg_ctl"):
            raise HTTPException(
                500,
                f"brew install succeeded but pg_ctl still missing — "
                f"try 'brew link postgresql@{_PREFERRED_PG_MAJOR}' manually",
            )

    initdb    = _find_pg_bin("initdb")
    pg_ctl    = _find_pg_bin("pg_ctl")
    psql      = _find_pg_bin("psql")
    createdb  = _find_pg_bin("createdb")
    createuser = _find_pg_bin("createuser")
    assert initdb and pg_ctl, "binaries checked above"

    # 2. initdb if the directory is empty / fresh.
    if not (pgdata / "PG_VERSION").is_file():
        if pgdata.is_dir() and any(pgdata.iterdir()):
            raise HTTPException(
                409,
                f"{pgdata} is non-empty but has no PG_VERSION. Refusing to "
                "overwrite. Remove it manually or pick a different location.",
            )
        pgdata.mkdir(parents=True, exist_ok=True)
        # Use scram-sha-256 for the new role's password (secure default).
        _step("initdb_start", pgdata=str(pgdata))
        r = subprocess.run(
            [initdb, "-D", str(pgdata),
             "--auth-local=trust", "--auth-host=scram-sha-256",
             "--encoding=UTF8", "--locale=C",
             "--username=postgres"],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            raise HTTPException(500, f"initdb failed: {r.stderr[:800]}")
        _step("initdb_done")

    # 3. Pick a port. Prefer whatever's in postgresql.conf, else
    # 5432 if free, else the first free port.
    conf = pgdata / "postgresql.conf"
    existing_port = 5432
    if conf.is_file():
        for line in conf.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"\s*port\s*=\s*(\d+)", line)
            if m:
                existing_port = int(m.group(1))
                break
    port = body.port or existing_port
    # If neither user-chosen nor existing port is actually free, step down.
    def _is_free(p: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try: s.bind(("127.0.0.1", p)); return True
            except OSError: return False
    if not _is_free(port) and not _pg_is_running(pgdata):
        port = _pick_free_pg_port()

    # Persist the chosen port on the cluster.
    _rewrite_conf_port(conf, port)
    _step("port_picked", port=port)

    # 4. Start pg_ctl.
    if not _pg_is_running(pgdata):
        _step("pg_ctl_start")
        r = subprocess.run(
            [pg_ctl, "-D", str(pgdata), "-l", str(pglog),
             "-o", f"-p {port}", "-w", "-t", "30", "start"],
            capture_output=True, text=True, timeout=40,
        )
        if r.returncode != 0:
            raise HTTPException(500, f"pg_ctl start failed: {r.stderr[:800]}")
    else:
        _step("pg_ctl_already_running")

    # 5. Create role + database via unix socket — initdb set
    # --auth-local=trust so the postgres superuser can log in locally
    # without a password. Connecting via TCP (PGHOST=127.0.0.1) would
    # hit the scram-sha-256 rule and fail with "no password supplied".
    # Point PGHOST at the socket directory postgres is listening on
    # (default /tmp on macOS, /var/run/postgresql on Debian); empty
    # PGHOST tells libpq to use the platform default socket path.
    socket_dir = ""
    for candidate in ("/tmp", "/var/run/postgresql", str(pgdata)):
        if Path(candidate).is_dir() and \
           (Path(candidate) / f".s.PGSQL.{port}").exists():
            socket_dir = candidate
            break
    env = {**os.environ, "PGPORT": str(port), "PGUSER": "postgres"}
    # Unset any inherited PGHOST so libpq picks default socket.
    env.pop("PGHOST", None)
    if socket_dir:
        env["PGHOST"] = socket_dir

    role = "vortex"
    dbname = "vortex"
    # Set / reset role password via ALTER ROLE so re-running this endpoint
    # after forgetting the password still works.
    create_sql = (
        f"DO $$ BEGIN "
        f"  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') "
        f"  THEN CREATE ROLE {role} LOGIN; "
        f"  END IF; "
        f"END $$;"
    )
    alter_sql = f"ALTER ROLE {role} WITH LOGIN PASSWORD '{_escape_sql(body.password)}';"
    assert psql, "psql should be present alongside pg_ctl"
    for sql in (create_sql, alter_sql):
        r = subprocess.run(
            [psql, "-v", "ON_ERROR_STOP=1", "-d", "postgres",
             "-c", sql],
            capture_output=True, text=True, timeout=15, env=env,
        )
        if r.returncode != 0:
            raise HTTPException(500, f"role setup failed: {r.stderr[:400]}")

    # Create the DB only if missing.
    r = subprocess.run(
        [psql, "-At", "-d", "postgres",
         "-c", f"SELECT 1 FROM pg_database WHERE datname = '{dbname}'"],
        capture_output=True, text=True, timeout=10, env=env,
    )
    if r.stdout.strip() != "1":
        if createdb is None:
            raise HTTPException(500, "createdb binary missing alongside pg_ctl")
        r = subprocess.run(
            [createdb, "-O", role, dbname],
            capture_output=True, text=True, timeout=15, env=env,
        )
        if r.returncode != 0 and "already exists" not in (r.stderr or ""):
            raise HTTPException(500, f"createdb failed: {r.stderr[:400]}")
    _step("role_and_db_ready", role=role, database=dbname, port=port)

    # 6. Write DATABASE_URL (and companion POSTGRES_* for apps that want
    # the individual components). Old SQLite path is left intact so an
    # /uninstall flip back is a one-liner.
    database_url = f"postgresql+asyncpg://{role}:{_url_quote(body.password)}@127.0.0.1:{port}/{dbname}"
    sync_database_url = f"postgresql+psycopg2://{role}:{_url_quote(body.password)}@127.0.0.1:{port}/{dbname}"
    _write_env_keys(env_file, {
        "DATABASE_URL":      database_url,
        "SYNC_DATABASE_URL": sync_database_url,
        "POSTGRES_HOST":     "127.0.0.1",
        "POSTGRES_PORT":     str(port),
        "POSTGRES_USER":     role,
        "POSTGRES_PASSWORD": body.password,
        "POSTGRES_DB":       dbname,
    })
    _step("env_updated", database_url="postgresql://" + role + ":***@127.0.0.1:" + str(port) + "/" + dbname)

    return {
        "ok":     True,
        "steps":  steps,
        "note":   "Node must be restarted to pick up the new DATABASE_URL",
        "port":   port,
        "pgdata": str(pgdata),
    }


# ── Start / stop / uninstall ──────────────────────────────────────────────


@router.post("/start")
async def db_start(request: Request) -> dict:
    pgdata = _pgdata(request)
    if not (pgdata / "PG_VERSION").is_file():
        raise HTTPException(409, f"cluster not initialised at {pgdata} — run /setup first")
    if _pg_is_running(pgdata):
        return {"ok": True, "already_running": True}
    pg_ctl = _find_pg_bin("pg_ctl")
    pglog = _pglog(request)
    if not pg_ctl:
        raise HTTPException(500, "pg_ctl not found")
    # Read port from postgresql.conf
    port = 5432
    conf = pgdata / "postgresql.conf"
    if conf.is_file():
        for line in conf.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"\s*port\s*=\s*(\d+)", line)
            if m:
                port = int(m.group(1))
                break
    r = subprocess.run(
        [pg_ctl, "-D", str(pgdata), "-l", str(pglog),
         "-o", f"-p {port}", "-w", "-t", "30", "start"],
        capture_output=True, text=True, timeout=40,
    )
    if r.returncode != 0:
        raise HTTPException(500, f"pg_ctl start failed: {r.stderr[:400]}")
    return {"ok": True, "started": True, "port": port}


@router.post("/stop")
async def db_stop(request: Request) -> dict:
    pgdata = _pgdata(request)
    if not _pg_is_running(pgdata):
        return {"ok": True, "was_running": False}
    pg_ctl = _find_pg_bin("pg_ctl")
    if not pg_ctl:
        raise HTTPException(500, "pg_ctl not found")
    r = subprocess.run(
        [pg_ctl, "-D", str(pgdata), "-m", "fast", "-w", "-t", "30", "stop"],
        capture_output=True, text=True, timeout=40,
    )
    if r.returncode != 0:
        raise HTTPException(500, f"pg_ctl stop failed: {r.stderr[:400]}")
    return {"ok": True, "stopped": True}


class UninstallBody(BaseModel):
    confirm: bool = Field(False, description="must be true — destructive")
    remove_cluster: bool = Field(True)


@router.post("/uninstall")
async def db_uninstall(body: UninstallBody, request: Request) -> dict:
    """Stop the cluster, optionally wipe pgdata, revert .env to SQLite."""
    if not body.confirm:
        raise HTTPException(400, "uninstall is destructive — pass confirm=true")
    pgdata = _pgdata(request)
    if _pg_is_running(pgdata):
        pg_ctl = _find_pg_bin("pg_ctl")
        if pg_ctl:
            subprocess.run(
                [pg_ctl, "-D", str(pgdata), "-m", "fast", "-w", "stop"],
                capture_output=True, text=True, timeout=30,
            )
    removed = False
    if body.remove_cluster and pgdata.is_dir():
        shutil.rmtree(pgdata, ignore_errors=True)
        removed = not pgdata.is_dir()

    env_file = _env_path(request)
    _write_env_keys(env_file, {
        "DATABASE_URL":      None,   # drop entirely — app falls back to CONTROLLER_DB/SQLite
        "SYNC_DATABASE_URL": None,
        "POSTGRES_HOST":     None,
        "POSTGRES_PORT":     None,
        "POSTGRES_USER":     None,
        "POSTGRES_PASSWORD": None,
        "POSTGRES_DB":       None,
    })
    return {"ok": True, "cluster_removed": removed}


# ── Helpers ────────────────────────────────────────────────────────────────


# ── DB viewer (read-only introspection) ───────────────────────────────────


def _resolve_db_url(env: dict[str, str], env_file: Path) -> tuple[str, str]:
    """Return (kind, connection_url) where kind ∈ {'postgres', 'sqlite'}.

    Prefers DATABASE_URL from .env. If that's absent or it's a sync
    postgres URL, we normalise to a form the chosen library understands.
    Falls back to the SQLite file next to the env.
    """
    url = (env.get("DATABASE_URL") or "").strip()
    if url.startswith("postgresql") or url.startswith("postgres://"):
        return "postgres", url
    db_path = env.get("DB_PATH", "vortex.db")
    sqlite_path = Path(db_path)
    if not sqlite_path.is_absolute():
        sqlite_path = env_file.parent / sqlite_path
    return "sqlite", str(sqlite_path)


@router.get("/tables")
async def db_tables(request: Request) -> dict:
    """List user tables with approximate row count + size."""
    env = _read_env_at(_env_path(request))
    kind, url_or_path = _resolve_db_url(env, _env_path(request))

    if kind == "sqlite":
        import sqlite3
        if not Path(url_or_path).is_file():
            return {"kind": "sqlite", "path": url_or_path, "tables": [],
                    "note": "database file does not exist yet"}
        con = sqlite3.connect(url_or_path)
        try:
            cur = con.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
            tables: list[dict] = []
            for (name,) in cur.fetchall():
                safe = _safe_ident(name)
                cur.execute(f"SELECT COUNT(*) FROM {safe}")
                rows = cur.fetchone()[0]
                tables.append({"name": name, "rows": rows, "bytes": None})
        finally:
            con.close()
        total = Path(url_or_path).stat().st_size
        return {"kind": "sqlite", "path": url_or_path,
                "total_bytes": total, "tables": tables}

    # Postgres — use the wizard-owned role via PGPASSWORD so we don't
    # need to parse the URL in Python. Cheap and robust.
    psql = _find_pg_bin("psql")
    if not psql:
        raise HTTPException(500, "psql not found — is PostgreSQL installed?")
    spawn_env = {
        **os.environ,
        "PGHOST":     env.get("POSTGRES_HOST", "127.0.0.1"),
        "PGPORT":     env.get("POSTGRES_PORT", "5432"),
        "PGUSER":     env.get("POSTGRES_USER", "vortex"),
        "PGPASSWORD": env.get("POSTGRES_PASSWORD", ""),
    }
    dbname = env.get("POSTGRES_DB", "vortex")
    # One query — table name, row count estimate, pretty size.
    sql = (
        "SELECT relname, n_live_tup, pg_total_relation_size(relid) "
        "FROM pg_stat_user_tables ORDER BY relname"
    )
    r = subprocess.run(
        [psql, "-At", "-F", "\t", "-d", dbname, "-c", sql],
        capture_output=True, text=True, timeout=10, env=spawn_env,
    )
    if r.returncode != 0:
        raise HTTPException(500, f"psql: {r.stderr[:400]}")
    tables = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            tables.append({
                "name":  parts[0],
                "rows":  int(parts[1] or 0),
                "bytes": int(parts[2] or 0),
            })
    # Total database size
    r2 = subprocess.run(
        [psql, "-At", "-d", dbname, "-c", f"SELECT pg_database_size('{dbname}')"],
        capture_output=True, text=True, timeout=5, env=spawn_env,
    )
    total = int(r2.stdout.strip() or "0") if r2.returncode == 0 else 0
    return {
        "kind":        "postgres",
        "host":        spawn_env["PGHOST"],
        "port":        int(spawn_env["PGPORT"]),
        "database":    dbname,
        "total_bytes": total,
        "tables":      tables,
    }


@router.get("/table/{name}")
async def db_table_rows(
    name: str, request: Request,
    limit: int = 50, offset: int = 0,
) -> dict:
    """Read up to ``limit`` rows from a single table — read-only preview."""
    if limit < 1 or limit > 500:
        raise HTTPException(400, "limit must be between 1 and 500")
    if offset < 0:
        raise HTTPException(400, "offset must be >= 0")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise HTTPException(400, "invalid table name")

    env = _read_env_at(_env_path(request))
    kind, url_or_path = _resolve_db_url(env, _env_path(request))

    if kind == "sqlite":
        import sqlite3
        if not Path(url_or_path).is_file():
            return {"columns": [], "rows": [], "total": 0}
        con = sqlite3.connect(url_or_path)
        try:
            cur = con.cursor()
            cur.execute(f"SELECT COUNT(*) FROM {_safe_ident(name)}")
            total = cur.fetchone()[0]
            cur.execute(
                f"SELECT * FROM {_safe_ident(name)} "
                f"LIMIT {int(limit)} OFFSET {int(offset)}"
            )
            cols = [d[0] for d in cur.description]
            rows = [list(row) for row in cur.fetchall()]
        finally:
            con.close()
        return {"columns": cols,
                "rows": [_stringify_row(r) for r in rows],
                "total": total}

    # Postgres
    psql = _find_pg_bin("psql")
    if not psql:
        raise HTTPException(500, "psql not found")
    spawn_env = {
        **os.environ,
        "PGHOST":     env.get("POSTGRES_HOST", "127.0.0.1"),
        "PGPORT":     env.get("POSTGRES_PORT", "5432"),
        "PGUSER":     env.get("POSTGRES_USER", "vortex"),
        "PGPASSWORD": env.get("POSTGRES_PASSWORD", ""),
    }
    dbname = env.get("POSTGRES_DB", "vortex")
    # Count
    rc = subprocess.run(
        [psql, "-At", "-d", dbname,
         "-c", f"SELECT COUNT(*) FROM \"{name}\""],
        capture_output=True, text=True, timeout=10, env=spawn_env,
    )
    total = int(rc.stdout.strip() or "0") if rc.returncode == 0 else 0
    # Rows — use \COPY-like TSV dump via -At for simplicity
    sql = (
        f"SELECT * FROM \"{name}\" ORDER BY 1 "
        f"LIMIT {int(limit)} OFFSET {int(offset)}"
    )
    r = subprocess.run(
        [psql, "-A", "-F", "\t", "-P", "null=∅", "-d", dbname, "-c", sql],
        capture_output=True, text=True, timeout=15, env=spawn_env,
    )
    if r.returncode != 0:
        raise HTTPException(500, f"psql: {r.stderr[:400]}")
    lines = r.stdout.rstrip("\n").split("\n")
    if not lines:
        return {"columns": [], "rows": [], "total": total}
    cols = lines[0].split("\t")
    data: list[list[str]] = []
    for line in lines[1:]:
        if line.startswith("(") and "row" in line:
            continue   # trailing "(N rows)" summary
        data.append(line.split("\t"))
    return {"columns": cols, "rows": data, "total": total}


def _safe_ident(name: str) -> str:
    """Allow only alnum+underscore identifiers — prevents injection in
    sqlite queries (which doesn't support parameterised table names).
    """
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise HTTPException(400, f"bad identifier: {name}")
    return name


def _stringify_row(row: list) -> list[str]:
    out = []
    for v in row:
        if v is None:
            out.append("")
        elif isinstance(v, bytes):
            out.append(v.hex()[:60] + "…" if len(v) > 30 else v.hex())
        else:
            s = str(v)
            out.append(s if len(s) <= 200 else s[:200] + "…")
    return out


def _rewrite_conf_port(conf: Path, port: int) -> None:
    if not conf.is_file():
        return
    text = conf.read_text(encoding="utf-8", errors="replace")
    new, n = re.subn(
        r"(^|\n)\s*#?\s*port\s*=\s*\d+\s*(#[^\n]*)?",
        f"\\1port = {port}  # vortex-wizard",
        text, count=1,
    )
    if n == 0:
        new = text.rstrip() + f"\nport = {port}  # vortex-wizard\n"
    conf.write_text(new, encoding="utf-8")


def _escape_sql(s: str) -> str:
    return s.replace("'", "''")


def _url_quote(s: str) -> str:
    from urllib.parse import quote
    return quote(s, safe="")
