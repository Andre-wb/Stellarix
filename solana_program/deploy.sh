#!/usr/bin/env bash
# Deploy vortex_registry to a Solana cluster and rewrite the program id
# across every source file that references it so they all agree.
#
# Workflow:
#   ./deploy.sh localnet      — build + deploy to local validator
#   ./deploy.sh devnet        — build + deploy to Solana devnet
#   ./deploy.sh mainnet       — requires a funded wallet; DANGEROUS
#   ./deploy.sh doctor        — report current program_id pins
#
# After deploy the script:
#   1. reads target/deploy/vortex_registry-keypair.json
#   2. rewrites declare_id!(...) in programs/vortex_registry/src/lib.rs
#   3. rewrites programs.<cluster> block in Anchor.toml
#   4. rewrites PROGRAM_ID_B58 in ../static/js/premium.js
#   5. cargo check to confirm nothing broke
set -euo pipefail

CLUSTER="${1:-doctor}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LIB_RS="$SCRIPT_DIR/programs/vortex_registry/src/lib.rs"
ANCHOR_TOML="$SCRIPT_DIR/Anchor.toml"
PREMIUM_JS="$REPO_ROOT/static/js/premium.js"
KEYPAIR_JSON="$SCRIPT_DIR/target/deploy/vortex_registry-keypair.json"

# ── Helpers ───────────────────────────────────────────────────────────────

bail() { echo "error: $*" >&2; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || bail "missing '$1' — install it first"; }

current_id_lib()     { grep -oE 'declare_id!\("[^"]+"\)' "$LIB_RS" | head -1 | sed -E 's/.*"([^"]+)".*/\1/'; }
current_id_anchor()  { grep -oE 'vortex_registry = "[^"]+"' "$ANCHOR_TOML" | head -1 | sed -E 's/.*"([^"]+)".*/\1/'; }
current_id_js()      { grep -oE "PROGRAM_ID_B58 = '[^']+'" "$PREMIUM_JS" | head -1 | sed -E "s/.*'([^']+)'.*/\1/"; }

doctor() {
    echo "── Vortex program-id pins (should all match after deploy) ──"
    printf "  lib.rs        : %s\n" "$(current_id_lib)"
    printf "  Anchor.toml   : %s\n" "$(current_id_anchor)"
    printf "  premium.js    : %s\n" "$(current_id_js)"
    if [[ -f "$KEYPAIR_JSON" ]]; then
        if command -v solana-keygen >/dev/null; then
            printf "  keypair.json  : %s (on-disk)\n" "$(solana-keygen pubkey "$KEYPAIR_JSON" 2>/dev/null || echo "?")"
        else
            printf "  keypair.json  : present (install solana-keygen to extract pubkey)\n"
        fi
    else
        printf "  keypair.json  : (not yet generated — run ./deploy.sh devnet)\n"
    fi
}

rewrite_sources() {
    local new_id="$1"
    # lib.rs
    if grep -q 'declare_id!' "$LIB_RS"; then
        # Portable sed — works on both GNU and BSD (macOS) sed.
        perl -pi -e "s/declare_id!\\(\"[^\"]+\"\\)/declare_id!(\"$new_id\")/" "$LIB_RS"
    fi
    # Anchor.toml
    perl -pi -e "s/vortex_registry = \"[^\"]+\"/vortex_registry = \"$new_id\"/g" "$ANCHOR_TOML"
    # premium.js
    if [[ -f "$PREMIUM_JS" ]]; then
        perl -pi -e "s/PROGRAM_ID_B58 = '[^']+'/PROGRAM_ID_B58 = '$new_id'/" "$PREMIUM_JS"
    fi
    echo "✓ program_id pinned as $new_id in lib.rs, Anchor.toml, premium.js"
}

build_and_deploy() {
    local cluster="$1"
    need anchor
    need solana
    need solana-keygen

    echo "── Building vortex_registry ──"
    ( cd "$SCRIPT_DIR" && anchor build )

    [[ -f "$KEYPAIR_JSON" ]] || bail "keypair not found at $KEYPAIR_JSON after anchor build"
    local new_id
    new_id="$(solana-keygen pubkey "$KEYPAIR_JSON")"
    echo "✓ program id: $new_id"

    rewrite_sources "$new_id"

    echo "── Rebuilding with pinned id (changes declare_id!) ──"
    ( cd "$SCRIPT_DIR" && anchor build )

    echo "── Deploying to $cluster ──"
    # Anchor reads cluster from Anchor.toml [provider], NOT solana config,
    # so we rewrite both to stay in sync.
    case "$cluster" in
        localnet)
            solana config set --url localhost >/dev/null
            perl -pi -e 's/^cluster = ".*"$/cluster = "Localnet"/' "$ANCHOR_TOML"
            ;;
        devnet)
            solana config set --url devnet >/dev/null
            perl -pi -e 's/^cluster = ".*"$/cluster = "Devnet"/' "$ANCHOR_TOML"
            ;;
        mainnet)
            read -rp "⚠  deploying to MAINNET. Type MAINNET to continue: " confirm
            [[ "$confirm" == "MAINNET" ]] || bail "aborted"
            solana config set --url mainnet-beta >/dev/null
            perl -pi -e 's/^cluster = ".*"$/cluster = "Mainnet"/' "$ANCHOR_TOML"
            ;;
        *) bail "unknown cluster: $cluster (use localnet/devnet/mainnet)" ;;
    esac
    ( cd "$SCRIPT_DIR" && anchor deploy )

    echo "✓ deployed. Run './deploy.sh doctor' to verify pins."
}

# ── Dispatch ──────────────────────────────────────────────────────────────

case "$CLUSTER" in
    doctor)   doctor ;;
    localnet|devnet|mainnet) build_and_deploy "$CLUSTER" ;;
    *) bail "usage: $0 {localnet|devnet|mainnet|doctor}" ;;
esac
