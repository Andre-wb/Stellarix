"""Full .env settings editor for the wizard admin UI.

Exposes a single pair of endpoints:

  GET  /api/wiz/admin/settings        → schema + current values
  POST /api/wiz/admin/settings        → write one or many keys

Well-known keys have rich metadata (type, group, label, description,
requires_restart). Anything else in .env but not in the schema appears
in the "Advanced" group as a raw string input — so operators can still
edit it safely from the UI.

The settings_api never touches secrets like JWT_SECRET (those have their
own dedicated rotation tool in W3) — they show as "•••" and clicking
reveal requires an explicit confirmation.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import security_api as _sec
from . import backup_api as _b

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin/settings", tags=["settings"])


# ── Schema ────────────────────────────────────────────────────────────────

FieldType = Literal["bool", "str", "int", "password", "select", "textarea"]


def _F(key: str, type: FieldType, group: str, label: str, *,
       default: str = "",
       desc:    str = "",
       restart: bool = True,
       options: Optional[list[str]] = None,
       secret:  bool = False) -> dict:
    return {
        "key":     key,
        "type":    type,
        "group":   group,
        "label":   label,
        "default": default,
        "desc":    desc,
        "requires_restart": restart,
        "options": options,
        "secret":  secret,
    }


SCHEMA: list[dict] = [
    # ── Network
    _F("HOST",             "str",   "Network", "Bind host",
       default="0.0.0.0",
       desc="Адрес на который слушает нода. 0.0.0.0 — все интерфейсы."),
    _F("PORT",             "int",   "Network", "Port", default="9000"),
    _F("NETWORK_MODE",     "select","Network", "Network mode",
       default="local",
       options=["local", "global", "custom"],
       desc="local = только LAN · global = через vortexx.sol · custom = свой controller."),
    _F("DEVICE_NAME",      "str",   "Network", "Device name"),
    _F("ANNOUNCE_URL",     "str",   "Network", "Public announce URL",
       desc="Адрес на который другие ноды подключаются (tunnel / static IP)."),
    _F("BOOTSTRAP_PEERS",  "textarea", "Network", "Bootstrap peers",
       desc="ip:port через запятую — стартовые пиры при отсутствии controller'а."),
    _F("CONTROLLER_URL",      "str", "Network", "Controller URL"),
    _F("CONTROLLER_PUBKEY",   "str", "Network", "Controller pubkey (hex)"),
    _F("CONTROLLER_FALLBACK_URLS", "textarea", "Network", "Fallback controllers"),

    # ── Database
    _F("DATABASE_URL",     "str",   "Database", "DATABASE_URL",
       desc="Пусто → SQLite vortex.db. Заполняется автоматически при Set up PostgreSQL."),
    _F("DB_PATH",          "str",   "Database", "SQLite path", default="vortex.db"),

    # ── Security
    _F("EPHEMERAL_MODE",   "bool",  "Security", "Ephemeral mode (RAM-only DB)",
       default="false",
       desc="Все данные в памяти. После перезапуска ноды — полный вайп. Экстремальный приватный режим."),
    _F("REQUIRE_HARDWARE_KEY", "bool", "Security", "Require hardware FIDO2 key",
       default="false",
       desc="Passkey registration требует cross-platform authenticator (YubiKey / SoloKey). Запрещает Touch ID / Windows Hello. Node-wide."),
    _F("TOR_HIDDEN_SERVICE", "bool", "Security", "Tor hidden service",
       default="false",
       desc="Запускать .onion endpoint. Нужен установленный tor."),
    _F("ONION_ONLY",       "bool",  "Security", "Onion-only outbound",
       default="false",
       desc="Весь исходящий HTTP через Tor SOCKS. Ломает federation если другие ноды не в Tor."),
    _F("STORE_IPS",        "bool",  "Security", "Store IPs",
       default="false",
       desc="Логать IP пользователей. Default false — приватность."),
    _F("HASH_IPS",         "bool",  "Security", "Hash IPs before storage",
       default="true"),
    _F("METADATA_PADDING", "bool",  "Security", "Metadata padding",
       default="true",
       desc="Дополняет сообщения до фиксированного размера, затрудняет анализ длины."),
    _F("EPHEMERAL_IDENTITIES", "bool", "Security", "Ephemeral session identities",
       default="false",
       desc="При каждом логине — новая пара ключей. Полная unlinkability между сессиями."),
    _F("CSP_PROFILE",      "select","Security", "CSP profile",
       default="strict",
       options=["strict", "relaxed", "off", "custom"],
       restart=False),
    _F("HSTS_PROFILE",     "select","Security", "HSTS profile",
       default="off",
       options=["off", "on", "preload"],
       restart=False),

    # ── Federation / BMP
    _F("BMP_DELIVERY",     "bool",  "Federation", "BMP anonymous delivery",
       default="true",
       desc="Blind Mailbox Pattern — сервер не знает кому шлёт сообщение."),
    _F("FEDERATION_ENABLED", "bool", "Federation", "Federation enabled",
       default="true"),

    # ── AI / integrations
    _F("AI_ENABLED",       "bool",  "AI",      "AI assistant",       default="true"),
    _F("AI_PROVIDER",      "select","AI",      "AI provider",
       default="auto", options=["auto","ollama","openai","anthropic"]),
    _F("OLLAMA_URL",       "str",   "AI",      "Ollama URL",          default="http://localhost:11434"),
    _F("OLLAMA_MODEL",     "str",   "AI",      "Ollama model",        default="llama3"),
    _F("AI_API_KEY",       "password","AI",    "External API key", secret=True),
    _F("AI_API_URL",       "str",   "AI",      "External API URL"),
    _F("AI_MODEL",         "str",   "AI",      "External model name"),
    _F("TRANSLATE_ENABLED","bool",  "AI",      "Translation",         default="false"),
    _F("TRANSLATE_URL",    "str",   "AI",      "Translate backend",   default="http://localhost:5000"),

    # ── Operator / monetization
    _F("MIRROR_ENABLED",   "bool",  "Operator","Backup mirror enabled", default="false"),
    _F("MIRROR_CONTROLLER_URL","str","Operator","Mirror controller URL"),
    _F("AUTOCOMPOUND_ENABLED","bool","Operator","Autocompound rewards", default="false"),
    _F("AUTOCOMPOUND_THRESHOLD","str","Operator","Autocompound threshold (SOL)", default="1.0"),
    _F("VERSION_PIN",      "bool",  "Operator","Pin version (no update banner)", default="false"),

    # ── Accessibility / wizard
    _F("TOUR_COMPLETED",   "bool",  "Wizard",  "Guided tour dismissed", default="false", restart=False),
]

# Keys we refuse to show/edit through this endpoint.
_FORBIDDEN = {"JWT_SECRET", "CSRF_SECRET", "NODE_PUBKEY", "WALLET_PUBKEY",
              "SHADOWSOCKS_PASSWORD", "CDN_RELAY_SECRET", "KEYS_DIR",
              "NODE_INITIALIZED"}


def _env_file(request: Request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


def _is_bool_val(v: str) -> bool:
    return v.strip().lower() in ("1","true","yes","on","0","false","no","off","")


# ── GET: schema + current values ─────────────────────────────────────────

@router.get("")
async def settings_get(request: Request) -> dict:
    env_file = _env_file(request)
    env = _b._read_env(env_file)

    known_keys = {s["key"] for s in SCHEMA}
    fields = []
    for s in SCHEMA:
        cur = env.get(s["key"], s["default"])
        if s["secret"] and cur:
            display = "•" * 10
        else:
            display = cur
        fields.append({**s, "value": display, "is_set": s["key"] in env})

    # Unknown keys → advanced section as raw strings
    advanced = []
    for k, v in env.items():
        if k in known_keys or k in _FORBIDDEN:
            continue
        advanced.append({
            "key":     k,
            "type":    "str",
            "group":   "Advanced",
            "label":   k,
            "value":   v,
            "default": "",
            "desc":    "",
            "requires_restart": True,
            "options": None,
            "secret":  False,
            "is_set":  True,
        })

    groups_order = ["Network","Database","Security","Federation","AI","Operator","Wizard","Advanced"]
    return {
        "fields":       fields + advanced,
        "groups_order": groups_order,
        "forbidden":    sorted(_FORBIDDEN),
        "env_path":     str(env_file),
    }


# ── POST: write one or many ──────────────────────────────────────────────

class PatchBody(BaseModel):
    changes: dict[str, str | bool | int] = Field(..., description="key → new value")


@router.post("")
async def settings_patch(body: PatchBody, request: Request) -> dict:
    env_file = _env_file(request)
    by_key = {s["key"]: s for s in SCHEMA}

    # Refuse forbidden keys
    bad = [k for k in body.changes if k in _FORBIDDEN]
    if bad:
        raise HTTPException(400, f"refusing to modify: {bad}")

    # Coerce + validate
    updates: dict[str, str] = {}
    for k, v in body.changes.items():
        spec = by_key.get(k)
        if spec is None:
            # Advanced key — accept as plain string, truncate
            updates[k] = str(v)[:4096]
            continue
        if spec["type"] == "bool":
            b = bool(v) if isinstance(v, bool) else str(v).lower() in ("1","true","yes","on")
            updates[k] = "true" if b else "false"
        elif spec["type"] == "int":
            try: updates[k] = str(int(v))
            except Exception: raise HTTPException(400, f"{k}: expected int, got {v!r}")
        elif spec["type"] == "select":
            s = str(v)
            if spec.get("options") and s not in spec["options"]:
                raise HTTPException(400, f"{k}: must be one of {spec['options']}")
            updates[k] = s
        elif spec["type"] == "password":
            updates[k] = str(v)   # stored plaintext in .env — FS permissions protect it
        else:
            updates[k] = str(v)[:4096]

    if not updates:
        return {"ok": True, "updated": 0}

    _sec._write_env_keys(env_file, updates)

    requires_restart = any(
        by_key.get(k, {}).get("requires_restart", True)
        for k in updates
    )
    return {
        "ok":              True,
        "updated":         len(updates),
        "keys":            sorted(updates.keys()),
        "requires_restart": requires_restart,
    }


# ── DELETE single key ─────────────────────────────────────────────────────

@router.delete("/{key}")
async def settings_delete(key: str, request: Request) -> dict:
    if key in _FORBIDDEN:
        raise HTTPException(400, "refusing to remove protected key")
    env_file = _env_file(request)
    env = _b._read_env(env_file)
    if key not in env:
        return {"ok": True, "already_missing": True}

    lines = []
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key}="):
                continue
            lines.append(line)
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "removed": key}


# ── Secret-reveal (requires passphrase-like confirm) ─────────────────────

class RevealBody(BaseModel):
    key:      str
    confirm:  str    # must equal "REVEAL"


@router.post("/reveal")
async def settings_reveal(body: RevealBody, request: Request) -> dict:
    if body.confirm != "REVEAL":
        raise HTTPException(400, "must pass confirm='REVEAL'")
    if body.key in _FORBIDDEN:
        raise HTTPException(400, "key is permanently hidden")
    env = _b._read_env(_env_file(request))
    return {"key": body.key, "value": env.get(body.key, "")}
