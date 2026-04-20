"""Log rotation + search for the wizard's admin UI.

The node's logs accumulate at ``<env-dir>/logs/vortex.log`` (or siblings)
because the wizard pipes the child's stdout/stderr there. Once the file
passes ~5 MiB we gzip it aside and start fresh, so the admin Logs tab
stays fast and disk usage stays bounded. Search can grep over both the
active file and every rotated .gz.

This is a separate router from ``admin_api.logs`` so the polling endpoint
there (every 3 s) stays on its own hot path.
"""
from __future__ import annotations

import gzip
import io
import logging
import re
import shutil
import time
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin/logs", tags=["logs"])


_ROTATE_THRESHOLD = 5 * 1024 * 1024       # 5 MiB
_MAX_ROTATED_KEPT = 20                    # per log file stem
_SEARCH_RESULTS_CAP = 500
_DEFAULT_LOG_NAMES = ("vortex.log", "vortex.json.log", "node.log")


def _logs_dir(env_file: Path) -> Path:
    return env_file.parent / "logs"


def _iter_all_log_files(env_file: Path) -> List[Path]:
    d = _logs_dir(env_file)
    if not d.is_dir():
        return []
    # Active logs + all *.log.YYYYMMDD-HHMMSS.gz archives
    files: List[Path] = []
    for name in _DEFAULT_LOG_NAMES:
        p = d / name
        if p.is_file():
            files.append(p)
    files.extend(sorted(d.glob("*.log.*.gz")))
    return files


def _env_file(request: Request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


@router.get("/files")
async def list_log_files(request: Request) -> dict:
    env = _env_file(request)
    out = []
    for p in _iter_all_log_files(env):
        try:
            st = p.stat()
        except OSError:
            continue
        out.append({
            "name":       p.name,
            "byte_size":  st.st_size,
            "modified":   int(st.st_mtime),
            "compressed": p.suffix == ".gz",
        })
    out.sort(key=lambda r: r["modified"], reverse=True)
    return {"files": out, "threshold": _ROTATE_THRESHOLD, "max_kept": _MAX_ROTATED_KEPT}


@router.post("/rotate")
async def rotate_logs(request: Request) -> dict:
    """Force-rotate any log file over the threshold.

    Safe to call while the node is writing — we copy then truncate in
    place so the writer's file descriptor stays valid.
    """
    env = _env_file(request)
    d = _logs_dir(env)
    if not d.is_dir():
        return {"rotated": []}

    rotated: list[str] = []
    for name in _DEFAULT_LOG_NAMES:
        src = d / name
        if not src.is_file():
            continue
        if src.stat().st_size < _ROTATE_THRESHOLD:
            continue
        archive = d / f"{name}.{time.strftime('%Y%m%d-%H%M%S')}.gz"
        try:
            with src.open("rb") as in_f, gzip.open(archive, "wb", compresslevel=6) as out_f:
                shutil.copyfileobj(in_f, out_f, length=1024 * 1024)
            # Truncate in place — the writer keeps its fd, its next write
            # appends from offset 0 (Unix semantics).
            with src.open("r+b") as f:
                f.truncate(0)
            rotated.append(name)
        except Exception as e:
            logger.warning("log rotate %s failed: %s", name, e)

    # GC: keep only the N newest archives per stem
    for name in _DEFAULT_LOG_NAMES:
        archives = sorted(d.glob(f"{name}.*.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in archives[_MAX_ROTATED_KEPT:]:
            try: old.unlink()
            except OSError: pass

    return {"rotated": rotated}


@router.get("/search")
async def search_logs(
    request: Request,
    q:    str,
    file: Optional[str] = None,
    case: bool = False,
) -> dict:
    if not q or len(q) > 200:
        raise HTTPException(400, "q required (1-200 chars)")
    env = _env_file(request)

    try:
        pattern = re.compile(re.escape(q), 0 if case else re.IGNORECASE)
    except re.error as e:
        raise HTTPException(400, f"bad query: {e}")

    files = _iter_all_log_files(env)
    if file:
        files = [p for p in files if p.name == file]
        if not files:
            raise HTTPException(404, f"log file not found: {file}")

    hits = []
    truncated = False
    for p in files:
        if len(hits) >= _SEARCH_RESULTS_CAP:
            truncated = True
            break
        try:
            opener = gzip.open if p.suffix == ".gz" else open
            with opener(p, "rt", encoding="utf-8", errors="replace") as f:
                for lineno, line in enumerate(f, 1):
                    if pattern.search(line):
                        hits.append({
                            "file":   p.name,
                            "line":   lineno,
                            "text":   line.rstrip("\n")[:2000],
                        })
                        if len(hits) >= _SEARCH_RESULTS_CAP:
                            truncated = True
                            break
        except OSError as e:
            logger.debug("search open %s failed: %s", p, e)
            continue

    return {"query": q, "hits": hits, "truncated": truncated, "total_files_searched": len(files)}
