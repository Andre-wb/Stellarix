# `app/bots/` — Bot Platform + Built-in IDE

Everything related to bots — CRUD, messaging, versioning, marketplace, anti-spam, and the in-browser IDE that authors Gravitix scripts. The Rust-based Gravitix runtime lives outside this package (in `../../Gravitix/`); this folder is the Python glue that exposes it over HTTP and WebSocket.

## Files by concern

### Bot lifecycle

| File                   | Covers                                                                |
| ---------------------- | --------------------------------------------------------------------- |
| `bot_crud.py`          | Create, list, update, delete bots. Ownership check, soft-delete.      |
| `bot_api.py`           | Top-level router; tag metadata, unified error shapes.                 |
| `bot_shared.py`        | Helpers shared between CRUD / messaging / marketplace.                |
| `bot_advanced.py`      | Slash-command registration, scheduled jobs, per-bot webhooks, AI helpers. |
| `bot_messaging.py`     | Bot ↔ user message delivery, receipt handling, scoped state.          |

### Marketplace

| File                | Covers                                                                  |
| ------------------- | ----------------------------------------------------------------------- |
| `bot_marketplace.py` | Publish, install, search, rating, version pinning. Signed-snapshot publication so marketplace installs can't be tampered with. |

### Anti-spam

| File               | Covers                                                                  |
| ------------------ | ----------------------------------------------------------------------- |
| `antispam_bot.py`  | Built-in moderator bot — rate limits, keyword / regex rules, Unicode confusable detection, captcha trigger, auto-kick. |

### IDE (Gravitix authoring)

| File                  | Covers                                                                       |
| --------------------- | ---------------------------------------------------------------------------- |
| `ide_routes.py`       | Top-level IDE router — mounted at `/api/bots/ide/*`.                         |
| `ide_projects.py`     | Project CRUD inside the bot workspace (see `../../bots_workspace/`).         |
| `ide_runner.py`       | Starts / stops / reloads a Gravitix interpreter per running bot. Sandboxed: resource limits, sanitised stdlib, per-project permissions (`_roles.json`). |
| `ide_versioning.py`   | Git-like history inside the workspace — each save is a signed commit; rollback to any previous revision. |
| `ide_monitoring.py`   | Live log stream, CPU / memory sampling, crash detection.                     |
| `ide_shared.py`       | Shared helpers for the IDE endpoints.                                        |
| `ide_bot_api.py`      | Bot's own API surface from inside Gravitix — message send, state get/set, HTTP fetch, scheduled callbacks. |

## Permissions model

Each project has a `_roles.json` next to the `.grav` file in `bots_workspace/`:

```json
{
  "owner": "user_123",
  "editors": ["user_456"],
  "runners": ["user_789"],
  "publishers": [],
  "secrets_readers": ["user_123"]
}
```

The IDE endpoints check this file, not the DB, on every action — see `ide_projects.py`.

## Sandboxing

- The Gravitix runtime is a **Rust VM** with a whitelisted stdlib. There is no Python `eval` or shell access.
- Resource limits: instructions per tick, wall-clock per handler, max heap.
- HTTP fetches from Gravitix go through `ide_bot_api.py`'s allow-listed client — a bot can't hit `http://localhost/admin` or the node's internal APIs.
- Crashes are captured in `ide_monitoring.py`; the runner restarts with backoff.

## Related directories

- `../../Gravitix/` — the language runtime itself.
- `../../bots_workspace/` — on-disk storage for `.grav` + `_roles.json` pairs.
- `../models/bot.py` — SQLAlchemy model for bot metadata.

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
