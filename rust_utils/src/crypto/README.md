# `rust_utils/src/crypto/` — High-level Crypto Combos

Combinations of primitives that are useful beyond what `crypto.rs` exposes at the top level. Each helper here composes two or more primitives into a single operation with a single nonce/tag check.

## Helpers

- `seal_and_sign(msg, sym_key, sign_priv) -> (ct, sig)` — AES-GCM encrypt + Ed25519 sign the ciphertext.
- `verify_and_open(ct, sig, sym_key, sign_pub) -> msg` — reverse.
- `ecies_encrypt(msg, recipient_x25519_pub) -> (eph_pub, ct)` — ECIES with X25519 + HKDF + AES-GCM.
- `ecies_decrypt(eph_pub, ct, x25519_priv) -> msg`.
- `hkdf_expand_multiple(salt, ikm, labels[]) -> [keys]` — derive N keys in one call.
- `constant_time_equal(a, b) -> bool`.

## Why a sub-module

`crypto.rs` at the src root handles simple one-primitive operations. This folder is for everything that would otherwise live there but has enough code to warrant a `mod.rs` + helpers file.

## Tests

See `../../tests/messages_tests.rs` and the inline `#[cfg(test)]` blocks.

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
