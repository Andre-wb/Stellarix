"""Standalone mock Vortex controller — zero dependencies on the main project.

Drop-in replacement for a real ``vortexx.sol`` controller during wizard /
client testing. Signs every response envelope with a fresh Ed25519
keypair generated at startup, so real signature verification passes.

Bundled as a PyInstaller binary so you can hand it to a colleague on a
machine that doesn't have this repo. Run:

    test-controller/dist/test-controller [--port 8800] [--host 0.0.0.0]

Or from source:

    python server.py

No external network calls, no database, no config file — everything
lives in memory for the life of the process.
"""
from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _resource_path(rel: str) -> Path:
    """Resolve a bundled-resource path that works both from source and
    from a PyInstaller one-file binary (where data files get extracted
    into ``sys._MEIPASS`` at startup).
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / rel
    return Path(__file__).resolve().parent / rel


WEB_DIR = _resource_path("web")

VERSION = "test-0.1.0"

# ── Ed25519 signing (generated fresh on each launch) ───────────────────────

_PRIV = Ed25519PrivateKey.generate()
_PUB_HEX = _PRIV.public_key().public_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PublicFormat.Raw,
).hex()


def _canonical_json(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_envelope(payload: dict) -> dict:
    sig = _PRIV.sign(_canonical_json(payload)).hex()
    return {"payload": payload, "signature": sig, "signed_by": _PUB_HEX}


# ── Mock data ──────────────────────────────────────────────────────────────

NOW = int(time.time())

ENTRY_URLS = [
    {"url": "wss://smith-labs-darwin-nicole.trycloudflare.com", "type": "tunnel"},
    {"url": "wss://quiet-fox-harbor-alpha.trycloudflare.com",   "type": "tunnel"},
    {"url": "http://abcdef123ghijk789lmnopqr456stuvwx.onion",   "type": "tor"},
    {"url": "ipfs://bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi", "type": "ipfs"},
    {"url": "wss://controller-mirror.vortex.example",          "type": "direct"},
]

MIRRORS = [
    {"url": "https://mirror-a.vortex.example",          "type": "web",
     "healthy": True,  "latency_ms": 84,  "last_checked": NOW - 20, "error": None},
    {"url": "https://mirror-b.vortex.example",          "type": "web",
     "healthy": False, "latency_ms": None, "last_checked": NOW - 40,
     "error": "ConnectError: connection refused"},
    {"url": "ipfs://bafybei000mirror1pin",              "type": "ipfs",
     "healthy": True,  "latency_ms": 312, "last_checked": NOW - 60, "error": None},
    {"url": "ipfs://bafybei000mirror2stale",            "type": "ipfs",
     "healthy": False, "latency_ms": None, "last_checked": NOW - 180,
     "error": "HTTPStatusError: 504 Gateway Timeout"},
    {"url": "http://m2vortex7example123onion567.onion", "type": "tor",
     "healthy": False, "latency_ms": None, "last_checked": NOW,
     "error": "no tor proxy configured"},
    {"url": "https://another-mirror.vortex.sol.site",   "type": "web",
     "healthy": None,  "latency_ms": None, "last_checked": 0, "error": None},
]

PEERS = [
    {"pubkey": "aa"*32,
     "endpoints": ["wss://node-eu-west-1.vortex.sol:9000"],
     "metadata": {"name":"node-A (prod)","region":"eu-west","version":"1.0.2"},
     "last_seen": NOW - 12, "sealed": True, "weight": 1.0},
    {"pubkey": "bb"*32,
     "endpoints": ["wss://node-us-east-1.vortex.sol:9000","http://aaanodebb8ej2ka.onion"],
     "metadata": {"name":"node-B","region":"us-east","version":"1.0.2"},
     "last_seen": NOW - 3600*20, "sealed": True, "weight": 0.8},
    {"pubkey": "cc"*32,
     "endpoints": ["wss://asia-southeast-1.vortex.sol:9000",
                   "http://cc7vortex4asianode9.onion","ipfs://bafybeinodeCC-static"],
     "metadata": {"name":"node-C (pan-continental)","region":"asia-se","version":"1.0.1"},
     "last_seen": NOW - 60*60*24*14, "sealed": True, "weight": 0.5},
    {"pubkey": "dd"*32,
     "endpoints": ["wss://home-nat-jitter.trycloudflare.com"],
     "metadata": {"name":"home-pi","region":"self","version":"0.9-rc"},
     "last_seen": NOW - 60*10, "sealed": False, "weight": 0.5},
    {"pubkey": "ee"*32,
     "endpoints": ["wss://dusty-corner.vortex.example:9000"],
     "metadata": {"name":"legacy-node","region":"eu-central","version":"0.8.4"},
     "last_seen": NOW - 60*60*24*120, "sealed": True, "weight": 0.2},
    {"pubkey": "11"*32,
     "endpoints": ["wss://solana-only-demo.trycloudflare.com"],
     "metadata": {"name":"solana-only","region":"unknown","sealed":True,
                  "code_hash":"feedfacecafebeef"+"00"*24},
     "last_seen": NOW - 90, "sealed": True, "weight": 1.0,
     "code_hash": "feedfacecafebeef"+"00"*24},
    {"pubkey": "22"*32,
     "endpoints": ["wss://controller-only.vortex.example"],
     "metadata": {"name":"ctrl-only","version":"1.0.0"},
     "last_seen": NOW - 30, "sealed": False, "weight": 0.9},
    {"pubkey": "33"*32,
     "endpoints": ["wss://bootstrap-seed.vortex.example"],
     "metadata": {"name":"bootstrap-seed"},
     "last_seen": NOW - 5, "sealed": False, "weight": 0.7},
]

STATS = {
    "total":    len(PEERS) + 12,
    "approved": len(PEERS) + 4,
    "online":   sum(1 for p in PEERS if NOW - p["last_seen"] < 300),
}


# ── API ────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="vortex-test-controller",
    version=VERSION,
    description="Mock Vortex controller for wizard / client testing.",
    docs_url=None, redoc_url=None, openapi_url=None,
)


# ── Static website — identical to vortex_controller/web/ ─────────────────
#
# We serve the same HTML/CSS/JS the production controller uses, so
# opening the public URL in a browser looks exactly like a real
# vortexx.sol deployment. The HTML is bundled via PyInstaller datas=;
# its runtime path is resolved through ``_resource_path()`` above.

PAGES = {
    "/":         "index.html",
    "/nodes":    "nodes.html",
    "/entries":  "entries.html",
    "/mirrors":  "mirrors.html",
    "/security": "security.html",
    "/admin":    "admin.html",
}


def _make_page(file_name: str):
    path = WEB_DIR / file_name

    async def _handler():
        if path.is_file():
            return FileResponse(path)
        return PlainTextResponse(
            f"Vortex test controller {VERSION}\n\n"
            f"pubkey: {_PUB_HEX}\n\n"
            f"(bundle missing {file_name})\n",
        )
    return _handler


# Register the HTML pages.
for _path, _file in PAGES.items():
    app.add_api_route(_path, _make_page(_file), methods=["GET"],
                      include_in_schema=False)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    fav = WEB_DIR / "favicon.ico"
    if fav.is_file():
        return FileResponse(fav)
    return PlainTextResponse("", status_code=404)


# /static/* → web/assets (CSS, JS, images) — matches how the real
# controller wires assets so the pages reference the same URLs.
_assets_dir = WEB_DIR / "assets"
if _assets_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_assets_dir)), name="static")

# /locales/<lang>.json
_locales_dir = WEB_DIR / "locales"
if _locales_dir.is_dir():
    app.mount("/locales", StaticFiles(directory=str(_locales_dir)), name="locales")


@app.get("/v1/health")
async def health():
    return {
        "status":  "ok",
        "version": VERSION,
        "pubkey":  _PUB_HEX,
        "stats":   STATS,
    }


@app.get("/v1/integrity")
async def integrity():
    return {
        "status":         "verified",
        "signed_by":      _PUB_HEX,
        "trusted_pubkey": _PUB_HEX,
        "version":        VERSION,
        "built_at":       NOW - 3600,
        "matched":        42,
        "mismatched":     [],
        "missing":        [],
        "extra":          [],
        "message":        f"All 42 files match manifest {VERSION} (test key)",
    }


@app.get("/v1/treasury")
async def treasury():
    return {
        "pubkey":       "5ABkkipTZZEEPNR3cP4MCzftpAhqv6jvM4UTSLPGt5Qq",
        "chain":        "solana",
        "sns_domain":   "vortexx.sol",
        "fee_schedule": {
            "register_fee_sol":    1.0,
            "premium_protocol_pct": 20,
        },
    }


@app.get("/v1/entries")
async def entries():
    return sign_envelope({
        "entries":     ENTRY_URLS,
        "issued_at":   NOW,
        "valid_until": NOW + 3600,
    })


@app.get("/v1/mirrors")
async def mirrors():
    items = []
    for m in MIRRORS:
        e = {"url": m["url"], "type": m["type"]}
        if m.get("healthy") is not None:
            e["healthy"] = m["healthy"]
            e["latency_ms"] = m["latency_ms"]
            e["last_checked"] = m["last_checked"]
            if m.get("error"):
                e["error"] = m["error"]
        items.append(e)
    return sign_envelope({
        "mirrors":     items,
        "issued_at":   NOW,
        "valid_until": NOW + 86400,
    })


@app.get("/v1/mirrors/health")
async def mirrors_health():
    return {
        "last_sweep": NOW - 5,
        "mirrors": [
            {
                "url":          m["url"],
                "ok":           bool(m.get("healthy")),
                "last_checked": m.get("last_checked", 0),
                "latency_ms":   m.get("latency_ms"),
                "error":        m.get("error"),
            }
            for m in MIRRORS
        ],
    }


@app.get("/v1/nodes/random")
async def nodes_random(count: int = 5):
    chosen = PEERS[: max(1, min(count, len(PEERS)))]
    return sign_envelope({"nodes": chosen, "count": len(chosen)})


@app.get("/v1/nodes/lookup/{pubkey}")
async def nodes_lookup(pubkey: str):
    pubkey = pubkey.lower()
    for p in PEERS:
        if p["pubkey"] == pubkey:
            return sign_envelope({"node": p})
    return JSONResponse({"detail": "node not found"}, status_code=404)


# Bonfida-SNS-like endpoints so wizards that auto-resolve vortexx.sol
# can be pointed straight at this server via DNS or /etc/hosts.
#
# When a cloudflared tunnel is active we return the public URL so the
# wizard sees exactly what it would see against the real Bonfida +
# production controller. Otherwise we fall back to the loopback URL.
@app.get("/v2/record/{domain}/URL")
async def sns_url(domain: str):
    url = _TUNNEL_URL or f"http://127.0.0.1:{_BIND_PORT}"
    return {"result": {"content": url}}


@app.get("/v2/record/{domain}/TXT")
async def sns_txt(domain: str):
    return {"result": {"content": f"pubkey={_PUB_HEX}"}}


# Shared state — set once at startup.
_BIND_PORT: int = 8800
_TUNNEL_URL: str | None = None
_TUNNEL_PROC: subprocess.Popen | None = None


# ── Cloudflared tunnel (optional) ──────────────────────────────────────────


def _find_cloudflared() -> str | None:
    """Locate cloudflared even when PATH is trimmed (e.g. Finder-launched)."""
    hit = shutil.which("cloudflared")
    if hit:
        return hit
    for c in (
        "/opt/homebrew/bin/cloudflared",
        "/usr/local/bin/cloudflared",
        "/opt/local/bin/cloudflared",
        "/snap/bin/cloudflared",
        "/usr/bin/cloudflared",
        r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
        r"C:\Program Files\cloudflared\cloudflared.exe",
    ):
        try:
            if os.path.isfile(c) and os.access(c, os.X_OK):
                return c
        except OSError:
            continue
    return None


def _start_tunnel_blocking(port: int, timeout: float = 45.0) -> str:
    """Spawn cloudflared quick-tunnel and return the issued trycloudflare URL.

    Blocks up to ``timeout`` seconds waiting for the URL to appear on
    cloudflared's stdout. The subprocess is kept alive; we register an
    atexit + signal handlers so it's cleaned up on shutdown.
    """
    global _TUNNEL_PROC
    bin_path = _find_cloudflared()
    if not bin_path:
        raise SystemExit(
            "cloudflared is not installed.\n"
            "macOS:   brew install cloudflared\n"
            "Linux:   https://pkg.cloudflare.com/\n"
            "Windows: winget install Cloudflare.cloudflared"
        )

    print(f"[tunnel] starting cloudflared via {bin_path} …", flush=True)
    proc = subprocess.Popen(
        [
            bin_path, "tunnel",
            "--url", f"http://localhost:{port}",
            "--protocol", "http2",
            "--no-autoupdate",
        ],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    _TUNNEL_PROC = proc

    url_re = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.stdout is None or proc.poll() is not None:
            raise SystemExit("cloudflared exited before producing a URL")
        try:
            line = proc.stdout.readline()
        except Exception:
            line = ""
        if not line:
            time.sleep(0.2)
            continue
        m = url_re.search(line)
        if m:
            return m.group(0)

    raise SystemExit(f"cloudflared didn't produce a URL in {int(timeout)}s")


def _pump_tunnel_logs_to_stderr() -> None:
    """Forward remaining cloudflared output so the user can still see errors
    (connection drops, quota hits, etc.) after we've captured the URL.
    """
    global _TUNNEL_PROC
    proc = _TUNNEL_PROC
    if proc is None or proc.stdout is None:
        return

    def _pump():
        for line in proc.stdout:
            sys.stderr.write(f"[cloudflared] {line}")
            sys.stderr.flush()

    threading.Thread(target=_pump, daemon=True).start()


def _terminate_tunnel(*_args) -> None:
    global _TUNNEL_PROC
    proc = _TUNNEL_PROC
    if proc is None:
        return
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
    finally:
        _TUNNEL_PROC = None


def main() -> None:
    global _BIND_PORT, _TUNNEL_URL
    ap = argparse.ArgumentParser(
        prog="test-controller",
        description="Standalone mock Vortex controller (signed envelopes).",
    )
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind host (default: 127.0.0.1)")
    ap.add_argument("--port", type=int, default=8800,
                    help="bind port (default: 8800)")
    ap.add_argument("--tunnel", action="store_true",
                    help="open a cloudflared tunnel and print the public "
                         "trycloudflare URL (requires cloudflared installed)")
    ap.add_argument("--print-key", action="store_true",
                    help="print the generated signing pubkey and exit")
    args = ap.parse_args()

    if args.print_key:
        print(_PUB_HEX)
        return

    _BIND_PORT = args.port

    # Start uvicorn FIRST in a background thread so cloudflared has
    # something to proxy to. Tunnel startup blocks on reading the URL
    # from cloudflared's stdout.
    server_thread = threading.Thread(
        target=uvicorn.run,
        kwargs={
            "app": app, "host": args.host, "port": args.port,
            "log_level": "warning", "access_log": False,
        },
        daemon=True,
    )
    server_thread.start()

    # Wait for the HTTP port to be listening before touching the tunnel.
    import socket as _socket
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        try:
            with _socket.create_connection((args.host, args.port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.1)
    else:
        raise SystemExit(f"server didn't start on {args.host}:{args.port}")

    if args.tunnel:
        atexit.register(_terminate_tunnel)
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, lambda *a: (_terminate_tunnel(), sys.exit(0)))
            except (ValueError, OSError):
                pass  # main thread only — best-effort
        _TUNNEL_URL = _start_tunnel_blocking(args.port)
        _pump_tunnel_logs_to_stderr()

    public_line = (
        f"  public URL:      {_TUNNEL_URL}\n"
        if _TUNNEL_URL else ""
    )
    banner = (
        f"\n─── vortex test-controller {VERSION} ───\n"
        f"  signing pubkey:  {_PUB_HEX}\n"
        f"  listening on:    http://{args.host}:{args.port}\n"
        f"{public_line}"
        f"  try it:          curl http://{args.host}:{args.port}/v1/health\n"
    )
    if _TUNNEL_URL:
        banner += (
            f"\n  For the Vortex wizard (Custom mode):\n"
            f"    CONTROLLER_URL    = {_TUNNEL_URL}\n"
            f"    CONTROLLER_PUBKEY = {_PUB_HEX}\n"
        )
    print(banner, flush=True)

    # Keep the main thread alive while uvicorn serves on the background
    # thread. Ctrl+C exits cleanly via the signal handlers above.
    try:
        while server_thread.is_alive():
            server_thread.join(timeout=1.0)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
