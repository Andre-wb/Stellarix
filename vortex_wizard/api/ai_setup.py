"""One-click Ollama setup for the wizard.

Parallel to the PostgreSQL flow in db_api.py:
  - Detect if ollama is installed (shutil.which / brew prefix)
  - Install via the platform's package manager on a single click
  - Pull the recommended paraphrase / summarization model
  - Start & stop the ollama daemon
  - Uninstall with confirmation

When the user enables AI on this node (AI_ENABLED=true), the node
advertises an ``ai_capable=true`` flag in its controller registration
metadata. The controller then weights AI-enabled nodes higher when
picking random peers — nodes without AI see their discovery weight
reduced by a configurable penalty.

SECURITY: all argv is constructed as a list (no shell), with Pydantic-
validated model/email/domain strings and an explicit argv-alphanumeric
check to reject anything funny before it reaches the child process.
"""
from __future__ import annotations

import asyncio
from asyncio import subprocess as _asp
import json
import logging
import os
import platform
import shutil
import time
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import backup_api as _b
from . import security_api as _sec

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin/ai", tags=["ai-setup"])


DEFAULT_MODEL = "qwen3:8b"
OLLAMA_URL    = "http://127.0.0.1:11434"


def _env_file(request: Request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


def _find_ollama() -> Optional[str]:
    p = shutil.which("ollama")
    if p:
        return p
    for c in ("/opt/homebrew/bin/ollama",
              "/usr/local/bin/ollama",
              "/usr/bin/ollama"):
        if Path(c).is_file():
            return c
    return None


def _find_brew() -> Optional[str]:
    p = shutil.which("brew")
    if p:
        return p
    for c in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew"):
        if Path(c).is_file():
            return c
    return None


async def _run(argv: list[str], timeout: int = 600) -> tuple[int, str, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=_asp.PIPE,
            stderr=_asp.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return (-1, "", "timeout")
        return (proc.returncode or 0,
                (out or b"").decode("utf-8", errors="replace"),
                (err or b"").decode("utf-8", errors="replace"))
    except FileNotFoundError:
        return (-2, "", f"not found: {argv[0]}")
    except Exception as e:
        return (-3, "", f"{type(e).__name__}: {e}")


async def _ollama_reachable(base: str = OLLAMA_URL) -> bool:
    try:
        async with httpx.AsyncClient(timeout=1.5, verify=False) as c:
            r = await c.get(base + "/api/tags")
            return r.status_code == 200
    except Exception:
        return False


async def _list_models(base: str = OLLAMA_URL) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=3.0, verify=False) as c:
            r = await c.get(base + "/api/tags")
            if r.status_code != 200:
                return []
            return (r.json().get("models") or [])
    except Exception:
        return []


@router.get("/status")
async def ai_status(request: Request) -> dict:
    env = _b._read_env(_env_file(request))
    installed = _find_ollama()
    reachable = await _ollama_reachable()
    models    = await _list_models() if reachable else []
    enabled   = env.get("AI_ENABLED", "true").lower() not in ("0", "false", "no")
    configured_model = env.get("OLLAMA_MODEL", DEFAULT_MODEL)
    return {
        "installed":        bool(installed),
        "ollama_path":      installed,
        "running":          reachable,
        "models":           [m.get("name") or "" for m in models],
        "ai_enabled":       enabled,
        "configured_model": configured_model,
        "weight_penalty_if_disabled": 0.15,
        "platform":         platform.system().lower(),
        "default_model":    DEFAULT_MODEL,
    }


class InstallBody(BaseModel):
    use_homebrew: bool = True


@router.post("/install")
async def ai_install(body: InstallBody) -> dict:
    if _find_ollama():
        return {"ok": True, "already": True}

    sys_name = platform.system().lower()
    if sys_name == "darwin":
        brew = _find_brew()
        if not brew:
            raise HTTPException(400, "Homebrew не найден. Установи brew: https://brew.sh")
        code, out, err = await _run([brew, "install", "ollama"], timeout=900)
        if code != 0:
            raise HTTPException(500, f"brew install failed: {err[:500]}")
        return {"ok": True, "installed_via": "brew", "stdout": out[-2000:]}

    if sys_name == "linux":
        return {
            "ok":     False,
            "manual": True,
            "command": "curl -fsSL https://ollama.com/install.sh | sh",
            "hint":   "Review the script and run it manually in a terminal.",
        }
    raise HTTPException(400, f"unsupported platform: {sys_name}")


class PullBody(BaseModel):
    model: str = Field(DEFAULT_MODEL, min_length=1, max_length=100)


@router.post("/pull")
async def ai_pull(body: PullBody, request: Request) -> dict:
    ol = _find_ollama()
    if not ol:
        raise HTTPException(400, "ollama not installed — call /install first")
    m = body.model.strip()
    if not all(c.isalnum() or c in ":/_.-" for c in m):
        raise HTTPException(400, "bad model name")

    if not await _ollama_reachable():
        asyncio.create_task(_run([ol, "serve"], timeout=3600 * 24))
        for _ in range(30):
            await asyncio.sleep(0.5)
            if await _ollama_reachable(): break

    code, out, err = await _run([ol, "pull", m], timeout=3600)
    if code != 0:
        raise HTTPException(500, f"pull failed: {(err or out)[:800]}")

    _sec._write_env_keys(_env_file(request), {"OLLAMA_MODEL": m})
    return {"ok": True, "model": m}


@router.post("/start")
async def ai_start() -> dict:
    ol = _find_ollama()
    if not ol:
        raise HTTPException(400, "ollama not installed")
    if await _ollama_reachable():
        return {"ok": True, "already_running": True}
    asyncio.create_task(_run([ol, "serve"], timeout=3600 * 24))
    for _ in range(20):
        await asyncio.sleep(0.3)
        if await _ollama_reachable():
            return {"ok": True, "running": True}
    return {"ok": False, "message": "daemon did not become reachable in 6s"}


@router.post("/stop")
async def ai_stop() -> dict:
    code, _, err = await _run(["pkill", "-TERM", "-x", "ollama"], timeout=10)
    return {"ok": code in (0, 1), "err": err[:200]}


class ToggleBody(BaseModel):
    enabled: bool


@router.post("/toggle")
async def ai_toggle(body: ToggleBody, request: Request) -> dict:
    _sec._write_env_keys(_env_file(request), {
        "AI_ENABLED": "true" if body.enabled else "false",
    })
    return {"ok": True, "ai_enabled": body.enabled}


@router.post("/uninstall")
async def ai_uninstall(request: Request) -> dict:
    sys_name = platform.system().lower()
    if sys_name != "darwin":
        raise HTTPException(400, "uninstall currently supports macOS/brew only")
    brew = _find_brew()
    if not brew:
        raise HTTPException(400, "Homebrew not found")
    code, out, err = await _run([brew, "uninstall", "ollama"], timeout=120)
    if code != 0:
        raise HTTPException(500, f"brew uninstall failed: {err[:400]}")
    _sec._write_env_keys(_env_file(request), {"AI_ENABLED": "false"})
    return {"ok": True, "removed": "ollama"}
