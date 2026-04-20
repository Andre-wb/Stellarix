"""Lightweight asyncio scheduler for recurring wizard jobs.

Registered jobs run on a configurable interval. State (last-run / success
flag) is persisted to ``<env-dir>/scheduler_state.json`` so the next boot
doesn't double-fire a job that just ran. No external dependency (would've
been APScheduler, but that's 2 MB of wheels + Cython — overkill for four
cron-ish tasks).

Every job is a plain ``async def job(env_file: Path) -> dict`` where the
returned dict is stored as the "last result" for the UI.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


JobFn = Callable[[Path], Awaitable[dict]]


# User-facing interval presets (seconds). "off" means job skipped.
INTERVAL_PRESETS = {
    "off":     0,
    "hourly":  3600,
    "daily":   86400,
    "weekly":  7 * 86400,
}


@dataclass
class Job:
    name:     str
    fn:       JobFn
    interval: str = "off"
    last_run: int = 0
    last_ok:  bool = False
    last_msg: str = ""
    # When interval == "off" this job is not scheduled, but can still be
    # invoked manually via run_once().


class Scheduler:
    def __init__(self, env_file: Path):
        self.env_file = env_file
        self.state_path = env_file.parent / "scheduler_state.json"
        self._jobs: dict[str, Job] = {}
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._tick_sec = 30
        self._load_state()

    # ── Job registration ────────────────────────────────────────────────
    def register(self, name: str, fn: JobFn, default_interval: str = "off") -> None:
        existing = self._jobs.get(name)
        if existing:
            existing.fn = fn                # allow re-registration
            return
        j = Job(name=name, fn=fn, interval=default_interval)
        # Hydrate from persisted state if available
        saved = self._saved.get(name, {})
        j.interval = saved.get("interval", j.interval)
        j.last_run = int(saved.get("last_run", 0))
        j.last_ok  = bool(saved.get("last_ok", False))
        j.last_msg = saved.get("last_msg", "")
        self._jobs[name] = j

    def set_interval(self, name: str, interval: str) -> None:
        if interval not in INTERVAL_PRESETS:
            raise ValueError(f"unknown interval: {interval}")
        j = self._jobs.get(name)
        if not j:
            raise KeyError(name)
        j.interval = interval
        self._save_state()

    def jobs(self) -> list[dict]:
        return [
            {
                "name":       j.name,
                "interval":   j.interval,
                "last_run":   j.last_run,
                "last_ok":    j.last_ok,
                "last_msg":   j.last_msg,
                "next_run":   _next_run_at(j),
            }
            for j in self._jobs.values()
        ]

    async def run_once(self, name: str) -> dict:
        j = self._jobs.get(name)
        if not j:
            raise KeyError(name)
        return await self._run(j)

    # ── Lifecycle ───────────────────────────────────────────────────────
    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="wizard-scheduler")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await self._task
            except Exception:
                pass
            self._task = None

    # ── Internals ───────────────────────────────────────────────────────
    async def _loop(self) -> None:
        while not self._stop.is_set():
            now = int(time.time())
            for j in list(self._jobs.values()):
                if j.interval == "off":
                    continue
                if now - j.last_run < INTERVAL_PRESETS[j.interval]:
                    continue
                # Fire-and-forget inside this loop — jobs are short-lived
                # (backup / VACUUM / resource check).
                try:
                    await self._run(j)
                except Exception as e:
                    logger.warning("scheduler job %s failed: %s", j.name, e)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._tick_sec)
            except asyncio.TimeoutError:
                pass

    async def _run(self, j: Job) -> dict:
        logger.info("scheduler: firing job %s", j.name)
        t0 = time.time()
        res: dict = {}
        try:
            res = await j.fn(self.env_file) or {}
            j.last_ok = True
            j.last_msg = str(res.get("message", "ok"))[:240]
        except Exception as e:
            j.last_ok = False
            j.last_msg = f"{type(e).__name__}: {e}"[:240]
            logger.exception("scheduler: %s raised", j.name)
            res = {"error": j.last_msg}
        finally:
            j.last_run = int(time.time())
            dur = time.time() - t0
            res["duration_sec"] = round(dur, 2)
            self._save_state()
        return res

    def _load_state(self) -> None:
        self._saved: dict[str, dict] = {}
        if self.state_path.is_file():
            try:
                self._saved = json.loads(self.state_path.read_text())
            except Exception:
                self._saved = {}

    def _save_state(self) -> None:
        payload = {
            j.name: {
                "interval": j.interval,
                "last_run": j.last_run,
                "last_ok":  j.last_ok,
                "last_msg": j.last_msg,
            }
            for j in self._jobs.values()
        }
        try:
            self.state_path.write_text(json.dumps(payload, indent=2))
        except Exception as e:
            logger.debug("scheduler state save failed: %s", e)


def _next_run_at(j: Job) -> int:
    if j.interval == "off":
        return 0
    return j.last_run + INTERVAL_PRESETS[j.interval]


# Module-level singleton — the wizard has exactly one.
_scheduler: Optional[Scheduler] = None


def get(env_file: Path) -> Scheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler(env_file)
    return _scheduler
