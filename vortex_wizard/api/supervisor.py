"""Wave 9 — multi-node supervisor + federation sync + rolling upgrade.

  #41 Supervisor mode — one wizard manages N remote nodes via their own
                         wizard APIs. Each "managed node" is a base URL +
                         ed25519 pubkey fingerprint.
  #42 Federation-wide settings sync — push a settings delta to every
                                       managed node in one call.
  #43 Rolling upgrade — upgrade managed nodes one-at-a-time with
                        health checks between steps.
  #4  Offline installer — ZIP containing node source + wheels + README.
  #5  Windows service — NSSM-style install script.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import zipfile
import io
from pathlib import Path
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field

from . import backup_api as _b
from . import security_api as _sec
from . import alerts as _alerts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin/super", tags=["supervisor"])


def _env_file(request: Request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


def _managed_path(env_file: Path) -> Path:
    return env_file.parent / "managed_nodes.json"


# ══════════════════════════════════════════════════════════════════════════
# #41 — Supervisor mode (managed nodes list)
# ══════════════════════════════════════════════════════════════════════════

class ManagedNodeBody(BaseModel):
    id:           Optional[str] = None
    label:        str = Field(..., min_length=1, max_length=60)
    base_url:     str = Field(..., min_length=8, max_length=512)
    pubkey:       str = Field(..., min_length=64, max_length=128, pattern=r"^[0-9a-fA-F]+$")
    auth_bearer:  Optional[str] = None
    tags:         list[str] = Field(default_factory=list)


@router.get("/nodes")
async def list_nodes(request: Request) -> dict:
    p = _managed_path(_env_file(request))
    if not p.is_file(): return {"nodes": []}
    try:
        nodes = json.loads(p.read_text()).get("nodes", [])
        # Mask bearer
        safe = []
        for n in nodes:
            c = dict(n)
            if c.get("auth_bearer"): c["auth_bearer"] = "•" * 10
            safe.append(c)
        return {"nodes": safe}
    except Exception: return {"nodes": []}


@router.post("/nodes")
async def add_node(body: ManagedNodeBody, request: Request) -> dict:
    env_file = _env_file(request)
    p = _managed_path(env_file)
    state = {"nodes": []}
    if p.is_file():
        try: state = json.loads(p.read_text())
        except Exception: pass
    import secrets as _s
    if body.id:
        for n in state["nodes"]:
            if n["id"] == body.id:
                n.update(body.model_dump(exclude_none=True))
                break
        else:
            raise HTTPException(404, "node id not found")
    else:
        entry = {**body.model_dump(exclude_none=True),
                 "id": _s.token_urlsafe(8), "added_at": int(time.time())}
        state["nodes"].append(entry)
    p.write_text(json.dumps(state, indent=2))
    return {"ok": True}


@router.delete("/nodes/{node_id}")
async def delete_node(node_id: str, request: Request) -> dict:
    env_file = _env_file(request)
    p = _managed_path(env_file)
    if not p.is_file(): return {"ok": True}
    state = json.loads(p.read_text())
    state["nodes"] = [n for n in state.get("nodes", []) if n["id"] != node_id]
    p.write_text(json.dumps(state, indent=2))
    return {"ok": True}


@router.get("/nodes/status")
async def aggregate_status(request: Request) -> dict:
    """Parallel /health probe across all managed nodes + local summary."""
    env_file = _env_file(request)
    p = _managed_path(env_file)
    if not p.is_file(): return {"nodes": []}
    nodes = json.loads(p.read_text()).get("nodes", [])

    async def _ping(n: dict) -> dict:
        base = n["base_url"].rstrip("/")
        headers = {}
        if n.get("auth_bearer"):
            headers["Authorization"] = f"Bearer {n['auth_bearer']}"
        try:
            async with httpx.AsyncClient(timeout=3.0, verify=False) as c:
                r = await c.get(base + "/health", headers=headers)
            if r.status_code == 200:
                d = r.json()
                return {"id": n["id"], "label": n["label"], "base_url": base,
                        "ok": True, "version": d.get("version"),
                        "uptime_seconds": d.get("uptime_seconds"),
                        "ws_connections": d.get("ws_connections")}
        except Exception as e:
            return {"id": n["id"], "label": n["label"], "base_url": base,
                    "ok": False, "error": f"{type(e).__name__}: {e}"}
        return {"id": n["id"], "label": n["label"], "base_url": base,
                "ok": False, "status": r.status_code}

    results = await asyncio.gather(*[_ping(n) for n in nodes])
    return {"nodes": results,
            "ok_count": sum(1 for r in results if r.get("ok"))}


# ══════════════════════════════════════════════════════════════════════════
# #42 — Federation-wide settings sync
# ══════════════════════════════════════════════════════════════════════════

class SyncBody(BaseModel):
    changes:      dict[str, str | bool | int]
    filter_tags:  list[str] = Field(default_factory=list,
                                    description="If set, only push to nodes with any matching tag")


@router.post("/sync")
async def sync_settings(body: SyncBody, request: Request) -> dict:
    env_file = _env_file(request)
    p = _managed_path(env_file)
    if not p.is_file(): raise HTTPException(400, "no managed nodes")
    nodes = json.loads(p.read_text()).get("nodes", [])
    if body.filter_tags:
        nodes = [n for n in nodes
                 if any(t in n.get("tags", []) for t in body.filter_tags)]

    async def _push(n: dict) -> tuple[str, str]:
        url = n["base_url"].rstrip("/") + "/api/wiz/admin/settings"
        headers = {"Content-Type": "application/json"}
        if n.get("auth_bearer"):
            headers["Authorization"] = f"Bearer {n['auth_bearer']}"
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=False) as c:
                r = await c.post(url, headers=headers,
                                  json={"changes": body.changes})
            if r.status_code < 400:
                return n["label"], "ok"
            return n["label"], f"http_{r.status_code}"
        except Exception as e:
            return n["label"], f"err:{type(e).__name__}"

    results = await asyncio.gather(*[_push(n) for n in nodes])
    return {
        "ok":            True,
        "pushed":        dict(results),
        "total_nodes":   len(nodes),
        "success_count": sum(1 for _, s in results if s == "ok"),
    }


# ══════════════════════════════════════════════════════════════════════════
# #43 — Rolling upgrade
# ══════════════════════════════════════════════════════════════════════════
#
# Strategy: for each managed node, invoke
#   POST /api/wiz/admin/net/update/check  (get current version)
#   POST /api/wiz/admin/ops/jobs/jwt_rotate/run (an example "upgrade action")
# and wait for /health to return 200 before moving to the next. If a
# node fails health check, rollback signal is sent (operator decides).
#
# We don't actually do binary swap here — that's out of scope. This
# endpoint gives the orchestration primitive.

class RollingBody(BaseModel):
    action_endpoint: str = Field(..., description="e.g. /api/wiz/admin/node/stop")
    action_method:   Literal["POST","PUT","PATCH"] = "POST"
    between_sec:     int = Field(30, ge=5, le=600)
    health_timeout:  int = Field(60, ge=5, le=600)


@router.post("/rolling")
async def rolling_execute(body: RollingBody, request: Request) -> dict:
    env_file = _env_file(request)
    p = _managed_path(env_file)
    if not p.is_file(): raise HTTPException(400, "no managed nodes")
    nodes = json.loads(p.read_text()).get("nodes", [])
    if not nodes: return {"ok": True, "processed": 0}

    report = []
    for n in nodes:
        base = n["base_url"].rstrip("/")
        headers = {}
        if n.get("auth_bearer"):
            headers["Authorization"] = f"Bearer {n['auth_bearer']}"

        # 1. Perform the action
        url = base + body.action_endpoint
        async with httpx.AsyncClient(timeout=30.0, verify=False) as c:
            try:
                r = await c.request(body.action_method, url, headers=headers)
                action_status = r.status_code
            except Exception as e:
                report.append({"node": n["label"], "step": "action",
                               "ok": False, "error": str(e)})
                await _alerts.dispatch(env_file, "error",
                    f"Rolling upgrade failed on {n['label']}", str(e),
                    tags=["rolling_upgrade"])
                return {"ok": False, "stopped_at": n["label"],
                        "report": report}

        # 2. Wait for health
        waited = 0; healthy = False
        while waited < body.health_timeout:
            await asyncio.sleep(2); waited += 2
            try:
                async with httpx.AsyncClient(timeout=3.0, verify=False) as c:
                    r = await c.get(base + "/health", headers=headers)
                if r.status_code == 200:
                    healthy = True; break
            except Exception:
                continue

        report.append({"node": n["label"], "step": "health",
                       "action_status": action_status,
                       "ok": healthy, "waited_sec": waited})
        if not healthy:
            await _alerts.dispatch(env_file, "critical",
                f"Rolling upgrade — node {n['label']} unhealthy",
                f"after {body.health_timeout}s", tags=["rolling_upgrade"])
            return {"ok": False, "stopped_at": n["label"], "report": report}

        # 3. Delay before next
        await asyncio.sleep(body.between_sec)

    return {"ok": True, "processed": len(nodes), "report": report}


# ══════════════════════════════════════════════════════════════════════════
# #4 — Offline installer ZIP
# ══════════════════════════════════════════════════════════════════════════

@router.get("/installer/offline.zip")
async def offline_installer(request: Request) -> StreamingResponse:
    """Pack the node's source tree + pinned requirements + install script
    into a ZIP for air-gapped deploys. Does NOT include downloaded pip
    wheels — operator runs pip install in a trusted environment."""
    env_file = _env_file(request)
    root = env_file.parent

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for rel in [
            "requirements.txt",
            "run.py",
            "README.md",
        ]:
            p = root / rel
            if p.is_file(): zf.write(p, arcname=rel)

        # Walk app/ and vortex_wizard/ and templates/ and static/
        for subdir in ["app", "templates", "static", "certs"]:
            base = root / subdir
            if not base.is_dir(): continue
            for p in base.rglob("*"):
                if p.is_file() and "__pycache__" not in p.parts:
                    zf.write(p, arcname=str(p.relative_to(root)))

        # Install script
        zf.writestr("install-offline.sh", _install_script())
        zf.writestr("INSTALL.md", _install_readme())

    buf.seek(0)
    name = f"vortex-offline-{time.strftime('%Y%m%d')}.zip"
    return StreamingResponse(buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _install_script() -> str:
    return """#!/usr/bin/env bash
# Offline install — for air-gapped machines.
# Prerequisites: python 3.11+, sqlite3, openssl, libffi-dev, libssl-dev.
set -euo pipefail

TARGET="${TARGET:-/opt/vortex}"
echo "Installing Vortex to $TARGET"

mkdir -p "$TARGET"
tar xf - -C "$TARGET" <<< "$(cat)"
cd "$TARGET"

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cat > "$TARGET/.env" <<ENV
HOST=0.0.0.0
PORT=9000
NETWORK_MODE=local
# Fill in CONTROLLER_URL + CONTROLLER_PUBKEY for global mode
ENV

echo "Done. Run:"
echo "  cd $TARGET && .venv/bin/python run.py"
"""


def _install_readme() -> str:
    return """# Vortex offline installer

## Quick start
    unzip vortex-offline-*.zip -d /tmp/vortex-src
    cd /tmp/vortex-src
    bash install-offline.sh

## What's included
- Full `app/` source tree (Python node)
- `templates/` + `static/` (web UI)
- `requirements.txt` (pinned deps)
- `install-offline.sh` (convenience script)

## What's NOT included
- Python interpreter (install separately)
- pip wheels (run `pip install -r requirements.txt` in a trusted env
  with access to PyPI — or pre-populate `.venv/` and tar it alongside)
- Rust `vortex_chat` extension (build with `maturin develop --release`)
"""


# ══════════════════════════════════════════════════════════════════════════
# #5 — Windows service template
# ══════════════════════════════════════════════════════════════════════════

@router.get("/windows/service.ps1")
async def windows_service() -> Response:
    """PowerShell script that installs Vortex as a Windows service via
    NSSM (https://nssm.cc). Operator downloads NSSM separately."""
    ps = """# Install Vortex as a Windows service (NSSM required).
# 1. Download NSSM from https://nssm.cc/download
# 2. Place nssm.exe in C:\\Windows\\System32\\
# 3. Run this script as Administrator:  powershell -File install-vortex.ps1

$ErrorActionPreference = "Stop"
$ServiceName = "Vortex"
$InstallPath = "C:\\Program Files\\Vortex"
$PythonExe   = "$InstallPath\\.venv\\Scripts\\python.exe"
$Script      = "$InstallPath\\run.py"

if (-not (Test-Path $PythonExe)) {
    Write-Error "Python venv not found at $PythonExe — run 'python -m venv .venv' in $InstallPath first."
    exit 1
}
if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
    Write-Error "nssm.exe not on PATH. Download from https://nssm.cc/"
    exit 1
}

Write-Host "Installing $ServiceName service..."
nssm install $ServiceName $PythonExe $Script
nssm set $ServiceName AppDirectory      $InstallPath
nssm set $ServiceName DisplayName       "Vortex P2P Node"
nssm set $ServiceName Description       "Privacy-first P2P messenger node"
nssm set $ServiceName Start             SERVICE_AUTO_START
nssm set $ServiceName AppStdout         "$InstallPath\\logs\\vortex.out.log"
nssm set $ServiceName AppStderr         "$InstallPath\\logs\\vortex.err.log"
nssm set $ServiceName AppRotateFiles    1
nssm set $ServiceName AppRotateBytes    10485760

Start-Service $ServiceName
Write-Host "$ServiceName installed and started."
Write-Host "Uninstall with:  nssm remove $ServiceName confirm"
"""
    return Response(content=ps, media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="install-vortex.ps1"'})
