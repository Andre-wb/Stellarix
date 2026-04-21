# `Gravitix/src/bot/` — Bot Runtime Integration

The layer that turns the Gravitix interpreter into a Vortex bot — event dispatch, `ctx`, `emit`, scheduling, state persistence, gated HTTP.

## What lives here

| Concern               | Detail                                                                            |
| --------------------- | --------------------------------------------------------------------------------- |
| **Handlers**          | `on /cmd { … }`, `on message { … }`, `on join { … }`, `on schedule("*/5 * * * *") { … }` — each registered into the dispatcher at program load. |
| **`ctx`**             | Immutable per-invocation object — `ctx.message`, `ctx.user`, `ctx.args`, `ctx.room`. |
| **`emit`**            | Sends a message back to the invoking room. Supports text, stickers, photos, cards, polls, Architex Mini Apps. |
| **`state`**           | Persistent KV store, scoped by `(bot_id, key_or_user_id)`. Backed by Vortex's DB. |
| **`schedule`**        | Cron-like entries. Registered at program load; the host kernel fires them.        |
| **HTTP (gated)**      | `http.get(url)` / `http.post(url, body)` — but only against the allow-list configured by the bot owner. No arbitrary fetches. |
| **Flows**             | `flow { on event … }` — named multi-step conversations (FSM helpers).             |

## Per-invocation budgets

Every handler run has a fresh budget:

- `INSTRUCTION_BUDGET` — AST nodes evaluated (default 500 000).
- `WALL_BUDGET` — seconds (default 5).
- `HEAP_BUDGET` — bytes for lists / maps / strings (default 16 MB).
- `HTTP_BUDGET` — outbound requests per invocation (default 5).

Exceeding any budget aborts the handler with a friendly error and logs an event for the bot owner.

## Security

- HTTP allow-list is enforced **per host**, not per URL — wildcards on subdomains are allowed, paths are free.
- State writes are audited; a bot can't read another bot's state even inside the same room.
- Every `emit` passes through the normal anti-spam + moderation pipeline.

## Testing

`../../tests/bot_integration.rs` runs a minimal mock host, loads an example bot, fires `ctx` events, asserts on emitted outputs.

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
