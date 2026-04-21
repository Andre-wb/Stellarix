# `app/chats/messages/` — Message Lifecycle

The message sub-package — from client upload through persistence, moderation, padding, delivery, push, history, edits, polls, and scheduled sends. One of the largest feature packages in `app/`.

Endpoints live under `/api/chat/messages/*` and `/ws/chat/{room_id}`.

## Files

### Core

| File          | Role                                                                                   |
| ------------- | -------------------------------------------------------------------------------------- |
| `_router.py`  | Wires every file below into one FastAPI router. Single entry for the parent package.  |
| `core.py`     | Message creation / retrieval orchestration — ties together storage, moderation, padding, delivery. |
| `messages.py` | Business-level message operations: create, update, delete, react, pin, forward.       |
| `rest.py`     | REST surface (GET /messages, GET /messages/<id>, POST /messages, …). Delegates to `core.py`. |
| `ws_signal.py`| WebSocket handler. Streams inbound messages, sends delivery receipts, handles typing + presence. |

### Persistence-aware helpers

| File            | Role                                                                                 |
| --------------- | ------------------------------------------------------------------------------------ |
| `history.py`    | Paginated history fetch. Cursor-based (`created_at` + `id`), respects read-up-to.   |
| `actions.py`    | Reactions, pins, stars, forwards, quote-references — everything the client does to an existing message. |
| `files.py`      | Attachment hookup. Takes a finalised upload (from `../../files/`) and links it to the message. |
| `keys.py`       | Per-message key negotiation helpers — if a new member joined since the last message, re-ECIES the current room key. |
| `moderation.py` | Runs the message through the moderation pipeline (antispam bot, URL blacklist, size, mention spam). |

### Cross-cutting

| File           | Role                                                                                   |
| -------------- | -------------------------------------------------------------------------------------- |
| `flood.py`     | Per-user per-room flood control. Sliding-window token bucket + exponential cool-down for offenders. |
| `padding.py`   | Appends constant-length padding to message envelopes — server-side cannot distinguish "short" from "long" ciphertext by network size. |
| `push.py`      | Dispatches push notifications for offline recipients. Calls into `../../push/`.       |
| `schedule.py`  | Scheduled sends — client uploads a ciphertext + send-at-timestamp, server delivers at time.  |
| `polls.py`     | Poll message type — single + multi choice, closed / open, per-option vote count.      |

## Message lifecycle (happy path)

```
1.  Client computes ciphertext under current room key.
2.  POST /api/chat/messages { room_id, ciphertext, nonce, key_id, kind }
3.  `rest.py` → `core.py`:
        → `flood.py`     (rate ok?)
        → `moderation.py`(not banned content by length/signature?)
        → `padding.py`   (envelope padded to nearest 256B bucket)
        → persist        (models_rooms.messages.Message)
4.  `core.py` fans out:
        → `ws_signal.py`  push to every connected member
        → `push.py`       wake offline members (Web Push / FCM / APNs)
        → `services.chat_service` → federation / bot hooks
5.  Client receives, decrypts, calls back for `read` receipts → `actions.py`.
```

## Testing

- `app/tests/test_dm_extended.py`, `test_messages.py`, `test_reactions.py`, `test_polls.py`, `test_moderation_advanced.py` cover most paths here.

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
