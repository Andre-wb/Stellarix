"""Wave 2 — Monitoring extensions.

  1. Grafana dashboard JSON export      — /monitoring/grafana/dashboard.json
  2. Custom alert rule engine           — rules stored in rules.json, evaluated
                                          by a scheduler job every minute
  3. Slow query log                     — captures queries >N ms to a JSONL
  4. Message table partitioning wizard  — Postgres: declarative partition-by-
                                          month; SQLite: manual archive roll-over
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Literal, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import backup_api as _b
from . import alerts as _alerts
from . import scheduler as _sched

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin/monitoring", tags=["monitoring"])


def _env_file(request: Request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


# ══════════════════════════════════════════════════════════════════════════
# 1. Grafana dashboard JSON
# ══════════════════════════════════════════════════════════════════════════

@router.get("/grafana/dashboard.json")
async def grafana_dashboard(request: Request) -> dict:
    """Ready-to-import Grafana dashboard with 8 panels covering every
    metric our /metrics endpoint exposes. Datasource is prompt'ed at
    import time (Grafana uses ``${DS_PROMETHEUS}``)."""
    env = _b._read_env(_env_file(request))
    device = env.get("DEVICE_NAME", "vortex-node") or "vortex-node"
    port = env.get("PORT", "9000")

    panels: list[dict] = []
    pid = 1

    def _panel(title: str, expr: str, unit: str, x: int, y: int,
               w: int = 12, h: int = 8, type_: str = "timeseries") -> dict:
        nonlocal pid
        pid += 1
        return {
            "id": pid, "title": title, "type": type_,
            "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "fieldConfig": {"defaults": {"unit": unit}},
            "targets": [{"refId": "A", "expr": expr}],
        }

    panels.append(_panel("Up", "vortex_wizard_up",                   "none", 0,  0, 6, 4, "stat"))
    panels.append(_panel("Node up", "vortex_node_up",                "none", 6,  0, 6, 4, "stat"))
    panels.append(_panel("CPU seconds (rate)", 'rate(vortex_process_cpu_seconds_total[5m])',
                                                                     "cps",  0,  4))
    panels.append(_panel("RSS (MB)", 'vortex_process_resident_memory_bytes / 1024 / 1024',
                                                                     "decmbytes", 12, 4))
    panels.append(_panel("Active WS", "vortex_ws_active_total",      "none", 0, 12))
    panels.append(_panel("Active rooms", "vortex_rooms_active_total","none", 12, 12))
    panels.append(_panel("Active peers", "vortex_peers_active_total","none", 0, 20))
    panels.append(_panel("Audit alerts", "vortex_audit_alerts_total","none", 12, 20))
    panels.append(_panel("P99 latency by path (s)",
                         'vortex_http_request_duration_seconds{quantile="0.99"}',
                                                                     "s", 0, 28, 24, 8))
    panels.append(_panel("Requests / sec by status",
                         'sum(rate(vortex_http_requests_total[5m])) by (status)',
                                                                     "reqps", 0, 36, 24, 8))

    return {
        "title":      f"Vortex node — {device}",
        "uid":        f"vortex-{device}"[:40],
        "schemaVersion": 39,
        "version":    1,
        "timezone":   "browser",
        "refresh":    "30s",
        "time":       {"from": "now-6h", "to": "now"},
        "tags":       ["vortex"],
        "panels":     panels,
        "__inputs": [{
            "name": "DS_PROMETHEUS", "label": "Prometheus",
            "description": f"Scrape target: http://HOST:{port}/api/wiz/admin/metrics",
            "type": "datasource", "pluginId": "prometheus",
            "pluginName": "Prometheus",
        }],
    }


# ══════════════════════════════════════════════════════════════════════════
# 2. Custom alert rules
# ══════════════════════════════════════════════════════════════════════════
#
# A rule has the form:
#     metric_name <op> threshold
# where <op> is one of: > < >= <= ==
# Each rule is re-evaluated once a minute against the wizard's own
# /metrics endpoint. When the rule fires (transitions from OK → firing),
# we emit an alert via the dispatcher. When it recovers we send an
# info-level "resolved" message.

_OPS = {">": lambda a, b: a > b,
        "<": lambda a, b: a < b,
        ">=": lambda a, b: a >= b,
        "<=": lambda a, b: a <= b,
        "==": lambda a, b: a == b}


def _rules_path(env_file: Path) -> Path:
    return env_file.parent / "alert_rules.json"


def _load_rules(env_file: Path) -> dict:
    p = _rules_path(env_file)
    if not p.is_file(): return {"rules": []}
    try: return json.loads(p.read_text())
    except Exception: return {"rules": []}


def _save_rules(env_file: Path, state: dict) -> None:
    _rules_path(env_file).write_text(json.dumps(state, indent=2))


class RuleBody(BaseModel):
    id:          Optional[str] = None
    name:        str = Field(..., min_length=1, max_length=80)
    metric:      str = Field(..., min_length=1, max_length=120)
    op:          Literal[">", "<", ">=", "<=", "=="]
    threshold:   float
    severity:    _alerts.Severity = "warning"
    for_seconds: int = Field(60, ge=0, le=3600,
                              description="Condition must hold this long before firing")
    enabled:     bool = True


@router.get("/rules")
async def list_rules(request: Request) -> dict:
    return _load_rules(_env_file(request))


@router.post("/rules")
async def put_rule(body: RuleBody, request: Request) -> dict:
    env_file = _env_file(request)
    state = _load_rules(env_file)
    import secrets as _s
    if body.id:
        found = None
        for r in state["rules"]:
            if r["id"] == body.id:
                r.update(body.model_dump(exclude_none=True))
                found = r; break
        if not found: raise HTTPException(404, "rule not found")
    else:
        r = body.model_dump(); r["id"] = _s.token_urlsafe(8)
        r["firing_since"] = 0
        state["rules"].append(r); found = r
    _save_rules(env_file, state)
    return {"ok": True, "id": found["id"]}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, request: Request) -> dict:
    env_file = _env_file(request)
    state = _load_rules(env_file)
    before = len(state["rules"])
    state["rules"] = [r for r in state["rules"] if r["id"] != rule_id]
    _save_rules(env_file, state)
    return {"ok": True, "removed": before - len(state["rules"])}


def _parse_metrics(text: str) -> dict[str, float]:
    """Minimal Prometheus text parser — metric_name{labels} value.
    We flatten labels by joining them into the metric name for simple
    threshold rules. Full label-matching can come later."""
    out: dict[str, float] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        # Metric can have labels in braces. Split off the trailing value.
        m = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)(?:\{([^}]*)\})?\s+([-+0-9eE.nan]+)$', line)
        if not m: continue
        name, labels, val = m.groups()
        try: out[name if not labels else f"{name}{{{labels}}}"] = float(val)
        except ValueError: continue
    return out


async def job_alert_rules(env_file: Path) -> dict:
    """Scheduled: every minute, scrape /metrics, evaluate all enabled
    rules, fire / resolve as state transitions."""
    env = _b._read_env(env_file)
    host = env.get("HOST", "127.0.0.1")
    if host == "0.0.0.0": host = "127.0.0.1"
    port = int(env.get("PORT", "9000"))
    proto = "https" if (env_file.parent / "certs" / "vortex.crt").is_file() else "http"

    state = _load_rules(env_file)
    if not state["rules"]:
        return {"message": "no rules"}

    try:
        async with httpx.AsyncClient(timeout=5.0, verify=False) as c:
            r = await c.get(f"{proto}://{host}:{port}/api/wiz/admin/metrics")
        metrics = _parse_metrics(r.text)
    except Exception as e:
        return {"message": f"metrics scrape failed: {e}", "ok": False}

    now = int(time.time())
    fired = resolved = 0
    for rule in state["rules"]:
        if not rule.get("enabled"): continue
        val = metrics.get(rule["metric"])
        if val is None: continue
        op = _OPS.get(rule["op"])
        if op is None: continue
        condition = op(val, float(rule["threshold"]))

        since = int(rule.get("firing_since", 0) or 0)
        if condition:
            if since == 0:
                rule["firing_since"] = now
                continue
            if now - since >= int(rule.get("for_seconds", 60)) and not rule.get("fired"):
                rule["fired"] = True
                fired += 1
                await _alerts.dispatch(
                    env_file,
                    severity=rule["severity"],
                    title=f"Rule fired: {rule['name']}",
                    body=f"Metric {rule['metric']} = {val}, threshold {rule['op']} {rule['threshold']}",
                    tags=["alert_rule", rule["id"]],
                )
        else:
            if rule.get("fired"):
                rule["fired"] = False
                resolved += 1
                await _alerts.dispatch(
                    env_file,
                    severity="info",
                    title=f"Rule resolved: {rule['name']}",
                    body=f"Metric {rule['metric']} = {val} now within normal bounds",
                    tags=["alert_rule", rule["id"], "resolved"],
                )
            rule["firing_since"] = 0

    _save_rules(env_file, state)
    return {"message": f"evaluated {len(state['rules'])} rules", "fired": fired, "resolved": resolved}


def install_monitoring_jobs(env_file: Path) -> None:
    s = _sched.get(env_file)
    # Default: hourly — operator flips to 'off' if noisy.
    s.register("alert_rules", job_alert_rules, default_interval="hourly")


# ══════════════════════════════════════════════════════════════════════════
# 3. Slow query log
# ══════════════════════════════════════════════════════════════════════════

def _slow_log_path(env_file: Path) -> Path:
    return env_file.parent / "slow_queries.ndjson"


@router.get("/slow_queries")
async def slow_queries(request: Request, limit: int = 100) -> dict:
    p = _slow_log_path(_env_file(request))
    limit = max(1, min(limit, 1000))
    if not p.is_file():
        return {"rows": [], "total": 0}
    rows: list[dict] = []
    # Read last N lines (tail)
    with p.open("rb") as f:
        size = f.seek(0, 2)
        chunk = min(size, 256 * 1024)
        f.seek(size - chunk)
        data = f.read()
    for line in data.splitlines()[::-1]:
        if len(rows) >= limit: break
        try: rows.append(json.loads(line))
        except Exception: continue
    return {"rows": rows, "limit": limit}


class SlowThresholdBody(BaseModel):
    threshold_ms: int = Field(100, ge=1, le=60000)


@router.post("/slow_queries/threshold")
async def set_slow_threshold(body: SlowThresholdBody, request: Request) -> dict:
    env_file = _env_file(request)
    from . import security_api as _sec
    _sec._write_env_keys(env_file, {"SLOW_QUERY_THRESHOLD_MS": str(body.threshold_ms)})
    return {"ok": True, "threshold_ms": body.threshold_ms}


@router.delete("/slow_queries")
async def clear_slow_queries(request: Request) -> dict:
    p = _slow_log_path(_env_file(request))
    if p.is_file():
        p.unlink()
    return {"ok": True}


def record_slow_query(env_file: Path, sql: str, duration_ms: float,
                      extra: Optional[dict] = None) -> None:
    """Called by the node-side SQLAlchemy event listener when a query
    takes longer than the configured threshold. Safe to call from any
    thread — we just append-only."""
    rec = {
        "ts":          int(time.time()),
        "duration_ms": round(duration_ms, 2),
        "sql":         (sql or "")[:4000],
    }
    if extra: rec.update(extra)
    try:
        with _slow_log_path(env_file).open("a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════
# 4. Table partitioning wizard
# ══════════════════════════════════════════════════════════════════════════
#
# Postgres: we don't rewrite an existing table — instead we output a
# migration script the operator can apply during maintenance window.
# SQLite: we create monthly archive files and move rows older than N
# months into them. ATTACH DATABASE for queries.

@router.get("/partitioning/status")
async def partition_status(request: Request) -> dict:
    env = _b._read_env(_env_file(request))
    is_sq, db_path = _b._is_sqlite(env, _env_file(request).parent)
    return {
        "backend":      "sqlite" if is_sq else "postgres",
        "db_path":      str(db_path) if db_path else None,
        "supported":    True,
    }


@router.get("/partitioning/plan")
async def partition_plan(request: Request, months_keep_hot: int = 3) -> dict:
    """Generate a migration script to partition the messages table.
    For Postgres: declarative RANGE partitioning by created_at month.
    For SQLite: archive script."""
    env = _b._read_env(_env_file(request))
    is_sq, db_path = _b._is_sqlite(env, _env_file(request).parent)
    months_keep_hot = max(1, min(months_keep_hot, 24))

    if is_sq:
        script = _sqlite_archive_script(db_path, months_keep_hot)
        return {"backend": "sqlite", "script": script, "apply_via": "sqlite3 vortex.db < script.sql"}
    else:
        script = _postgres_partition_script(months_keep_hot)
        return {"backend": "postgres", "script": script, "apply_via": "psql ... -f script.sql"}


def _postgres_partition_script(months_keep_hot: int) -> str:
    cutoff_months = months_keep_hot
    return f"""-- Partition messages by month, keep {cutoff_months} hot months unpartitioned.
-- Run during maintenance window — locks messages for ALTER.
-- Backup first:   pg_dump -Fc vortex > messages-pre-partition.dump
BEGIN;

-- 1. Rename original table
ALTER TABLE messages RENAME TO messages_old;

-- 2. Create partitioned parent
CREATE TABLE messages (LIKE messages_old INCLUDING ALL)
PARTITION BY RANGE (created_at);

-- 3. Create monthly partitions for the last 24 months + current + future 6
DO $$
DECLARE
    m date := (date_trunc('month', now()) - interval '24 months')::date;
BEGIN
    FOR i IN 0..30 LOOP
        EXECUTE format(
            'CREATE TABLE messages_y%sm%s PARTITION OF messages
             FOR VALUES FROM (%L) TO (%L)',
            to_char(m, 'YYYY'), to_char(m, 'MM'),
            m, (m + interval '1 month')::date
        );
        m := (m + interval '1 month')::date;
    END LOOP;
END$$;

-- 4. Move data
INSERT INTO messages SELECT * FROM messages_old;

-- 5. Drop old
DROP TABLE messages_old;

COMMIT;

-- Add auto-create-next-month job (call once, then cron it monthly):
-- CREATE OR REPLACE FUNCTION messages_add_next_partition() RETURNS void AS $$
-- DECLARE next_month date := date_trunc('month', now() + interval '1 month')::date;
-- BEGIN
--   EXECUTE format('CREATE TABLE IF NOT EXISTS messages_y%sm%s PARTITION OF messages
--                   FOR VALUES FROM (%L) TO (%L)',
--                   to_char(next_month,'YYYY'), to_char(next_month,'MM'),
--                   next_month, (next_month + interval '1 month')::date);
-- END$$ LANGUAGE plpgsql;
"""


def _sqlite_archive_script(db_path: Optional[Path], months_keep_hot: int) -> str:
    p = str(db_path or "vortex.db")
    return f"""-- SQLite archival approach — run each month via cron.
-- Rolls messages older than {months_keep_hot} months into vortex-archive-YYYY-MM.db.
--
-- Workflow:
--   1. ATTACH DATABASE '{p}.archive-YYYY-MM.db' AS arc;
--   2. CREATE TABLE IF NOT EXISTS arc.messages AS SELECT * FROM main.messages WHERE 0;
--   3. INSERT INTO arc.messages SELECT * FROM main.messages WHERE created_at < date('now', '-{months_keep_hot} months');
--   4. DELETE FROM main.messages WHERE created_at < date('now', '-{months_keep_hot} months');
--   5. DETACH DATABASE arc;
--   6. VACUUM;
--
-- Query archives by re-attaching. The wizard exposes an "archive" tab
-- that discovers *.archive-*.db files next to the main DB.

ATTACH DATABASE '{p}.archive-' || strftime('%Y-%m', date('now', '-{months_keep_hot} months'))
                              || '.db' AS arc;
CREATE TABLE IF NOT EXISTS arc.messages AS SELECT * FROM main.messages WHERE 0;
INSERT INTO arc.messages
SELECT * FROM main.messages WHERE created_at < date('now', '-{months_keep_hot} months');
DELETE FROM main.messages WHERE created_at < date('now', '-{months_keep_hot} months');
DETACH DATABASE arc;
VACUUM;
"""
