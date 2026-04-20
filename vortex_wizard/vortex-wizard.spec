# PyInstaller spec for `vortex-wizard` — self-contained bundle.
#
# Packs BOTH the wizard UI and the full Vortex node backend (run.py +
# app/ + vortex_controller/ + vortex_chat Rust extension) into one
# .app so the end user doesn't need a git checkout, a venv, or any
# pre-installed Python. Two modes of the same binary:
#
#   vortex-wizard                 → wizard UI (default)
#   vortex-wizard --run-node      → node backend (run.py)
#
# Usage:
#   cd <project root>
#   pyinstaller vortex_wizard/vortex-wizard.spec --clean --noconfirm
#
# Produces:
#   dist/vortex-wizard            (raw executable folder)
#   dist/Vortex Wizard.app        (macOS .app)
from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
ROOT = Path(SPECPATH).resolve().parent  # project root


# ── Data files — everything the bundled node needs at runtime ─────────────

datas = [
    # Wizard UI
    (str(ROOT / "vortex_wizard" / "web"), "vortex_wizard/web"),
    # Node source tree — run.py re-imports app/ and vortex_controller/
    # via the sys._MEIPASS injection in vortex_wizard/__main__.py.
    (str(ROOT / "app"), "app"),
    (str(ROOT / "vortex_controller"), "vortex_controller"),
    (str(ROOT / "run.py"), "."),
    (str(ROOT / "alembic"), "alembic") if (ROOT / "alembic").is_dir() else (str(ROOT / "README.md"), "."),
    # Web client the node serves (templates, static assets, brand logos)
    (str(ROOT / "static"), "static")     if (ROOT / "static").is_dir()    else (str(ROOT / "README.md"), "."),
    (str(ROOT / "templates"), "templates") if (ROOT / "templates").is_dir() else (str(ROOT / "README.md"), "."),
    (str(ROOT / "logo"), "logo")           if (ROOT / "logo").is_dir()     else (str(ROOT / "README.md"), "."),
    # Signed integrity manifest shipped next to run.py in the real repo
    (str(ROOT / "INTEGRITY.sig.json"), ".") if (ROOT / "INTEGRITY.sig.json").is_file() else (str(ROOT / "README.md"), "."),
    # Repo-wide integrity tool + manifest — the wizard loads scripts/integrity_repo.py
    # via importlib from the admin backend so "Sign repo" / "Verify" work
    # inside the bundle without a dev checkout.
    (str(ROOT / "scripts"), "scripts") if (ROOT / "scripts").is_dir() else (str(ROOT / "README.md"), "."),
    (str(ROOT / "INTEGRITY.repo.json"), ".") if (ROOT / "INTEGRITY.repo.json").is_file() else (str(ROOT / "README.md"), "."),
]
# Dedupe — same file can legitimately land in datas twice via the
# conditional placeholders above.
_seen = set()
datas = [(s, d) for (s, d) in datas if (s, d) not in _seen and not _seen.add((s, d))]


# ── Hidden imports — anything imported dynamically / via string ───────────

hiddenimports = [
    # uvicorn / starlette chosen at runtime
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.uvloop",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    # cryptography used by wizard and node
    "cryptography",
    "cryptography.hazmat.primitives.asymmetric.ed25519",
    "httpx",
    # pywebview — dispatcher chosen at runtime
    "webview",
    "webview.platforms.cocoa",
    "webview.platforms.winforms",
    "webview.platforms.gtk",
    "webview.platforms.qt",
    # node extras
    "aiosqlite",
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.dialects.sqlite.aiosqlite",
    "sqlalchemy.ext.asyncio",
    "argon2",
    "vortex_chat",   # Rust extension (maturin-installed)
    "blake3",
    "base58",
    "mnemonic",
    "jwt",            # PyJWT
    "solders",
]

# Let PyInstaller walk the full package trees so dynamic imports work.
for pkg in ("app", "vortex_controller"):
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception as e:
        print(f"WARN: collect_submodules({pkg}) failed: {e}")


# ── Binaries / datas for native deps ──────────────────────────────────────

binaries = []
for pkg in (
    "vortex_chat",       # native .so from maturin
    "cryptography",
    "argon2",
    "blake3",
    "solders",
    "curl_cffi",         # TLS fingerprinting (stealth mode)
    "pqcrypto",          # post-quantum fallback
    "oqs",               # liboqs-python (bundled native lib when present)
    "PIL",               # Pillow — image handling
    "numpy",             # used transitively by the node
    "magic",             # python-magic file-type detection
    "jinja2",            # fastapi.templating
    "fastapi",           # full FastAPI surface (templating, security, etc.)
    "starlette",         # underlying ASGI framework
    "pywebpush",         # push notifications
    "alembic",           # db migrations
):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:
        print(f"WARN: collect_all({pkg}) failed: {e}")


# ── Exclude things we definitely don't need ───────────────────────────────

excludes = [
    "tkinter", "matplotlib", "pandas", "scipy",
    "setuptools", "pip", "pkg_resources",
    # PIL/Pillow and numpy are USED by the node (image resize, antispam).
    # Leave them in the bundle.
]


# ── Analysis + EXE ────────────────────────────────────────────────────────

a = Analysis(
    [str(ROOT / "vortex_wizard" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

_icns = ROOT / "vortex_wizard" / "web" / "assets" / "icon.icns"
_ico  = ROOT / "vortex_wizard" / "web" / "assets" / "favicon.ico"
_icon_path = str(_icns) if (sys.platform == "darwin" and _icns.is_file()) else str(_ico)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="vortex-wizard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="vortex-wizard",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Vortex Wizard.app",
        icon=str(_icns) if _icns.is_file() else None,
        bundle_identifier="sol.vortexx.wizard",
        version="0.1.0",
        info_plist={
            "NSHighResolutionCapable": "True",
            "LSUIElement": "False",
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "0.1.0",
            "NSHumanReadableCopyright": "Vortex — decentralized",
            "NSAppTransportSecurity": {
                "NSAllowsLocalNetworking": True,
                "NSAllowsArbitraryLoads": True,
            },
        },
    )
