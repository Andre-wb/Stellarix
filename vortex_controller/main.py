"""Vortex Controller — FastAPI entry point.

Run:
    cd vortex_controller
    python -m vortex_controller.main

Environment variables:
    CONTROLLER_HOST       bind host (default 0.0.0.0)
    CONTROLLER_PORT       bind port (default 8800)
    CONTROLLER_KEYS_DIR   keypair directory (default keys/)
    AUTO_APPROVE          auto-approve registering nodes (default true)
    ENTRY_URLS            comma-separated bootstrap entry URLs

    DATABASE_URL          full SQLAlchemy URL (PostgreSQL preferred):
                          postgresql://user:pw@host:5432/vortex_controller
    POSTGRES_HOST         PostgreSQL host (alternative to DATABASE_URL)
    POSTGRES_PORT         PostgreSQL port (default 5432)
    POSTGRES_USER         PostgreSQL user (default vortex)
    POSTGRES_DB           PostgreSQL database (default vortex_controller)
    POSTGRES_PASSWORD     PostgreSQL password
    CONTROLLER_DB         SQLite path if no PostgreSQL configured (default controller.db)
"""
from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import VERSION
from .controller_crypto import ControllerKey
from .endpoints import admin as admin_ep
from .endpoints import backup as backup_ep
from .endpoints import entries as entries_ep
from .endpoints import health as health_ep
from .endpoints import integrity as integrity_ep
from .endpoints import mirrors as mirrors_ep
from .endpoints import nodes as nodes_ep
from .endpoints import register as register_ep
from .integrity.verify import verify_at_startup
from .integrity_gate import IntegrityGateMiddleware
from .mirror_health import MirrorHealthChecker, load_tor_socks_from_env
from .storage import Storage, resolve_database_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("vortex_controller")


def _parse_entry_urls(raw: str) -> list[str]:
    return [u.strip() for u in raw.split(",") if u.strip()]


def _log_integrity(report) -> None:
    """Pretty-print the integrity report with the right log level."""
    status = report.status
    if status == "verified":
        logger.info("✅ Integrity: %s", report.message)
    elif status == "no_manifest":
        logger.warning("ℹ️  Integrity: %s", report.message)
    else:
        logger.error("⚠️  Integrity FAILED (%s): %s", status, report.message)
        if report.mismatched:
            logger.error("   Modified files: %s", ", ".join(report.mismatched[:5]))
        if report.missing:
            logger.error("   Missing files: %s", ", ".join(report.missing[:5]))


def create_app(
    keys_dir: Path,
    auto_approve: bool,
    entry_urls: list[str],
    mirror_urls: Optional[list[str]] = None,
    db_url: Optional[str] = None,
    treasury_pubkey: str = "",
    admin_token: str = "",
) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        # 1. Code integrity check — do this BEFORE loading any per-deployment
        #    key material, so the report is available even if a subsequent
        #    step fails.
        import os
        controller_root = Path(__file__).parent
        report = verify_at_startup(root=controller_root)
        app.state.integrity = report
        _log_integrity(report)
        if report.status in ("tampered", "bad_signature", "wrong_key") and \
                os.getenv("INTEGRITY_STRICT", "false").lower() in ("1", "true", "yes"):
            logger.error("INTEGRITY_STRICT is set and verification failed — refusing to start")
            raise SystemExit(2)

        app.state.storage = Storage(db_url)
        await app.state.storage.init_schema()
        app.state.controller_key = ControllerKey.load_or_create(keys_dir)
        app.state.auto_approve = auto_approve
        app.state.entry_urls = entry_urls
        app.state.mirror_urls = mirror_urls or []
        app.state.treasury_pubkey = treasury_pubkey
        app.state.admin_token = admin_token
        app.state.mirror_health = MirrorHealthChecker(
            urls=app.state.mirror_urls,
            tor_socks=load_tor_socks_from_env(),
        )
        logger.info("Controller pubkey: %s", app.state.controller_key.pubkey_hex())
        logger.info("Auto-approve: %s", auto_approve)
        logger.info("Entry URLs: %d configured", len(entry_urls))
        logger.info("Mirror URLs: %d configured", len(app.state.mirror_urls))
        await app.state.mirror_health.start()
        try:
            yield
        finally:
            await app.state.mirror_health.stop()
            await app.state.storage.close()

    app = FastAPI(
        title="Vortex Controller",
        version=VERSION,
        description="Discovery/registry control plane for Vortex nodes",
        lifespan=lifespan,
    )

    # Integrity gate must be the outermost middleware so failing builds can't
    # reach any endpoint (including any future ones) that isn't explicitly
    # whitelisted.
    app.add_middleware(IntegrityGateMiddleware)

    app.include_router(register_ep.router)
    app.include_router(nodes_ep.router)
    app.include_router(entries_ep.router)
    app.include_router(mirrors_ep.router)
    app.include_router(integrity_ep.router)
    app.include_router(health_ep.router)
    app.include_router(admin_ep.router)
    app.include_router(backup_ep.router)

    # Static website — multi-page
    web_dir = Path(__file__).parent / "web"
    if web_dir.is_dir():
        # Each top-level page is its own HTML file; the root "/" redirects
        # to index.html. Everything else under /static/* and /locales/* is
        # served as raw assets.
        PAGES = {
            "/":         "index.html",
            "/nodes":    "nodes.html",
            "/entries":  "entries.html",
            "/mirrors":  "mirrors.html",
            "/security": "security.html",
            # Platform-owner revenue dashboard. The HTML is public (no
            # secrets in it) but every data fetch goes through a bearer-
            # token guarded endpoint; the page renders a token-prompt
            # when it isn't authenticated yet.
            "/admin":    "admin.html",
        }

        def _make_page_handler(path_: str):
            file_name = PAGES[path_]
            async def _handler() -> FileResponse:
                return FileResponse(web_dir / file_name)
            return _handler

        for path_, _ in PAGES.items():
            app.add_api_route(
                path_, _make_page_handler(path_),
                methods=["GET"], include_in_schema=False,
            )

        @app.get("/favicon.ico", include_in_schema=False)
        async def _favicon() -> FileResponse:
            return FileResponse(web_dir / "favicon.ico")

        @app.get("/INTEGRITY.sig.json", include_in_schema=False)
        async def _integrity_bundle():
            """Serve the raw signed manifest for Phase 7C cross-verification."""
            manifest_path = Path(__file__).resolve().parent.parent / "INTEGRITY.sig.json"
            if not manifest_path.is_file():
                from fastapi import HTTPException
                raise HTTPException(404, "manifest not available")
            return FileResponse(
                manifest_path,
                media_type="application/json",
                headers={"Cache-Control": "no-store"},
            )

        # /static/<file> — css, js, images
        assets_dir = web_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/static", StaticFiles(directory=str(assets_dir)), name="web_static")
        else:
            app.mount("/static", StaticFiles(directory=str(web_dir)), name="web_static")

        # Locale JSONs
        app.mount(
            "/locales",
            StaticFiles(directory=str(web_dir / "locales")),
            name="locales",
        )

    return app


def main() -> None:
    host = os.getenv("CONTROLLER_HOST", "0.0.0.0")
    port = int(os.getenv("CONTROLLER_PORT", "8800"))
    keys_dir = Path(os.getenv("CONTROLLER_KEYS_DIR", "keys"))
    auto_approve = os.getenv("AUTO_APPROVE", "true").lower() in ("1", "true", "yes")
    entry_urls = _parse_entry_urls(os.getenv("ENTRY_URLS", ""))
    mirror_urls = _parse_entry_urls(os.getenv("MIRROR_URLS", ""))

    # Solana wallet that receives register fees + treasury cut of premium
    # subscriptions. Default points at the SNS owner of vortexx.sol —
    # override via TREASURY_PUBKEY for forks/test deployments.
    treasury_pubkey = os.getenv(
        "TREASURY_PUBKEY",
        "5ABkkipTZZEEPNR3cP4MCzftpAhqv6jvM4UTSLPGt5Qq",
    ).strip()
    admin_token = os.getenv("ADMIN_TOKEN", "").strip()

    app = create_app(
        keys_dir=keys_dir,
        auto_approve=auto_approve,
        entry_urls=entry_urls,
        mirror_urls=mirror_urls,
        db_url=resolve_database_url(),
        treasury_pubkey=treasury_pubkey,
        admin_token=admin_token,
    )
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
