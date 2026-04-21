# `app/chats/rooms/` — Room Lifecycle & Key Distribution

The rooms sub-package — CRUD, member management, invite flows, key distribution (ECIES + sealed), themes, per-room public keys.

Endpoints live under `/api/rooms/*`.

## Files

| File              | Role                                                                                   |
| ----------------- | -------------------------------------------------------------------------------------- |
| `crud.py`         | Create, list, show, update, delete, leave. Paginates user's rooms; serves public catalog. |
| `helpers.py`      | Internal utilities — slug generation, invite-code mint, membership joins.              |
| `members.py`      | Member management — add, remove, change role, transfer ownership. Emits audit entries. |
| `keys.py`         | Per-room symmetric key distribution: ECIES-encrypt the current room key to each member using their published X25519 key; handle re-keying when membership changes. |
| `public_keys.py`  | Public-room mode — anyone can derive the room key from a well-known published packet signed by the room owner. Used for rooms you want anyone with the link to decrypt. |
| `sealed_keys.py`  | Sealed-key distribution — an intermediate mode where key delivery hides the sender. Used for rooms created under sealed-sender policy. |
| `theme.py`        | Room theme CRUD — background, accent colour, icon tint. Stored per-room, shown to every member. |

## Room kinds

| Kind      | How keys work                                                                           |
| --------- | --------------------------------------------------------------------------------------- |
| `private` | ECIES-delivered room key on join (via `keys.py`). Full E2E, server never sees plaintext. |
| `public`  | Room key derivable from `public_keys.py` registry entry. Anyone with the link can read. |
| `sealed`  | Key delivery uses `sealed_keys.py` to hide who sent the key.                            |
| `dm`      | Pair-scoped key derived from the two users' long-term keys; no room-key distribution step. (See `../dm.py` — DMs live outside this folder.) |

## Key rotation

A room's symmetric key rotates on:

- A member is removed or banned → immediate rotation.
- Owner clicks "Rotate key" → immediate.
- `ROOM_KEY_ROTATE_DAYS` elapsed since last rotation (default 30).

Rotation is a multi-step dance in `keys.py`: generate new key → ECIES-deliver to every current member → clients acknowledge → flip the "active key" pointer. Old messages stay readable with the old key, which each client caches locally.

## Related

- `../../models_rooms/rooms.py`, `../../models_rooms/encryption.py`, `../../models_rooms/permissions.py` — the SQLAlchemy models.
- `../messages/keys.py` — uses the key pointer set here.
- `../../security/key_exchange.py` — underlying X3DH-ish handshake called by `keys.py`.

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
