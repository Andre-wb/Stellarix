# `app/models_rooms/` — Room-scoped SQLAlchemy Models

ORM models that are **tightly coupled to rooms** — they are partitioned by `room_id` and generally migrate together. Split out from `../models/` so the global tables (User, Bot, Contact, etc.) can evolve independently of room-internal schemas.

## Files

| File             | Model(s)                                                                                 |
| ---------------- | ---------------------------------------------------------------------------------------- |
| `rooms.py`       | `Room`, `RoomMember`, `RoomInvite`. The core room table.                                 |
| `messages.py`    | `Message`, `MessageEdit`, `MessageReaction`, `MessagePoll`, `MessagePoll{Option,Vote}`, `Thread`, `Attachment`. |
| `encryption.py`  | `RoomKey`, `RoomKeyDelivery`, `RoomRatchetState`. Per-room key material and ratchet bookkeeping. |
| `permissions.py` | `Role`, `RoomRole`, `Permission`, `RolePermission`. Fine-grained per-room RBAC.          |
| `admin.py`       | `RoomBan`, `RoomKick`, `RoomAuditEntry`. Moderator-visible log.                          |
| `public_keys.py` | `RoomPublicKeyRegistry`, `SealedRoomKey`. Public-key room support (anyone can join without per-user invite). |
| `enums.py`       | Shared enums — `RoomKind`, `MessageKind`, `ReactionKind`, `StreamState`, …              |
| `spaces.py`      | `Space`, `SpaceCategory`, `SpaceMember`, `SpaceRole`, `SpaceEmoji`. Community container around rooms. |
| `feeds.py`       | `ChannelFeed`, `ChannelPost`, `ChannelComment`, `ChannelSubscriber`, `RssFeed`.          |
| `stickers.py`    | `StickerPack`, `Sticker`, `StickerInstall`.                                              |
| `collections.py` | `Folder`, `FolderItem` — client-managed room organisation.                               |
| `discussions.py` | `ForumTopic`, `ForumPost`. Forum-style rooms.                                            |
| `analytics.py`   | `RoomAnalyticsDaily`, `RoomAnalyticsHourly`. Aggregates for the admin dashboard.         |
| `federation.py`  | `FederatedMirror`, `FederationSeq`. Per-room federation bookkeeping.                     |

## Conventions

- Every table carries `room_id` as a foreign key to `rooms.id`.
- Indexes on `(room_id, created_at)` for append-only tables (messages, audit, analytics).
- Composite primary keys on bridge tables (`room_id + user_id` for memberships, `room_id + role_id` for role assignments).
- **Key material** in `encryption.py` is encrypted-at-rest with a per-node master key before it hits the DB — the plaintext lives only in memory, and only for rooms the node is an active member of.

## Partitioning in PostgreSQL

For large deployments, `messages` and `analytics` tables are declared partitionable on `room_id` modulo N. The partition DDL is **not** in this folder (it's in `alembic/versions/<rev>_partition_messages.py`) so operators can pick the shard count at migration time.

## Testing

Fixtures for these models live in `conftest.py` at the repo root (`room_with_members`, `message_with_thread`, `encrypted_room`). Most feature tests under `app/tests/` consume them.

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
