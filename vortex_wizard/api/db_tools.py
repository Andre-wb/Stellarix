"""Wave 7 — database tools for the admin UI.

Operates directly against the managed node's SQLite file (read-only
where possible). Five features:

  1. SQL console — read-only SELECT, with a safety filter.
  2. Room graph — nodes/edges for D3 rendering (rooms ↔ members).
  3. Per-user storage quota — per-user disk usage stats.
  4. FTS5 toggle — create a virtual fts5 index over message sender_pseudo
     + timestamps for the admin's SQL console.
  5. Chat export — metadata-only enumeration (ciphertext dumps). Client
     decrypts using its room keys.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import backup_api as _b

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin/dbtools", tags=["db-tools"])


def _env_file(request: Request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


def _open_ro(env_file: Path) -> sqlite3.Connection:
    env = _b._read_env(env_file)
    is_sq, db_path = _b._is_sqlite(env, env_file.parent)
    if not is_sq or not db_path or not db_path.is_file():
        raise HTTPException(400, "node is not on SQLite or DB not found")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    # Row-level write refusal — belt over the mode=ro braces.
    conn.execute("PRAGMA query_only = 1")
    return conn


def _open_rw(env_file: Path) -> sqlite3.Connection:
    env = _b._read_env(env_file)
    is_sq, db_path = _b._is_sqlite(env, env_file.parent)
    if not is_sq or not db_path or not db_path.is_file():
        raise HTTPException(400, "node is not on SQLite or DB not found")
    return sqlite3.connect(str(db_path))


# ══════════════════════════════════════════════════════════════════════════
# 1. SQL console (read-only)
# ══════════════════════════════════════════════════════════════════════════

# Accept only SELECT / WITH / EXPLAIN / PRAGMA … hint. Refuse DDL/DML.
_READONLY_OK = re.compile(r"^\s*(select|with|explain|pragma)\b", re.IGNORECASE)
_FORBIDDEN   = re.compile(r";\s*(insert|update|delete|drop|alter|attach|replace|create)\b",
                           re.IGNORECASE)


class SqlBody(BaseModel):
    query: str  = Field(..., min_length=1, max_length=10_000)
    limit: int  = Field(200, ge=1, le=1000)


@router.post("/sql")
async def sql_console(body: SqlBody, request: Request) -> dict:
    if not _READONLY_OK.match(body.query):
        raise HTTPException(400, "only SELECT / WITH / EXPLAIN / PRAGMA allowed")
    if _FORBIDDEN.search(body.query):
        raise HTTPException(400, "multi-statement write-like query rejected")

    conn = _open_ro(_env_file(request))
    try:
        # Wrap in a LIMIT if one isn't already present — a SELECT * on a
        # big table would happily send 10M rows.
        q = body.query.strip().rstrip(";")
        if " limit " not in q.lower():
            q = f"SELECT * FROM ({q}) LIMIT {body.limit}"
        t0 = time.perf_counter()
        cur = conn.execute(q)
        rows = cur.fetchmany(body.limit)
        cols = [d[0] for d in cur.description] if cur.description else []
        dur_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "columns":  cols,
            "rows":     [[_stringify(v) for v in r] for r in rows],
            "row_count": len(rows),
            "duration_ms": dur_ms,
            "truncated": len(rows) == body.limit,
        }
    except sqlite3.Error as e:
        raise HTTPException(400, f"sqlite: {e}")
    finally:
        conn.close()


def _stringify(v):
    if isinstance(v, (bytes, bytearray, memoryview)):
        b = bytes(v)
        if len(b) > 128:
            return b[:128].hex() + f"…(+{len(b) - 128} bytes)"
        return b.hex()
    return v


# ══════════════════════════════════════════════════════════════════════════
# 2. Room graph (for D3 rendering in the UI)
# ══════════════════════════════════════════════════════════════════════════

@router.get("/graph")
async def room_graph(request: Request, limit_rooms: int = 200) -> dict:
    conn = _open_ro(_env_file(request))
    try:
        limit_rooms = max(1, min(limit_rooms, 500))
        rooms = conn.execute(
            "SELECT id, name, is_dm, is_channel, creator_id, created_at "
            "FROM rooms ORDER BY updated_at DESC LIMIT ?",
            (limit_rooms,),
        ).fetchall()
        room_ids = [r["id"] for r in rooms]
        if not room_ids:
            return {"nodes": [], "edges": [], "counts": {"rooms": 0, "users": 0}}

        placeholders = ",".join("?" * len(room_ids))
        members = conn.execute(
            f"SELECT room_id, user_id, role FROM room_members WHERE room_id IN ({placeholders})",
            room_ids,
        ).fetchall()
        user_ids = sorted({m["user_id"] for m in members})
        users_by_id = {}
        if user_ids:
            ph2 = ",".join("?" * len(user_ids))
            users = conn.execute(
                f"SELECT id, username, display_name FROM users WHERE id IN ({ph2})",
                user_ids,
            ).fetchall()
            users_by_id = {u["id"]: dict(u) for u in users}

        nodes = []
        for r in rooms:
            nodes.append({
                "id":   f"r{r['id']}",
                "kind": "channel" if r["is_channel"] else ("dm" if r["is_dm"] else "group"),
                "label": r["name"],
                "created_at": r["created_at"],
            })
        for uid in user_ids:
            u = users_by_id.get(uid, {})
            nodes.append({
                "id":   f"u{uid}",
                "kind": "user",
                "label": u.get("display_name") or u.get("username") or f"user#{uid}",
            })
        edges = [
            {"source": f"u{m['user_id']}", "target": f"r{m['room_id']}", "role": m["role"]}
            for m in members
        ]
        return {
            "nodes":  nodes,
            "edges":  edges,
            "counts": {"rooms": len(rooms), "users": len(user_ids), "memberships": len(members)},
        }
    except sqlite3.Error as e:
        raise HTTPException(500, f"sqlite: {e}")
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════
# 3. Per-user storage quota
# ══════════════════════════════════════════════════════════════════════════

@router.get("/storage")
async def storage_stats(request: Request, top: int = 50) -> dict:
    conn = _open_ro(_env_file(request))
    try:
        top = max(1, min(top, 500))
        # Sum sizes of messages authored by each user (ciphertext blob len).
        rows = conn.execute(
            "SELECT u.id, u.username, u.display_name, "
            "  COUNT(m.id) AS msg_count, "
            "  COALESCE(SUM(LENGTH(m.content_encrypted)), 0) AS bytes "
            "FROM users u LEFT JOIN messages m ON m.sender_id = u.id "
            "GROUP BY u.id ORDER BY bytes DESC LIMIT ?",
            (top,),
        ).fetchall()
        return {
            "rows": [
                {
                    "user_id":      r["id"],
                    "username":     r["username"],
                    "display_name": r["display_name"],
                    "msg_count":    int(r["msg_count"] or 0),
                    "bytes":        int(r["bytes"] or 0),
                }
                for r in rows
            ]
        }
    except sqlite3.Error as e:
        raise HTTPException(500, f"sqlite: {e}")
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════
# 4. FTS5 toggle (over messages.sender_pseudo + created_at)
# ══════════════════════════════════════════════════════════════════════════

# Note — we deliberately do NOT index ciphertext; it's encrypted. The
# index is for the admin console (pseudo lookup, timestamp range). If a
# user wants to full-text-search their own messages, that has to happen
# client-side where room keys are available.

@router.get("/fts/status")
async def fts_status(request: Request) -> dict:
    conn = _open_ro(_env_file(request))
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='messages_fts'"
        ).fetchone()
        return {"enabled": bool(row)}
    finally:
        conn.close()


@router.post("/fts/enable")
async def fts_enable(request: Request) -> dict:
    conn = _open_rw(_env_file(request))
    try:
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='messages_fts'"
        ).fetchone()
        if existing:
            return {"ok": True, "already": True}

        conn.executescript("""
            CREATE VIRTUAL TABLE messages_fts USING fts5(
                sender_pseudo UNINDEXED,
                created_at UNINDEXED,
                content,
                content='messages',
                content_rowid='id'
            );
            -- Triggers to keep FTS in sync
            CREATE TRIGGER IF NOT EXISTS messages_fts_ai AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(rowid, sender_pseudo, created_at, content)
                VALUES (new.id, new.sender_pseudo, new.created_at, '');
            END;
            CREATE TRIGGER IF NOT EXISTS messages_fts_ad AFTER DELETE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, sender_pseudo, created_at, content)
                VALUES ('delete', old.id, old.sender_pseudo, old.created_at, '');
            END;
        """)
        # Backfill existing rows
        conn.execute(
            "INSERT INTO messages_fts(rowid, sender_pseudo, created_at, content) "
            "SELECT id, sender_pseudo, created_at, '' FROM messages"
        )
        conn.commit()
        return {"ok": True}
    except sqlite3.OperationalError as e:
        if "FTS5" in str(e).upper() or "fts5" in str(e):
            raise HTTPException(400, "this SQLite build has no FTS5 support")
        raise HTTPException(500, f"sqlite: {e}")
    finally:
        conn.close()


@router.post("/fts/disable")
async def fts_disable(request: Request) -> dict:
    conn = _open_rw(_env_file(request))
    try:
        conn.executescript("""
            DROP TRIGGER IF EXISTS messages_fts_ai;
            DROP TRIGGER IF EXISTS messages_fts_ad;
            DROP TABLE IF EXISTS messages_fts;
        """)
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════
# 5. Chat export (metadata-only — content stays ciphertext)
# ══════════════════════════════════════════════════════════════════════════

@router.get("/export/room/{room_id}")
async def export_room(
    room_id: int,
    request: Request,
    limit: int = Query(5000, ge=1, le=50000),
    offset: int = Query(0, ge=0),
) -> dict:
    """Dump a room's messages with ciphertext + timestamps.

    The wizard cannot decrypt — the operator downloads the dump, and
    their client (which has the room_key) decrypts offline. This keeps
    the E2E guarantee intact while giving a path to archive chats.
    """
    conn = _open_ro(_env_file(request))
    try:
        room = conn.execute(
            "SELECT id, name, created_at, is_dm, is_channel "
            "FROM rooms WHERE id = ?",
            (room_id,),
        ).fetchone()
        if not room:
            raise HTTPException(404, "room not found")

        msgs = conn.execute(
            "SELECT id, sender_id, sender_pseudo, content_encrypted, "
            "       created_at, edited_at, expires_at, reply_to_id, forwarded_from "
            "FROM messages WHERE room_id = ? "
            "ORDER BY id ASC LIMIT ? OFFSET ?",
            (room_id, limit, offset),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE room_id = ?", (room_id,),
        ).fetchone()[0]

        return {
            "room": dict(room),
            "messages": [
                {
                    "msg_id":    m["id"],
                    "sender_id": m["sender_id"],
                    "sender_pseudo": m["sender_pseudo"],
                    "ciphertext_hex": (bytes(m["content_encrypted"]).hex()
                                       if m["content_encrypted"] else None),
                    "created_at":  m["created_at"],
                    "edited_at":   m["edited_at"],
                    "expires_at":  m["expires_at"],
                    "reply_to_id": m["reply_to_id"],
                    "forwarded_from": m["forwarded_from"],
                }
                for m in msgs
            ],
            "offset":    offset,
            "limit":     limit,
            "total":     int(total),
            "exported_at": int(time.time()),
        }
    except sqlite3.Error as e:
        raise HTTPException(500, f"sqlite: {e}")
    finally:
        conn.close()


@router.get("/export/rooms")
async def export_rooms_index(request: Request) -> dict:
    """List every room with message counts — feeds the client's export
    UI so the user can pick which chats to download and decrypt."""
    conn = _open_ro(_env_file(request))
    try:
        rows = conn.execute(
            "SELECT r.id, r.name, r.is_dm, r.is_channel, r.created_at, "
            "       (SELECT COUNT(*) FROM messages m WHERE m.room_id = r.id) AS msg_count "
            "FROM rooms r ORDER BY r.updated_at DESC"
        ).fetchall()
        return {"rooms": [dict(r) for r in rows]}
    finally:
        conn.close()
