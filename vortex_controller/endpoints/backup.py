"""POST /v1/backup* — Encrypted backup storage.

The controller stores *opaque* ciphertext blobs on behalf of nodes. Every
request is signed with the node's Ed25519 key so a stranger can't
retrieve or overwrite someone else's backup.

Endpoints (all POST because every request carries a signed payload):
    /v1/backup         — upload or replace the blob
    /v1/backup/fetch   — download the blob
    /v1/backup/meta    — return metadata without the blob
    /v1/backup/delete  — remove the backup

The controller NEVER sees plaintext. Key derivation, encryption, and
decryption happen exclusively on the node side (see
``app/backup/client.py``).
"""
from __future__ import annotations

import base64
import time
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..controller_crypto import verify_signature

router = APIRouter(prefix="/v1/backup", tags=["backup"])

# Clock skew allowance for replay protection (same as /v1/register).
MAX_CLOCK_SKEW_SEC = 300


class PutBackupPayload(BaseModel):
    action:    Literal["put"]         = "put"
    pubkey:    str                    = Field(..., min_length=64, max_length=128, pattern=r"^[0-9a-f]+$")
    sha256:    str                    = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    byte_size: int                    = Field(..., ge=1)
    blob_b64:  str                    = Field(..., min_length=4)
    timestamp: int                    = Field(..., ge=0)


class FetchBackupPayload(BaseModel):
    action:    Literal["fetch", "meta", "delete"]
    pubkey:    str                    = Field(..., min_length=64, max_length=128, pattern=r"^[0-9a-f]+$")
    timestamp: int                    = Field(..., ge=0)


class SignedPutBackup(BaseModel):
    payload:   PutBackupPayload
    signature: str = Field(..., min_length=128, max_length=128, pattern=r"^[0-9a-f]{128}$")


class SignedFetchBackup(BaseModel):
    payload:   FetchBackupPayload
    signature: str = Field(..., min_length=128, max_length=128, pattern=r"^[0-9a-f]{128}$")


def _within_skew(ts: int) -> bool:
    return abs(int(time.time()) - ts) <= MAX_CLOCK_SKEW_SEC


def _verify(body_payload, body_signature: str) -> None:
    if not _within_skew(body_payload.timestamp):
        raise HTTPException(400, "timestamp too far from server clock")
    if not verify_signature(
        pubkey_hex    = body_payload.pubkey,
        signature_hex = body_signature,
        payload       = body_payload.model_dump(),
    ):
        raise HTTPException(401, "invalid signature")


@router.post("")
async def put_backup(req: SignedPutBackup, request: Request) -> dict:
    _verify(req.payload, req.signature)

    try:
        blob = base64.b64decode(req.payload.blob_b64, validate=True)
    except Exception:
        raise HTTPException(400, "blob_b64 is not valid base64")

    if len(blob) != req.payload.byte_size:
        raise HTTPException(400, "byte_size mismatch")

    # Cheap integrity check — mostly to stop truncated uploads silently winning.
    import hashlib as _h
    if _h.sha256(blob).hexdigest() != req.payload.sha256:
        raise HTTPException(400, "sha256 mismatch (transport corruption?)")

    storage = request.app.state.storage
    try:
        info = await storage.put_backup(req.payload.pubkey, blob, req.payload.sha256)
    except ValueError as e:
        raise HTTPException(413, str(e))
    return {"ok": True, **info}


@router.post("/fetch")
async def fetch_backup(req: SignedFetchBackup, request: Request) -> dict:
    if req.payload.action != "fetch":
        raise HTTPException(400, "expected action='fetch'")
    _verify(req.payload, req.signature)

    storage = request.app.state.storage
    row = await storage.get_backup(req.payload.pubkey)
    if not row:
        raise HTTPException(404, "no backup found")

    return {
        "ok":          True,
        "pubkey_hex":  row["pubkey_hex"],
        "sha256":      row["sha256"],
        "byte_size":   row["byte_size"],
        "created_at":  row["created_at"],
        "updated_at":  row["updated_at"],
        "blob_b64":    base64.b64encode(row["blob"]).decode("ascii"),
    }


@router.post("/meta")
async def meta_backup(req: SignedFetchBackup, request: Request) -> dict:
    if req.payload.action != "meta":
        raise HTTPException(400, "expected action='meta'")
    _verify(req.payload, req.signature)

    storage = request.app.state.storage
    row = await storage.get_backup_meta(req.payload.pubkey)
    if not row:
        return {"ok": True, "exists": False}
    return {"ok": True, "exists": True, **row}


@router.post("/delete")
async def delete_backup(req: SignedFetchBackup, request: Request) -> dict:
    if req.payload.action != "delete":
        raise HTTPException(400, "expected action='delete'")
    _verify(req.payload, req.signature)

    storage = request.app.state.storage
    deleted = await storage.delete_backup(req.payload.pubkey)
    return {"ok": True, "deleted": bool(deleted)}
