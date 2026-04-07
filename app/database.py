"""Database engine — SQLite (default) or PostgreSQL (opt-in via DATABASE_URL).

Provides both synchronous and asynchronous engines/sessions.
Sync is used by existing endpoints; async is available for new code and
scales better with PostgreSQL + asyncpg.
"""
from __future__ import annotations

import logging
import sqlite3

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import Config

logger = logging.getLogger(__name__)
from app.base import Base  # noqa: E402
from app import models, models_rooms  # noqa: E402, F401  — register models
from app.models import contact as _models_contact  # noqa: F401  — register Contact table

# ---------------------------------------------------------------------------
# Resolve the effective database URL
# ---------------------------------------------------------------------------
if Config.DATABASE_URL:
    DATABASE_URL = Config.DATABASE_URL
else:
    DATABASE_URL = f"sqlite:///{Config.DB_PATH}"

_is_sqlite = DATABASE_URL.startswith("sqlite://")
_is_postgres = DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgresql+")

# ---------------------------------------------------------------------------
# Async URL variant (for async engine)
# ---------------------------------------------------------------------------
if _is_postgres:
    # postgresql://user:pass@host/db  →  postgresql+asyncpg://user:pass@host/db
    if "postgresql+asyncpg" in DATABASE_URL:
        ASYNC_DATABASE_URL = DATABASE_URL
    elif "postgresql+psycopg2" in DATABASE_URL:
        ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+psycopg2", "postgresql+asyncpg", 1)
    elif DATABASE_URL.startswith("postgresql://"):
        ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    else:
        ASYNC_DATABASE_URL = DATABASE_URL

    # Ensure sync URL uses psycopg2 explicitly
    if DATABASE_URL.startswith("postgresql://"):
        SYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    elif "postgresql+asyncpg" in DATABASE_URL:
        SYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2", 1)
    else:
        SYNC_DATABASE_URL = DATABASE_URL
else:
    ASYNC_DATABASE_URL = None
    SYNC_DATABASE_URL = DATABASE_URL

# ---------------------------------------------------------------------------
# Synchronous engine (used by existing code)
# ---------------------------------------------------------------------------
if _is_postgres:
    engine = create_engine(
        SYNC_DATABASE_URL,
        pool_size=Config.DB_POOL_SIZE,
        max_overflow=Config.DB_MAX_OVERFLOW,
        pool_pre_ping=True,
        pool_recycle=Config.DB_POOL_RECYCLE,
    )
    logger.info(
        "Database engine: PostgreSQL (pool_size=%d, max_overflow=%d, recycle=%ds)",
        Config.DB_POOL_SIZE, Config.DB_MAX_OVERFLOW, Config.DB_POOL_RECYCLE,
    )
else:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    logger.info("Database engine: SQLite (%s)", DATABASE_URL)

# ---------------------------------------------------------------------------
# SQLite-specific pragmas (only for SQLite connections)
# ---------------------------------------------------------------------------
if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_pragmas(conn, _):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA temp_store=MEMORY")
        cur.execute("PRAGMA mmap_size=268435456")
        cur.close()

# ---------------------------------------------------------------------------
# Synchronous session factory
# ---------------------------------------------------------------------------
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency — yields a sync DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Async engine & session (PostgreSQL only)
# ---------------------------------------------------------------------------
AsyncSessionLocal = None
async_engine = None

if _is_postgres and ASYNC_DATABASE_URL:
    try:
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker as _sessionmaker

        async_engine = create_async_engine(
            ASYNC_DATABASE_URL,
            pool_size=Config.DB_POOL_SIZE,
            max_overflow=Config.DB_MAX_OVERFLOW,
            pool_pre_ping=True,
            pool_recycle=Config.DB_POOL_RECYCLE,
            echo=False,
        )

        AsyncSessionLocal = _sessionmaker(
            bind=async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        logger.info(
            "Async engine: PostgreSQL+asyncpg (pool_size=%d, max_overflow=%d)",
            Config.DB_POOL_SIZE, Config.DB_MAX_OVERFLOW,
        )
    except ImportError:
        logger.warning("asyncpg or sqlalchemy[asyncio] not installed — async engine disabled")


async def get_async_db():
    """FastAPI dependency — yields an async DB session (PostgreSQL only)."""
    if AsyncSessionLocal is None:
        raise RuntimeError(
            "Async database session not available. "
            "Set DATABASE_URL to a PostgreSQL URL and install asyncpg."
        )
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------
def init_db() -> None:
    """Create all tables from ORM metadata (sync engine)."""
    Base.metadata.create_all(bind=engine)

    if _is_sqlite:
        # Safe migration: add columns if they don't exist (SQLite-only,
        # because PostgreSQL migrations are handled via Alembic).
        _text = __import__("sqlalchemy").text
        migration_stmts = [
            "ALTER TABLE users ADD COLUMN avatar_url VARCHAR(255)",
            "ALTER TABLE rooms ADD COLUMN avatar_emoji VARCHAR(10) DEFAULT '\U0001f4ac'",
            "ALTER TABLE rooms ADD COLUMN avatar_url VARCHAR(255)",
            "ALTER TABLE rooms ADD COLUMN antispam_enabled BOOLEAN DEFAULT 1",
            "ALTER TABLE users ADD COLUMN is_bot BOOLEAN DEFAULT 0",
            "ALTER TABLE rooms ADD COLUMN is_voice BOOLEAN DEFAULT 0",
            "ALTER TABLE rooms ADD COLUMN space_id INTEGER REFERENCES spaces(id) ON DELETE SET NULL",
            "ALTER TABLE rooms ADD COLUMN category_id INTEGER REFERENCES space_categories(id) ON DELETE SET NULL",
            "ALTER TABLE rooms ADD COLUMN order_idx INTEGER DEFAULT 0",
            "ALTER TABLE rooms ADD COLUMN antispam_config TEXT DEFAULT '{}'",
            "ALTER TABLE users ADD COLUMN global_muted_until DATETIME",
            "ALTER TABLE users ADD COLUMN banned_until DATETIME",
            "ALTER TABLE users ADD COLUMN strike_count INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN custom_status VARCHAR(100)",
            "ALTER TABLE users ADD COLUMN status_emoji VARCHAR(10)",
            "ALTER TABLE users ADD COLUMN presence VARCHAR(20) DEFAULT 'online'",
            "ALTER TABLE rooms ADD COLUMN is_forum BOOLEAN DEFAULT 0",
            "ALTER TABLE spaces ADD COLUMN parent_id INTEGER REFERENCES spaces(id) ON DELETE SET NULL",
            "ALTER TABLE spaces ADD COLUMN vanity_url VARCHAR(50)",
            "ALTER TABLE spaces ADD COLUMN welcome_message TEXT DEFAULT ''",
            "ALTER TABLE spaces ADD COLUMN rules TEXT DEFAULT ''",
            "ALTER TABLE spaces ADD COLUMN onboarding_roles TEXT DEFAULT '[]'",
            "ALTER TABLE spaces ADD COLUMN template_id VARCHAR(30)",
            "ALTER TABLE users ADD COLUMN bio VARCHAR(300)",
            "ALTER TABLE users ADD COLUMN birth_date DATE",
            "ALTER TABLE users ADD COLUMN profile_bg VARCHAR(30)",
            "ALTER TABLE users ADD COLUMN profile_icon VARCHAR(50)",
            "ALTER TABLE users ADD COLUMN network_mode VARCHAR(20) DEFAULT 'standard'",
            "ALTER TABLE users ADD COLUMN totp_secret VARCHAR(64)",
            "ALTER TABLE users ADD COLUMN totp_enabled BOOLEAN DEFAULT 0",
            "ALTER TABLE users ADD COLUMN email VARCHAR(120)",
            "ALTER TABLE users ADD COLUMN last_ip VARCHAR(45)",
            "CREATE TABLE IF NOT EXISTS user_devices (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, device_name VARCHAR(255) NOT NULL, device_type VARCHAR(50) DEFAULT 'web', ip_address VARCHAR(45), last_active DATETIME, created_at DATETIME, refresh_token_hash VARCHAR(64))",
            "CREATE INDEX IF NOT EXISTS ix_user_devices_user_id ON user_devices(user_id)",
            "CREATE INDEX IF NOT EXISTS ix_user_devices_token_hash ON user_devices(refresh_token_hash)",
            "ALTER TABLE rooms ADD COLUMN theme_json TEXT",
            "ALTER TABLE spaces ADD COLUMN theme_json TEXT",
            "ALTER TABLE users ADD COLUMN kyber_public_key TEXT",
            "CREATE TABLE IF NOT EXISTS channel_feeds (id INTEGER PRIMARY KEY AUTOINCREMENT, room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE, feed_type VARCHAR(20) NOT NULL, url TEXT NOT NULL, last_fetched DATETIME, last_item_id TEXT, is_active BOOLEAN DEFAULT 1, created_at DATETIME)",
            "CREATE INDEX IF NOT EXISTS ix_channel_feeds_room_id ON channel_feeds(room_id)",
            "CREATE TABLE IF NOT EXISTS message_edit_history (id INTEGER PRIMARY KEY AUTOINCREMENT, message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE, ciphertext_hex TEXT NOT NULL, edited_at DATETIME NOT NULL)",
            "CREATE INDEX IF NOT EXISTS ix_edit_history_message_id ON message_edit_history(message_id)",
            "ALTER TABLE messages ADD COLUMN edited_at DATETIME",
            "ALTER TABLE messages ADD COLUMN sender_pseudo VARCHAR(64)",
            "CREATE INDEX IF NOT EXISTS ix_messages_sender_pseudo ON messages(sender_pseudo)",
            "ALTER TABLE users ADD COLUMN seed_phrase_hash VARCHAR(512)",
            "ALTER TABLE contacts ADD COLUMN fingerprint_verified BOOLEAN DEFAULT 0",
            "ALTER TABLE contacts ADD COLUMN fingerprint_verified_at DATETIME",
            "ALTER TABLE contacts ADD COLUMN fingerprint_pubkey_hash VARCHAR(64)",
            "CREATE TABLE IF NOT EXISTS key_backups (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE, vault_data TEXT NOT NULL, vault_salt VARCHAR(64) NOT NULL, kdf_params TEXT NOT NULL, version INTEGER DEFAULT 1, created_at DATETIME, updated_at DATETIME)",
            "CREATE INDEX IF NOT EXISTS ix_key_backups_user_id ON key_backups(user_id)",
            "CREATE TABLE IF NOT EXISTS device_link_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, link_code_hash VARCHAR(64) NOT NULL, new_device_pub VARCHAR(64) NOT NULL, status VARCHAR(20) DEFAULT 'pending', encrypted_keys TEXT, created_at DATETIME, expires_at DATETIME NOT NULL)",
            "CREATE INDEX IF NOT EXISTS ix_device_link_requests_user_id ON device_link_requests(user_id)",
            "CREATE INDEX IF NOT EXISTS ix_device_link_requests_code ON device_link_requests(link_code_hash)",
            "CREATE TABLE IF NOT EXISTS sync_events (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, device_id INTEGER NOT NULL, event_type VARCHAR(20) NOT NULL, payload TEXT NOT NULL, seq INTEGER DEFAULT 0, created_at DATETIME)",
            "CREATE INDEX IF NOT EXISTS ix_sync_events_user_seq ON sync_events(user_id, seq)",
            "CREATE TABLE IF NOT EXISTS device_cross_signs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, signer_device INTEGER NOT NULL, signed_device INTEGER NOT NULL, signature TEXT NOT NULL, signer_pub_hash VARCHAR(64) NOT NULL, signed_pub_hash VARCHAR(64) NOT NULL, created_at DATETIME)",
            "CREATE INDEX IF NOT EXISTS ix_device_cross_signs_user ON device_cross_signs(user_id)",
            "ALTER TABLE user_devices ADD COLUMN device_pub_key VARCHAR(64)",
            "CREATE TABLE IF NOT EXISTS secret_shares (id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, recipient_id INTEGER REFERENCES users(id) ON DELETE SET NULL, share_index INTEGER NOT NULL, encrypted_share TEXT NOT NULL, threshold INTEGER NOT NULL, total_shares INTEGER NOT NULL, label VARCHAR(100), status VARCHAR(20) DEFAULT 'active', created_at DATETIME)",
            "CREATE INDEX IF NOT EXISTS ix_secret_shares_owner ON secret_shares(owner_id)",
            "CREATE INDEX IF NOT EXISTS ix_secret_shares_recipient ON secret_shares(recipient_id)",
            "CREATE TABLE IF NOT EXISTS federated_backup_shards (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, shard_index INTEGER NOT NULL, peer_ip VARCHAR(45) NOT NULL, peer_port INTEGER NOT NULL, encrypted_shard TEXT NOT NULL, shard_hash VARCHAR(64) NOT NULL, status VARCHAR(20) DEFAULT 'placed', threshold INTEGER NOT NULL, total_shards INTEGER NOT NULL, created_at DATETIME)",
            "CREATE INDEX IF NOT EXISTS ix_fed_backup_shards_user ON federated_backup_shards(user_id)",
            "CREATE TABLE IF NOT EXISTS key_transparency_log (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, key_type VARCHAR(30) NOT NULL, pub_key_hash VARCHAR(64) NOT NULL, prev_hash VARCHAR(64), signature TEXT NOT NULL, device_id INTEGER, seq INTEGER DEFAULT 0, created_at DATETIME)",
            "CREATE INDEX IF NOT EXISTS ix_kt_log_user_seq ON key_transparency_log(user_id, seq)",
            "ALTER TABLE rooms ADD COLUMN discussion_enabled BOOLEAN DEFAULT 0",
            "ALTER TABLE rooms ADD COLUMN reactions_type VARCHAR(20) DEFAULT 'all'",
            "ALTER TABLE rooms ADD COLUMN allowed_reactions TEXT DEFAULT ''",
            "ALTER TABLE rooms ADD COLUMN admin_signatures BOOLEAN DEFAULT 0",
            "ALTER TABLE rooms ADD COLUMN copy_protection BOOLEAN DEFAULT 0",
            "ALTER TABLE rooms ADD COLUMN silent_default BOOLEAN DEFAULT 0",
            "ALTER TABLE rooms ADD COLUMN join_approval BOOLEAN DEFAULT 0",
            "ALTER TABLE rooms ADD COLUMN hashtags_enabled BOOLEAN DEFAULT 1",
        ]
        with engine.connect() as conn:
            try:
                for stmt in migration_stmts:
                    try:
                        conn.execute(_text(stmt))
                    except sqlite3.OperationalError as e:
                        if "duplicate column" in str(e).lower():
                            continue
                        raise
                    except Exception as e:
                        orig = getattr(e, "orig", e)
                        if isinstance(orig, sqlite3.OperationalError) and "duplicate column" in str(orig).lower():
                            continue
                        raise
                conn.commit()
            except Exception:
                conn.rollback()
                logger.exception("SQLite migration batch failed — rolled back all changes")
    else:
        logger.info(
            "PostgreSQL detected — skipping SQLite ALTER TABLE migrations. "
            "Use Alembic for schema migrations: alembic upgrade head"
        )


def get_engine_info() -> dict:
    """Return engine metadata for health checks and diagnostics."""
    info = {
        "backend": "postgresql" if _is_postgres else "sqlite",
        "url_scheme": DATABASE_URL.split("://")[0] if "://" in DATABASE_URL else "unknown",
        "async_available": async_engine is not None,
    }
    if _is_postgres:
        info["pool_size"] = Config.DB_POOL_SIZE
        info["max_overflow"] = Config.DB_MAX_OVERFLOW
        info["pool_recycle"] = Config.DB_POOL_RECYCLE
    return info
