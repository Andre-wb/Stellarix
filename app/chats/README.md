# `app/chats/` — All conversational surfaces

The biggest sub-package in `app/`. Everything that carries user-visible conversation content: rooms, DMs, channels, groups, spaces, streams, voice, calls, stories, statuses, stickers, polls, reports, saved-messages, translation, AI assistant, bridges.

Most endpoints live under `/api/chat/`, `/api/rooms/`, `/api/dm/`, `/api/channels/`, `/api/spaces/`, `/api/stream/`, `/api/voice/`, `/api/calls/`.

## Files

### Rooms & messages (nested packages)

| Path           | Role                                                                                          |
| -------------- | --------------------------------------------------------------------------------------------- |
| `rooms/`       | Room CRUD, member management, key distribution, themes, public/sealed keys. See its README.  |
| `messages/`    | Message CRUD, history, flood control, polls, actions, attachments, moderation, scheduling, push dispatch, padding. See its README. |

### Private messaging

| File            | Covers                                                     |
| --------------- | ---------------------------------------------------------- |
| `dm.py`         | 1-to-1 direct messaging. Uses the same E2E primitives as rooms, but with a pair-scoped key. |
| `contacts.py`   | Contact list — add, remove, block.                         |
| `contact_sync.py` | Privacy-preserving phone-number / handle sync (hashed before upload). |

### Broadcast / discovery

| File                | Covers                                                                      |
| ------------------- | --------------------------------------------------------------------------- |
| `channels.py`       | One-to-many channels — posts, comments, subscribers, moderation.           |
| `channel_feeds.py`  | RSS/Atom ingestion into channels.                                           |
| `spaces.py`         | Spaces (communities) — category tree, membership, per-space permissions.   |
| `spaces_advanced.py`| Advanced space features — custom emojis, role hierarchies, audit log.      |
| `groups.py`         | Group-room helpers (multi-user private rooms).                              |
| `stories.py`        | 24-hour ephemeral posts with viewer tracking.                               |
| `statuses.py`       | Short text statuses under the user's name.                                  |

### Media & voice

| File            | Covers                                                                         |
| --------------- | ------------------------------------------------------------------------------ |
| `voice.py`      | Voice channels (persistent rooms you talk in) — JWT-scoped SFU tokens.         |
| `calls.py`      | 1-to-1 + small-group calls (signalled peer-to-peer).                           |
| `group_calls.py`| Large group calls — bridged through the SFU.                                   |
| `stream.py`     | Live streams — start/stop, hand-raise, reactions, donations.                   |
| `sfu.py`        | Thin wrapper around the SFU bridge in `../media/sfu_bridge.py`.                |
| `stickers.py`   | Sticker packs — upload, subscribe, per-space custom packs.                     |
| `saved_gifs.py` | User's saved-GIFs library.                                                     |

### Cross-feature

| File               | Covers                                                             |
| ------------------ | ------------------------------------------------------------------ |
| `chat.py`          | Entry-point router + shared dispatchers.                           |
| `search.py`        | Full-text search across messages + rooms (scope-scoped, encrypted where client has the key). |
| `saved.py`         | Saved messages / bookmarks.                                        |
| `link_preview.py`  | Fetches, caches, and serves link-preview cards. Privacy: fetched by the publisher's node, not the recipient. |
| `translate.py`     | Per-message translation via the AI provider.                       |
| `ai_assistant.py`  | In-chat "/ai" command.                                             |
| `tasks.py`         | Room-scoped to-do lists.                                           |
| `tipping.py`       | On-chain tips (Solana) to message authors.                         |
| `reports.py`       | User-filed reports — routed to room admins, space admins, or system moderators. |
| `bridge.py`        | Bridge to other protocols (experimental).                          |

## Testing

Most tests for this package live in `../tests/test_dm*.py`, `../tests/test_channels*.py`, `../tests/test_calls*.py`, etc. Run them with:

```bash
pytest app/tests/ -k "dm or channel or room"
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
