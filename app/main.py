"""
Vortex Chat — децентрализованный мессенджер.
X25519+AES-256-GCM, Argon2, WAF, CSRF, security headers.

v3: Добавлена федерация — вступление в комнаты других узлов без регистрации.
"""
from __future__ import annotations
import logging, os, socket
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.files.resumable import router as resumable_router, cleanup_sessions_loop
from app.config import Config
from app.database import init_db
from app.peer.peer_registry import start_discovery, registry
from app.peer.connection_manager import manager
from app.security.crypto import load_or_create_node_keypair, rust_available
from app.authentication.auth  import router as auth_router
from app.chats.rooms          import router as rooms_router
from app.chats.chat           import router as chat_router
from app.peer.peer_registry   import router as peers_router
from app.keys.keys            import router as keys_router
from app.federation.federation import router as federation_router, ws_router as fed_ws_router
from app.security.waf import WAFMiddleware, waf_router, init_waf_engine
from app.security.middleware import (
    SecurityHeadersMiddleware,
    LoggingMiddleware,
    CSRFMiddleware,
    TokenRefreshMiddleware,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Config.ensure_dirs()
    init_db()
    logger.info("✅ БД инициализирована")
    _, pub = load_or_create_node_keypair(Config.KEYS_DIR)
    logger.info(f"🔑 X25519 pubkey: {pub.hex()[:32]}...")
    if rust_available():
        import vortex_chat
        logger.info(f"🦀 Rust crypto: vortex_chat {vortex_chat.VERSION}")
    else:
        logger.warning("🐍 Python crypto fallback (компилируйте Rust для скорости)")

    name = Config.DEVICE_NAME or socket.gethostname()
    start_discovery(name)

    import asyncio
    asyncio.create_task(cleanup_sessions_loop())

    yield
    logger.info("⛔ Vortex остановлен")


app = FastAPI(
    title="Vortex Chat",
    description="100% децентрализованный мессенджер. X25519+AES-256-GCM, Argon2, WAF.",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
)

waf_config = {
    "rate_limit_requests": Config.WAF_RATE_LIMIT_REQUESTS,
    "rate_limit_window":   Config.WAF_RATE_LIMIT_WINDOW,
    "block_duration":      Config.WAF_BLOCK_DURATION,
    "max_content_length":  10 * 1024 * 1024,
}
waf_engine = init_waf_engine(waf_config)

app.add_middleware(WAFMiddleware, waf_engine=waf_engine)
app.add_middleware(TokenRefreshMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(keys_router)
app.include_router(resumable_router)
app.include_router(auth_router)
app.include_router(rooms_router)
app.include_router(chat_router)
app.include_router(peers_router)
app.include_router(waf_router)
app.include_router(federation_router)
app.include_router(fed_ws_router)

if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
    if os.path.isdir("static/js"):
        app.mount("/js", StaticFiles(directory="static/js"), name="js")


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse("templates/index.html")


@app.get('/service-worker.js', include_in_schema=False)
async def service_worker():
    return FileResponse(
        'static/js/service-worker.js',
        headers={
            'Service-Worker-Allowed': '/',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Content-Type': 'application/javascript',
        }
    )


@app.get('/manifest.json', include_in_schema=False)
async def manifest():
    return FileResponse(
        'static/manifest.json',
        headers={'Content-Type': 'application/manifest+json'}
    )


@app.get("/health")
async def health():
    return {
        "status":         "ok",
        "version":        "3.0.0",
        "crypto_backend": "rust" if rust_available() else "python",
        "key_exchange":   "X25519+HKDF-SHA256",
        "encryption":     "AES-256-GCM",
        "password_hash":  "Argon2id",
        "authentication": "JWT-HS256",
        "federation":     "enabled",
        "active_peers":   len(registry.active()),
        "ws_connections": manager.total_connections(),
        "own_ip":         registry.own_ip,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=Config.HOST,
        port=Config.PORT,
        reload=False,
        log_level="info",
        access_log=False,
    )