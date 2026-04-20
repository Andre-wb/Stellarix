"""Wave 4 — seed management tools & onboarding helpers.

Bundles 5 features into one module because they all touch the setup/seed
path and share helpers:

  1. Shamir secret split (GF(256)) — K-of-N shares of the 24-word seed.
  2. Duress seed — alternate mnemonic whose hash, when provided at
     restore, yields a fresh empty identity instead of the real one.
  3. Contacts CSV staging — user uploads a CSV during setup, node
     processes it on first boot.
  4. Pre-flight check — ping controller, check cloudflared, port, disk.
  5. Helper to expose "restore from backup" as a first-class setup step
     (wired in the setup HTML; this module just provides the API the UI
     hits to fetch the controller's backup metadata).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets as _secrets
import shutil
import socket
import time
from pathlib import Path
from typing import Optional

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from pydantic import BaseModel, Field

from . import backup_api as _backup_api
from . import security_api as _sec

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/seed", tags=["seed"])


# ══════════════════════════════════════════════════════════════════════════
# 1. Shamir Secret Sharing over GF(256)
# ══════════════════════════════════════════════════════════════════════════
#
# Classic SSS on polynomials over GF(256). Each share is
#     bytes: [version (1B)] [k (1B)] [idx (1B)] [y-values (N-1 B)]
# where y-values are evaluated at x=idx, one per byte of the input.
# Reconstruction uses Lagrange interpolation at x=0.
#
# GF(256) table-based arithmetic — constant time per byte.

_GF_POLY = 0x11B
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    # Multiply _x by the primitive element 0x03 (= x+1) in GF(2^8).
    # {02} alone is not a generator under this reduction polynomial —
    # its multiplicative order is 51, which would skip most field
    # elements (every value whose gcd with 51 doesn't match).
    _y = (_x << 1)
    if _y & 0x100:
        _y ^= _GF_POLY
    _x = _y ^ _x
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _gf_div(a: int, b: int) -> int:
    if a == 0:
        return 0
    if b == 0:
        raise ZeroDivisionError
    return _EXP[_LOG[a] + 255 - _LOG[b]]


def _eval_poly(coeffs: list[int], x: int) -> int:
    # Horner
    y = 0
    for c in reversed(coeffs):
        y = _gf_mul(y, x) ^ c
    return y


def shamir_split(secret: bytes, k: int, n: int) -> list[bytes]:
    if not (1 <= k <= n <= 255):
        raise ValueError("require 1 <= k <= n <= 255")
    if not secret:
        raise ValueError("empty secret")
    shares_y = [bytearray() for _ in range(n)]
    for byte in secret:
        coeffs = [byte] + [_secrets.randbelow(256) for _ in range(k - 1)]
        for i in range(n):
            shares_y[i].append(_eval_poly(coeffs, i + 1))
    # Prefix each share with (version, k, idx). Version byte 0x01.
    return [
        bytes([0x01, k, i + 1]) + bytes(shares_y[i])
        for i in range(n)
    ]


def shamir_combine(shares: list[bytes]) -> bytes:
    if len(shares) < 1:
        raise ValueError("no shares")
    # Validate shape + common k
    parsed = []
    for s in shares:
        if len(s) < 4 or s[0] != 0x01:
            raise ValueError("invalid share: wrong version/header")
        k = s[1]
        idx = s[2]
        y = s[3:]
        if idx == 0 or idx > 255:
            raise ValueError("invalid idx")
        parsed.append((k, idx, y))
    k = parsed[0][0]
    if not all(p[0] == k for p in parsed):
        raise ValueError("shares disagree on k")
    if len(parsed) < k:
        raise ValueError(f"need at least {k} shares, got {len(parsed)}")
    secret_len = len(parsed[0][2])
    if not all(len(p[2]) == secret_len for p in parsed):
        raise ValueError("shares have different lengths")

    # Use exactly k shares (the first k valid ones). Duplicate idx is
    # treated as an error.
    use = parsed[:k]
    seen = set()
    for p in use:
        if p[1] in seen:
            raise ValueError("duplicate share idx")
        seen.add(p[1])

    out = bytearray(secret_len)
    for byte_idx in range(secret_len):
        total = 0
        for j in range(k):
            xj, yj = use[j][1], use[j][2][byte_idx]
            num = 1
            den = 1
            for m in range(k):
                if m == j:
                    continue
                xm = use[m][1]
                num = _gf_mul(num, xm)                 # 0 - xm == xm in GF(256)
                den = _gf_mul(den, xj ^ xm)
            total ^= _gf_mul(yj, _gf_div(num, den))
        out[byte_idx] = total
    return bytes(out)


class ShamirSplitBody(BaseModel):
    mnemonic: str = Field(..., min_length=20)
    k:        int = Field(..., ge=2, le=10)
    n:        int = Field(..., ge=2, le=10)


class ShamirCombineBody(BaseModel):
    shares_b64: list[str] = Field(..., min_length=1, max_length=10)


@router.post("/shamir/split")
async def shamir_split_endpoint(body: ShamirSplitBody) -> dict:
    if body.k > body.n:
        raise HTTPException(400, "k must be <= n")
    data = body.mnemonic.strip().encode("utf-8")
    try:
        shares = shamir_split(data, body.k, body.n)
    except Exception as e:
        raise HTTPException(400, str(e))
    return {
        "k": body.k,
        "n": body.n,
        "shares_b64": [base64.urlsafe_b64encode(s).decode("ascii") for s in shares],
        "byte_size":  len(shares[0]),
    }


@router.post("/shamir/combine")
async def shamir_combine_endpoint(body: ShamirCombineBody) -> dict:
    try:
        raw = [base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)) for s in body.shares_b64]
    except Exception:
        raise HTTPException(400, "one of the shares isn't valid base64")
    try:
        secret = shamir_combine(raw)
    except Exception as e:
        raise HTTPException(400, str(e))
    try:
        mnemonic = secret.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "recovered bytes are not valid UTF-8 (wrong shares?)")
    return {"mnemonic": mnemonic}


# ══════════════════════════════════════════════════════════════════════════
# 2. Duress seed
# ══════════════════════════════════════════════════════════════════════════

def _duress_hash(phrase: str) -> str:
    norm = " ".join(phrase.strip().lower().split())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


class DuressSetBody(BaseModel):
    phrase: str = Field(..., min_length=20)


class DuressCheckBody(BaseModel):
    phrase: str = Field(..., min_length=20)


def _duress_state_path(env_file: Path) -> Path:
    return env_file.parent / "duress_state.json"


def _load_duress(env_file: Path) -> dict:
    p = _duress_state_path(env_file)
    if not p.is_file():
        return {}
    try: return json.loads(p.read_text())
    except Exception: return {}


def _save_duress(env_file: Path, state: dict) -> None:
    _duress_state_path(env_file).write_text(json.dumps(state))


def _env_file(request: Request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


@router.post("/duress/set")
async def duress_set(body: DuressSetBody, request: Request) -> dict:
    env_file = _env_file(request)
    h = _duress_hash(body.phrase)
    _save_duress(env_file, {"hash": h, "set_at": int(time.time())})
    return {"ok": True}


@router.post("/duress/check")
async def duress_check(body: DuressCheckBody, request: Request) -> dict:
    """Returns {is_duress: true} if the phrase matches the stored hash.

    The setup flow calls this before derivation — if duress, it skips
    real-seed processing and creates a fresh empty identity instead.
    """
    env_file = _env_file(request)
    st = _load_duress(env_file)
    if not st.get("hash"):
        return {"is_duress": False, "configured": False}
    ok = hmac.compare_digest(_duress_hash(body.phrase), st["hash"])
    return {"is_duress": bool(ok), "configured": True}


@router.delete("/duress")
async def duress_delete(request: Request) -> dict:
    p = _duress_state_path(_env_file(request))
    if p.is_file():
        p.unlink()
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
# 3. Contacts CSV staging
# ══════════════════════════════════════════════════════════════════════════

def _pending_contacts_path(env_file: Path) -> Path:
    return env_file.parent / "pending_contacts.csv"


@router.post("/contacts/upload")
async def contacts_upload(
    request: Request,
    file: UploadFile = File(...),
) -> dict:
    env_file = _env_file(request)
    data = await file.read()
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(413, "file too large (>2 MiB)")
    # Minimal sanity: must look like CSV or vCard.
    lower = data[:256].decode("utf-8", errors="replace").lower()
    if not ("," in lower or "begin:vcard" in lower or "\n" in lower):
        raise HTTPException(400, "doesn't look like CSV/vCard")
    # Count non-empty lines (CSV) or BEGIN:VCARD blocks.
    text = data.decode("utf-8", errors="replace")
    if "begin:vcard" in text.lower():
        count = text.lower().count("begin:vcard")
    else:
        lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
        count = max(0, len(lines) - 1)  # minus header
    _pending_contacts_path(env_file).write_bytes(data)
    return {"ok": True, "entries": count, "byte_size": len(data)}


@router.get("/contacts/pending")
async def contacts_pending_status(request: Request) -> dict:
    env_file = _env_file(request)
    p = _pending_contacts_path(env_file)
    if not p.is_file():
        return {"pending": False}
    return {
        "pending":    True,
        "byte_size":  p.stat().st_size,
        "uploaded_at": int(p.stat().st_mtime),
    }


@router.delete("/contacts/pending")
async def contacts_pending_delete(request: Request) -> dict:
    p = _pending_contacts_path(_env_file(request))
    if p.is_file():
        p.unlink()
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
# 4. Pre-flight check
# ══════════════════════════════════════════════════════════════════════════

class PreflightBody(BaseModel):
    controller_url:   Optional[str] = None
    port:             Optional[int] = 9000
    require_tunnel:   bool = False


@router.post("/preflight")
async def preflight(body: PreflightBody, request: Request) -> dict:
    checks: list[dict] = []

    # Disk free % on the wizard state directory
    env_file = _env_file(request)
    try:
        du = shutil.disk_usage(str(env_file.parent))
        free_pct = (du.free / du.total) * 100 if du.total else 0
        ok = free_pct > 5
        checks.append({
            "name": "disk_free",
            "ok":   ok,
            "detail": f"{free_pct:.1f}% free ({du.free // (1024**3)} GB)",
        })
    except Exception as e:
        checks.append({"name": "disk_free", "ok": False, "detail": str(e)})

    # Port availability
    port = body.port or 9000
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            r = s.connect_ex(("127.0.0.1", int(port)))
            in_use = (r == 0)
        checks.append({
            "name": "port_free",
            "ok":   not in_use,
            "detail": f"port {port} " + ("occupied" if in_use else "free"),
        })
    except Exception as e:
        checks.append({"name": "port_free", "ok": False, "detail": str(e)})

    # Controller reachability
    if body.controller_url:
        url = body.controller_url.rstrip("/") + "/v1/health"
        try:
            async with httpx.AsyncClient(timeout=4.0, verify=False) as c:
                r = await c.get(url)
                ok = r.status_code == 200
                checks.append({
                    "name": "controller",
                    "ok":   ok,
                    "detail": f"{r.status_code} from {url}",
                })
        except Exception as e:
            checks.append({"name": "controller", "ok": False, "detail": str(e)})

    # cloudflared binary
    if body.require_tunnel:
        from .admin_api import _find_cloudflared  # reuse existing finder
        path = _find_cloudflared()
        checks.append({
            "name": "cloudflared",
            "ok":   bool(path),
            "detail": path or "not found on PATH or common brew dirs",
        })

    all_ok = all(c["ok"] for c in checks)
    return {"all_ok": all_ok, "checks": checks}


# ══════════════════════════════════════════════════════════════════════════
# 5. Backup-on-controller discovery (setup first-screen)
# ══════════════════════════════════════════════════════════════════════════

class BackupDiscoverBody(BaseModel):
    controller_url: str = Field(..., min_length=8, max_length=2048)
    mnemonic:       str = Field(..., min_length=20)


@router.post("/backup/discover")
async def backup_discover(body: BackupDiscoverBody) -> dict:
    """Given a controller URL + seed phrase, tells the setup flow whether
    a backup exists on that controller for the derived pubkey.

    The flow: user enters seed → we derive node pubkey → signed /meta
    query → controller reports presence + size. No need to complete full
    setup to know if there's something to restore.
    """
    from .seed_derive import derive_identity, normalize_mnemonic, validate_mnemonic
    phrase = normalize_mnemonic(body.mnemonic)
    if not validate_mnemonic(phrase):
        raise HTTPException(400, "invalid BIP39 checksum")
    ident = derive_identity(phrase)

    priv = Ed25519PrivateKey.from_private_bytes(ident.node_priv_raw)
    pub = ident.node_pubkey_hex
    payload = {"action": "meta", "pubkey": pub, "timestamp": int(time.time())}
    sig = priv.sign(_canonical(payload)).hex()

    url = body.controller_url.rstrip("/") + "/v1/backup/meta"
    try:
        async with httpx.AsyncClient(timeout=6.0, verify=False) as c:
            r = await c.post(url, json={"payload": payload, "signature": sig})
        if r.status_code >= 400:
            return {"exists": False, "error": f"HTTP {r.status_code}"}
        d = r.json()
        return {
            "exists":     bool(d.get("exists")),
            "byte_size":  d.get("byte_size"),
            "updated_at": d.get("updated_at"),
            "sha256":     d.get("sha256"),
            "pubkey":     pub,
        }
    except Exception as e:
        return {"exists": False, "error": f"{type(e).__name__}: {e}"}


def _canonical(data) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
