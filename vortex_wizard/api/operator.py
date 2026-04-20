"""Wave 10 — failover mirror + operator finance.

  1. #44 Failover mirror   — push encrypted backup to a SECOND controller
                             so losing primary doesn't orphan the node.
  2. #47 Staking wizard    — build (unsigned) Solana stake / unstake txs
                             the client can sign with the wallet key.
  3. #48 Payout history    — enumerate historical payouts (read marker
                             file + on-chain events if available).
  4. #49 Tax export        — CSV of payouts for FIFO cost-basis.
  5. #50 Autocompound      — config flag + scheduled job that restakes
                             idle rewards.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import logging
import time
from pathlib import Path
from typing import Optional

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import backup_api as _b
from . import security_api as _sec
from . import scheduler as _sched

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin/op", tags=["operator"])


def _env_file(request: Request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


# ══════════════════════════════════════════════════════════════════════════
# 1. Failover mirror (#44)
# ══════════════════════════════════════════════════════════════════════════

class MirrorBody(BaseModel):
    controller_url: str = Field(..., min_length=8, max_length=2048)
    enabled:        bool = True


@router.get("/mirror")
async def mirror_get(request: Request) -> dict:
    env = _b._read_env(_env_file(request))
    return {
        "enabled":        env.get("MIRROR_ENABLED", "").lower() in ("1","true","yes"),
        "mirror_url":     env.get("MIRROR_CONTROLLER_URL", ""),
        "primary_url":    env.get("CONTROLLER_URL", ""),
    }


@router.post("/mirror")
async def mirror_set(body: MirrorBody, request: Request) -> dict:
    env_file = _env_file(request)
    _sec._write_env_keys(env_file, {
        "MIRROR_ENABLED":        "true" if body.enabled else "false",
        "MIRROR_CONTROLLER_URL": body.controller_url if body.enabled else "",
    })
    return {"ok": True}


async def job_mirror_backup(env_file: Path) -> dict:
    """Scheduled job — mirrors the latest blob to MIRROR_CONTROLLER_URL
    if configured and differs from the primary."""
    env = _b._read_env(env_file)
    if env.get("MIRROR_ENABLED", "").lower() not in ("1", "true", "yes"):
        return {"skipped": True, "message": "mirror disabled"}
    mirror_url = env.get("MIRROR_CONTROLLER_URL", "").rstrip("/")
    if not mirror_url or mirror_url == env.get("CONTROLLER_URL", "").rstrip("/"):
        return {"skipped": True, "message": "no separate mirror configured"}

    # Reuse the same encrypted-blob path as cron_backup, but ship to the
    # mirror instead.
    is_sq, db_path = _b._is_sqlite(env, env_file.parent)
    if not is_sq or not db_path or not db_path.is_file():
        return {"skipped": True, "message": "no sqlite file"}

    priv_bytes = _b._signing_key_bytes(env_file)
    priv = Ed25519PrivateKey.from_private_bytes(priv_bytes)
    pub = _b._node_pubkey_hex(priv)
    blob_key = _b._derive_blob_key(priv_bytes)
    plaintext = _b._sqlite_snapshot(db_path)
    blob = _b._encrypt_blob(plaintext, blob_key)
    sha = hashlib.sha256(blob).hexdigest()

    payload = {
        "action":    "put",
        "pubkey":    pub,
        "sha256":    sha,
        "byte_size": len(blob),
        "blob_b64":  base64.b64encode(blob).decode("ascii"),
        "timestamp": int(time.time()),
    }
    sig = priv.sign(
        json.dumps(payload, sort_keys=True, separators=(",",":")).encode("utf-8")
    ).hex()
    try:
        async with httpx.AsyncClient(timeout=60.0, verify=False) as c:
            r = await c.post(mirror_url + "/v1/backup", json={"payload": payload, "signature": sig})
        if r.status_code >= 400:
            return {"message": f"mirror HTTP {r.status_code}", "ok": False}
    except Exception as e:
        return {"message": f"mirror error: {e}", "ok": False}
    return {"message": f"mirrored {len(blob)} B to {mirror_url}", "byte_size": len(blob)}


# ══════════════════════════════════════════════════════════════════════════
# 2. Staking wizard (#47)
# ══════════════════════════════════════════════════════════════════════════

# We don't sign on the server — the node's wallet key is derived client-
# side. This endpoint returns enough scaffolding for a frontend wallet to
# build & sign a real Solana transaction.

class StakeBuildBody(BaseModel):
    amount_sol:    float = Field(..., ge=0.0001, le=10000)
    action:        str   = Field(..., pattern=r"^(stake|unstake|claim)$")


@router.post("/stake/build")
async def stake_build(body: StakeBuildBody, request: Request) -> dict:
    env = _b._read_env(_env_file(request))
    wallet = env.get("WALLET_PUBKEY", "")
    program_id = env.get("VORTEX_PROGRAM_ID", "8iNKGfNtAwZY8VLnoxardTstm5FFSePR5mN7LUyH4TRR")
    if not wallet:
        raise HTTPException(400, "WALLET_PUBKEY not in .env")
    lamports = int(body.amount_sol * 1_000_000_000)
    return {
        "ok":       True,
        "action":   body.action,
        "wallet":   wallet,
        "program":  program_id,
        "lamports": lamports,
        "note":     "client must build+sign via @solana/web3.js using Anchor IDL",
        "instruction_hint": {
            "stake":   "vortex_registry.stake(lamports)",
            "unstake": "vortex_registry.unstake(lamports)",
            "claim":   "vortex_registry.claim_unstake()",
        }[body.action],
    }


# ══════════════════════════════════════════════════════════════════════════
# 3. Payout history (#48)
# ══════════════════════════════════════════════════════════════════════════

def _payout_log_path(env_file: Path) -> Path:
    return env_file.parent / "payouts.ndjson"


@router.get("/payouts")
async def payouts_list(request: Request, limit: int = 200) -> dict:
    p = _payout_log_path(_env_file(request))
    limit = max(1, min(limit, 1000))
    if not p.is_file():
        return {"payouts": [], "total": 0, "note": "no on-chain events observed yet"}
    rows: list[dict] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            try: rows.append(json.loads(line))
            except Exception: continue
    rows.sort(key=lambda r: r.get("ts", 0), reverse=True)
    return {"payouts": rows[:limit], "total": len(rows)}


class PayoutRecordBody(BaseModel):
    lamports:   int    = Field(..., ge=0)
    ts:         int    = Field(..., ge=0)
    tx_sig:     str    = Field(..., max_length=200)
    note:       Optional[str] = Field(None, max_length=200)


@router.post("/payouts")
async def payout_record(body: PayoutRecordBody, request: Request) -> dict:
    """Record a payout event. Invoked by the node when it observes an
    on-chain transfer to its wallet, or manually by the operator."""
    env_file = _env_file(request)
    p = _payout_log_path(env_file)
    entry = body.model_dump()
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return {"ok": True, "recorded": entry}


# ══════════════════════════════════════════════════════════════════════════
# 4. Tax CSV export (#49)
# ══════════════════════════════════════════════════════════════════════════

@router.get("/payouts.csv")
async def payouts_csv(request: Request) -> Response:
    env_file = _env_file(request)
    p = _payout_log_path(env_file)
    rows: list[dict] = []
    if p.is_file():
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                try: rows.append(json.loads(line))
                except Exception: continue

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date_utc", "epoch", "amount_sol", "amount_lamports", "tx_sig", "note"])
    for r in sorted(rows, key=lambda x: x.get("ts", 0)):
        ts = int(r.get("ts", 0))
        lamports = int(r.get("lamports", 0))
        w.writerow([
            time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts)),
            ts,
            f"{lamports / 1_000_000_000:.9f}",
            lamports,
            r.get("tx_sig", ""),
            r.get("note", ""),
        ])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="vortex-payouts.csv"'},
    )


# ══════════════════════════════════════════════════════════════════════════
# 5. Autocompound (#50)
# ══════════════════════════════════════════════════════════════════════════

class AutocompoundBody(BaseModel):
    enabled:       bool
    threshold_sol: float = Field(1.0, ge=0.01, le=10000.0)


@router.get("/autocompound")
async def autocompound_get(request: Request) -> dict:
    env = _b._read_env(_env_file(request))
    return {
        "enabled":        env.get("AUTOCOMPOUND_ENABLED", "").lower() in ("1","true","yes"),
        "threshold_sol":  float(env.get("AUTOCOMPOUND_THRESHOLD", "1.0") or 1.0),
    }


@router.post("/autocompound")
async def autocompound_set(body: AutocompoundBody, request: Request) -> dict:
    env_file = _env_file(request)
    _sec._write_env_keys(env_file, {
        "AUTOCOMPOUND_ENABLED":   "true" if body.enabled else "false",
        "AUTOCOMPOUND_THRESHOLD": str(body.threshold_sol),
    })
    return {"ok": True}


async def job_autocompound(env_file: Path) -> dict:
    """Sum recent payouts; if threshold is reached, stage a stake tx for
    the client to sign. We never sign on-chain ourselves — the operator
    has to approve in their wallet."""
    env = _b._read_env(env_file)
    if env.get("AUTOCOMPOUND_ENABLED", "").lower() not in ("1","true","yes"):
        return {"skipped": True, "message": "autocompound disabled"}

    try:
        threshold = float(env.get("AUTOCOMPOUND_THRESHOLD", "1.0"))
    except ValueError:
        threshold = 1.0
    threshold_lamports = int(threshold * 1_000_000_000)

    p = _payout_log_path(env_file)
    if not p.is_file():
        return {"skipped": True, "message": "no payouts yet"}

    # Sum payouts newer than the last compound marker.
    marker_path = env_file.parent / "autocompound_last.json"
    last_ts = 0
    if marker_path.is_file():
        try: last_ts = int(json.loads(marker_path.read_text()).get("last_ts", 0))
        except Exception: pass

    pending = 0
    latest_ts = last_ts
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                ts = int(r.get("ts", 0))
                if ts > last_ts:
                    pending += int(r.get("lamports", 0))
                    latest_ts = max(latest_ts, ts)
            except Exception:
                continue

    if pending < threshold_lamports:
        return {
            "skipped":  True,
            "message":  f"pending {pending / 1e9:.3f} SOL < threshold {threshold}",
        }

    # Stage a stake-candidate file so the frontend wallet flow picks it
    # up on next admin login.
    candidate_path = env_file.parent / "autocompound_candidate.json"
    candidate_path.write_text(json.dumps({
        "action":    "stake",
        "lamports":  pending,
        "amount_sol": pending / 1_000_000_000,
        "staged_at": int(time.time()),
        "latest_payout_ts": latest_ts,
    }))
    marker_path.write_text(json.dumps({"last_ts": latest_ts}))
    return {
        "message":   f"candidate staged: restake {pending / 1e9:.3f} SOL",
        "lamports":  pending,
    }


@router.get("/autocompound/candidate")
async def autocompound_candidate_get(request: Request) -> dict:
    p = _env_file(request).parent / "autocompound_candidate.json"
    if not p.is_file():
        return {"pending": False}
    try:
        return {"pending": True, **json.loads(p.read_text())}
    except Exception:
        return {"pending": False}


@router.delete("/autocompound/candidate")
async def autocompound_candidate_clear(request: Request) -> dict:
    p = _env_file(request).parent / "autocompound_candidate.json"
    if p.is_file():
        p.unlink()
    return {"ok": True}


# ── Register jobs with the wizard scheduler ───────────────────────────────

def install_jobs(env_file: Path) -> None:
    s = _sched.get(env_file)
    s.register("mirror_backup",  job_mirror_backup,  default_interval="daily")
    s.register("autocompound",   job_autocompound,   default_interval="weekly")
