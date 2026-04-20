"""Encrypted backup & restore to the controller.

The wizard reads the node's local SQLite database, encrypts it with a key
derived from the node's Ed25519 signing key, and uploads the opaque blob
to the controller over HTTPS. The controller stores ciphertext only — it
cannot decrypt.

On recovery (new machine with the same 24-word seed phrase), the wizard
re-derives the same signing key, fetches the blob, decrypts, and replaces
the local DB file. Same seed = same node identity = same blob key, so the
whole flow works offline-once-the-wizard-runs.

Current limitations (documented so users know what to expect):
  - SQLite only. Postgres nodes can still back up local wizard files but
    the DB itself must be dumped manually via pg_dump (future work).
  - The node must be stopped before /restore (we overwrite the .db file).
  - Blob size capped at 64 MiB (matches controller MAX_BACKUP_BYTES).
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import io
import logging
import os
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin/backup", tags=["backup"])


# ── Constants ─────────────────────────────────────────────────────────────

_BLOB_MAGIC  = b"VTXBK1"     # 6-byte magic so we reject stray files
_NONCE_LEN   = 12
_KEY_LEN     = 32
_HKDF_INFO   = b"vortex-backup-key-v1"
_CLIENT_TIMEOUT = 60.0       # generous — uploads can take a while


def _canonical(data: Any) -> bytes:
    import json as _json
    return _json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


# ── Env / file discovery ──────────────────────────────────────────────────

def _env_path(request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


def _read_env(env_file: Path) -> dict[str, str]:
    if not env_file.is_file():
        return {}
    out: dict[str, str] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def _node_root(env_file: Path) -> Path:
    return env_file.parent


def _signing_key_bytes(env_file: Path) -> bytes:
    """Read the raw 32-byte Ed25519 private key from the node's keys dir.

    Never leaves this machine — only used to derive the backup key locally.
    """
    env = _read_env(env_file)
    keys_dir = Path(env.get("KEYS_DIR", str(env_file.parent / "keys")))
    sig_path = keys_dir / "ed25519_signing.bin"
    if not sig_path.is_file():
        raise HTTPException(400, "node signing key missing; run setup first")
    data = sig_path.read_bytes()
    if len(data) != 32:
        raise HTTPException(500, f"unexpected signing key length: {len(data)}")
    return data


def _signing_priv(env_file: Path) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_signing_key_bytes(env_file))


def _node_pubkey_hex(priv: Ed25519PrivateKey) -> str:
    return priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()


def _derive_blob_key(priv_bytes: bytes) -> bytes:
    """HKDF-SHA256 over the signing key. Same seed → same derived key."""
    return HKDF(
        algorithm = hashes.SHA256(),
        length    = _KEY_LEN,
        salt      = None,
        info      = _HKDF_INFO,
    ).derive(priv_bytes)


# ── SQLite snapshot ───────────────────────────────────────────────────────

def _is_sqlite(env: dict, node_root: Optional[Path] = None) -> tuple[bool, Optional[Path]]:
    """Return (is_sqlite, absolute_path_to_db_file).

    Mirrors ``Config.get_database_url`` default:
      1. DATABASE_URL is set → parse sqlite path (or return False for Postgres)
      2. DATABASE_URL unset → default to ``<node_root>/<DB_PATH or "vortex.db">``
    """
    db_url = env.get("DATABASE_URL", "").strip()
    if db_url and not db_url.startswith("sqlite"):
        return False, None

    path_str = ""
    if db_url.startswith("sqlite:///"):
        path_str = db_url[len("sqlite:///"):]
    elif db_url.startswith("sqlite+aiosqlite:///"):
        path_str = db_url[len("sqlite+aiosqlite:///"):]
    if not path_str:
        # No URL set — fall back to the same default app/config.Config uses.
        path_str = env.get("DB_PATH", "").strip() or "vortex.db"

    p = Path(path_str)
    if not p.is_absolute() and node_root is not None:
        p = (node_root / p).resolve()
    return True, p


def _sqlite_snapshot(src: Path) -> bytes:
    """Return a consistent byte snapshot of a live SQLite DB.

    Uses the online ``backup`` API so we don't trip over WAL/journal files
    or concurrent writes from a running node.
    """
    if not src.is_file():
        raise HTTPException(404, f"database file not found: {src}")
    with tempfile.NamedTemporaryFile(
        suffix=".db", delete=False, dir=str(src.parent)
    ) as tmp_f:
        tmp_path = Path(tmp_f.name)
    try:
        src_conn = sqlite3.connect(str(src))
        try:
            dst_conn = sqlite3.connect(str(tmp_path))
            try:
                src_conn.backup(dst_conn)
            finally:
                dst_conn.close()
        finally:
            src_conn.close()
        return tmp_path.read_bytes()
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


# ── Encrypt / decrypt blob ────────────────────────────────────────────────

def _encrypt_blob(plaintext: bytes, blob_key: bytes) -> bytes:
    gz = gzip.compress(plaintext, compresslevel=6)
    aes = AESGCM(blob_key)
    nonce = os.urandom(_NONCE_LEN)
    ct = aes.encrypt(nonce, gz, _BLOB_MAGIC)
    return _BLOB_MAGIC + nonce + ct


def _decrypt_blob(blob: bytes, blob_key: bytes) -> bytes:
    if len(blob) < len(_BLOB_MAGIC) + _NONCE_LEN + 16:
        raise HTTPException(400, "blob too short")
    if blob[: len(_BLOB_MAGIC)] != _BLOB_MAGIC:
        raise HTTPException(400, "wrong blob magic (not a vortex backup?)")
    nonce = blob[len(_BLOB_MAGIC) : len(_BLOB_MAGIC) + _NONCE_LEN]
    ct    = blob[len(_BLOB_MAGIC) + _NONCE_LEN :]
    aes   = AESGCM(blob_key)
    try:
        gz = aes.decrypt(nonce, ct, _BLOB_MAGIC)
    except Exception:
        raise HTTPException(400, "decrypt failed — wrong key or corrupted blob")
    try:
        return gzip.decompress(gz)
    except Exception:
        raise HTTPException(400, "decompression failed")


# ── Signed controller request ─────────────────────────────────────────────

def _controller_url(env: dict) -> str:
    url = env.get("CONTROLLER_URL", "").strip().rstrip("/")
    if not url:
        raise HTTPException(400, "CONTROLLER_URL not set in .env")
    return url


async def _post_signed(controller_url: str, path: str, payload: dict,
                        priv: Ed25519PrivateKey) -> dict:
    sig = priv.sign(_canonical(payload)).hex()
    body = {"payload": payload, "signature": sig}
    url = f"{controller_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=_CLIENT_TIMEOUT, verify=False) as client:
            r = await client.post(url, json=body)
    except httpx.ConnectError:
        raise HTTPException(503, f"controller unreachable at {controller_url} — is it running?")
    except httpx.TimeoutException:
        raise HTTPException(504, f"controller timeout at {controller_url}")
    except Exception as e:
        raise HTTPException(502, f"controller request failed: {type(e).__name__}: {e}")

    if r.status_code == 404:
        # Specific hint — most common cause is an old controller deploy
        # that doesn't have the /v1/backup endpoints yet.
        raise HTTPException(
            404,
            f"controller at {controller_url} doesn't expose {path}. "
            "Either it's an older build (upgrade to one with vortex_controller/endpoints/backup.py), "
            "or your CONTROLLER_URL in .env points to the wrong service."
        )
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail") or r.text
        except Exception:
            detail = r.text
        raise HTTPException(r.status_code, f"controller rejected: {detail}")
    return r.json()


# ── Endpoints ─────────────────────────────────────────────────────────────

class RestoreBody(BaseModel):
    confirm: bool = False


@router.get("/status")
async def backup_status(request: Request) -> dict:
    """Return backup status: does a blob exist on the controller?"""
    env_file = _env_path(request)
    env = _read_env(env_file)
    is_sq, db_path = _is_sqlite(env, _node_root(env_file))
    ctrl_url = env.get("CONTROLLER_URL", "").strip()
    out: dict[str, Any] = {
        "supported":          is_sq,
        "database_backend":   "sqlite" if is_sq else "postgres",
        "database_path":      str(db_path) if db_path else None,
        "database_exists":    bool(db_path and db_path.is_file()),
        "database_byte_size": db_path.stat().st_size if (db_path and db_path.is_file()) else 0,
        "controller_url":     ctrl_url,
        "controller_reachable": False,
        "remote_exists":      False,
        "remote_updated_at":  None,
        "remote_byte_size":   None,
        "remote_sha256":      None,
    }
    if not ctrl_url:
        return out

    # Query controller for our blob's metadata — signed so we can't phish
    # someone else's pubkey.
    try:
        priv = _signing_priv(env_file)
    except HTTPException:
        return out
    pub = _node_pubkey_hex(priv)

    try:
        payload = {"action": "meta", "pubkey": pub, "timestamp": int(time.time())}
        res = await _post_signed(ctrl_url.rstrip("/"), "/v1/backup/meta", payload, priv)
        out["controller_reachable"] = True
        if res.get("exists"):
            out["remote_exists"]     = True
            out["remote_updated_at"] = res.get("updated_at")
            out["remote_byte_size"]  = res.get("byte_size")
            out["remote_sha256"]     = res.get("sha256")
    except HTTPException as e:
        out["controller_error"] = e.detail
    except Exception as e:
        out["controller_error"] = f"{type(e).__name__}: {e}"

    return out


@router.post("/upload")
async def backup_upload(request: Request) -> dict:
    env_file = _env_path(request)
    env = _read_env(env_file)
    is_sq, db_path = _is_sqlite(env, _node_root(env_file))
    if not is_sq:
        raise HTTPException(400, "backup currently supports SQLite nodes only")
    if not db_path or not db_path.is_file():
        raise HTTPException(404, f"database file missing: {db_path}")

    priv_bytes = _signing_key_bytes(env_file)
    priv       = Ed25519PrivateKey.from_private_bytes(priv_bytes)
    pub        = _node_pubkey_hex(priv)
    blob_key   = _derive_blob_key(priv_bytes)

    plaintext  = _sqlite_snapshot(db_path)
    blob       = _encrypt_blob(plaintext, blob_key)
    sha256_hex = hashlib.sha256(blob).hexdigest()
    byte_size  = len(blob)

    ctrl_url = _controller_url(env)
    payload = {
        "action":    "put",
        "pubkey":    pub,
        "sha256":    sha256_hex,
        "byte_size": byte_size,
        "blob_b64":  base64.b64encode(blob).decode("ascii"),
        "timestamp": int(time.time()),
    }
    res = await _post_signed(ctrl_url, "/v1/backup", payload, priv)

    # Drop a tiny marker file so the Prometheus exporter can surface
    # "last backup at T" without re-querying the controller.
    try:
        import json as _json
        (env_file.parent / "backup_last.meta").write_text(_json.dumps({
            "updated_at": res.get("updated_at") or int(time.time()),
            "byte_size":  byte_size,
            "sha256":     sha256_hex,
        }))
    except Exception:
        pass

    logger.info("backup uploaded: %d bytes, sha256=%s", byte_size, sha256_hex[:12])
    return {
        "ok":         True,
        "byte_size":  byte_size,
        "sha256":     sha256_hex,
        "updated_at": res.get("updated_at"),
        "plaintext_byte_size": len(plaintext),
    }


@router.post("/restore")
async def backup_restore(body: RestoreBody, request: Request) -> dict:
    if not body.confirm:
        raise HTTPException(400, "must pass confirm=true — this overwrites the local database")

    env_file = _env_path(request)
    env = _read_env(env_file)
    is_sq, db_path = _is_sqlite(env, _node_root(env_file))
    if not is_sq:
        raise HTTPException(400, "restore currently supports SQLite nodes only")
    if not db_path:
        raise HTTPException(400, "cannot resolve local database path")

    # Safety: don't clobber a running node's db. The wizard admin API
    # already has a node_start/stop — we refuse if the node is listening.
    if _node_is_alive(env):
        raise HTTPException(409, "stop the node before restoring (port still in use)")

    priv_bytes = _signing_key_bytes(env_file)
    priv       = Ed25519PrivateKey.from_private_bytes(priv_bytes)
    pub        = _node_pubkey_hex(priv)
    blob_key   = _derive_blob_key(priv_bytes)
    ctrl_url   = _controller_url(env)

    payload = {"action": "fetch", "pubkey": pub, "timestamp": int(time.time())}
    res = await _post_signed(ctrl_url, "/v1/backup/fetch", payload, priv)

    blob_b64   = res.get("blob_b64") or ""
    sha256_hex = res.get("sha256") or ""
    try:
        blob = base64.b64decode(blob_b64, validate=True)
    except Exception:
        raise HTTPException(500, "controller returned invalid base64")
    if hashlib.sha256(blob).hexdigest() != sha256_hex:
        raise HTTPException(500, "sha256 mismatch on download — blob corrupted")

    plaintext = _decrypt_blob(blob, blob_key)

    # Atomic replace: write to tmp then rename.
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_suffix(".db.restore.tmp")
    tmp.write_bytes(plaintext)
    # Back up the current file (if any) before swap so the user can rollback.
    if db_path.is_file():
        bak = db_path.with_suffix(".db.pre-restore.bak")
        shutil.copy2(db_path, bak)
    os.replace(tmp, db_path)

    logger.info("backup restored: %d bytes plaintext into %s", len(plaintext), db_path)
    return {
        "ok":                True,
        "restored_to":       str(db_path),
        "plaintext_byte_size": len(plaintext),
        "blob_byte_size":    len(blob),
    }


@router.post("/delete")
async def backup_delete(request: Request) -> dict:
    env_file = _env_path(request)
    env = _read_env(env_file)
    ctrl_url = _controller_url(env)
    priv = _signing_priv(env_file)
    pub = _node_pubkey_hex(priv)
    payload = {"action": "delete", "pubkey": pub, "timestamp": int(time.time())}
    res = await _post_signed(ctrl_url, "/v1/backup/delete", payload, priv)
    return res


# ── Internal helpers ──────────────────────────────────────────────────────

def _node_is_alive(env: dict) -> bool:
    """True iff something is listening on the node's configured port."""
    import socket
    host = env.get("HOST", "127.0.0.1")
    if host == "0.0.0.0":
        host = "127.0.0.1"
    try:
        port = int(env.get("PORT", "9000"))
    except ValueError:
        return False
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False
