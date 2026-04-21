# `app/tests/` — Backend Test Suite

Pytest suite for the Vortex node. **120+ modules**, ~75% line coverage on the backend. Run from the repo root:

```bash
pytest app/tests/                    # everything (~5 min)
pytest app/tests/test_e2e_encryption.py -v
pytest app/tests/ -k "bmp or federation"
pytest app/tests/ --cov=app --cov-report=term-missing
```

## Shape

Each module exercises one feature area end-to-end: routes, DB state, cryptography, and (where relevant) a second node stub for federation.

### Coverage buckets

| Module set                         | Covers                                                 |
| ---------------------------------- | ------------------------------------------------------ |
| `test_auth_*.py`                   | Register, login (password + seed + key + passkey + QR), refresh, 2FA. |
| `test_crypto_core.py`, `test_crypto_roundtrip.py` | Rust crypto wrappers, AES-GCM, X25519, HKDF, ratchet. |
| `test_e2e_encryption.py`           | Full end-to-end: two clients, one message, correct plaintext.   |
| `test_dm_*.py`                     | Direct messaging — pair keys, edit, delete, read-receipts.      |
| `test_channels.py`                 | Broadcast channels + RSS ingestion.                             |
| `test_bots*.py`, `test_bot_marketplace.py`, `test_bot_messaging.py` | Bot CRUD, IDE runner, marketplace publish + install, message delivery. |
| `test_calls.py`, `test_federation*.py` | WebRTC signalling, SFU bridge, pairwise federation envelope round-trip. |
| `test_files_*.py`                  | Single-shot + resumable uploads, chunk assembly, MIME policy.   |
| `test_bmp.py`, `test_bmp_push.py`  | BMP mailbox ID derivation, cover-traffic mixing, blind push proxy. |
| `test_blockchain_verify.py`        | On-chain payment verification for tips and subscriptions.       |
| `test_contact_sync.py`, `test_contacts.py` | Contact hashing + sync privacy.                         |
| `test_ai_assistant.py`             | AI provider adapter — happy path, timeout, rate limit.          |
| `test_config.py`                   | Config parsing, secret auto-generation, env override.           |
| `test_100_coverage_*.py`, `test_coverage_boost.py` | Coverage-driven edge-case sweeps.                     |

### Fixtures

Core fixtures live in `../../conftest.py` (repo root). They provide:

- `client` — a logged-in `httpx.AsyncClient` against the test app.
- `second_client` — a second user in the same test DB, for pair / group tests.
- `room_with_members` — pre-created private room with the two clients joined.
- `rsa_keys`, `ed25519_keys`, `x25519_keys` — deterministic test key material.
- `ai_provider_stub` — patches `app.ai.provider` to return canned responses.
- `federation_peer` — stub second node with reachable `/api/federation/*` endpoints.
- `tmp_uploads` — isolated uploads directory per test.

Test isolation is per-module — a fresh in-memory SQLite + wiped uploads dir.

## Not here

- **Playwright browser tests** live under `../../playwright-tests/`.
- **Load tests** live under `../../deploy/loadtest/`.
- **Solana contract tests** live under `../../solana_program/tests/`.
- **iOS XCTest** — `ios/Modules/Tests/`.
- **Android unit tests** — `android/app/src/test/`.

## Adding a test

1. One test module per feature file you touch (if it doesn't already exist).
2. Use the `client` fixture — it respects every middleware, so tests are realistic.
3. Never hit the real filesystem outside `tmp_uploads` / `tmp_path`.
4. Never talk to real Solana, real push services, real AI providers — stub via fixtures.

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
