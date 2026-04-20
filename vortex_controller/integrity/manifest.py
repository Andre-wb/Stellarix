"""Deterministic manifest builder for code integrity attestation.

The manifest is a dict of ``{relative_path: sha256_hex}`` plus a version and
build timestamp. File walking is strictly deterministic (sorted paths) so
two independent builds of the same source produce byte-identical manifests.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Iterator

# File suffixes we consider "code" — everything else (uploads, cached db,
# runtime keys, virtualenv bytecode) is skipped.
_TRACKED_SUFFIXES = {
    ".py", ".html", ".css", ".js", ".json",
    ".md", ".toml", ".txt", ".svg",
}

# Path components that must always be skipped, even if they contain tracked
# file types (e.g. a test-generated SQLite file dropped under a source dir).
_EXCLUDE_ANY = {
    "__pycache__", ".venv", "venv", ".git", "node_modules",
    "target", "dist", "build", ".pytest_cache", ".mypy_cache",
    "keys",  # runtime keypairs are per-deployment, not part of the release
    "logs",
}

# Specific file names to skip (signature file excluded from self-signing).
_EXCLUDE_NAMES = {
    "INTEGRITY.sig.json",
    "controller.db",
    ".env",
    "controller.key",
}


def _should_include(relative_path: Path) -> bool:
    if relative_path.suffix.lower() not in _TRACKED_SUFFIXES:
        return False
    if relative_path.name in _EXCLUDE_NAMES:
        return False
    for part in relative_path.parts:
        if part in _EXCLUDE_ANY:
            return False
    return True


def _walk_files(root: Path) -> Iterator[Path]:
    """Yield tracked files under ``root`` as paths relative to ``root``,
    sorted deterministically."""
    collected = []
    for base, dirs, files in os.walk(root):
        # Prune excluded dirs in-place so os.walk doesn't descend into them.
        dirs[:] = [d for d in dirs if d not in _EXCLUDE_ANY]
        for f in files:
            abs_path = Path(base) / f
            rel = abs_path.relative_to(root)
            if _should_include(rel):
                collected.append(rel)
    for p in sorted(collected):
        yield p


try:
    import vortex_chat as _vc_rust
    _HAS_RUST_SHA = hasattr(_vc_rust, "sha256_hex")
except ImportError:
    _HAS_RUST_SHA = False


def sha256_of_file(path: Path, chunk_size: int = 65536) -> str:
    # Rust path: ~2 ms for 10 MB vs 15 ms in Python stdlib hashlib.
    if _HAS_RUST_SHA:
        try:
            with path.open("rb") as f:
                return _vc_rust.sha256_hex(f.read())
        except OSError:
            pass
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(root: Path, version: str, built_at: int) -> dict:
    """Produce a deterministic manifest of source files under ``root``."""
    files: list[dict] = []
    for rel in _walk_files(root):
        files.append({
            "path": rel.as_posix(),
            "sha256": sha256_of_file(root / rel),
        })
    return {
        "version": version,
        "built_at": int(built_at),
        "algorithm": "sha256",
        "root": root.name,
        "files": files,
    }


def verify_files(manifest: dict, root: Path) -> dict:
    """Recompute hashes and return structured diff against the manifest.

    Returns::

        {
            "matched": <int>,
            "mismatched": [relative_path, ...],
            "missing":    [relative_path, ...],
            "extra":      [relative_path, ...],   # files on disk not in manifest
        }
    """
    expected = {f["path"]: f["sha256"] for f in manifest.get("files", [])}
    mismatched: list[str] = []
    missing: list[str] = []
    matched = 0

    for rel_str, want_hash in expected.items():
        abs_path = root / rel_str
        if not abs_path.is_file():
            missing.append(rel_str)
            continue
        got = sha256_of_file(abs_path)
        if got != want_hash:
            mismatched.append(rel_str)
        else:
            matched += 1

    on_disk = {p.as_posix() for p in _walk_files(root)}
    extra = sorted(on_disk - set(expected.keys()))

    return {
        "matched": matched,
        "mismatched": sorted(mismatched),
        "missing": sorted(missing),
        "extra": extra,
    }


def canonical_json(obj) -> bytes:
    """Same canonicalization as controller_crypto — bytes that the signature covers."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
