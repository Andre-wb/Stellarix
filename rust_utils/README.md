# `rust_utils/` — Rust Crypto & Transport Helpers

Rust crate that exposes performance-critical helpers to Python via PyO3. Sits alongside `vortex_chat` (the main crypto crate) and covers the **non-primitive** helpers — BMP, canonical JSON, UDP broadcast, ratchet KDF, sealed sender, steganography, metadata padding.

Everything here is deliberately **stateless**. State (keys, ratchets, counters) lives in Python; Rust just gets called with raw bytes in, raw bytes out.

## Layout

```
rust_utils/
├── Cargo.toml              ← crate config + PyO3 bindings
├── src/
│   ├── lib.rs              ← #[pymodule] — publishes every helper to Python
│   ├── auth.rs             ← auth-related helpers (challenge signing, HMAC)
│   ├── auth/               ← sub-module for larger auth helpers
│   ├── batch_verify.rs     ← batch Ed25519 signature verification
│   ├── bmp/                ← Blind Mailbox Protocol — mailbox id derivation, cover-traffic mixing
│   ├── canonical_json.rs   ← RFC 8785-compatible JSON canonicalisation for signing
│   ├── chunk_hash.rs       ← rolling BLAKE3 over upload chunks
│   ├── crypto.rs           ← one-shot crypto helpers (layered on vortex_chat)
│   ├── crypto/             ← sub-module for higher-level combos (seal + sign, etc.)
│   ├── integrity_walk.rs   ← recursive file-tree BLAKE3 for INTEGRITY manifests
│   ├── messages.rs         ← wire envelope pack/unpack (CBOR)
│   ├── messages/           ← message-specific sub-helpers
│   ├── metadata_padding.rs ← constant-length padding for message envelopes
│   ├── ratchet_kdf.rs      ← Double Ratchet KDF chain + MK/CK derivation
│   ├── sealed_sender.rs    ← Signal-style sealed-sender envelope
│   ├── steganography.rs    ← bit-level LSB embedder for cover images
│   ├── udp_broadcast.rs    ← LAN broadcast protocol for peer discovery
│   └── udp_broadcast/      ← sub-module for advanced discovery modes
└── tests/
    └── messages_tests.rs   ← Rust-side unit tests for the wire format
```

## Building

Built via maturin so Python can `import rust_utils`:

```bash
cd rust_utils
maturin develop --release      # installs into the active venv
# or for a standalone wheel:
maturin build --release
```

During the PyInstaller wizard build, the compiled extension is picked up automatically via `collect_all("rust_utils")` in `vortex-wizard.spec`.

## Python surface (selected)

```python
import rust_utils

# BMP
mailbox_id = rust_utils.bmp_mailbox_id(shared_secret, epoch_seconds, period=3600)
covers     = rust_utils.bmp_generate_covers(real_ids, count=50)

# Canonical JSON (for signing)
canon = rust_utils.canonicalize_json(obj)             # bytes, stable ordering
sig   = rust_utils.sign_canonical(priv, obj)

# Ratchet
mk, ck = rust_utils.ratchet_step(ck_prev, info=b"msg")

# Integrity
tree_hash = rust_utils.integrity_walk(path)           # recursive BLAKE3

# Sealed sender
env = rust_utils.seal_envelope(plaintext, recipient_pub, sender_identity)
```

## Test

```bash
cargo test                     # Rust-side tests (fast, no Python)
pytest app/tests/test_crypto_core.py -k rust_utils  # Python-side integration
```

---

## License

Vortex is released under the **Apache License 2.0**.

```
Copyright 2026 Andrey Karavaev, Boris Maltsev

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

---

## Authors

**Boris Maltsev**

[![GitHub](https://img.shields.io/badge/GitHub-BorisMalts-181717?style=flat-square&logo=github)](https://github.com/BorisMalts)

**Andrey Karavaev**

[![GitHub](https://img.shields.io/badge/GitHub-Andre--wb-181717?style=flat-square&logo=github)](https://github.com/Andre-wb)
