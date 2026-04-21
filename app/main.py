"""
Vortex Chat — децентрализованный мессенджер.
X25519+AES-256-GCM, Argon2, WAF, CSRF, security headers.

v5: Global mode, structured logging, Prometheus metrics, graceful shutdown.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Config
from app.database import init_db
from app.files.resumable import router as resumable_router, cleanup_sessions_loop
from app.logging_config import setup_logging, correlation_id, new_correlation_id
from app.peer.connection_manager import manager
from app.peer.peer_registry import start_discovery, registry
from app.security.crypto import load_or_create_node_keypair, rust_available

# Routers
from app.authentication import router as auth_router
from app.bots.bot_api import router as bots_router
from app.bots.ide_routes import router as ide_router, bot_call_router as ide_bot_call_router, federated_router as ide_federated_router, webhook_router as ide_webhook_router
from app.chats.channels import router as channels_router
from app.chats.channel_feeds import router as channel_feeds_router
from app.chats.chat import router as chat_router
from app.chats.contacts import router as contacts_router, block_router
from app.chats.contact_sync import router as contact_sync_router
from app.chats.dm import router as dm_router
from app.chats.link_preview import router as link_preview_router
from app.chats.reports import router as reports_router
from app.chats.rooms import router as rooms_router
from app.chats.saved import router as saved_router
from app.chats.search import router as search_router, messages_search_router
from app.chats.spaces import router as spaces_router
from app.chats.statuses import router as statuses_router
from app.chats.stickers import router as stickers_router
from app.chats.saved_gifs import router as saved_gifs_router
from app.push.bmp_push_proxy import router as bmp_push_router
from app.chats.tasks import router as tasks_router
from app.chats.voice import router as voice_router, ws_router as voice_ws_router
from app.federation.federation import router as federation_router, ws_router as fed_ws_router
from app.federation.replication import router as replication_router
from app.federation.trusted_nodes import trusted_nodes_router
from app.security.zero_knowledge import zk_router
from app.keys.keys import router as keys_router
from app.peer.peer_registry import router as peers_router
# Side-effect import: registers /api/peers/controller-proxy on peers_router
from app.peer import controller_proxy as _controller_proxy  # noqa: F401
from app.session.migration import router as session_router
from app.security.middleware import (
    CSRFMiddleware,
    LoggingMiddleware,
    SecurityHeadersMiddleware,
    TokenRefreshMiddleware,
)
from app.transport.stealth import StealthMiddleware, is_stealth
from app.security.waf import WAFMiddleware, init_waf_engine, waf_router

# ── Structured Logging Setup ─────────────────────────────────────────────────
setup_logging()
logger = logging.getLogger(__name__)

# ── Sentry Error Tracking ───────────────────────────────────────────────────
_SENTRY_DSN = os.getenv("SENTRY_DSN", "")
if _SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            environment=os.getenv("SENTRY_ENVIRONMENT", Config.ENVIRONMENT),
            release=f"vortex@1.0.0",
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_RATE", "0.1")),
            profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_RATE", "0.1")),
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlalchemyIntegration(),
            ],
            send_default_pii=False,
        )
        logger.info("Sentry error tracking enabled (env=%s)", os.getenv("SENTRY_ENVIRONMENT", Config.ENVIRONMENT))
    except ImportError:
        logger.warning("sentry-sdk not installed — error tracking disabled")
    except Exception as e:
        logger.warning("Sentry initialization failed: %s", e)

# ── Prometheus Metrics ────────────────────────────────────────────────────────
try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )

    REQUEST_COUNT = Counter(
        "vortex_http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status"],
    )
    REQUEST_DURATION = Histogram(
        "vortex_http_request_duration_seconds",
        "HTTP request duration",
        ["method", "endpoint"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    )
    ACTIVE_CONNECTIONS = Gauge(
        "vortex_ws_connections_active",
        "Active WebSocket connections",
    )
    ACTIVE_PEERS = Gauge(
        "vortex_peers_active",
        "Active P2P peers",
    )
    DB_ERRORS = Counter(
        "vortex_db_errors_total",
        "Database errors",
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False

# ── Background task references (for graceful shutdown) ────────────────────────
_background_tasks: list[asyncio.Task] = []
_startup_time: float = 0.0


def _create_background_task(coro, name: str) -> asyncio.Task:
    """Create a named background task and track it for graceful shutdown."""
    task = asyncio.create_task(coro, name=name)
    _background_tasks.append(task)
    return task


# ── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _startup_time
    _startup_time = time.monotonic()

    Config.ensure_dirs()
    Config.validate()
    init_db()
    logger.info("DB initialized")

    # Create system antispam bot if it doesn't exist
    from app.bots.antispam_bot import ensure_antispam_bot
    from app.database import SessionLocal

    _startup_db = SessionLocal()
    try:
        ensure_antispam_bot(_startup_db)
        _startup_db.commit()
        logger.info("Antispam bot ready")
    finally:
        _startup_db.close()

    _, pub = load_or_create_node_keypair(Config.KEYS_DIR)
    logger.info("X25519 node pubkey: %s...", pub.hex()[:32])

    # ── Post-quantum crypto status (MANDATORY by default) ──────────────
    _pq_required = os.environ.get("VORTEX_PQ_REQUIRED", "true").lower() in ("1", "true", "yes")
    try:
        from app.security.post_quantum import get_pq_status
        _pq = get_pq_status()
        if _pq.get("secure"):
            logger.info(
                "Post-quantum crypto active — algorithm: %s, backend: %s",
                _pq.get("algorithm", "unknown"),
                _pq.get("backend", "unknown"),
            )
        elif _pq_required:
            # PQ is required but not available (or simulation only)
            if _pq.get("simulated") or _pq.get("backend") == "simulated":
                logger.critical(
                    "FATAL: VORTEX_PQ_REQUIRED=true but PQ is in SIMULATION mode. "
                    "Simulation provides NO real post-quantum security. "
                    "Install liboqs-python: pip install liboqs-python"
                )
                raise SystemExit(
                    "Post-quantum cryptography is REQUIRED but only simulation is available. "
                    "Install a real PQ library (pip install liboqs-python) or set "
                    "VORTEX_PQ_REQUIRED=false to allow startup without PQ protection."
                )
            else:
                logger.critical(
                    "FATAL: VORTEX_PQ_REQUIRED=true but no PQ library available (backend=%s). "
                    "Install liboqs-python: pip install liboqs-python",
                    _pq.get("backend", "unavailable"),
                )
                raise SystemExit(
                    "Post-quantum cryptography is REQUIRED but unavailable. "
                    "Install liboqs-python (pip install liboqs-python) or set "
                    "VORTEX_PQ_REQUIRED=false to allow startup without PQ protection."
                )
        else:
            logger.warning(
                "POST-QUANTUM CRYPTO UNAVAILABLE — backend: %s. "
                "VORTEX_PQ_REQUIRED=false, allowing startup with X25519 only. "
                "Install liboqs-python for quantum resistance.",
                _pq.get("backend", "unavailable"),
            )
    except SystemExit:
        raise
    except Exception as _pq_err:
        if _pq_required:
            raise SystemExit(
                f"Post-quantum cryptography is REQUIRED but status check failed: {_pq_err}. "
                "Set VORTEX_PQ_REQUIRED=false to allow startup without PQ."
            )
        logger.warning("Could not determine PQ-crypto status: %s", _pq_err)

    # ── Redis for horizontal scaling ─────────────────────────────────
    from app.peer.redis_pubsub import init_redis, start_subscriber, is_redis_available
    redis_ok = await init_redis()
    if redis_ok:
        async def _on_redis_room_msg(room_id, payload):
            try:
                await manager.broadcast_to_room(room_id, payload)
            except Exception:
                logger.exception("Redis room message broadcast failed (room=%s)", room_id)
        async def _on_redis_notification(user_id, payload):
            try:
                await manager.notify_user(user_id, payload)
            except Exception:
                logger.exception("Redis notification delivery failed (user=%s)", user_id)
        await start_subscriber(_on_redis_room_msg, _on_redis_notification)
        logger.info("Redis pub/sub enabled — horizontal scaling active")

    if rust_available():
        import vortex_chat
        logger.info("Rust crypto backend: vortex_chat %s", vortex_chat.VERSION)
    else:
        logger.warning("Python crypto fallback (compile Rust module for performance)")

    name = Config.DEVICE_NAME or socket.gethostname()

    if Config.NETWORK_MODE == "global":
        from app.transport.global_transport import global_transport
        bootstrap = [p.strip() for p in Config.BOOTSTRAP_PEERS.split(",") if p.strip()]
        await global_transport.start(bootstrap)
        logger.info("Global mode: gossip started, bootstrap=%d", len(bootstrap))
    else:
        start_discovery(name)

    # ── Self-hosted TURN (coturn) ──────────────────────────────────────
    from app.keys.keys import start_coturn
    start_coturn()

    # ── Tor Hidden Service (.onion) ─────────────────────────────────────
    if Config.TOR_HIDDEN_SERVICE:
        from app.security.tor_hidden_service import tor_hidden_service
        onion = await tor_hidden_service.start(listen_port=Config.PORT)
        if onion:
            logger.info("Tor Hidden Service: http://%s", onion)
        else:
            logger.warning("TOR_HIDDEN_SERVICE=true but Tor HS could not start")

    # ── Restore federated rooms from DB ──────────────────────────────────
    from app.federation.federation import relay as _fed_relay
    _fed_restored = await _fed_relay.restore_from_db()
    if _fed_restored:
        logger.info("Federation: restored %d virtual room(s) from DB", _fed_restored)

    # ── Start trusted nodes monitor (health checks + token rotation) ─────
    from app.federation.trusted_nodes import start_federation_monitor
    await start_federation_monitor()
    logger.info("Federation: trusted nodes monitor started")

    # ── Background cleanup tasks ─────────────────────────────────────────
    _create_background_task(cleanup_sessions_loop(), "cleanup-upload-sessions")

    async def _expired_msg_loop():
        from app.chats.chat import cleanup_expired_messages
        while True:
            await asyncio.sleep(30)
            try:
                db = SessionLocal()
                try:
                    await cleanup_expired_messages(db)
                finally:
                    db.close()
            except Exception as e:
                logger.warning("Expired messages cleanup error: %s", e)

    async def _expired_status_loop():
        from app.chats.statuses import cleanup_expired_statuses
        while True:
            await asyncio.sleep(300)
            try:
                db = SessionLocal()
                try:
                    await cleanup_expired_statuses(db)
                finally:
                    db.close()
            except Exception as e:
                logger.warning("Expired statuses cleanup error: %s", e)

    async def _punishment_cleanup_loop():
        from app.chats.reports import cleanup_expired_punishments
        while True:
            await asyncio.sleep(300)
            try:
                db = SessionLocal()
                try:
                    await cleanup_expired_punishments(db)
                finally:
                    db.close()
            except Exception as e:
                logger.warning("Punishment cleanup error: %s", e)

    async def _metrics_update_loop():
        """Periodically update Prometheus gauges."""
        while _PROMETHEUS_AVAILABLE:
            await asyncio.sleep(15)
            try:
                ACTIVE_CONNECTIONS.set(manager.total_connections())
                ACTIVE_PEERS.set(len(registry.active()))
            except Exception:
                pass

    async def _ws_cleanup_loop():
        """Periodically remove stale WebSocket connections."""
        while True:
            await asyncio.sleep(30)
            try:
                await manager.cleanup_stale()
            except Exception as e:
                logger.debug("WS cleanup error: %s", e)

    _create_background_task(_expired_msg_loop(), "cleanup-expired-messages")
    _create_background_task(_expired_status_loop(), "cleanup-expired-statuses")
    _create_background_task(_punishment_cleanup_loop(), "cleanup-punishments")
    _create_background_task(_ws_cleanup_loop(), "cleanup-stale-ws")

    async def _rss_poll_loop():
        from app.chats.channel_feeds import poll_rss_feeds
        while True:
            await asyncio.sleep(300)  # every 5 minutes
            try:
                db = SessionLocal()
                try:
                    await poll_rss_feeds(db)
                finally:
                    db.close()
            except Exception as e:
                logger.warning("RSS poll error: %s", e)

    _create_background_task(_rss_poll_loop(), "rss-feed-poller")

    # ── Pending delivery queue cleanup (every 10 min) ────────────────────
    from app.peer.connection_manager import pending_queue as _pq

    async def _pending_queue_cleanup():
        while True:
            await asyncio.sleep(600)
            try:
                removed = await _pq.cleanup()
                if removed > 0:
                    logger.debug("Pending queue cleanup: removed %d expired entries", removed)
            except Exception as e:
                logger.warning("Pending queue cleanup error: %s", e)

    _create_background_task(_pending_queue_cleanup(), "pending-queue-cleanup")

    # ── Edge cache + sealed push init ───────────────────────────────────
    try:
        from app.peer.edge_cache import edge_cache as _ec
        _ec.start()

        async def _edge_cache_cleanup():
            while True:
                await asyncio.sleep(3600)
                try:
                    expired = await _ec.cleanup_expired()
                    if expired > 0:
                        logger.debug("Edge cache cleanup: %d expired", expired)
                except Exception as e:
                    logger.warning("Edge cache cleanup error: %s", e)

        _create_background_task(_edge_cache_cleanup(), "edge-cache-cleanup")
    except Exception as e:
        logger.warning("Edge cache init: %s", e)

    try:
        from app.services.sealed_push import vapid
        vapid.load()
    except Exception as e:
        logger.debug("Sealed push init: %s", e)

    # ── Smart relay + store-and-forward ────────────────────────────────
    try:
        from app.transport.smart_relay import smart_relay as _sr
        _create_background_task(_sr.start(), "smart-relay")
    except Exception as e:
        logger.debug("Smart relay init: %s", e)

    try:
        from app.transport.store_forward import store_forward as _sf
        _create_background_task(_sf.start(), "store-forward")
    except Exception as e:
        logger.debug("Store-forward init: %s", e)

    # ── Blind Mailbox Protocol ────────────────────────────────────────
    try:
        from app.transport.blind_mailbox import start_bmp
        await start_bmp()
    except Exception as e:
        logger.debug("BMP init: %s", e)

    if _PROMETHEUS_AVAILABLE:
        _create_background_task(_metrics_update_loop(), "metrics-updater")

    # Start scheduled stream checker
    try:
        from app.chats.stream import start_schedule_checker
        start_schedule_checker()
    except Exception as e:
        logger.debug("Stream schedule checker init: %s", e)

    # ── Stealth transport startup ──────────────────────────────────────────
    try:
        from app.transport.auto_stealth import start_auto_stealth
        await start_auto_stealth()
    except Exception as e:
        logger.debug("Auto-stealth init: %s", e)

    try:
        from app.transport.advanced_stealth import advanced_stealth
        await advanced_stealth.start()
    except Exception as e:
        logger.debug("Advanced stealth init: %s", e)

    try:
        from app.transport.stealth_level3 import stealth_l3
        site_url = f"https://{Config.HOST}:{Config.PORT}" if hasattr(Config, "HOST") else ""
        await stealth_l3.start(site_url=site_url)
    except Exception as e:
        logger.debug("Stealth L3 init: %s", e)

    try:
        from app.transport.stealth_level4 import stealth_l4
        await stealth_l4.start()
    except Exception as e:
        logger.debug("Stealth L4 init: %s", e)

    # Start the migration pusher (Phase 6): watches for sustained overload and
    # proactively nudges connected users toward verified alternative nodes.
    try:
        from app.session.migration_pusher import pusher as _migration_pusher
        await _migration_pusher.start()
    except Exception as e:
        logger.debug("migration pusher start failed: %s", e)

    startup_duration = time.monotonic() - _startup_time
    logger.info("Vortex started in %.2fs (mode=%s, peers=%d)",
                startup_duration, Config.NETWORK_MODE, len(registry.active()))

    yield

    try:
        from app.session.migration_pusher import pusher as _migration_pusher
        await _migration_pusher.stop()
    except Exception as e:
        logger.debug("migration pusher stop failed: %s", e)


    # ── Graceful shutdown ────────────────────────────────────────────────
    ws_count = manager.total_connections()
    logger.info("Shutting down — closing %d WebSocket connections, cancelling %d tasks",
                ws_count, len(_background_tasks))

    # Close all active WebSocket connections gracefully
    try:
        await manager.close_all()
    except Exception as e:
        logger.warning("Error closing WebSocket connections: %s", e)

    # Cancel background tasks
    for task in _background_tasks:
        task.cancel()

    # Wait for tasks to finish (with timeout)
    if _background_tasks:
        await asyncio.gather(*_background_tasks, return_exceptions=True)
    _background_tasks.clear()

    # Stop trusted nodes monitor
    from app.federation.trusted_nodes import stop_federation_monitor
    await stop_federation_monitor()

    if Config.NETWORK_MODE == "global":
        from app.transport.global_transport import global_transport
        await global_transport.stop()

    # Stop Tor Hidden Service
    if Config.TOR_HIDDEN_SERVICE:
        from app.security.tor_hidden_service import tor_hidden_service
        await tor_hidden_service.stop()

    # Stop stealth transports
    try:
        from app.transport.auto_stealth import stop_auto_stealth
        await stop_auto_stealth()
    except Exception:
        pass
    try:
        from app.transport.advanced_stealth import advanced_stealth
        advanced_stealth.stop()
    except Exception:
        pass
    try:
        from app.transport.stealth_level3 import stealth_l3
        stealth_l3.stop()
    except Exception:
        pass
    try:
        from app.transport.stealth_level4 import stealth_l4
        stealth_l4.stop()
    except Exception:
        pass

    # Close Redis
    from app.peer.redis_pubsub import close_redis
    await close_redis()

    from app.keys.keys import stop_coturn
    stop_coturn()

    logger.info("Vortex stopped")


# ── App Instance ─────────────────────────────────────────────────────────────

from app.docs.openapi_config import get_openapi_config
_oapi = get_openapi_config()

app = FastAPI(
    title=_oapi["title"],
    description=_oapi["description"],
    version=_oapi["version"],
    contact=_oapi["contact"],
    license_info=_oapi["license_info"],
    openapi_tags=_oapi["openapi_tags"],
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)


# ── Global Exception Handlers ────────────────────────────────────────────────

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Structured HTTP error responses."""
    logger.warning(
        "HTTP %d: %s %s — %s",
        exc.status_code, request.method, request.url.path, exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status": exc.status_code,
            "path": request.url.path,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Structured validation error responses."""
    errors = []
    for err in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in err.get("loc", [])),
            "message": err.get("msg", ""),
            "type": err.get("type", ""),
        })
    logger.warning(
        "Validation error: %s %s — %d errors",
        request.method, request.url.path, len(errors),
    )
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation error",
            "status": 422,
            "details": errors,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions — never expose internals."""
    logger.error(
        "Unhandled exception: %s %s — %s: %s",
        request.method, request.url.path,
        type(exc).__name__, exc,
        exc_info=True,
    )
    if _PROMETHEUS_AVAILABLE:
        DB_ERRORS.inc()
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "status": 500,
            "path": request.url.path,
        },
    )


# ── Correlation ID Middleware ─────────────────────────────────────────────────

@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Inject correlation ID for request tracing."""
    cid = request.headers.get("X-Request-ID", new_correlation_id())
    token = correlation_id.set(cid)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = cid
        return response
    finally:
        correlation_id.reset(token)


# ── Prometheus Metrics Middleware ─────────────────────────────────────────────

if _PROMETHEUS_AVAILABLE:
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        if request.url.path in ("/metrics", "/health", "/favicon.ico") \
                or request.url.path.startswith("/static/"):
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        # Normalize path to avoid high cardinality
        endpoint = request.url.path.split("?")[0]
        # Collapse numeric IDs: /api/rooms/123 → /api/rooms/{id}
        parts = endpoint.split("/")
        normalized = "/".join("{id}" if p.isdigit() else p for p in parts)

        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=normalized,
            status=response.status_code,
        ).inc()
        REQUEST_DURATION.labels(
            method=request.method,
            endpoint=normalized,
        ).observe(duration)

        return response


# ── Security Middleware Stack ─────────────────────────────────────────────────

waf_config = {
    "rate_limit_requests": Config.WAF_RATE_LIMIT_REQUESTS,
    "rate_limit_window": Config.WAF_RATE_LIMIT_WINDOW,
    "block_duration": Config.WAF_BLOCK_DURATION,
    "max_content_length": 10 * 1024 * 1024,
}
waf_engine = init_waf_engine(waf_config)

app.add_middleware(WAFMiddleware, waf_engine=waf_engine)
app.add_middleware(TokenRefreshMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
if is_stealth():
    app.add_middleware(StealthMiddleware)
    logger.info("🛡️ Stealth mode ENABLED — traffic camouflage active")


# ── Routers ──────────────────────────────────────────────────────────────────

app.include_router(keys_router)
app.include_router(resumable_router)
app.include_router(auth_router)
# On-chain premium subscription lookup (/api/premium/*) — reads Subscription
# PDA from Solana, caches 5 min. Safe to mount unconditionally; when no
# SOLANA_RPC_URL is configured the endpoints return "no subscription".
from app.security.premium_check import router as premium_router
app.include_router(premium_router)
app.include_router(session_router)
app.include_router(rooms_router)
app.include_router(chat_router)
app.include_router(peers_router)
app.include_router(waf_router)
app.include_router(contacts_router)
app.include_router(contact_sync_router)
app.include_router(block_router)
app.include_router(search_router)
app.include_router(messages_search_router)
app.include_router(dm_router)
app.include_router(channels_router)
app.include_router(channel_feeds_router)
app.include_router(statuses_router)
app.include_router(saved_router)
app.include_router(tasks_router)
app.include_router(link_preview_router)
app.include_router(stickers_router)
app.include_router(saved_gifs_router)
app.include_router(bmp_push_router)
app.include_router(voice_router)
app.include_router(voice_ws_router)
app.include_router(federation_router)
app.include_router(fed_ws_router)
app.include_router(replication_router)
app.include_router(trusted_nodes_router)
app.include_router(zk_router)
app.include_router(bots_router)
app.include_router(ide_router)
app.include_router(ide_bot_call_router)
app.include_router(ide_federated_router)
app.include_router(ide_webhook_router)
app.include_router(reports_router)

from app.chats.translate import router as translate_router
app.include_router(translate_router)

from app.chats.bridge import router as bridge_router
app.include_router(bridge_router)

from app.chats.ai_assistant import router as ai_router
app.include_router(ai_router)

from app.chats.tipping import router as tipping_router
app.include_router(tipping_router)

from app.security.panic import router as panic_router
app.include_router(panic_router)

from app.transport.blind_mailbox import router as bmp_router
app.include_router(bmp_router)

from app.chats.calls import router as calls_router
app.include_router(calls_router)

from app.chats.group_calls import router as group_calls_router
app.include_router(group_calls_router)

from app.chats.sfu import router as sfu_router
app.include_router(sfu_router)

from app.chats.stream import router as stream_router, ws_router as stream_ws_router
app.include_router(stream_router)
app.include_router(stream_ws_router)

from app.security.key_backup import router as key_backup_router
app.include_router(key_backup_router)

from app.chats.stories import router as stories_router
app.include_router(stories_router)

from app.push.web_push import router as push_router
app.include_router(push_router)

from app.keys.prekeys import router as prekeys_router
app.include_router(prekeys_router)

# ── Bots Advanced (inline, keyboards, components, slash, webhooks, payments, store, scopes)
from app.bots.bot_advanced import router as bots_adv_router
app.include_router(bots_adv_router)

# ── Groups (Topics, Forum, Permissions, AutoMod, Slowmode) ───────────
from app.chats.groups import router as groups_router
app.include_router(groups_router)

# ── Spaces Advanced (nested, onboarding, discovery, audit, emoji, vanity, templates)
# Must be included BEFORE spaces_router so literal paths (/templates, /discover)
# take precedence over the /{space_id} pattern route in spaces_router.
from app.chats.spaces_advanced import router as spaces_adv_router
app.include_router(spaces_adv_router)
app.include_router(spaces_router)

# ── Files Advanced (distributed storage, gallery, search, compression) ─
from app.files.files_advanced import router as files_adv_router
app.include_router(files_adv_router)

# ── Post-Quantum Crypto (Kyber-768 hybrid) ────────────────────────────
from app.security.post_quantum import get_pq_status

@app.get("/api/crypto/pq-status", include_in_schema=True, tags=["crypto"])
async def pq_status():
    """Post-quantum cryptography subsystem status."""
    return get_pq_status()

# ── Privacy (Tor, ephemeral IDs, ZK membership, metadata padding) ─────
from app.security.privacy_routes import router as privacy_router
app.include_router(privacy_router)

# ── Native Bridge (Capacitor, UnifiedPush, biometric) ────────────────
from app.services.native_bridge import router as native_bridge_router
app.include_router(native_bridge_router)

# ── Warrant Canary (cryptographically signed) ────────────────────────
from app.security.canary import router as canary_router
app.include_router(canary_router)

# ── GDPR Compliance (export, erase, portability, rights) ─────────────
from app.security.gdpr import router as gdpr_router
app.include_router(gdpr_router)

# ── SSE транспорт (альтернатива WebSocket, неотличим от HTTP/2) ───────
from app.transport.sse_transport import router as sse_router
app.include_router(sse_router)

# ── Pluggable transports (obfs4, domain fronting, bridges, stego, tunnel) ──
from app.transport.pluggable_routes import router as pluggable_router
app.include_router(pluggable_router)

# Configure transport manager
from app.transport.pluggable import transport_manager
transport_manager.configure({
    "cdn_relay_url": Config.CDN_RELAY_URL,
    "shadowsocks_password": os.getenv("SHADOWSOCKS_PASSWORD", ""),
})

# ── Global routes: always register so auth-protected endpoints exist ───
# Global routes are always registered (regardless of NETWORK_MODE) so that
# auth-protected endpoints (/api/global/peers, /api/global/cdn-status, etc.)
# return 401 for unauthenticated access rather than 404.
from app.transport.global_routes import router as global_router
app.include_router(global_router)

# ── NAT Traversal & Transport signaling (ICE candidates, hole punching, BLE, Wi-Fi Direct) ──
from app.transport.routes import router as transport_router
app.include_router(transport_router)

# ── Cover-traffic pages (always available) ─────────────────────────────
from app.transport.cover_traffic import router as cover_router
app.include_router(cover_router)
if Config.NETWORK_MODE == "global":
    logger.info("Global mode: gossip + cover routes enabled")

# ── Obfuscation middleware (cover-заголовки + padding ко всем ответам) ────
if Config.OBFUSCATION_ENABLED:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request as StarletteRequest
    from starlette.responses import Response as StarletteResponse
    from app.transport.obfuscation import TrafficObfuscator
    from app.transport.auto_stealth import add_response_padding

    class ObfuscationMiddleware(BaseHTTPMiddleware):
        """Добавляет cover HTTP-заголовки, padding, probe detection ко всем ответам."""
        async def dispatch(self, request: StarletteRequest, call_next):
            # Active probe detection: если зонд — отдаём cover site
            try:
                from app.transport.stealth_level3 import stealth_l3
                req_info = {
                    "ip": request.client.host if request.client else "",
                    "headers": dict(request.headers),
                    "path": request.url.path,
                    "method": request.method,
                }
                is_probe, reason = stealth_l3.probe_detector.is_probe(req_info)
                if is_probe:
                    from app.transport.cover_traffic import COVER_PAGES
                    from fastapi.responses import HTMLResponse
                    html = COVER_PAGES.get(request.url.path, COVER_PAGES["/"])
                    return HTMLResponse(html, headers={"Server": "nginx/1.24.0"})
            except Exception:
                pass

            response: StarletteResponse = await call_next(request)
            for k, v in TrafficObfuscator.get_cover_headers().items():
                response.headers[k] = v
            add_response_padding(response.headers)
            return response

    app.add_middleware(ObfuscationMiddleware)
    logger.info("Obfuscation middleware enabled (all modes)")

## Stealth startup/shutdown moved to lifespan (above)


# ── Static Files ─────────────────────────────────────────────────────────────

if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
    if os.path.isdir("static/js"):
        app.mount("/js", StaticFiles(directory="static/js"), name="js")

if os.path.isdir("logo"):
    app.mount("/logo", StaticFiles(directory="logo"), name="logo")

os.makedirs("uploads/avatars", exist_ok=True)
os.makedirs("uploads/room_avatars", exist_ok=True)
os.makedirs("uploads/space_avatars", exist_ok=True)
os.makedirs("uploads/stickers", exist_ok=True)
os.makedirs("uploads/saved_gifs", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# ── Routes ───────────────────────────────────────────────────────────────────

from fastapi.templating import Jinja2Templates
_templates = Jinja2Templates(directory="templates")

@app.get("/", include_in_schema=False)
async def root(request: Request):
    csrf = request.cookies.get("csrf_token", "")
    return _templates.TemplateResponse(request, "base.html", {
        "csrf_token": csrf,
        "registration_mode": Config.REGISTRATION_MODE,
    })


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.ico", media_type="image/x-icon")


@app.get("/service-worker.js", include_in_schema=False)
async def service_worker():
    return FileResponse(
        "static/js/service-worker.js",
        headers={
            "Service-Worker-Allowed": "/",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Content-Type": "application/javascript",
        },
    )


@app.get("/manifest.json", include_in_schema=False)
async def manifest():
    return FileResponse(
        "static/manifest.json",
        headers={"Content-Type": "application/manifest+json"},
    )


@app.get("/v1/integrity")
async def v1_integrity_probe():
    """Client-bootstrap probe — iOS/Android Bootstrap modules hit
    `<base>/v1/integrity` and look for `status: "verified"` before they
    allow auth calls. In full deployments the controller serves this
    path (on a separate port); in a single-process dev setup the node
    can answer for itself with a static OK."""
    return {"status": "verified", "version": "0.1.0-dev"}


@app.get("/health")
async def health():
    """Liveness probe — basic health status."""
    # Stealth mode: return minimal info (handled by StealthMiddleware returning 404,
    # but if called internally we still limit exposure)
    if is_stealth():
        return {"status": "ok"}

    from app.database import get_engine_info
    from app.peer.redis_pubsub import is_redis_available, get_instance_id
    result = {
        "status": "ok",
        "version": "1.0.0",
        "instance_id": get_instance_id() or "single",
        "crypto_backend": "rust" if rust_available() else "python",
        "key_exchange": "X25519+Kyber768+HKDF-SHA256" if get_pq_status()["available"] else "X25519+HKDF-SHA256",
        "post_quantum": get_pq_status()["backend"],
        "encryption": "AES-256-GCM",
        "password_hash": "Argon2id",
        "authentication": "JWT-HS256",
        "federation": "enabled",
        "database": get_engine_info(),
        "redis": "connected" if is_redis_available() else "disabled",
        "scaling": "horizontal" if is_redis_available() else "single-node",
        "network_mode": Config.NETWORK_MODE,
        "active_peers": len(registry.active()),
        "ws_connections": manager.total_connections(),
        "own_ip": registry.own_ip,
        "uptime_seconds": round(time.monotonic() - _startup_time, 1) if _startup_time else 0,
        "ephemeral":   bool(os.getenv("EPHEMERAL_MODE", "").lower() in ("1","true","yes")),
        "metadata_padding": bool(getattr(Config, "METADATA_PADDING", True)),
    }
    if Config.NETWORK_MODE == "global":
        from app.transport.global_transport import global_transport
        result["global_peers"] = global_transport.peer_count()
        result["obfuscation"] = Config.OBFUSCATION_ENABLED
    return result


@app.get("/health/ready")
async def readiness():
    """Readiness probe — checks all critical subsystems."""
    from app.database import SessionLocal
    checks = {}
    all_ok = True

    # Database
    try:
        db = SessionLocal()
        try:
            from sqlalchemy import text
            db.execute(text("SELECT 1"))
            checks["database"] = "ok"
        finally:
            db.close()
    except Exception as e:
        checks["database"] = f"error: {e}"
        all_ok = False

    # Upload directory writable
    try:
        test_path = Config.UPLOAD_DIR / ".healthcheck"
        test_path.write_text("ok")
        test_path.unlink()
        checks["uploads_dir"] = "ok"
    except Exception as e:
        checks["uploads_dir"] = f"error: {e}"
        all_ok = False

    # Keys directory accessible
    checks["keys_dir"] = "ok" if Config.KEYS_DIR.exists() else "missing"
    if checks["keys_dir"] != "ok":
        all_ok = False

    # Background tasks alive
    alive_tasks = sum(1 for t in _background_tasks if not t.done())
    checks["background_tasks"] = f"{alive_tasks}/{len(_background_tasks)} alive"
    if alive_tasks == 0 and len(_background_tasks) > 0:
        all_ok = False

    status = "ready" if all_ok else "degraded"
    code = 200 if all_ok else 503

    if not all_ok:
        logger.warning("Readiness check degraded: %s", checks)

    return JSONResponse(
        status_code=code,
        content={"status": status, **checks},
    )


# ── Prometheus Metrics Endpoint ──────────────────────────────────────────────

if _PROMETHEUS_AVAILABLE:
    from starlette.responses import Response

    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        """Prometheus metrics endpoint."""
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=Config.HOST,
        port=Config.PORT,
        reload=False,
        log_level="info",
        access_log=False,
    )
