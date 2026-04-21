# `app/` — Vortex Node Backend

The Python backend that every Vortex node runs. A single FastAPI process that owns the **data plane**: chats, rooms, files, calls, federation. Plays no part in the discovery control plane — that lives in `../vortex_controller/`.

## Boot

```
run.py  ──▶  app.main:create_app()  ──▶  uvicorn
                    │
                    ├── config.py         ← env + .env
                    ├── database.py       ← SQLAlchemy engine, async session factory
                    ├── logging_config.py ← structured logs, rotation
                    └── base.py           ← declarative base + metadata
```

`main.py` assembles:

1. **Middleware stack** (outermost → innermost):
   Security Headers → Logging → CSRF → TokenRefresh → WAF.
2. **Routers** from every feature sub-package (`authentication/`, `chats/`, `files/`, …).
3. **Lifespan hook** — opens DB, starts peer discovery, warms edge cache, boots bot runners, lifts BMP proxy.

## Layout

| Path              | Role                                                                                                       |
| ----------------- | ---------------------------------------------------------------------------------------------------------- |
| `main.py`         | `create_app()` + router/middleware wiring.                                                                 |
| `config.py`       | Typed settings (pydantic). Auto-generates JWT + CSRF secrets on first run.                                 |
| `database.py`     | Async engine (SQLite WAL in dev, PostgreSQL in prod). `AsyncSessionFactory` used by every endpoint.        |
| `base.py`         | SQLAlchemy `DeclarativeBase`, shared metadata, mixin helpers (timestamps, soft-delete).                    |
| `logging_config.py` | JSON logs, rotating file handler, uvicorn integration.                                                   |
| `authentication/` | Register, login, password, passkey, 2FA, QR login, security questions, profile, session.                   |
| `chats/`          | Rooms, messages, DMs, channels, stories, statuses, calls, streams, SFU, stickers, search, …               |
| `bots/`           | Bot CRUD + marketplace + built-in IDE runner + Gravitix pipeline.                                          |
| `files/`          | Resumable uploads, chunked download, gallery.                                                              |
| `keys/`           | Long-term + pre-keys for E2E, ECIES distribution.                                                          |
| `federation/`     | Node-to-node replication, trusted-node list, cross-node read.                                              |
| `peer/`           | LAN/BLE discovery, controller client, SNS (`vortexx.sol`), Solana on-chain registry lookup.                |
| `transport/`      | Obfuscation, BMP, cover traffic, BLE, Wi-Fi Direct, Tor, CDN relay, steganography, stealth levels 1–4.     |
| `security/`       | JWT, WAF, double ratchet, post-quantum, sealed sender, GDPR, key backup, Shamir, privacy toggles.          |
| `push/`           | Web Push + BMP push proxy (blinded push ids).                                                              |
| `services/`       | Cross-feature glue — chat service, native bridge, webhooks, unified push, sealed push.                     |
| `routes/`         | Top-level routing (currently just the shared WebSocket entry).                                             |
| `session/`        | Multi-device handoff, session migration, migration pusher.                                                 |
| `media/`          | SFU bridge for mass voice/video.                                                                           |
| `ai/`             | Provider abstraction (OpenAI-compatible + Qwen local).                                                     |
| `models/`         | SQLAlchemy models that live outside the room system — User, Bot, Contact, Media, Moderation, Prekeys.      |
| `models_rooms/`   | Models tightly coupled to rooms — permissions, encryption metadata, spaces, feeds, stickers, analytics.    |
| `benchmarks/`     | Synthetic load harness — throughput + crypto micro-benchmarks.                                             |
| `utilites/`       | Pure helpers. Intentional spelling.                                                                        |
| `tests/`          | 120+ pytest modules. Run from repo root: `pytest app/tests/`.                                              |
| `docs/`           | Per-service OpenAPI tag config.                                                                            |

## Testing

```bash
cd /Users/borismaltsev/RustroverProjects/Vortex
pytest app/tests/                   # whole suite
pytest app/tests/test_e2e_encryption.py -v
pytest app/tests/test_100_coverage_1.py -k "login"
```

Test settings live in `conftest.py` at the repo root. The suite uses SQLite in-memory by default; point `DATABASE_URL` at a throw-away PostgreSQL for integration testing.

## Runtime integrations

- **`vortex_chat` (Rust / PyO3)** — provides AES-GCM, X25519, Ed25519, BLAKE3, Argon2id, HKDF-SHA256. `app/security/crypto.py` is the thin Python wrapper.
- **`rust_utils/`** — BMP, canonical-JSON, UDP broadcast, metadata padding, steganography, ratchet KDF.
- **Gravitix** — bot runtime invoked from `app/bots/ide_runner.py`.
- **Controller** — `app/peer/controller_client.py` fetches random nodes + signed entry URLs at boot.
- **Solana** — `app/peer/solana_registry.py` reads peer PDAs for on-chain trust decay.

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
