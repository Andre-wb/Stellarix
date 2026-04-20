"""Database engine -- SQLite (default) or PostgreSQL (opt-in via DATABASE_URL).

Provides both synchronous and asynchronous engines/sessions.
Sync is used by existing endpoints; async is available for new code and
scales better with PostgreSQL + asyncpg.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import subprocess

from sqlalchemy import create_engine, event, text as _text
from sqlalchemy.orm import sessionmaker

from app.config import Config

logger = logging.getLogger(__name__)
from app.base import Base  # noqa: E402
from app import models, models_rooms  # noqa: E402, F401  -- register models
from app.models import contact as _models_contact  # noqa: F401  -- register Contact table
from app.models import prekeys as _models_prekeys  # noqa: F401  -- register PreKeyBundle/OneTimePreKey

# ---------------------------------------------------------------------------
# Resolve the effective database URL
# ---------------------------------------------------------------------------
DATABASE_URL = Config.get_database_url()

# Ephemeral mode — no disk persistence. Every message, key, and metadata
# lives only in memory; restart = complete wipe. Overrides DATABASE_URL.
if os.getenv("EPHEMERAL_MODE", "").lower() in ("1", "true", "yes"):
    DATABASE_URL = "sqlite:///:memory:"

_is_sqlite = DATABASE_URL.startswith("sqlite://")
_is_postgres = DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgresql+")

# ---------------------------------------------------------------------------
# Async URL variant (for async engine)
# ---------------------------------------------------------------------------
if _is_postgres:
    if "postgresql+asyncpg" in DATABASE_URL:
        ASYNC_DATABASE_URL = DATABASE_URL
    elif "postgresql+psycopg2" in DATABASE_URL:
        ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+psycopg2", "postgresql+asyncpg", 1)
    elif DATABASE_URL.startswith("postgresql://"):
        ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    else:
        ASYNC_DATABASE_URL = DATABASE_URL

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
    """FastAPI dependency -- yields a sync DB session."""
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
        logger.warning("asyncpg or sqlalchemy[asyncio] not installed -- async engine disabled")


async def get_async_db():
    """FastAPI dependency -- yields an async DB session (PostgreSQL only)."""
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
# Alembic helpers
# ---------------------------------------------------------------------------
def _alembic_available() -> bool:
    """Check if Alembic is installed and migration directory exists."""
    try:
        import alembic  # noqa: F401
    except ImportError:
        return False

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ini_path = os.path.join(project_root, "alembic.ini")
    versions_dir = os.path.join(project_root, "alembic", "versions")
    if not (os.path.isfile(ini_path) and os.path.isdir(versions_dir)):
        return False
    # Check there are actual migration .py files (not just __pycache__)
    import glob
    migrations = glob.glob(os.path.join(versions_dir, "*.py"))
    return len(migrations) > 0


def _alembic_needs_stamp() -> bool:
    """Check if DB has tables but no alembic_version — needs stamp, not upgrade."""
    try:
        with engine.connect() as conn:
            # Check if alembic_version table exists and has rows
            try:
                row = conn.execute(_text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
                if row:
                    return False  # Already stamped — normal upgrade
            except Exception:
                pass  # alembic_version doesn't exist yet

            # Check if main tables already exist (created by create_all)
            try:
                conn.execute(_text("SELECT 1 FROM users LIMIT 1"))
                return True  # Tables exist but no alembic version — need stamp
            except Exception:
                return False  # Fresh DB — normal upgrade will create everything
    except Exception:
        return False


def _run_alembic_stamp() -> bool:
    """Run ``alembic stamp head`` to mark existing DB as up-to-date."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        result = subprocess.run(
            ["python", "-m", "alembic", "stamp", "head"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info("Alembic stamp head -- existing DB marked as current")
            return True
        logger.warning("Alembic stamp failed: %s", result.stderr.strip())
        return False
    except Exception as exc:
        logger.warning("Alembic stamp error: %s", exc)
        return False


def _run_alembic_upgrade() -> bool:
    """Run ``alembic upgrade head`` as a subprocess.

    Returns True if upgrade succeeded, False otherwise.
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # If tables exist but alembic doesn't know — stamp first
    if _alembic_needs_stamp():
        logger.info("DB tables exist but no alembic version -- stamping as current")
        _run_alembic_stamp()

    try:
        result = subprocess.run(
            ["python", "-m", "alembic", "upgrade", "head"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            logger.info("Alembic migration completed successfully")
            if result.stdout.strip():
                for line in result.stdout.strip().splitlines():
                    logger.info("  alembic: %s", line)
            return True
        else:
            logger.warning(
                "Alembic upgrade failed (exit %d): %s",
                result.returncode,
                result.stderr.strip() or result.stdout.strip(),
            )
            return False
    except FileNotFoundError:
        logger.warning("Could not run alembic -- 'python' not found in PATH")
        return False
    except subprocess.TimeoutExpired:
        logger.warning("Alembic upgrade timed out (120s)")
        return False
    except Exception as exc:
        logger.warning("Alembic upgrade error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------
def init_db() -> None:
    """Create/migrate database schema.

    Strategy:
      1. If Alembic is available and migrations directory exists, run
         ``alembic upgrade head`` (works with both SQLite and PostgreSQL).
      2. If Alembic is unavailable or fails, fall back:
         - Run ``Base.metadata.create_all`` to create any missing tables.
         - For SQLite only, run the legacy ALTER TABLE migration statements
           (safe idempotent approach for single-file deploys).
         - For PostgreSQL without Alembic, only create_all is used (no ALTER).
    """
    alembic_ok = False

    if _alembic_available():
        logger.info("Alembic detected -- running migrations via 'alembic upgrade head'")
        alembic_ok = _run_alembic_upgrade()

    if not alembic_ok:
        if _alembic_available():
            logger.warning("Alembic migration failed -- falling back to create_all + ALTER TABLE")
        else:
            logger.info("Alembic not available -- using create_all + ALTER TABLE fallback")

        # Lazy-import models that can't be imported at module level (circular deps)
        try:
            from app.authentication.security_questions import SecurityQuestion  # noqa: F401
        except ImportError:
            pass

        Base.metadata.create_all(bind=engine)

        if _is_sqlite:
            # Safe migration: add columns if they don't exist (SQLite-only,
            # because PostgreSQL migrations are handled via Alembic).
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
                "ALTER TABLE users ADD COLUMN wallet_pubkey VARCHAR(48)",
                "CREATE INDEX IF NOT EXISTS ix_users_wallet_pubkey ON users(wallet_pubkey)",
                "CREATE TABLE IF NOT EXISTS user_devices (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, device_name VARCHAR(255) NOT NULL, device_type VARCHAR(50) DEFAULT 'web', ip_address VARCHAR(45), last_active DATETIME, created_at DATETIME, refresh_token_hash VARCHAR(64))",
                "CREATE INDEX IF NOT EXISTS ix_user_devices_user_id ON user_devices(user_id)",
                "CREATE INDEX IF NOT EXISTS ix_user_devices_token_hash ON user_devices(refresh_token_hash)",
                "ALTER TABLE rooms ADD COLUMN theme_json TEXT",
                "ALTER TABLE spaces ADD COLUMN theme_json TEXT",
                "ALTER TABLE users ADD COLUMN kyber_public_key TEXT",
                "CREATE TABLE IF NOT EXISTS channel_feeds (id INTEGER PRIMARY KEY AUTOINCREMENT, room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE, feed_type VARCHAR(20) NOT NULL, url TEXT NOT NULL, last_fetched DATETIME, last_item_id TEXT, is_active BOOLEAN DEFAULT 1, created_at DATETIME)",
                # Variant-B public-room key escrow (server stores the symmetric
                # key in plaintext; rows exist ONLY for is_private=0 rooms).
                "CREATE TABLE IF NOT EXISTS public_room_keys (room_id INTEGER PRIMARY KEY REFERENCES rooms(id) ON DELETE CASCADE, key_hex VARCHAR(64) NOT NULL, algorithm VARCHAR(32) NOT NULL DEFAULT 'aes-256-gcm', created_at DATETIME, rotated_at DATETIME)",
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
                "ALTER TABLE room_members ADD COLUMN tag VARCHAR(30)",
                "ALTER TABLE room_members ADD COLUMN tag_color VARCHAR(7)",
                "ALTER TABLE room_members ADD COLUMN custom_permissions TEXT",
                "ALTER TABLE call_history ADD COLUMN seen BOOLEAN DEFAULT 0",
                "ALTER TABLE users ADD COLUMN auto_delete_days INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN passkey_credential_id VARCHAR(256)",
                "ALTER TABLE users ADD COLUMN passkey_public_key TEXT",
                "ALTER TABLE users ADD COLUMN passkey_sign_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN show_last_seen BOOLEAN DEFAULT 1",
                # Double Ratchet / X3DH pre-key tables
                "CREATE TABLE IF NOT EXISTS prekey_bundles (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE, identity_key BLOB NOT NULL, signed_prekey BLOB NOT NULL, signed_prekey_sig BLOB NOT NULL, signed_prekey_id INTEGER NOT NULL DEFAULT 0, created_at DATETIME, updated_at DATETIME)",
                "CREATE INDEX IF NOT EXISTS ix_prekey_bundles_user_id ON prekey_bundles(user_id)",
                "CREATE TABLE IF NOT EXISTS onetime_prekeys (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, key_id INTEGER NOT NULL, public_key BLOB NOT NULL, used BOOLEAN DEFAULT 0, created_at DATETIME)",
                "CREATE INDEX IF NOT EXISTS ix_onetime_prekeys_user_id ON onetime_prekeys(user_id)",
                "CREATE INDEX IF NOT EXISTS ix_onetime_prekeys_available ON onetime_prekeys(user_id, used)",
                # Push subscriptions
                "CREATE TABLE IF NOT EXISTS push_subscriptions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, endpoint VARCHAR(512) NOT NULL UNIQUE, p256dh VARCHAR(256) NOT NULL, auth VARCHAR(256) NOT NULL, created_at DATETIME)",
                "CREATE INDEX IF NOT EXISTS ix_push_subscriptions_user_id ON push_subscriptions(user_id)",
                # Room-level cross-node replication policy (owner opt-in)
                "ALTER TABLE rooms ADD COLUMN replication_mode VARCHAR(16) NOT NULL DEFAULT 'none'",
                # DM tipping log (tip_events)
                "CREATE TABLE IF NOT EXISTS tip_events ("
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  from_user INTEGER,"
                "  to_user INTEGER,"
                "  to_wallet VARCHAR(64) NOT NULL,"
                "  lamports INTEGER NOT NULL,"
                "  note VARCHAR(200) DEFAULT '',"
                "  tx_sig VARCHAR(200),"
                "  confirmed INTEGER DEFAULT 0,"
                "  created_at DATETIME"
                ")",
                "CREATE INDEX IF NOT EXISTS ix_tip_from ON tip_events(from_user)",
                "CREATE INDEX IF NOT EXISTS ix_tip_to ON tip_events(to_user)",
                "CREATE INDEX IF NOT EXISTS ix_tip_sig ON tip_events(tx_sig)",
                # Replicated envelopes received from peer nodes (federated rooms)
                "CREATE TABLE IF NOT EXISTS federated_envelopes ("
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  origin_pubkey_hex VARCHAR(64) NOT NULL,"
                "  room_id_origin INTEGER NOT NULL,"
                "  envelope_hash VARCHAR(64) NOT NULL UNIQUE,"
                "  payload_blob BLOB NOT NULL,"
                "  signature_hex VARCHAR(128) NOT NULL,"
                "  sender_ts INTEGER NOT NULL,"
                "  created_at DATETIME"
                ")",
                "CREATE INDEX IF NOT EXISTS ix_fed_env_origin ON federated_envelopes(origin_pubkey_hex)",
                "CREATE INDEX IF NOT EXISTS ix_fed_env_room_origin ON federated_envelopes(room_id_origin, origin_pubkey_hex)",
                "CREATE INDEX IF NOT EXISTS ix_fed_env_created_at ON federated_envelopes(created_at)",
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
                    logger.exception("SQLite migration batch failed -- rolled back all changes")
        else:
            logger.info(
                "PostgreSQL detected -- skipping SQLite ALTER TABLE migrations. "
                "Use Alembic for schema migrations: alembic upgrade head"
            )

        # After create_all + ALTER TABLE, stamp Alembic so next startup uses upgrade
        if _alembic_available():
            _run_alembic_stamp()


def get_engine_info() -> dict:
    """Return engine metadata for health checks and diagnostics."""
    info = {
        "backend": "postgresql" if _is_postgres else "sqlite",
        "url_scheme": DATABASE_URL.split("://")[0] if "://" in DATABASE_URL else "unknown",
        "async_available": async_engine is not None,
        "alembic_available": _alembic_available(),
    }
    if _is_postgres:
        info["pool_size"] = Config.DB_POOL_SIZE
        info["max_overflow"] = Config.DB_MAX_OVERFLOW
        info["pool_recycle"] = Config.DB_POOL_RECYCLE
    return info
