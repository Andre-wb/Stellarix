"""Entry point — also doubles as the bundled node launcher.

This one binary can be invoked two ways:

  * no arguments (or normal wizard args) → opens the wizard UI
  * first argument ``--run-node`` → starts the Vortex node (run.py)

The double role lets the PyInstaller-built ``Vortex Wizard.app`` spawn
the node as a child process (``sys.executable --run-node``) without
requiring a separate Python interpreter or ``run.py`` on the user's
machine. Everything needed to run the node lives inside the bundle.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _run_bundled_node() -> int:
    """Execute the bundled ``run.py`` as if it were ``python run.py``."""
    import runpy

    # Pop our own switch so run.py's argparse sees only its own args.
    sys.argv.pop(1)

    mei = getattr(sys, "_MEIPASS", None)
    if mei:
        run_py = Path(mei) / "run.py"
    else:
        # Dev checkout — run.py sits one level above this package.
        run_py = Path(__file__).resolve().parents[1] / "run.py"

    if not run_py.is_file():
        print(f"FATAL: run.py not found at {run_py}", file=sys.stderr)
        return 2

    # Node writes files relative to CWD (db, logs, uploads, certs). Pin it
    # to a stable per-user directory instead of whatever CWD the wizard
    # happened to be in — same dir the wizard uses for its .env.
    import os
    if sys.platform == "darwin":
        state_root = Path.home() / "Library" / "Application Support" / "Vortex"
    elif sys.platform.startswith("win"):
        state_root = Path(os.environ.get("APPDATA") or Path.home()) / "Vortex"
    else:
        state_root = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "vortex"
    state_root.mkdir(parents=True, exist_ok=True)

    # Node's ``app/main.py`` mounts ``StaticFiles(directory="static")`` and
    # ``Jinja2Templates(directory="templates")`` — that's CWD-relative. In
    # a dev checkout CWD *is* the repo root so those paths resolve. In the
    # frozen .app CWD is the per-user state dir, which has no assets; we
    # symlink the bundled read-only folders into place so the same
    # relative lookups work without touching the node code.
    if mei:
        import shutil as _shutil
        # These are READ-ONLY, bundle-owned assets. Safe to rewrite every
        # boot — they are NOT user data. User data (vortex.db, logs,
        # keys, uploads) is never on this list.
        for asset in ("templates", "static", "logo", "vortex_controller"):
            src = Path(mei) / asset
            dst = state_root / asset
            if not src.exists():
                continue
            try:
                if dst.is_symlink() or dst.is_file():
                    dst.unlink()
                elif dst.is_dir():
                    _shutil.rmtree(dst)
            except OSError:
                continue
            try:
                dst.symlink_to(src, target_is_directory=src.is_dir())
            except OSError:
                try:
                    _shutil.copytree(src, dst)
                except Exception:
                    pass

    os.chdir(state_root)

    runpy.run_path(str(run_py), run_name="__main__")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--run-node":
        raise SystemExit(_run_bundled_node())
    from vortex_wizard.app import main
    raise SystemExit(main())
