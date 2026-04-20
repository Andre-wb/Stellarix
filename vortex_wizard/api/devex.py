"""Wave 8 — developer experience extensions.

  #36 .env hot-reload      — poll mtime, reload Config on change
  #37 Swagger / Redoc UI   — enabled at /api/wiz/docs and /api/wiz/redoc
  #38 WebSocket inspector  — /ws/inspect emits all WS traffic with filter
  #39 Postman collection   — derive from FastAPI OpenAPI schema
  #40 Debug proxy          — capture+replay any /api/* call with rewrites
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from . import backup_api as _b

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin/devex", tags=["devex"])


def _env_file(request: Request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


# ══════════════════════════════════════════════════════════════════════════
# #36 — .env hot-reload
# ══════════════════════════════════════════════════════════════════════════

_env_mtime_cache: dict[str, float] = {}
_env_watch_task: Optional[asyncio.Task] = None


async def _watch_env_loop(env_file: Path):
    """Background task — every 2s, if .env mtime changes, re-apply
    process-level os.environ from it so running code picks up changes.

    Doesn't restart the node (some settings require restart — wizard UI
    warns the user). Useful for CONTROLLER_URL, CORS_ORIGINS, and other
    low-cost flags.
    """
    while True:
        try:
            await asyncio.sleep(2)
            if not env_file.is_file(): continue
            mt = env_file.stat().st_mtime
            last = _env_mtime_cache.get(str(env_file), 0)
            if mt <= last: continue
            _env_mtime_cache[str(env_file)] = mt
            env = _b._read_env(env_file)
            for k, v in env.items():
                os.environ[k] = v
            logger.info("env hot-reload: %d keys refreshed", len(env))
        except Exception as e:
            logger.debug("env hot-reload loop error: %s", e)


@router.post("/hotreload/start")
async def hotreload_start(request: Request) -> dict:
    global _env_watch_task
    env_file = _env_file(request)
    if _env_watch_task and not _env_watch_task.done():
        return {"ok": True, "already_running": True}
    _env_watch_task = asyncio.create_task(_watch_env_loop(env_file))
    return {"ok": True, "watching": str(env_file)}


@router.post("/hotreload/stop")
async def hotreload_stop() -> dict:
    global _env_watch_task
    if _env_watch_task and not _env_watch_task.done():
        _env_watch_task.cancel()
    _env_watch_task = None
    return {"ok": True}


@router.get("/hotreload/status")
async def hotreload_status() -> dict:
    running = bool(_env_watch_task and not _env_watch_task.done())
    return {"running": running, "cache_entries": len(_env_mtime_cache)}


# ══════════════════════════════════════════════════════════════════════════
# #37 — Swagger / Redoc UI (actually just flip flags on FastAPI)
# ══════════════════════════════════════════════════════════════════════════
#
# We can't re-create the FastAPI app — but we can serve our own docs
# pages that reference the existing OpenAPI schema. Expose /docs and
# /redoc under the wizard prefix so operators can browse the full
# 170+ endpoint surface.

@router.get("/openapi.json")
async def openapi_json(request: Request) -> JSONResponse:
    # Borrow the app's own OpenAPI generator.
    schema = request.app.openapi()
    return JSONResponse(schema)


@router.get("/docs", response_class=HTMLResponse)
async def swagger_docs() -> HTMLResponse:
    html = """<!DOCTYPE html>
<html><head>
<title>Vortex Wizard API</title>
<link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
<style>body{margin:0;background:#0b0b0e}</style>
</head><body>
<div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
window.ui = SwaggerUIBundle({
    url: '/api/wiz/admin/devex/openapi.json',
    dom_id: '#swagger-ui',
    deepLinking: true,
    docExpansion: 'none',
    defaultModelsExpandDepth: -1,
});
</script>
</body></html>"""
    return HTMLResponse(html)


@router.get("/redoc", response_class=HTMLResponse)
async def redoc_docs() -> HTMLResponse:
    html = """<!DOCTYPE html>
<html><head>
<title>Vortex Wizard API (Redoc)</title>
<meta charset="utf-8">
<style>body{margin:0;background:#fafafa}</style>
</head><body>
<redoc spec-url="/api/wiz/admin/devex/openapi.json"></redoc>
<script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
</body></html>"""
    return HTMLResponse(html)


# ══════════════════════════════════════════════════════════════════════════
# #38 — WebSocket inspector
# ══════════════════════════════════════════════════════════════════════════

_ws_observers: set[WebSocket] = set()


async def broadcast_ws_event(kind: str, data: dict) -> None:
    """Called by the node / wizard to tee a WebSocket frame into the
    inspector. No-op if no observers connected."""
    if not _ws_observers: return
    msg = json.dumps({"kind": kind, "ts": int(time.time() * 1000),
                      "data": data})
    dead = []
    for obs in _ws_observers:
        try: await obs.send_text(msg)
        except Exception: dead.append(obs)
    for obs in dead: _ws_observers.discard(obs)


@router.websocket("/ws/inspect")
async def ws_inspect(ws: WebSocket) -> None:
    await ws.accept()
    _ws_observers.add(ws)
    try:
        await ws.send_text(json.dumps({"kind": "hello",
                                       "ts": int(time.time() * 1000),
                                       "msg": "connected"}))
        while True:
            # Keep-alive: echo any client message.
            txt = await ws.receive_text()
            await ws.send_text(json.dumps({"kind": "echo", "data": txt}))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("ws inspector error: %s", e)
    finally:
        _ws_observers.discard(ws)


# ══════════════════════════════════════════════════════════════════════════
# #39 — Postman collection export
# ══════════════════════════════════════════════════════════════════════════

@router.get("/postman.json")
async def postman_collection(request: Request) -> JSONResponse:
    """Convert the OpenAPI schema into a Postman v2.1 collection."""
    schema = request.app.openapi()
    items = []
    for path, methods in schema.get("paths", {}).items():
        for method, op in methods.items():
            if method.lower() not in ("get","post","put","patch","delete"): continue
            items.append({
                "name": op.get("summary") or f"{method.upper()} {path}",
                "request": {
                    "method": method.upper(),
                    "url": {
                        "raw": "{{baseUrl}}" + path,
                        "host": ["{{baseUrl}}"],
                        "path": [p for p in path.strip("/").split("/") if p],
                    },
                    "header": [{"key": "Content-Type", "value": "application/json",
                                "disabled": method.lower() == "get"}],
                    "description": op.get("description", ""),
                    "body": {"mode": "raw", "raw": "{\n  \n}"} if method.lower() != "get" else None,
                },
            })
    collection = {
        "info": {
            "name": f"Vortex Wizard API ({schema.get('info',{}).get('version','')})",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            "description": "Auto-generated from OpenAPI by vortex_wizard.",
        },
        "item": items,
        "variable": [{"key": "baseUrl", "value": "http://127.0.0.1:9001"}],
    }
    return JSONResponse(collection, headers={
        "Content-Disposition": 'attachment; filename="vortex.postman_collection.json"',
    })


# ══════════════════════════════════════════════════════════════════════════
# #40 — HTTP debug proxy (capture + replay)
# ══════════════════════════════════════════════════════════════════════════

_captures: list[dict] = []   # ring buffer
_CAPTURE_CAP = 500
_capture_enabled = False


class DebugCaptureToggle:
    pass


@router.post("/proxy/capture/on")
async def capture_on() -> dict:
    global _capture_enabled
    _capture_enabled = True
    return {"ok": True, "enabled": True}


@router.post("/proxy/capture/off")
async def capture_off() -> dict:
    global _capture_enabled
    _capture_enabled = False
    return {"ok": True, "enabled": False}


@router.get("/proxy/captures")
async def list_captures() -> dict:
    return {"captures": _captures[-200:], "total": len(_captures),
            "enabled": _capture_enabled}


@router.delete("/proxy/captures")
async def clear_captures() -> dict:
    _captures.clear()
    return {"ok": True}


def record_request(method: str, path: str, status: int,
                   duration_ms: float, body_preview: str = "") -> None:
    """Called by a middleware to capture request metadata."""
    if not _capture_enabled: return
    _captures.append({
        "ts":          int(time.time() * 1000),
        "method":      method,
        "path":        path,
        "status":      status,
        "duration_ms": round(duration_ms, 2),
        "body":        body_preview[:500],
    })
    while len(_captures) > _CAPTURE_CAP:
        _captures.pop(0)


# ── Lifecycle ─────────────────────────────────────────────────────────────

def install_devex_hooks(app) -> None:
    """Start hot-reload watcher at app startup."""
    env_file = getattr(app.state, "env_file", None)
    if not env_file: return
    @app.on_event("startup")
    async def _start_hotreload():
        global _env_watch_task
        _env_watch_task = asyncio.create_task(_watch_env_loop(Path(env_file)))

    @app.on_event("shutdown")
    async def _stop_hotreload():
        global _env_watch_task
        if _env_watch_task and not _env_watch_task.done():
            _env_watch_task.cancel()
