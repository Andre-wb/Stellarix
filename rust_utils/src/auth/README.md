# `rust_utils/src/auth/` — Signed Challenge Helpers

Ed25519 proof-of-possession helpers used by the node-side key-login + federation link flows. Complements `auth.rs` at the parent level — which holds the simple `sign_challenge(nonce) -> sig` / `verify_challenge(nonce, sig, pub) -> bool` primitives — with higher-level compositions.

## What's here

- **Challenge / response pairs** — `make_challenge()` produces a bound (nonce, issued_at, context_hash), `verify_response(challenge, sig, pub)` checks all three.
- **Batch verification** — when the caller has N signed challenges to verify (e.g. federation handshake + key publish), `batch_verify_context(responses)` verifies them in one go via `ed25519-dalek` batch path (~10× throughput vs. individual verify).
- **Issuance policy** — an opaque token that carries expiry, subject, and audience; signed by the controller or the node itself depending on the flow.

## Tests

Covered by `../../tests/messages_tests.rs` (section `auth_*`) and inline `#[cfg(test)]` mods.

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
