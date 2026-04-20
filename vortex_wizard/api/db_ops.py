"""Wave 3 — Advanced DB operations.

  #11 SQLite → PostgreSQL auto-migration (copy all rows, preserve PKs)
  #12 Point-in-time restore from snapshot history
  #13 Schema diff (expected from SQLAlchemy models vs actual)
  #44 Centralized audit aggregator (pull audit logs from sibling nodes)
  #45 Geo-distributed failover table (CNAME-style routing)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Literal, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import backup_api as _b
from . import security_api as _sec

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin/dbops", tags=["db-ops"])


def _env_file(request: Request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


# ══════════════════════════════════════════════════════════════════════════
# #11 — SQLite → PostgreSQL auto-migration
# ══════════════════════════════════════════════════════════════════════════

class MigrateBody(BaseModel):
    pg_host:      str = Field("127.0.0.1", min_length=1, max_length=253)
    pg_port:      int = Field(5432, ge=1, le=65535)
    pg_user:      str = Field("vortex", min_length=1, max_length=60)
    pg_password:  str = Field(..., min_length=8)
    pg_database:  str = Field("vortex", min_length=1, max_length=60)
    # Whether to flip DATABASE_URL in .env after a successful copy.
    switch_env:   bool = True


@router.get("/migrate/dryrun")
async def migrate_dryrun(request: Request) -> dict:
    """Inspect the local SQLite DB and report what would be migrated."""
    env_file = _env_file(request)
    env = _b._read_env(env_file)
    is_sq, db_path = _b._is_sqlite(env, env_file.parent)
    if not is_sq:
        return {"ok": False, "reason": "already running on postgres"}
    if not (db_path and db_path.is_file()):
        return {"ok": False, "reason": "sqlite db not found"}

    summary = []
    conn = sqlite3.connect(str(db_path))
    try:
        for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ):
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM \"{name}\"").fetchone()[0]
            except sqlite3.Error:
                n = None
            summary.append({"table": name, "rows": n})
    finally:
        conn.close()

    total = sum(t["rows"] or 0 for t in summary)
    return {"ok": True, "tables": summary, "total_rows": int(total), "db_path": str(db_path)}


@router.post("/migrate/run")
async def migrate_run(body: MigrateBody, request: Request) -> dict:
    """Copy every row from SQLite → PostgreSQL. Runs synchronously —
    big DBs (>100K rows) take a minute or two. Returns per-table row
    counts for verification."""
    env_file = _env_file(request)
    env = _b._read_env(env_file)
    is_sq, db_path = _b._is_sqlite(env, env_file.parent)
    if not is_sq or not (db_path and db_path.is_file()):
        raise HTTPException(400, "SQLite source not found")

    try:
        import psycopg2
        from psycopg2.extras import execute_values
    except ImportError:
        raise HTTPException(500, "psycopg2 not installed — pip install psycopg2-binary")

    pg_url = f"postgresql://{body.pg_user}:{body.pg_password}@{body.pg_host}:{body.pg_port}/{body.pg_database}"
    report: dict[str, int | str] = {}

    # Connect to PG first to surface credential errors early.
    try:
        pg = psycopg2.connect(
            host=body.pg_host, port=body.pg_port,
            user=body.pg_user, password=body.pg_password,
            dbname=body.pg_database,
        )
    except Exception as e:
        raise HTTPException(502, f"postgres connect failed: {e}")

    sq = sqlite3.connect(str(db_path))
    sq.row_factory = sqlite3.Row
    try:
        # Create schema on PG via the node's Base.metadata.create_all —
        # use the node's own DATABASE_URL temporarily.
        import sys; sys.path.insert(0, str(env_file.parent))
        import importlib
        old_db_url = os.environ.get("DATABASE_URL", "")
        os.environ["DATABASE_URL"] = pg_url
        try:
            if "app.base" in sys.modules:
                importlib.reload(sys.modules["app.base"])
            from app.base import Base
            from sqlalchemy import create_engine
            for name in list(sys.modules.keys()):
                if name.startswith("app.models") or name.startswith("app.security."):
                    try: importlib.import_module(name)
                    except Exception: pass
            engine = create_engine(pg_url)
            Base.metadata.create_all(engine)
        finally:
            os.environ["DATABASE_URL"] = old_db_url

        # Iterate every SQLite table and copy rows.
        for (table,) in sq.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ):
            if table.startswith("alembic_"): continue
            cols = [r["name"] for r in sq.execute(f"PRAGMA table_info(\"{table}\")")]
            if not cols: continue
            rows = sq.execute(f"SELECT {','.join(cols)} FROM \"{table}\"").fetchall()
            if not rows:
                report[table] = 0
                continue
            quoted_cols = ",".join(f'"{c}"' for c in cols)
            sql = f'INSERT INTO "{table}" ({quoted_cols}) VALUES %s ON CONFLICT DO NOTHING'
            with pg.cursor() as cur:
                try:
                    execute_values(cur, sql, [tuple(r) for r in rows], page_size=1000)
                    report[table] = len(rows)
                except Exception as e:
                    pg.rollback()
                    report[table] = f"err: {type(e).__name__}: {e}"
                    continue
            pg.commit()
    finally:
        sq.close()
        pg.close()

    if body.switch_env:
        _sec._write_env_keys(env_file, {"DATABASE_URL": pg_url})

    return {
        "ok":           True,
        "rows_copied":  {k: v for k, v in report.items() if isinstance(v, int)},
        "errors":       {k: v for k, v in report.items() if not isinstance(v, int)},
        "env_switched": body.switch_env,
        "note":         "restart the node to use Postgres",
    }


# ══════════════════════════════════════════════════════════════════════════
# #12 — Point-in-time restore
# ══════════════════════════════════════════════════════════════════════════

def _snap_dir(env_file: Path) -> Path:
    d = env_file.parent / "snapshots"
    d.mkdir(exist_ok=True)
    return d


async def job_snapshot(env_file: Path) -> dict:
    """Scheduled snapshot — SQLite only (uses online backup API).
    Keeps last 24 hourly + 14 daily + 12 monthly, automatic pruning."""
    env = _b._read_env(env_file)
    is_sq, db_path = _b._is_sqlite(env, env_file.parent)
    if not (is_sq and db_path and db_path.is_file()):
        return {"skipped": True, "message": "sqlite file not present"}

    d = _snap_dir(env_file)
    tag = time.strftime("%Y%m%dT%H%M%S")
    snap = d / f"vortex-{tag}.db"
    try:
        src = sqlite3.connect(str(db_path))
        dst = sqlite3.connect(str(snap))
        with dst:
            src.backup(dst)
        src.close(); dst.close()
    except Exception as e:
        return {"message": f"snapshot failed: {e}", "ok": False}

    _prune_snapshots(d)
    size = snap.stat().st_size
    return {"message": f"snapshot {tag} ({size} B)", "tag": tag}


def _prune_snapshots(d: Path) -> None:
    """Keep 24h hourly, 14d daily, 12m monthly. Everything else deleted."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    keep: set[str] = set()
    snaps = sorted(d.glob("vortex-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    hourly_cutoff  = now - timedelta(hours=24)
    daily_cutoff   = now - timedelta(days=14)
    monthly_cutoff = now - timedelta(days=365)
    seen_days: set[str] = set()
    seen_months: set[str] = set()
    for p in snaps:
        mt = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        if mt >= hourly_cutoff:
            keep.add(p.name)
            continue
        if mt >= daily_cutoff:
            day = mt.strftime("%Y-%m-%d")
            if day not in seen_days:
                keep.add(p.name); seen_days.add(day)
            continue
        if mt >= monthly_cutoff:
            month = mt.strftime("%Y-%m")
            if month not in seen_months:
                keep.add(p.name); seen_months.add(month)
            continue
    for p in snaps:
        if p.name not in keep:
            try: p.unlink()
            except OSError: pass


@router.get("/pitr/list")
async def pitr_list(request: Request) -> dict:
    d = _snap_dir(_env_file(request))
    rows = []
    for p in sorted(d.glob("vortex-*.db"), key=lambda f: f.stat().st_mtime, reverse=True):
        st = p.stat()
        rows.append({
            "tag":       p.stem.replace("vortex-", ""),
            "file":      p.name,
            "byte_size": st.st_size,
            "mtime":     int(st.st_mtime),
        })
    return {"snapshots": rows, "total": len(rows)}


class PitrRestoreBody(BaseModel):
    tag:     str = Field(..., min_length=1, max_length=50)
    confirm: bool = False


@router.post("/pitr/restore")
async def pitr_restore(body: PitrRestoreBody, request: Request) -> dict:
    if not body.confirm:
        raise HTTPException(400, "must pass confirm=true")
    env_file = _env_file(request)
    env = _b._read_env(env_file)
    is_sq, db_path = _b._is_sqlite(env, env_file.parent)
    if not (is_sq and db_path):
        raise HTTPException(400, "pitr only supported for sqlite nodes")

    # Safety — refuse if node is running
    if _b._node_is_alive(env):
        raise HTTPException(409, "stop the node before restoring")

    snap = _snap_dir(env_file) / f"vortex-{body.tag}.db"
    if not snap.is_file():
        raise HTTPException(404, f"snapshot not found: {body.tag}")

    # Move current to .pre-restore, copy snapshot in place.
    if db_path.is_file():
        shutil.copy2(db_path, db_path.with_suffix(".db.pre-pitr.bak"))
    shutil.copy2(snap, db_path)
    return {"ok": True, "restored_from": body.tag, "destination": str(db_path)}


@router.delete("/pitr/{tag}")
async def pitr_delete(tag: str, request: Request) -> dict:
    snap = _snap_dir(_env_file(request)) / f"vortex-{tag}.db"
    if not snap.is_file():
        raise HTTPException(404, "not found")
    snap.unlink()
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
# #13 — Schema diff
# ══════════════════════════════════════════════════════════════════════════

@router.get("/schema/diff")
async def schema_diff(request: Request) -> dict:
    """Compare live DB schema against SQLAlchemy models. Reports
    missing tables / missing columns / unexpected extras. Read-only."""
    env_file = _env_file(request)
    env = _b._read_env(env_file)
    is_sq, db_path = _b._is_sqlite(env, env_file.parent)

    # Import the node's models to get the expected schema.
    import sys; sys.path.insert(0, str(env_file.parent))
    try:
        from app.base import Base
        for n in list(sys.modules.keys()):
            if n.startswith("app.models"):
                import importlib; importlib.import_module(n)
    except Exception as e:
        raise HTTPException(500, f"cannot import app.base: {e}")

    expected = {}
    for table in Base.metadata.tables.values():
        expected[table.name] = {c.name: str(c.type) for c in table.columns}

    # Introspect live schema.
    actual: dict[str, dict[str, str]] = {}
    if is_sq and db_path and db_path.is_file():
        c = sqlite3.connect(str(db_path))
        try:
            for (name,) in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ):
                cols = {r[1]: r[2] for r in c.execute(f'PRAGMA table_info("{name}")')}
                actual[name] = cols
        finally:
            c.close()
    else:
        try:
            import psycopg2
            from urllib.parse import urlparse
            u = urlparse(env.get("DATABASE_URL", "").replace("postgresql+psycopg2://","postgresql://"))
            pg = psycopg2.connect(host=u.hostname, port=u.port or 5432, user=u.username, password=u.password, dbname=(u.path or "/").lstrip("/"))
            with pg.cursor() as cur:
                cur.execute("""
                    SELECT table_name, column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                """)
                for table, col, dtype in cur.fetchall():
                    actual.setdefault(table, {})[col] = dtype
            pg.close()
        except Exception as e:
            raise HTTPException(500, f"schema introspection failed: {e}")

    missing_tables = sorted(set(expected) - set(actual))
    extra_tables   = sorted(set(actual) - set(expected))
    column_issues  = []
    for t in sorted(set(expected) & set(actual)):
        miss = sorted(set(expected[t]) - set(actual[t]))
        extra = sorted(set(actual[t]) - set(expected[t]))
        if miss or extra:
            column_issues.append({"table": t, "missing": miss, "extra": extra})
    return {
        "ok":             not (missing_tables or column_issues),
        "missing_tables": missing_tables,
        "extra_tables":   extra_tables,
        "column_issues":  column_issues,
        "expected_tables_total": len(expected),
        "actual_tables_total":   len(actual),
    }


# ══════════════════════════════════════════════════════════════════════════
# #44 — Centralized audit aggregator
# ══════════════════════════════════════════════════════════════════════════

def _central_state_path(env_file: Path) -> Path:
    return env_file.parent / "audit_central.json"


class AddNodeBody(BaseModel):
    label:        str = Field(..., min_length=1, max_length=60)
    base_url:     str = Field(..., min_length=8, max_length=512)
    auth_bearer:  Optional[str] = None


@router.get("/central_audit/nodes")
async def central_audit_nodes(request: Request) -> dict:
    env_file = _env_file(request)
    p = _central_state_path(env_file)
    if not p.is_file(): return {"nodes": []}
    try: return {"nodes": json.loads(p.read_text()).get("nodes", [])}
    except Exception: return {"nodes": []}


@router.post("/central_audit/nodes")
async def central_audit_add(body: AddNodeBody, request: Request) -> dict:
    env_file = _env_file(request)
    p = _central_state_path(env_file)
    state = {"nodes": []}
    if p.is_file():
        try: state = json.loads(p.read_text())
        except Exception: pass
    import secrets as _s
    entry = {**body.model_dump(), "id": _s.token_urlsafe(8), "added_at": int(time.time())}
    state.setdefault("nodes", []).append(entry)
    p.write_text(json.dumps(state, indent=2))
    return {"ok": True, "id": entry["id"]}


@router.post("/central_audit/pull")
async def central_audit_pull(request: Request) -> dict:
    """Fan out to every registered node and pull its /audit entries.
    Merge by timestamp. Returns aggregated list."""
    env_file = _env_file(request)
    p = _central_state_path(env_file)
    nodes = []
    if p.is_file():
        try: nodes = json.loads(p.read_text()).get("nodes", [])
        except Exception: pass

    async def _pull(n: dict) -> tuple[str, list[dict]]:
        base = n["base_url"].rstrip("/")
        url = f"{base}/api/wiz/admin/audit?limit=200"
        headers = {}
        if n.get("auth_bearer"):
            headers["Authorization"] = f"Bearer {n['auth_bearer']}"
        try:
            async with httpx.AsyncClient(timeout=5.0, verify=False) as c:
                r = await c.get(url, headers=headers)
            if r.status_code != 200: return n["label"], []
            return n["label"], (r.json().get("entries") or [])
        except Exception:
            return n["label"], []

    results = await asyncio.gather(*[_pull(n) for n in nodes])
    merged: list[dict] = []
    for label, entries in results:
        for e in entries:
            e = dict(e); e["node"] = label
            merged.append(e)
    merged.sort(key=lambda e: e.get("ts") or 0, reverse=True)
    return {"nodes": len(nodes), "total": len(merged), "entries": merged[:500]}


@router.delete("/central_audit/nodes/{node_id}")
async def central_audit_delete(node_id: str, request: Request) -> dict:
    env_file = _env_file(request)
    p = _central_state_path(env_file)
    if not p.is_file(): return {"ok": True}
    state = json.loads(p.read_text())
    state["nodes"] = [n for n in state.get("nodes", []) if n.get("id") != node_id]
    p.write_text(json.dumps(state, indent=2))
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
# #45 — Geo-distributed failover
# ══════════════════════════════════════════════════════════════════════════
#
# A simple JSON table mapping primary_region → list of fallback nodes in
# priority order. When a client's current node is unhealthy, the wizard
# can point them at the next fallback via /api/wiz/admin/dbops/failover/resolve.

class FailoverRegion(BaseModel):
    region:    str = Field(..., min_length=2, max_length=30)
    primary:   str = Field(..., description="base URL of primary node")
    fallbacks: list[str] = Field(default_factory=list,
                                 description="ordered list of fallback base URLs")


def _failover_path(env_file: Path) -> Path:
    return env_file.parent / "failover.json"


@router.get("/failover")
async def failover_list(request: Request) -> dict:
    p = _failover_path(_env_file(request))
    if not p.is_file(): return {"regions": []}
    try: return json.loads(p.read_text())
    except Exception: return {"regions": []}


@router.post("/failover")
async def failover_set(body: FailoverRegion, request: Request) -> dict:
    env_file = _env_file(request)
    p = _failover_path(env_file)
    state = {"regions": []}
    if p.is_file():
        try: state = json.loads(p.read_text())
        except Exception: pass
    state["regions"] = [r for r in state.get("regions", []) if r["region"] != body.region]
    state["regions"].append(body.model_dump())
    p.write_text(json.dumps(state, indent=2))
    return {"ok": True}


@router.get("/failover/resolve")
async def failover_resolve(request: Request, region: str) -> dict:
    """Live health check — walks primary → fallbacks, returns the first
    URL responding 200 on /health. Used by clients to fail over."""
    p = _failover_path(_env_file(request))
    if not p.is_file():
        raise HTTPException(404, "no failover config")
    state = json.loads(p.read_text())
    for r in state.get("regions", []):
        if r["region"] != region: continue
        candidates = [r["primary"]] + (r.get("fallbacks") or [])
        for url in candidates:
            try:
                async with httpx.AsyncClient(timeout=2.0, verify=False) as c:
                    resp = await c.get(url.rstrip("/") + "/health")
                if resp.status_code == 200:
                    return {"region": region, "resolved": url, "healthy": True}
            except Exception:
                continue
        return {"region": region, "resolved": None, "healthy": False,
                "tried": candidates}
    raise HTTPException(404, f"unknown region: {region}")


# ── Scheduler registration ────────────────────────────────────────────────

def install_dbops_jobs(env_file: Path) -> None:
    # PITR snapshots — hourly. Operator can flip to 'off' if not on SQLite.
    from . import scheduler as _sched
    s = _sched.get(env_file)
    s.register("pitr_snapshot", job_snapshot, default_interval="hourly")
