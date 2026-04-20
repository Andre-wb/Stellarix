"""Wave 5 — Secrets management.

  #21 HashiCorp Vault integration — pull JWT_SECRET / CSRF_SECRET from Vault on demand
  #22 AWS / GCP Secrets Manager  — same with cloud provider APIs
  #23 Multi-sig key ceremony     — N-of-M admins must approve before secret rotation
  #24 Expiry reminders           — track rotation ages, alert when stale
  #25 Access audit               — every reveal / rotate logged
"""
from __future__ import annotations

import base64
import json
import logging
import os
import secrets as _secrets
import time
from pathlib import Path
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import backup_api as _b
from . import security_api as _sec
from . import alerts as _alerts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin/secrets", tags=["secrets-mgr"])


def _env_file(request: Request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


def _sec_state_path(env_file: Path) -> Path:
    return env_file.parent / "secrets_state.json"


def _load_state(env_file: Path) -> dict:
    p = _sec_state_path(env_file)
    if not p.is_file():
        return {"providers": [], "ceremony": None, "expiries": {}, "access_log": []}
    try:
        d = json.loads(p.read_text())
        d.setdefault("providers", [])
        d.setdefault("ceremony",  None)
        d.setdefault("expiries",  {})
        d.setdefault("access_log",[])
        return d
    except Exception:
        return {"providers": [], "ceremony": None, "expiries": {}, "access_log": []}


def _save_state(env_file: Path, state: dict) -> None:
    _sec_state_path(env_file).write_text(json.dumps(state, indent=2))


# ══════════════════════════════════════════════════════════════════════════
# #21 / #22 — External secret providers (Vault / AWS / GCP)
# ══════════════════════════════════════════════════════════════════════════

class ProviderBody(BaseModel):
    id:       Optional[str] = None
    type:     Literal["vault", "aws", "gcp"]
    name:     str = Field(..., min_length=1, max_length=60)
    # Vault: url, token, path (e.g. secret/vortex)
    # AWS:   region, access_key_id, secret_access_key, secret_id
    # GCP:   project, service_account_json, secret_name
    config:   dict = Field(default_factory=dict)
    enabled:  bool = True


@router.get("/providers")
async def list_providers(request: Request) -> dict:
    state = _load_state(_env_file(request))
    # Mask secret values from config before returning
    safe = []
    for p in state["providers"]:
        c = dict(p); cfg = dict(c.get("config", {}))
        for k in cfg:
            if any(s in k.lower() for s in ("token","key","secret","password","account_json")):
                cfg[k] = "•" * 10 if cfg[k] else ""
        c["config"] = cfg
        safe.append(c)
    return {"providers": safe}


@router.post("/providers")
async def add_provider(body: ProviderBody, request: Request) -> dict:
    env_file = _env_file(request)
    state = _load_state(env_file)
    if body.id:
        for p in state["providers"]:
            if p["id"] == body.id:
                p.update(body.model_dump(exclude_none=True))
                break
        else:
            raise HTTPException(404, "provider not found")
    else:
        pid = _secrets.token_urlsafe(8)
        state["providers"].append({**body.model_dump(), "id": pid})
    _save_state(env_file, state)
    return {"ok": True}


@router.delete("/providers/{pid}")
async def delete_provider(pid: str, request: Request) -> dict:
    env_file = _env_file(request)
    state = _load_state(env_file)
    state["providers"] = [p for p in state["providers"] if p["id"] != pid]
    _save_state(env_file, state)
    return {"ok": True}


class PullBody(BaseModel):
    provider_id: str
    env_key:     str = Field(..., min_length=2, max_length=80)


@router.post("/pull")
async def pull_secret(body: PullBody, request: Request) -> dict:
    """Fetch the named secret from the provider and write into .env.
    Also records access in the audit log."""
    env_file = _env_file(request)
    state = _load_state(env_file)
    prov = next((p for p in state["providers"] if p["id"] == body.provider_id), None)
    if not prov or not prov.get("enabled"):
        raise HTTPException(404, "provider not found or disabled")

    try:
        value = await _fetch_from_provider(prov)
    except Exception as e:
        raise HTTPException(502, f"provider fetch failed: {e}")

    if not isinstance(value, str) or len(value) < 8:
        raise HTTPException(502, "secret value is empty or too short")

    _sec._write_env_keys(env_file, {body.env_key: value})
    state["expiries"][body.env_key] = {
        "pulled_at": int(time.time()),
        "provider":  prov["id"],
    }
    _record_access(state, action="pull", env_key=body.env_key,
                   provider=prov["id"])
    _save_state(env_file, state)
    return {"ok": True, "env_key": body.env_key, "note": "restart the node to apply"}


async def _fetch_from_provider(prov: dict) -> str:
    t = prov["type"]; cfg = prov["config"]
    if t == "vault":
        url = cfg["url"].rstrip("/") + "/v1/" + cfg["path"].lstrip("/")
        async with httpx.AsyncClient(timeout=5.0, verify=True) as c:
            r = await c.get(url, headers={"X-Vault-Token": cfg["token"]})
        r.raise_for_status()
        data = r.json()
        # KV v2 nests under .data.data, KV v1 under .data
        nested = (data.get("data") or {}).get("data") or data.get("data") or {}
        # Take the first non-meta value
        for k, v in nested.items():
            if isinstance(v, str) and v: return v
        raise RuntimeError("no string values in response")

    if t == "aws":
        # Uses the AWS Secrets Manager REST endpoint via SigV4 — simplified
        # to a call through boto3 if installed, else fail.
        import boto3
        region = cfg.get("region", "us-east-1")
        c = boto3.client(
            "secretsmanager", region_name=region,
            aws_access_key_id=cfg["access_key_id"],
            aws_secret_access_key=cfg["secret_access_key"],
        )
        resp = c.get_secret_value(SecretId=cfg["secret_id"])
        return resp.get("SecretString") or base64.b64decode(resp["SecretBinary"]).decode()

    if t == "gcp":
        from google.cloud import secretmanager  # type: ignore[import-untyped]
        from google.oauth2 import service_account  # type: ignore[import-untyped]
        creds = service_account.Credentials.from_service_account_info(
            json.loads(cfg["service_account_json"]))
        client = secretmanager.SecretManagerServiceClient(credentials=creds)
        name = f"projects/{cfg['project']}/secrets/{cfg['secret_name']}/versions/latest"
        resp = client.access_secret_version(request={"name": name})
        return resp.payload.data.decode("utf-8")

    raise ValueError(f"unknown provider type: {t}")


# ══════════════════════════════════════════════════════════════════════════
# #23 — Multi-sig key ceremony
# ══════════════════════════════════════════════════════════════════════════
#
# Destructive operations (wipe, JWT rotation, panic) can require N-of-M
# admin approvals before executing. Ceremony record stores pending +
# approved signers.

class CeremonyConfigBody(BaseModel):
    required_approvals: int = Field(2, ge=1, le=10)
    admin_pubkeys:      list[str] = Field(...,
                            description="Ed25519 pubkeys of admin signers, hex")


@router.get("/ceremony")
async def ceremony_config(request: Request) -> dict:
    state = _load_state(_env_file(request))
    return {"ceremony": state.get("ceremony")}


@router.post("/ceremony")
async def set_ceremony(body: CeremonyConfigBody, request: Request) -> dict:
    env_file = _env_file(request)
    state = _load_state(env_file)
    if body.required_approvals > len(body.admin_pubkeys):
        raise HTTPException(400, "required_approvals > len(admin_pubkeys)")
    state["ceremony"] = {
        "required_approvals": body.required_approvals,
        "admin_pubkeys":      [p.lower() for p in body.admin_pubkeys],
        "pending":             [],
        "configured_at":       int(time.time()),
    }
    _save_state(env_file, state)
    return {"ok": True}


class StartCeremonyBody(BaseModel):
    action: Literal["rotate_jwt", "rotate_csrf", "panic_wipe"]


@router.post("/ceremony/start")
async def ceremony_start(body: StartCeremonyBody, request: Request) -> dict:
    env_file = _env_file(request)
    state = _load_state(env_file)
    if not state.get("ceremony"):
        raise HTTPException(400, "ceremony not configured")
    req_id = _secrets.token_urlsafe(10)
    pending = state["ceremony"].setdefault("pending", [])
    pending.append({
        "id":         req_id,
        "action":     body.action,
        "opened_at":  int(time.time()),
        "signatures": [],
    })
    _save_state(env_file, state)
    _record_access(state, action=f"ceremony_start:{body.action}", env_key="", provider="")
    _save_state(env_file, state)
    return {"ok": True, "ceremony_id": req_id,
            "need_approvals": state["ceremony"]["required_approvals"]}


class ApproveBody(BaseModel):
    ceremony_id: str
    pubkey:      str
    signature:   str = Field(..., min_length=128, max_length=128)


@router.post("/ceremony/approve")
async def ceremony_approve(body: ApproveBody, request: Request) -> dict:
    env_file = _env_file(request)
    state = _load_state(env_file)
    cer = state.get("ceremony") or {}
    if body.pubkey.lower() not in cer.get("admin_pubkeys", []):
        raise HTTPException(403, "not an admin signer")
    target = None
    for p in cer.get("pending", []):
        if p["id"] == body.ceremony_id:
            target = p; break
    if not target:
        raise HTTPException(404, "ceremony not found")

    # Verify Ed25519 signature over "{action}:{ceremony_id}"
    msg = f"{target['action']}:{body.ceremony_id}".encode()
    try:
        try:
            import vortex_chat as _vc
            ok = _vc.verify_signature(bytes.fromhex(body.pubkey),
                                      msg, bytes.fromhex(body.signature))
        except Exception:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(body.pubkey)).verify(
                bytes.fromhex(body.signature), msg
            )
            ok = True
    except Exception:
        raise HTTPException(401, "signature invalid")
    if not ok:
        raise HTTPException(401, "signature invalid")

    if any(s["pubkey"] == body.pubkey.lower() for s in target["signatures"]):
        return {"ok": True, "already_signed": True,
                "count": len(target["signatures"]),
                "need":  cer["required_approvals"]}

    target["signatures"].append({
        "pubkey":   body.pubkey.lower(),
        "at":       int(time.time()),
        "sig":      body.signature,
    })

    fired = None
    if len(target["signatures"]) >= cer["required_approvals"]:
        fired = await _execute_ceremony(env_file, target, state)
        # Remove from pending
        cer["pending"] = [p for p in cer["pending"] if p["id"] != target["id"]]
    _save_state(env_file, state)
    return {
        "ok":      True,
        "count":   len(target["signatures"]),
        "need":    cer["required_approvals"],
        "fired":   fired,
    }


async def _execute_ceremony(env_file: Path, target: dict, state: dict) -> str:
    """Run the approved destructive action."""
    action = target["action"]
    if action == "rotate_jwt":
        from . import security_api as _ss
        await _ss.job_jwt_rotate(env_file)  # type: ignore[arg-type]
        _record_access(state, action="ceremony_exec:rotate_jwt", env_key="JWT_SECRET", provider="")
        return "rotate_jwt"
    if action == "rotate_csrf":
        new = _secrets.token_urlsafe(48)
        _sec._write_env_keys(env_file, {"CSRF_SECRET": new})
        _record_access(state, action="ceremony_exec:rotate_csrf", env_key="CSRF_SECRET", provider="")
        return "rotate_csrf"
    if action == "panic_wipe":
        # Same as the panic endpoint but invoked by multi-sig approval.
        from . import security_api as _ss
        class _Body:
            confirm = "WIPE AND STOP"
        class _Req:
            def __init__(self, ef):
                class _S: pass
                self.app = type('a', (), {'state': _S()})
                self.app.state.env_file = ef
        await _ss.panic(_Body(), _Req(env_file))  # type: ignore[arg-type]
        _record_access(state, action="ceremony_exec:panic_wipe", env_key="", provider="")
        return "panic_wipe"
    return "unknown"


# ══════════════════════════════════════════════════════════════════════════
# #24 — Expiry reminders
# ══════════════════════════════════════════════════════════════════════════

DEFAULT_MAX_AGE_DAYS = {
    "JWT_SECRET":  90,
    "CSRF_SECRET": 90,
    "LETSENCRYPT_": 30,   # cert expiry checked separately elsewhere
}


async def job_secret_expiry(env_file: Path) -> dict:
    state = _load_state(env_file)
    env = _b._read_env(env_file)
    now = int(time.time())
    stale = []
    for key, meta in (state.get("expiries") or {}).items():
        pulled = int(meta.get("pulled_at", 0))
        age_d = (now - pulled) / 86400
        max_age = None
        for prefix, days in DEFAULT_MAX_AGE_DAYS.items():
            if key.startswith(prefix):
                max_age = days; break
        if max_age and age_d > max_age:
            stale.append({"key": key, "age_days": round(age_d, 1), "max": max_age})

    # Also look at secrets in .env never pulled from provider — estimate
    # from backup_last.meta if older than max_age
    if stale:
        await _alerts.dispatch(
            env_file, severity="warning",
            title="Secrets past rotation deadline",
            body=json.dumps(stale, indent=2),
            tags=["secret_expiry"],
        )
    return {"message": f"{len(stale)} stale secrets", "stale": stale}


def install_secrets_jobs(env_file: Path) -> None:
    from . import scheduler as _sched
    s = _sched.get(env_file)
    s.register("secret_expiry", job_secret_expiry, default_interval="daily")


# ══════════════════════════════════════════════════════════════════════════
# #25 — Access audit
# ══════════════════════════════════════════════════════════════════════════

def _record_access(state: dict, action: str, env_key: str, provider: str) -> None:
    log = state.setdefault("access_log", [])
    log.append({
        "ts":       int(time.time()),
        "action":   action,
        "env_key":  env_key,
        "provider": provider,
    })
    state["access_log"] = log[-2000:]


@router.get("/audit")
async def access_audit(request: Request, limit: int = 200) -> dict:
    state = _load_state(_env_file(request))
    log = state.get("access_log", [])
    return {"entries": log[-limit:][::-1], "total": len(log)}
