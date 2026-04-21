# `app/keys/` — Key Management

Server-side state for public keys and one-time pre-keys. All **private** key material stays on the client — this folder only stores what the server legitimately needs in order to route E2E handshakes.

Endpoints live under `/api/keys/*`.

## Files

| File          | Role                                                                                          |
| ------------- | --------------------------------------------------------------------------------------------- |
| `keys.py`     | Long-term public key publish + lookup. Holds each user's published X25519 + Ed25519 pubkeys.  |
| `prekeys.py`  | One-time pre-keys (Signal-style). User uploads a batch; the server hands one out per new session request, then marks it consumed so the same key is never re-used. |

## What the server sees

For each user, per device:

- `identity_x25519_pub`  — long-term DH key.
- `identity_ed25519_pub` — long-term signing key.
- `signed_prekey_pub`   — medium-term DH key + signature under the identity key.
- `one_time_prekeys[]`  — batch of OTKs (server pops one per session).

Everything here is **public**. The server never stores plaintext private keys; encrypted-at-rest private blobs live in `app/security/key_backup.py` (separate concern — user can opt out).

## Key exchange flow (room invite)

```
Alice invites Bob to a room:
  GET /api/keys/prekeys/<bob>         → { signed_prekey, otk, ids }
  (client-side) performs X3DH-like handshake, derives shared key K
  ECIES-encrypts the room key under K → sends via /api/rooms/<id>/keys/deliver
  Bob fetches his queued key packet → decrypts with his OTK → has the room key
```

## Related

- `app/security/key_exchange.py` — X3DH-like composition (the protocol itself).
- `app/security/double_ratchet.py` — per-session ratchet after the initial exchange.
- `app/security/key_backup.py` — encrypted vault for user's own keys (client-controlled passphrase).
- `app/session/handoff_token.py` — pairing new devices without re-typing the seed.

## Limits

| Setting                 | Default | Purpose                                          |
| ----------------------- | ------- | ------------------------------------------------ |
| `PREKEY_BATCH_SIZE`     | 100     | How many OTKs the server allows at once.         |
| `PREKEY_REFILL_MIN`     | 20      | Client re-uploads when pool drops below this.    |
| `SIGNED_PREKEY_ROTATE_DAYS` | 30  | Forced rotation for the signed prekey.           |

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
