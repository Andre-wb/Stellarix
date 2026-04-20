"""Unified alert dispatcher — email + webhook destinations.

Alert channels can be added from the wizard UI. Each channel has:
  - type:    "email" | "slack" | "discord" | "telegram" | "matrix" | "webhook" | "pagerduty"
  - config:  destination-specific fields
  - filters: severity threshold, tag match
  - enabled: per-channel on/off

When another wizard module (watchdog, audit alert, backup failure)
wants to raise an alert, it calls ``alerts.dispatch(severity, title,
body, tags)`` — this module fans the message out to all enabled
channels that match the severity/filters.

Config is persisted in `<env-dir>/alert_channels.json`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import smtplib
import ssl
import time
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin/alerts", tags=["alerts"])


# ── Config storage ────────────────────────────────────────────────────────

def _env_file(request: Request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


def _state_path(env_file: Path) -> Path:
    return env_file.parent / "alert_channels.json"


def _load(env_file: Path) -> dict:
    p = _state_path(env_file)
    if not p.is_file():
        return {"channels": [], "history": []}
    try:
        data = json.loads(p.read_text())
        data.setdefault("channels", [])
        data.setdefault("history", [])
        return data
    except Exception:
        return {"channels": [], "history": []}


def _save(env_file: Path, data: dict) -> None:
    p = _state_path(env_file)
    p.write_text(json.dumps(data, indent=2))


# ── Channel schemas ───────────────────────────────────────────────────────

ChannelType = Literal[
    "email", "slack", "discord", "telegram", "matrix", "webhook", "pagerduty"
]
Severity = Literal["info", "warning", "error", "critical"]

_SEVERITY_LEVEL = {"info": 0, "warning": 1, "error": 2, "critical": 3}


class ChannelBody(BaseModel):
    id:       Optional[str] = None
    type:     ChannelType
    name:     str = Field(..., min_length=1, max_length=60)
    config:   dict = Field(default_factory=dict)
    min_severity: Severity = "warning"
    enabled:  bool = True


# ── Dispatcher — core API ────────────────────────────────────────────────

async def dispatch(
    env_file: Path,
    severity: Severity,
    title: str,
    body: str = "",
    tags: Optional[list[str]] = None,
) -> dict:
    """Fan out an alert to all enabled channels that pass severity filter.

    Never raises — a channel failure is logged and the next one tries.
    Returns `{channel_id: "sent" | "skipped" | "err:..."}` for audit.
    """
    state = _load(env_file)
    threshold = _SEVERITY_LEVEL[severity]
    report: dict[str, str] = {}

    tasks = []
    for ch in state.get("channels", []):
        if not ch.get("enabled"): continue
        min_lvl = _SEVERITY_LEVEL.get(ch.get("min_severity", "warning"), 1)
        if threshold < min_lvl:
            report[ch["id"]] = "skipped:below_threshold"
            continue
        tasks.append((ch, asyncio.create_task(
            _send_to_channel(ch, severity, title, body, tags or [])
        )))

    for ch, t in tasks:
        try:
            ok, note = await t
            report[ch["id"]] = "sent" if ok else f"err:{note}"
        except Exception as e:
            report[ch["id"]] = f"err:{type(e).__name__}"

    # Record last-N in history
    entry = {
        "ts":       int(time.time()),
        "severity": severity,
        "title":    title,
        "tags":     tags or [],
        "report":   report,
    }
    hist = state.get("history", [])
    hist.append(entry)
    state["history"] = hist[-200:]
    _save(env_file, state)
    return report


# ── Per-channel senders ───────────────────────────────────────────────────

async def _send_to_channel(
    ch: dict, severity: str, title: str, body: str, tags: list[str]
) -> tuple[bool, str]:
    t = ch["type"]
    cfg = ch.get("config", {})
    try:
        if t == "email":
            return await _send_email(cfg, severity, title, body, tags)
        if t == "slack":
            return await _send_slack(cfg, severity, title, body, tags)
        if t == "discord":
            return await _send_discord(cfg, severity, title, body, tags)
        if t == "telegram":
            return await _send_telegram(cfg, severity, title, body, tags)
        if t == "matrix":
            return await _send_matrix(cfg, severity, title, body, tags)
        if t == "webhook":
            return await _send_webhook(cfg, severity, title, body, tags)
        if t == "pagerduty":
            return await _send_pagerduty(cfg, severity, title, body, tags)
    except Exception as e:
        return False, f"{type(e).__name__}:{e}"
    return False, "unknown_channel_type"


def _format_plain(sev: str, title: str, body: str, tags: list[str]) -> str:
    parts = [f"[{sev.upper()}] {title}"]
    if tags:
        parts.append("Tags: " + ", ".join(tags))
    if body:
        parts.append("")
        parts.append(body)
    return "\n".join(parts)


# Email via SMTP (STARTTLS/SSL). Blocking smtplib runs in a thread.
async def _send_email(cfg: dict, severity: str, title: str, body: str, tags: list[str]):
    required = ("smtp_host", "smtp_port", "smtp_user", "smtp_password", "from_addr", "to_addr")
    for k in required:
        if not cfg.get(k):
            return False, f"missing:{k}"
    msg = MIMEText(_format_plain(severity, title, body, tags), "plain", "utf-8")
    msg["Subject"] = f"[vortex/{severity}] {title}"[:180]
    msg["From"] = cfg["from_addr"]
    msg["To"] = cfg["to_addr"]

    def _blocking_send():
        ctx = ssl.create_default_context()
        port = int(cfg["smtp_port"])
        if port == 465:
            with smtplib.SMTP_SSL(cfg["smtp_host"], port, context=ctx, timeout=10) as s:
                s.login(cfg["smtp_user"], cfg["smtp_password"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(cfg["smtp_host"], port, timeout=10) as s:
                s.ehlo()
                if port == 587: s.starttls(context=ctx)
                s.login(cfg["smtp_user"], cfg["smtp_password"])
                s.send_message(msg)
    await asyncio.to_thread(_blocking_send)
    return True, ""


async def _send_slack(cfg: dict, severity: str, title: str, body: str, tags: list[str]):
    url = cfg.get("webhook_url")
    if not url: return False, "missing:webhook_url"
    color = {"info":"#4b9eff","warning":"#f59e0b","error":"#ef4444","critical":"#b91c1c"}[severity]
    payload = {
        "attachments": [{
            "color": color,
            "title": f"[{severity.upper()}] {title}",
            "text":  body or "",
            "fields": [{"title": "tags", "value": ", ".join(tags) or "-", "short": True}],
            "ts":    int(time.time()),
        }]
    }
    async with httpx.AsyncClient(timeout=5.0, verify=True) as c:
        r = await c.post(url, json=payload)
    return r.status_code < 400, f"http_{r.status_code}"


async def _send_discord(cfg: dict, severity: str, title: str, body: str, tags: list[str]):
    url = cfg.get("webhook_url")
    if not url: return False, "missing:webhook_url"
    color_map = {"info":0x4b9eff,"warning":0xf59e0b,"error":0xef4444,"critical":0xb91c1c}
    embed = {
        "title": f"[{severity.upper()}] {title}"[:250],
        "description": body[:4000] if body else "",
        "color": color_map[severity],
        "footer": {"text": "vortex • " + (", ".join(tags) or "no tags")},
    }
    async with httpx.AsyncClient(timeout=5.0, verify=True) as c:
        r = await c.post(url, json={"embeds": [embed]})
    return r.status_code < 400, f"http_{r.status_code}"


async def _send_telegram(cfg: dict, severity: str, title: str, body: str, tags: list[str]):
    token = cfg.get("bot_token")
    chat  = cfg.get("chat_id")
    if not (token and chat): return False, "missing:bot_token_or_chat_id"
    text = _format_plain(severity, title, body, tags)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=5.0, verify=True) as c:
        r = await c.post(url, json={"chat_id": chat, "text": text[:4000]})
    return r.status_code < 400, f"http_{r.status_code}"


async def _send_matrix(cfg: dict, severity: str, title: str, body: str, tags: list[str]):
    # Uses Matrix client-server API's /rooms/{roomId}/send/m.room.message endpoint.
    base = (cfg.get("homeserver") or "").rstrip("/")
    room = cfg.get("room_id", "").strip()
    token = cfg.get("access_token", "").strip()
    if not (base and room and token): return False, "missing:homeserver_room_token"
    url = f"{base}/_matrix/client/v3/rooms/{room}/send/m.room.message/{int(time.time()*1000)}"
    payload = {"msgtype": "m.notice", "body": _format_plain(severity, title, body, tags)}
    async with httpx.AsyncClient(timeout=5.0, verify=True) as c:
        r = await c.put(url, json=payload, headers={"Authorization": f"Bearer {token}"})
    return r.status_code < 400, f"http_{r.status_code}"


async def _send_webhook(cfg: dict, severity: str, title: str, body: str, tags: list[str]):
    url = cfg.get("url")
    if not url: return False, "missing:url"
    payload = {
        "severity": severity, "title": title, "body": body,
        "tags": tags, "ts": int(time.time()),
        "source": "vortex-wizard",
    }
    headers = {}
    if cfg.get("auth_bearer"):
        headers["Authorization"] = f"Bearer {cfg['auth_bearer']}"
    async with httpx.AsyncClient(timeout=5.0, verify=True) as c:
        r = await c.post(url, json=payload, headers=headers)
    return r.status_code < 400, f"http_{r.status_code}"


async def _send_pagerduty(cfg: dict, severity: str, title: str, body: str, tags: list[str]):
    # PagerDuty Events API v2.
    routing = cfg.get("routing_key")
    if not routing: return False, "missing:routing_key"
    sev_map = {"info":"info","warning":"warning","error":"error","critical":"critical"}
    payload = {
        "routing_key": routing,
        "event_action": "trigger",
        "payload": {
            "summary":  title,
            "severity": sev_map[severity],
            "source":   "vortex-node",
            "custom_details": {"body": body, "tags": tags},
        },
    }
    async with httpx.AsyncClient(timeout=5.0, verify=True) as c:
        r = await c.post("https://events.pagerduty.com/v2/enqueue", json=payload)
    return r.status_code < 400, f"http_{r.status_code}"


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.get("")
async def list_channels(request: Request) -> dict:
    state = _load(_env_file(request))
    # Mask secrets on output
    safe = []
    for ch in state.get("channels", []):
        copy = dict(ch); cfg = dict(copy.get("config", {}))
        for k in list(cfg.keys()):
            lk = k.lower()
            if any(s in lk for s in ("password","token","key","secret","routing")):
                cfg[k] = "•" * 10 if cfg[k] else ""
        copy["config"] = cfg
        safe.append(copy)
    return {"channels": safe, "history": state.get("history", [])[-50:]}


@router.post("")
async def add_or_update(body: ChannelBody, request: Request) -> dict:
    env_file = _env_file(request)
    state = _load(env_file)
    import secrets as _s
    if body.id:
        found = None
        for ch in state["channels"]:
            if ch["id"] == body.id:
                ch.update(body.model_dump(exclude_none=True))
                found = ch; break
        if not found:
            raise HTTPException(404, "channel id not found")
    else:
        ch = body.model_dump()
        ch["id"] = _s.token_urlsafe(10)
        state["channels"].append(ch)
        found = ch
    _save(env_file, state)
    return {"ok": True, "id": found["id"]}


@router.delete("/{channel_id}")
async def delete_channel(channel_id: str, request: Request) -> dict:
    env_file = _env_file(request)
    state = _load(env_file)
    before = len(state["channels"])
    state["channels"] = [c for c in state["channels"] if c["id"] != channel_id]
    _save(env_file, state)
    return {"ok": True, "removed": before - len(state["channels"])}


class TestBody(BaseModel):
    channel_id: Optional[str] = None
    severity:   Severity = "info"
    title:      str = "Vortex alert test"
    body:       str = "This is a test alert dispatched from the wizard."


@router.post("/test")
async def send_test(body: TestBody, request: Request) -> dict:
    env_file = _env_file(request)
    state = _load(env_file)
    # If channel_id given, fire only to that one; otherwise fan-out.
    if body.channel_id:
        for ch in state["channels"]:
            if ch["id"] == body.channel_id:
                ok, note = await _send_to_channel(ch, body.severity, body.title, body.body, ["test"])
                return {"ok": ok, "note": note}
        raise HTTPException(404, "channel not found")
    report = await dispatch(env_file, body.severity, body.title, body.body, ["test"])
    return {"ok": True, "report": report}
