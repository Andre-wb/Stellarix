# Vortex Wizard — build matrix

## Native builds (run on the target OS)

PyInstaller doesn't cross-compile. You need native machines / runners
for each OS. The spec file (`vortex_wizard/vortex-wizard.spec`) auto-
detects the platform and produces the right artifact.

| OS         | Builder command                       | Output                                |
|------------|--------------------------------------|----------------------------------------|
| macOS      | `pyinstaller vortex_wizard/vortex-wizard.spec --clean --noconfirm` | `dist/Vortex Wizard.app` |
| Windows    | `.\scripts\build-windows.ps1`       | `dist\vortex-wizard\vortex-wizard.exe` |
| Linux      | `bash scripts/build-linux.sh`        | `dist-linux/vortex-wizard-*.tar.gz` + `.AppImage` |
| Docker     | included in build-linux.sh          | self-contained image |

## Zero-setup: GitHub Actions

Push a tag starting with `wizard-v*` (e.g. `wizard-v0.2.0`) and the CI
(`.github/workflows/release.yml`) builds for **macOS ARM64 / macOS
Intel / Windows / Linux** in parallel, attaches all 4 archives + a
SHA256SUMS file to a new GitHub Release.

    git tag wizard-v0.2.0
    git push origin wizard-v0.2.0

No credentials required for unsigned builds. For signed macOS bundles,
add Apple Developer ID to the workflow secrets and enable the signing
step when you're ready.

## Platform notes

### macOS
- Spec auto-creates `Vortex Wizard.app` with `LSUIElement=False`.
- pywebview uses the Cocoa backend (PyObjC).
- Without code signing, macOS 13+ shows a Gatekeeper prompt — user
  right-clicks → Open → confirms once.

### Windows
- Output is a folder bundle, not a single .exe — PyInstaller single-file
  builds have slow startup (extract to temp on every launch).
- pywebview uses the Edge WebView2 runtime (ships with Windows 11 by
  default; fallback installer ships with your app).
- SmartScreen will warn about an unsigned executable — same as Gatekeeper.

### Linux (AppImage preferred)
- AppImage runs on any distro with glibc 2.28+: Ubuntu 18.04+, Debian
  10+, Fedora 30+, RHEL 8+, openSUSE 15.2+, Arch (rolling).
- User: `chmod +x vortex-wizard-*.AppImage && ./vortex-wizard-*.AppImage`
- pywebview needs `libwebkit2gtk-4.1-0` and `libgtk-3-0` — packaged
  inside the AppImage so no apt install needed.

### ChromeOS
- Enable the Linux container (**Settings → Advanced → Developers**).
- Install the Linux `.AppImage` exactly as on any Linux.
- Or use the `.deb` via `sudo dpkg -i` if you add one (can be generated
  from the tarball with `fpm`).

## Files in this directory

| File | Purpose |
|---|---|
| `BUILD.md` | this document |
| `Dockerfile.build-linux` | Debian Bookworm container used for the Linux build (works from any host with Docker) |
| `build-linux.sh` | wrapper — `docker build` + `docker run` → `dist-linux/` |
| `build-windows.ps1` | PowerShell driver for native Windows builds |

## Rust hot-path (optional but recommended)

All builders try to `maturin develop --release` the `rust_utils/` crate
before calling PyInstaller. If the Rust toolchain isn't present the
build still succeeds — the Python fallback path is always available
(just 10-40× slower on sealed sender, canonical JSON, ratchet KDF, and
integrity walks).

Install Rust once:

    # macOS / Linux:
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

    # Windows:
    winget install Rustlang.Rustup
