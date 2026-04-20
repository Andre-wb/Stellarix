#!/usr/bin/env bash
# Production Linux build — outputs AppImage + .deb + .rpm + tarball.
#
# Works from macOS / Windows WSL / Linux with Docker installed.
#
# Usage:
#   bash scripts/build-linux.sh                    # native arch (arm64 on Apple Silicon, amd64 on Intel)
#   TARGET_ARCH=amd64 bash scripts/build-linux.sh  # force x86_64 (via QEMU on arm64 host)
#   TARGET_ARCH=arm64 bash scripts/build-linux.sh  # force aarch64
#
# Output directory: ./dist-linux/
#   vortex-wizard-<date>-<arch>.AppImage      (universal, single-file)
#   vortex-wizard_<version>-1.<date>_<arch>.deb    (Debian / Ubuntu)
#   vortex-wizard-<version>-1.<date>.<rpm_arch>.rpm   (RHEL / Fedora / SUSE)
#   vortex-wizard-linux-<date>-<arch>.tar.gz   (manual install)
#   install.sh                                 (detects distro, picks format)
#   SHA256SUMS

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
    echo "error: docker not found. Install Docker Desktop / Colima / Rancher." >&2
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    echo "error: Docker daemon isn't running." >&2
    exit 1
fi

TARGET_ARCH="${TARGET_ARCH:-$(uname -m)}"
case "$TARGET_ARCH" in
    arm64|aarch64) PLATFORM="linux/arm64" ;;
    amd64|x86_64)  PLATFORM="linux/amd64" ;;
    *) echo "error: unknown TARGET_ARCH '$TARGET_ARCH'" >&2; exit 1 ;;
esac

# Ensure buildx is available — needed for cross-arch builds.
if [ "$PLATFORM" = "linux/amd64" ] && [ "$(uname -m)" = "arm64" ]; then
    echo "⚠ Building for linux/amd64 on arm64 host — this uses QEMU emulation."
    echo "  Expect 40-60 min for first run vs ~15 min native."
    # Make sure binfmt is registered
    docker run --privileged --rm tonistiigi/binfmt --install amd64 >/dev/null 2>&1 || true
fi

IMAGE="vortex-builder:$(echo "$PLATFORM" | tr / -)"
echo "=== Platform: $PLATFORM ==="
echo "=== Image:    $IMAGE ==="

echo "=== [1/2] Building image ==="
docker buildx build \
    --platform "$PLATFORM" \
    --load \
    -f scripts/Dockerfile.build-linux \
    -t "$IMAGE" \
    .

mkdir -p dist-linux
echo "=== [2/2] Running build ==="
# --privileged needed for some AppImage tooling on older Docker.
# --device /dev/fuse + --cap-add SYS_ADMIN would be tighter, but many
# Docker Desktop versions don't expose /dev/fuse to the VM. Privileged
# is fine for a local build box.
docker run --rm \
    --platform "$PLATFORM" \
    --privileged \
    -v "$ROOT/dist-linux:/out" \
    "$IMAGE"

echo
echo "=== Linux artifacts ==="
ls -lh dist-linux/ | grep -v '^d' | grep -v '^total'
echo
echo "=== SHA256SUMS ==="
cat dist-linux/SHA256SUMS 2>/dev/null || echo "(missing)"
echo
cat <<EOF
Install on a target machine:
  # Auto-detect distro:
  scp dist-linux/* user@host:/tmp/ && ssh user@host 'cd /tmp && bash install.sh'

  # Or pick the right file manually:
  #   Debian / Ubuntu:   sudo dpkg -i vortex-wizard_*.deb
  #   Fedora / RHEL:     sudo rpm -Uvh vortex-wizard-*.rpm
  #   Any distro:        chmod +x vortex-wizard-*.AppImage && ./vortex-wizard-*.AppImage
EOF
