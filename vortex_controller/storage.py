"""Async storage for the controller (PostgreSQL primary, SQLite fallback).

Schema:
    nodes(
        pubkey_hex     TEXT PRIMARY KEY,
        endpoints      JSONB/JSON  (list of strings),
        metadata       JSONB/JSON  (name, version, region, ...),
        registered_at  BIGINT,
        last_heartbeat BIGINT,
        approved       BOOLEAN
    )

An "online" node is approved AND last_heartbeat within ONLINE_WINDOW_SEC.

URL resolution:
    1. DATABASE_URL env var (explicit, e.g. postgresql+asyncpg://user:pw@host/db)
    2. POSTGRES_* env vars → postgresql+asyncpg://...
    3. sqlite+aiosqlite:///controller.db (dev fallback)
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Index,
    Integer,
    LargeBinary,
    String,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON as _SAJson

logger = logging.getLogger(__name__)

ONLINE_WINDOW_SEC = 300  # 5 min


# ── Cross-dialect JSON type ────────────────────────────────────────────────
# PostgreSQL → JSONB, SQLite → JSON
_JSONType = _SAJson().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class EncryptedBackup(Base):
    """Opaque encrypted DB snapshot stored on behalf of a node.

    The controller never sees plaintext. The blob is encrypted client-side
    with a key derived from the node's 24-word seed phrase (same seed that
    owns ``pubkey_hex``). Ownership is proved by the client signing a
    request envelope with its Ed25519 node key before each upload/fetch.

    The controller only stores:
      - `pubkey_hex` of the owning node
      - ciphertext blob (opaque)
      - sha256 of ciphertext for tamper-detection
      - size and timestamps for dashboards
    """
    __tablename__ = "encrypted_backups"

    pubkey_hex: Mapped[str] = mapped_column(String(128), primary_key=True)
    blob:       Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sha256_hex: Mapped[str]   = mapped_column(String(64),  nullable=False)
    byte_size:  Mapped[int]   = mapped_column(Integer,     nullable=False)
    created_at: Mapped[int]   = mapped_column(BigInteger,  nullable=False)
    updated_at: Mapped[int]   = mapped_column(BigInteger,  nullable=False)


class Node(Base):
    __tablename__ = "nodes"

    pubkey_hex: Mapped[str] = mapped_column(String(128), primary_key=True)
    endpoints: Mapped[list] = mapped_column(_JSONType, nullable=False, default=list)
    node_metadata: Mapped[dict] = mapped_column(
        "metadata", _JSONType, nullable=False, default=dict
    )
    registered_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_heartbeat: Mapped[int] = mapped_column(BigInteger, nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("idx_nodes_last_heartbeat", "last_heartbeat"),
        Index("idx_nodes_approved", "approved"),
    )


# ── URL resolver ───────────────────────────────────────────────────────────

def resolve_database_url() -> str:
    """Determine the async SQLAlchemy URL from env vars."""
    explicit = os.getenv("DATABASE_URL", "").strip()
    if explicit:
        return _ensure_async_driver(explicit)

    pg_host = os.getenv("POSTGRES_HOST")
    pg_pw = os.getenv("POSTGRES_PASSWORD")
    if pg_host and pg_pw:
        user = os.getenv("POSTGRES_USER", "vortex")
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "vortex_controller")
        return f"postgresql+asyncpg://{user}:{pg_pw}@{pg_host}:{port}/{db}"

    sqlite_path = os.getenv("CONTROLLER_DB", "controller.db")
    return f"sqlite+aiosqlite:///{sqlite_path}"


def _ensure_async_driver(url: str) -> str:
    """Convert sync URLs to their async equivalents."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite://") and "aiosqlite" not in url:
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url


# ── Storage ────────────────────────────────────────────────────────────────

class Storage:
    """Async SQLAlchemy storage for controller nodes."""

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or resolve_database_url()
        connect_args: dict = {}
        if self.db_url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
        self._engine = create_async_engine(
            self.db_url,
            connect_args=connect_args,
            pool_pre_ping=True,
            future=True,
        )
        self._session_maker = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        logger.info("Storage: %s", self._redacted_url())

    def _redacted_url(self) -> str:
        url = self.db_url
        if "@" in url and "://" in url:
            scheme, rest = url.split("://", 1)
            if "@" in rest:
                creds, host = rest.rsplit("@", 1)
                if ":" in creds:
                    user, _ = creds.split(":", 1)
                    return f"{scheme}://{user}:***@{host}"
        return url

    async def init_schema(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self._engine.dispose()

    # ── Writes ────────────────────────────────────────────────────────────

    async def register(
        self,
        pubkey_hex: str,
        endpoints: list[str],
        metadata: dict,
        approved: bool = True,
    ) -> None:
        now = int(time.time())
        async with self._session_maker() as s:
            existing = await s.get(Node, pubkey_hex)
            if existing:
                existing.endpoints = list(endpoints)
                existing.node_metadata = dict(metadata)
                existing.last_heartbeat = now
                # Don't override approval on re-register; operator controls that.
            else:
                s.add(
                    Node(
                        pubkey_hex=pubkey_hex,
                        endpoints=list(endpoints),
                        node_metadata=dict(metadata),
                        registered_at=now,
                        last_heartbeat=now,
                        approved=approved,
                    )
                )
            await s.commit()

    async def heartbeat(self, pubkey_hex: str) -> bool:
        now = int(time.time())
        async with self._session_maker() as s:
            node = await s.get(Node, pubkey_hex)
            if not node:
                return False
            node.last_heartbeat = now
            await s.commit()
            return True

    # ── Reads ─────────────────────────────────────────────────────────────

    async def get(self, pubkey_hex: str) -> Optional[dict]:
        async with self._session_maker() as s:
            node = await s.get(Node, pubkey_hex)
            return _to_dict(node) if node else None

    async def random_online(self, count: int) -> list[dict]:
        """Return ``count`` online peers weighted by freshness (Phase 7B).

        Freshness weight mirrors ``PeerAccount.weight``:
            < 7 days   → 1.00
            < 30 days  → 0.80
            < 90 days  → 0.50
            < 180 days → 0.20
            else       → 0.00 (excluded)

        Nodes without any recent heartbeat are not returned at all, so
        stale operators naturally stop receiving traffic.
        """
        import random as _random

        cutoff = int(time.time()) - ONLINE_WINDOW_SEC
        stmt = (
            select(Node)
            .where(Node.approved.is_(True))
            .where(Node.last_heartbeat >= cutoff)
        )
        async with self._session_maker() as s:
            all_rows = (await s.execute(stmt)).scalars().all()

        pool: list[tuple[Node, float]] = []
        for r in all_rows:
            w = _freshness_weight(r.last_heartbeat)
            if w > 0:
                pool.append((r, w))

        if not pool:
            return []

        # weighted random sample without replacement
        rows: list[Node] = []
        nodes, weights = zip(*pool)
        nodes = list(nodes)
        weights = list(weights)
        chosen = min(count, len(nodes))
        for _ in range(chosen):
            idx = _random.choices(range(len(nodes)), weights=weights, k=1)[0]
            rows.append(nodes.pop(idx))
            weights.pop(idx)
        return [_to_dict(r) for r in rows]

    # ── Encrypted backups (opaque blobs) ──────────────────────────────────

    # Hard cap on blob size to stop a node from occupying unbounded storage
    # on the controller. Real-world backups should compress far under this
    # (a 50MB sqlite db gzips to ~10MB, AES-GCM adds 28B overhead).
    MAX_BACKUP_BYTES = 64 * 1024 * 1024  # 64 MiB

    async def put_backup(self, pubkey_hex: str, blob: bytes, sha256_hex: str) -> dict:
        size = len(blob)
        if size == 0:
            raise ValueError("empty blob")
        if size > self.MAX_BACKUP_BYTES:
            raise ValueError(f"blob exceeds {self.MAX_BACKUP_BYTES} bytes")

        now = int(time.time())
        async with self._session_maker() as s:
            existing = await s.get(EncryptedBackup, pubkey_hex)
            if existing:
                existing.blob       = blob
                existing.sha256_hex = sha256_hex
                existing.byte_size  = size
                existing.updated_at = now
                created = existing.created_at
            else:
                s.add(EncryptedBackup(
                    pubkey_hex = pubkey_hex,
                    blob       = blob,
                    sha256_hex = sha256_hex,
                    byte_size  = size,
                    created_at = now,
                    updated_at = now,
                ))
                created = now
            await s.commit()
        return {
            "pubkey_hex": pubkey_hex,
            "sha256":     sha256_hex,
            "byte_size":  size,
            "created_at": created,
            "updated_at": now,
        }

    async def get_backup(self, pubkey_hex: str) -> Optional[dict]:
        async with self._session_maker() as s:
            row = await s.get(EncryptedBackup, pubkey_hex)
            if not row:
                return None
            return {
                "pubkey_hex": row.pubkey_hex,
                "blob":       bytes(row.blob),
                "sha256":     row.sha256_hex,
                "byte_size":  int(row.byte_size),
                "created_at": int(row.created_at),
                "updated_at": int(row.updated_at),
            }

    async def get_backup_meta(self, pubkey_hex: str) -> Optional[dict]:
        """Return metadata without the blob — useful for 'have you backed up?' UI."""
        async with self._session_maker() as s:
            row = await s.get(EncryptedBackup, pubkey_hex)
            if not row:
                return None
            return {
                "pubkey_hex": row.pubkey_hex,
                "sha256":     row.sha256_hex,
                "byte_size":  int(row.byte_size),
                "created_at": int(row.created_at),
                "updated_at": int(row.updated_at),
            }

    async def delete_backup(self, pubkey_hex: str) -> bool:
        async with self._session_maker() as s:
            row = await s.get(EncryptedBackup, pubkey_hex)
            if not row:
                return False
            await s.delete(row)
            await s.commit()
            return True

    async def stats(self) -> dict[str, Any]:
        cutoff = int(time.time()) - ONLINE_WINDOW_SEC
        async with self._session_maker() as s:
            total = (await s.execute(select(func.count()).select_from(Node))).scalar_one()
            approved = (
                await s.execute(
                    select(func.count()).select_from(Node).where(Node.approved.is_(True))
                )
            ).scalar_one()
            online = (
                await s.execute(
                    select(func.count())
                    .select_from(Node)
                    .where(Node.approved.is_(True))
                    .where(Node.last_heartbeat >= cutoff)
                )
            ).scalar_one()
        return {"total": int(total), "approved": int(approved), "online": int(online)}


def _to_dict(node: Node) -> dict:
    meta = dict(node.node_metadata or {})
    w = _freshness_weight(node.last_heartbeat) * _capability_weight(meta)
    return {
        "pubkey_hex": node.pubkey_hex,
        "endpoints": list(node.endpoints or []),
        "metadata": meta,
        "registered_at": node.registered_at,
        "last_heartbeat": node.last_heartbeat,
        "approved": bool(node.approved),
        "weight": round(w, 4),
    }


# Penalty applied to node weight when capabilities are missing. Lower
# weight = fewer users get routed to this node through /v1/nodes/random.
_CAP_PENALTY = {
    "ai_capable": 0.15,   # nodes without local AI lose ~15% of weight
}


def _capability_weight(meta: dict) -> float:
    """Multiply base freshness weight by a capability factor.

    Reads flags from the node's self-reported metadata (set when it
    registers / heartbeats). A missing flag is treated as disabled.
    """
    mul = 1.0
    for flag, penalty in _CAP_PENALTY.items():
        if not bool(meta.get(flag)):
            mul *= (1.0 - penalty)
    return mul


def _freshness_weight(last_heartbeat: int, now: Optional[int] = None) -> float:
    """Phase 7B decay — fresh heartbeats get full weight, stale ones fall off.

    Mirrors ``PeerAccount.weight`` in the Solana client so both discovery
    sources converge on the same trust model.
    """
    now = now if now is not None else int(time.time())
    days = max(0.0, (now - last_heartbeat) / 86400)
    if days < 7:
        return 1.0
    if days < 30:
        return 0.8
    if days < 90:
        return 0.5
    if days < 180:
        return 0.2
    return 0.0
