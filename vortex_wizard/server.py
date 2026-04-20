"""Internal FastAPI app that powers the Wizard UI.

Serves two SPAs:
    /           — setup wizard (when mode=="setup")
    /           — admin dashboard (when mode=="admin")

Plus a small set of /api/wiz/* endpoints for data the UI needs. Every
endpoint is loopback-only (server binds 127.0.0.1) — no network exposure.
"""
from __future__ import annotations

import contextlib
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import VERSION
from .api import setup_api, admin_api, db_api, backup_api, audit, metrics, profiler, logs_tools, ops_jobs, security_api, seed_tools, peer_tools, advanced_net, db_tools, multidevice, onboarding, operator, settings_api, ai_setup, deploy_gen, alerts, monitoring, db_ops, peer_advanced, secrets_mgr, backup_plus, devex, supervisor, hardware
from .api.audit import AuditMiddleware
from .api.profiler import ProfilerMiddleware
from .api.security_api import TOTPMiddleware

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent / "web"


def build_app(mode: str, env_file: "Path | None" = None) -> FastAPI:
    if mode not in ("setup", "admin"):
        raise ValueError(f"invalid mode: {mode!r}")

    app = FastAPI(
        title="Vortex Wizard",
        version=VERSION,
        docs_url=None, redoc_url=None, openapi_url=None,
    )
    app.state.mode = mode
    # Where to read/write the Vortex env file — set once here so both
    # setup_api and admin_api pick it up via request.app.state.env_file.
    app.state.env_file = (env_file or Path(".env")).expanduser().resolve()
    logger.info("Wizard env file: %s", app.state.env_file)

    # Both APIs are always mounted so either SPA can call either endpoint
    # during its lifetime (e.g. an admin user reconfiguring, or a setup flow
    # reading the current system before writing).
    app.include_router(setup_api.router)
    app.include_router(admin_api.router)
    app.include_router(db_api.router)
    app.include_router(backup_api.router)
    app.include_router(audit.router)
    app.include_router(metrics.router)
    app.include_router(profiler.router)
    app.include_router(logs_tools.router)
    app.include_router(ops_jobs.router)
    app.include_router(security_api.router)
    app.include_router(seed_tools.router)
    app.include_router(peer_tools.router)
    app.include_router(advanced_net.router)
    app.include_router(db_tools.router)
    app.include_router(multidevice.router)
    app.include_router(onboarding.router)
    app.include_router(operator.router)
    app.include_router(settings_api.router)
    app.include_router(ai_setup.router)
    app.include_router(deploy_gen.router)
    app.include_router(alerts.router)
    app.include_router(monitoring.router)
    app.include_router(db_ops.router)
    app.include_router(peer_advanced.router)
    app.include_router(secrets_mgr.router)
    app.include_router(backup_plus.router)
    app.include_router(devex.router)
    devex.install_devex_hooks(app)
    app.include_router(supervisor.router)
    app.include_router(hardware.router)

    @app.on_event("startup")
    async def _start_scheduler():
        # Register default jobs and kick the loop. The scheduler is a
        # singleton per wizard process; its state is persisted to the
        # env dir so a restart doesn't double-fire anything.
        try:
            ops_jobs.install_default_jobs(app.state.env_file)
        except Exception as e:
            logger.warning("scheduler init failed: %s", e)

    @app.on_event("shutdown")
    async def _stop_scheduler():
        try:
            from .api.scheduler import get as _getsched
            await _getsched(app.state.env_file).stop()
        except Exception:
            pass

    # Audit middleware runs after routers are registered so it sees every
    # admin call (including the ones the wizard itself triggers from the
    # sidebar). Installed with add_middleware so it sits at the outermost
    # layer and can observe both 4xx/5xx and late exceptions.
    app.add_middleware(AuditMiddleware)
    app.add_middleware(ProfilerMiddleware)
    # TOTP is outermost so a missing 2FA cookie short-circuits before we
    # spend any work on downstream handlers.
    app.add_middleware(TOTPMiddleware)

    # Shared static assets (common.css, fonts, icons, locales)
    assets_dir = WEB_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(assets_dir)), name="static")

    locales_dir = WEB_DIR / "locales"
    if locales_dir.is_dir():
        app.mount("/locales", StaticFiles(directory=str(locales_dir)), name="locales")

    # Force browsers to revalidate /static/ on every reload. Without this
    # JS/CSS changes ship with a new wizard release but users keep seeing
    # the old cached version — which shows up as "my click does nothing"
    # (old handler code), stale integrity timestamps, etc.
    # "no-cache" != "no-store": the file IS still kept in the HTTP cache,
    # but every request hits the server with If-Modified-Since. Unchanged
    # files return 304 (~1 KB roundtrip), changed files return 200 with
    # the new payload.
    @app.middleware("http")
    async def _no_cache_static(request, call_next):
        resp = await call_next(request)
        if request.url.path.startswith("/static/") or \
           request.url.path.startswith("/locales/"):
            resp.headers["Cache-Control"] = "no-cache, must-revalidate"
        return resp

    def _current_mode() -> str:
        """Pick mode per-request, derived from the env file's state.

        The ``NODE_INITIALIZED=true`` marker is the single source of
        truth: present → admin UI, absent → setup UI. This is symmetric,
        so the admin "Reset" action (which deletes the env file) flips
        us back to setup without a restart.
        """
        ef = app.state.env_file
        if not ef.is_file():
            return "setup"
        try:
            for line in ef.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s.startswith("NODE_INITIALIZED="):
                    val = s.split("=", 1)[1].strip().lower()
                    if val in ("true", "1", "yes"):
                        return "admin"
        except OSError:
            pass
        return "setup"

    @app.get("/mode", include_in_schema=False)
    async def _mode_info():
        return {"mode": _current_mode(), "version": VERSION}

    # Index pages must never be cached — if the browser holds onto the
    # old setup/index.html after setup completes, the user sees the
    # wizard welcome again even though NODE_INITIALIZED=true is set.
    _NO_CACHE_HEADERS = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma":        "no-cache",
        "Expires":       "0",
    }

    @app.get("/{path:path}", include_in_schema=False)
    async def _spa(path: str):
        """SPA catch-all: serve static files from the *current* mode's dir."""
        cur = _current_mode()
        spa_dir = WEB_DIR / cur
        index_path = spa_dir / "index.html"
        target = spa_dir / path
        if path and target.is_file():
            # Static assets (CSS/JS/PNG) — let them be cached normally;
            # they're versioned by filename when they need to change.
            return FileResponse(target)
        # Index HTML: never cache, so mode flips become visible immediately.
        return FileResponse(index_path, headers=_NO_CACHE_HEADERS)

    return app
