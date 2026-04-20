#!/usr/bin/env python3
"""Whole-repo integrity signer for the Vortex source tree.

Where vortex_controller/integrity/ signs only the ~170 files of the
discovery controller, this tool signs every source file in the entire
Vortex repo — app/, vortex_wizard/, static/, rust_utils/, and so on.
User data, caches, build artifacts, and secrets are excluded.

Usage (from repo root):

    # one-shot sign (auto-generates keys/repo-release.key first time)
    python scripts/integrity_repo.py sign

    # verify current disk state against the signed manifest
    python scripts/integrity_repo.py verify

    # list what would be signed (no key, no network)
    python scripts/integrity_repo.py list

    # print the current release pubkey (pin this in clients)
    python scripts/integrity_repo.py show-pubkey

Outputs: INTEGRITY.repo.json at the repo root. This is a DIFFERENT
file from vortex_controller's INTEGRITY.sig.json — the two manifests
coexist and are signed by different Ed25519 keypairs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Iterator

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey,
    )
    from cryptography.exceptions import InvalidSignature
except ImportError:
    sys.stderr.write("cryptography not installed; run: pip install cryptography\n")
    sys.exit(1)

# ── Layout ──────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "INTEGRITY.repo.json"
DEFAULT_KEY_PATH = REPO_ROOT / "keys" / "repo-release.key"
MANIFEST_VERSION = "0.1.0"

# ── What to include ─────────────────────────────────────────────────────
TRACKED_SUFFIXES = {
    # Code
    ".py", ".rs", ".js", ".mjs", ".ts", ".tsx", ".jsx",
    # Web
    ".html", ".css", ".svg",
    # Data / config
    ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".conf",
    ".service", ".lock", ".spec",
    # Docs / plain
    ".md", ".txt",
    # Scripts
    ".sh", ".ps1",
    # Schema
    ".sql", ".proto",
}

# Path components that are always skipped even if they contain .py files.
EXCLUDE_ANY = {
    # Virtual-envs / build artifacts
    "__pycache__", ".venv", ".venv-build", "venv", "env",
    "target", "dist", "build", "out",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache",
    # Editor / tooling state
    ".idea", ".vscode", ".github", ".claude",
    # VCS
    ".git",
    # Third-party
    "node_modules",
    # Runtime user data — must never be signed (changes constantly)
    "uploads", "bots_workspace", "logs",
    # Test runs & scratch copies
    "coverage", "test-results", "playwright-tests", "test-ledger",
    "test-controller", "vortex-test", "example-page",
    # Heavy binary drops that aren't code
    "Qwen3-8B",
    # Runtime secrets — private keys live here, never signed
    "keys",
}

# Specific files to always skip.
EXCLUDE_NAMES = {
    # The signature files themselves (can't self-sign)
    "INTEGRITY.sig.json", "INTEGRITY.repo.json",
    # Runtime secrets / databases
    ".env", ".env.local", ".env.production",
    "controller.db", "controller.key",
    # OS noise
    ".DS_Store", "Thumbs.db",
    # Huge / noisy lockfiles that churn frequently
    "package-lock.json",
}


def _should_include(rel: Path) -> bool:
    if rel.name.startswith(".") and rel.name != ".gitignore":
        return False
    if rel.suffix.lower() not in TRACKED_SUFFIXES:
        return False
    if rel.name in EXCLUDE_NAMES:
        return False
    for part in rel.parts:
        if part in EXCLUDE_ANY:
            return False
        # Any venv variant, e.g. .venv-39, .venv-rust, etc.
        if part.startswith(".venv") or part.startswith("venv-"):
            return False
    return True


def _walk(root: Path) -> Iterator[Path]:
    collected: list[Path] = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [
            d for d in dirs
            if d not in EXCLUDE_ANY
            and not d.startswith(".venv")
            and not d.startswith("venv-")
        ]
        for name in files:
            rel = (Path(base) / name).relative_to(root)
            if _should_include(rel):
                collected.append(rel)
    # Deterministic order — two independent builds produce byte-identical manifests.
    for p in sorted(collected, key=lambda q: q.as_posix()):
        yield p


# Rust acceleration (same pattern as vortex_controller/integrity/manifest.py):
# ~10x speedup for SHA-256 on big JSON locale files.
try:
    import vortex_chat as _vc
    _HAS_RUST_SHA = hasattr(_vc, "sha256_hex")
except ImportError:
    _HAS_RUST_SHA = False


def _sha256(path: Path) -> str:
    if _HAS_RUST_SHA:
        try:
            return _vc.sha256_hex(path.read_bytes())
        except OSError:
            pass
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_manifest(root: Path, version: str) -> dict:
    files = []
    for rel in _walk(root):
        files.append({"path": rel.as_posix(), "sha256": _sha256(root / rel)})
    return {
        "version": version,
        "built_at": int(time.time()),
        "algorithm": "sha256",
        "root": root.name,
        "files": files,
    }


# ── Key management ──────────────────────────────────────────────────────
def _load_or_create_key(path: Path) -> Ed25519PrivateKey:
    if path.exists():
        return Ed25519PrivateKey.from_private_bytes(path.read_bytes())
    path.parent.mkdir(parents=True, exist_ok=True)
    priv = Ed25519PrivateKey.generate()
    raw = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path.write_bytes(raw)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return priv


def _pubkey_hex(priv: Ed25519PrivateKey) -> str:
    return priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()


# ── Verification ────────────────────────────────────────────────────────
def verify_signature(signed: dict) -> bool:
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(signed["signed_by"]))
        pub.verify(bytes.fromhex(signed["signature"]), _canonical(signed["payload"]))
        return True
    except (InvalidSignature, ValueError, KeyError):
        return False


def verify_files(manifest: dict, root: Path) -> dict:
    expected = {f["path"]: f["sha256"] for f in manifest.get("files", [])}
    mismatched: list[str] = []
    missing: list[str] = []
    matched = 0
    for rel, want in expected.items():
        p = root / rel
        if not p.is_file():
            missing.append(rel)
            continue
        got = _sha256(p)
        if got != want:
            mismatched.append(rel)
        else:
            matched += 1
    on_disk = {p.as_posix() for p in _walk(root)}
    extra = sorted(on_disk - set(expected.keys()))
    return {
        "matched": matched, "total_expected": len(expected),
        "mismatched": sorted(mismatched),
        "missing": sorted(missing), "extra": extra,
    }


# ── Library API (callable from the wizard's admin backend) ─────────────
# These wrap the same logic used by the CLI commands below. They return
# structured dicts instead of writing to stdout so the wizard can show
# results in the admin panel without shelling out.

def sign_repo(
    key_path: Path = DEFAULT_KEY_PATH,
    out_path: Path = MANIFEST_PATH,
    version: str = MANIFEST_VERSION,
) -> dict:
    """Build + sign the manifest. Generates the key on first run."""
    t0 = time.time()
    priv = _load_or_create_key(key_path)
    manifest = build_manifest(REPO_ROOT, version)
    signed = {
        "payload": manifest,
        "signature": priv.sign(_canonical(manifest)).hex(),
        "signed_by": _pubkey_hex(priv),
    }
    out_path.write_text(json.dumps(signed, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "pubkey": _pubkey_hex(priv),
        "files": len(manifest["files"]),
        "built_at": manifest["built_at"],
        "duration_s": round(time.time() - t0, 2),
        "manifest_path": str(out_path.relative_to(REPO_ROOT)),
        "key_path": str(key_path.relative_to(REPO_ROOT)),
    }


def verify_repo(manifest_path: Path = MANIFEST_PATH) -> dict:
    """Verify disk state against signed manifest. Returns a structured report."""
    if not manifest_path.is_file():
        return {"ok": False, "status": "no_manifest",
                "message": f"No manifest at {manifest_path}"}
    signed = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not verify_signature(signed):
        return {"ok": False, "status": "bad_signature",
                "message": "Signature invalid — manifest tampered or wrong key"}
    manifest = signed["payload"]
    result = verify_files(manifest, REPO_ROOT)
    ok = not result["mismatched"] and not result["missing"]
    return {
        "ok": ok,
        "status": "verified" if ok else "tampered",
        "pubkey": signed["signed_by"],
        "built_at": manifest["built_at"],
        "total": result["total_expected"],
        "matched": result["matched"],
        "mismatched": result["mismatched"],
        "missing": result["missing"],
        "extra": result["extra"],
    }


def get_status(manifest_path: Path = MANIFEST_PATH,
               key_path: Path = DEFAULT_KEY_PATH) -> dict:
    """Quick status — does the manifest/key exist, when was it last signed."""
    info = {
        "has_manifest": manifest_path.is_file(),
        "has_key": key_path.exists(),
    }
    if info["has_manifest"]:
        try:
            signed = json.loads(manifest_path.read_text(encoding="utf-8"))
            info.update({
                "pubkey": signed.get("signed_by"),
                "built_at": signed.get("payload", {}).get("built_at"),
                "file_count": len(signed.get("payload", {}).get("files", [])),
                "version": signed.get("payload", {}).get("version"),
            })
        except (json.JSONDecodeError, OSError) as e:
            info["error"] = str(e)
    return info


# ── CLI ─────────────────────────────────────────────────────────────────
def cmd_list(args) -> int:
    n = 0
    total_bytes = 0
    for rel in _walk(REPO_ROOT):
        try:
            total_bytes += (REPO_ROOT / rel).stat().st_size
        except OSError:
            pass
        n += 1
        if args.paths:
            print(rel.as_posix())
    if not args.paths:
        print(f"{n} files, {total_bytes/1024/1024:.1f} MB")
    else:
        print(f"# {n} files, {total_bytes/1024/1024:.1f} MB", file=sys.stderr)
    return 0


def cmd_sign(args) -> int:
    priv = _load_or_create_key(args.key)
    print(f"Hashing files under {REPO_ROOT}...")
    t0 = time.time()
    manifest = build_manifest(REPO_ROOT, args.version)
    payload = _canonical(manifest)
    signed = {
        "payload": manifest,
        "signature": priv.sign(payload).hex(),
        "signed_by": _pubkey_hex(priv),
    }
    args.out.write_text(json.dumps(signed, indent=2), encoding="utf-8")
    dt = time.time() - t0
    print(f"✅ Signed {len(manifest['files'])} files in {dt:.1f}s")
    print(f"   Release pubkey: {_pubkey_hex(priv)}")
    print(f"   Written to:     {args.out.relative_to(REPO_ROOT)}")
    print(f"   Key file:       {args.key.relative_to(REPO_ROOT)}  (keep safe, don't commit)")
    return 0


def cmd_verify(args) -> int:
    if not args.manifest.is_file():
        print(f"❌ manifest not found: {args.manifest}", file=sys.stderr)
        return 2
    signed = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not verify_signature(signed):
        print("❌ SIGNATURE INVALID — manifest tampered or signed by unknown key")
        return 3
    manifest = signed["payload"]
    print(f"✓ Signature valid ({signed['signed_by'][:16]}...)")
    print(f"  Manifest: {len(manifest['files'])} files, built {manifest['built_at']}")
    result = verify_files(manifest, REPO_ROOT)
    print(f"  Matched:    {result['matched']}/{result['total_expected']}")
    if result["mismatched"]:
        print(f"  ⚠️  TAMPERED ({len(result['mismatched'])}):")
        for p in result["mismatched"][:20]:
            print(f"      - {p}")
        if len(result["mismatched"]) > 20:
            print(f"      ... +{len(result['mismatched']) - 20} more")
    if result["missing"]:
        print(f"  ⚠️  MISSING ({len(result['missing'])}):")
        for p in result["missing"][:20]:
            print(f"      - {p}")
        if len(result["missing"]) > 20:
            print(f"      ... +{len(result['missing']) - 20} more")
    if result["extra"]:
        print(f"  ℹ  EXTRA ON DISK ({len(result['extra'])}, not signed):")
        for p in result["extra"][:10]:
            print(f"      + {p}")
        if len(result["extra"]) > 10:
            print(f"      ... +{len(result['extra']) - 10} more")
    ok = not result["mismatched"] and not result["missing"]
    print("✅ OK — all signed files match disk" if ok else "❌ FAILED")
    return 0 if ok else 1


def cmd_show_pubkey(args) -> int:
    if not args.key.exists():
        print(f"❌ no key at {args.key}", file=sys.stderr)
        return 2
    priv = _load_or_create_key(args.key)
    print(_pubkey_hex(priv))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_sign = sub.add_parser("sign", help="Build and sign INTEGRITY.repo.json")
    p_sign.add_argument("--key", type=Path, default=DEFAULT_KEY_PATH)
    p_sign.add_argument("--out", type=Path, default=MANIFEST_PATH)
    p_sign.add_argument("--version", default=MANIFEST_VERSION)
    p_sign.set_defaults(func=cmd_sign)

    p_verify = sub.add_parser("verify", help="Verify disk against signed manifest")
    p_verify.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    p_verify.set_defaults(func=cmd_verify)

    p_list = sub.add_parser("list", help="List files that would be signed")
    p_list.add_argument("--paths", action="store_true",
                        help="Print each path (default: only the summary)")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show-pubkey", help="Print release pubkey (hex)")
    p_show.add_argument("--key", type=Path, default=DEFAULT_KEY_PATH)
    p_show.set_defaults(func=cmd_show_pubkey)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
