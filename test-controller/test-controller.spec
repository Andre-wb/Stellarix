# PyInstaller spec for test-controller — standalone signed-envelope mock.
#
# Usage (from this directory):
#   pyinstaller test-controller.spec --clean --noconfirm
#
# Output:
#   dist/test-controller       — one-file executable you can hand off
from __future__ import annotations

from pathlib import Path
import sys

block_cipher = None
ROOT = Path(SPECPATH).resolve()

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.uvloop",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "fastapi",
    "cryptography",
    "cryptography.hazmat.primitives.asymmetric.ed25519",
]

excludes = [
    "tkinter", "matplotlib", "numpy", "pandas", "scipy", "PIL",
    "setuptools", "pip", "pkg_resources", "webview",
]

a = Analysis(
    [str(ROOT / "server.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Ship the whole website tree — HTML, CSS, JS, 146 locale JSONs.
        # Extracted to sys._MEIPASS/web/ at runtime.
        (str(ROOT / "web"), "web"),
    ],
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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="test-controller",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # single-binary CLI — print to stdout
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
