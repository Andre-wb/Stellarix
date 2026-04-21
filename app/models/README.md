# `app/models/` — Top-level SQLAlchemy Models

ORM models that sit **outside** the room subsystem. These represent users, bots, contacts, media, moderation state, prekey storage.

Room-scoped models (rooms themselves, permissions, feeds, spaces, etc.) live in `../models_rooms/`. The split is deliberate — room data is large, partitioned by room id, and migrated together; everything here is global.

## Files

| File           | Model(s)                                                      |
| -------------- | ------------------------------------------------------------- |
| `user.py`      | `User` — identity, profile, credentials, sessions, 2FA state, passkeys.                              |
| `bot.py`       | `Bot`, `BotVersion`, `BotInstallation`, `BotWebhook`. Owned by a `User`. Project source lives on disk in `bots_workspace/`. |
| `contact.py`   | `Contact` — directed (follower / followee / blocked). Also holds per-contact policy (mute, pin). |
| `media.py`     | `File`, `FileChunk`, `FilePreview`. Metadata only — bytes live under `uploads/`.                  |
| `moderation.py`| `Report`, `ModerationAction`, `AntispamRule`. Room reports link back here for cross-room offender tracking. |
| `prekeys.py`   | `PreKey`, `SignedPreKey`, `OneTimePreKey`. Server-side public half of the X3DH-like handshake.     |

## Conventions

- Every model inherits from `app.base.Base`.
- Every table has `id` (UUID), `created_at`, `updated_at`. Soft-deletable tables add `deleted_at`.
- Foreign keys use `ON DELETE CASCADE` where the child is strictly owned (e.g. `BotVersion → Bot`) and `ON DELETE SET NULL` where it's a reference (e.g. a `Report.reporter_id` when a user is deleted).
- **No migration code here.** Schema changes go through `alembic/versions/`.

## Loading strategy

- Endpoints fetch by explicit `selectinload` / `joinedload` as needed. Avoid implicit lazy loads under async — SQLAlchemy 2.0 will raise.
- `User` is intentionally lean — session / device / 2FA details hang off it via relationships so cold logins don't need to hydrate everything.

## Testing

See `app/tests/test_auth_core.py`, `test_bots.py`, `test_contacts.py`, `test_moderation_advanced.py` for fixtures that exercise these models.

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
