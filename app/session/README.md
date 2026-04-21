# `app/session/` — Multi-device Handoff & Migration

Everything that lets one user run Vortex on multiple devices without re-entering the seed. This is NOT login (see `../authentication/`) — it's the wiring that moves an authenticated session between devices while preserving E2E keys.

## Files

| File                  | Role                                                                                  |
| --------------------- | ------------------------------------------------------------------------------------- |
| `handoff_token.py`    | Short-lived signed token the already-authenticated device hands to the new device (scanned from QR or typed in). Carries a one-time-encrypted bundle of the identity + room keys. |
| `migration.py`        | Full migration — moving an account from node A to node B. Exports the user's federated state, mints a signed migration payload, coordinates re-registration on the new node. |
| `migration_pusher.py` | Push-style migration progress updates. Keeps the user informed while the transfer is in flight (rooms, messages, keys, files…). |

## Handoff flow

```
Device A (authenticated)          Server               Device B (new)
──────────────────────           ──────               ──────────────
POST /session/handoff/new    ──▶
                                   store nonce
                             ◀──── { handoff_id, qr_payload }
show QR                                                 scan QR
                                                        POST /session/handoff/accept
                                                          { handoff_id, device_pub, sig }
                             ◀──── notify A                       │
A shows "confirm?" prompt                                           │
POST /session/handoff/approve  ──▶
  encrypt bundle(identity, rooms, prekeys) with
  per-session key derived from handoff nonce + device_pub
                                   relay ciphertext ────▶
                                                          decrypt with own priv + nonce
                                                          provision local DB → ready
```

At no point does the server see the plaintext bundle — the nonce lives in Device A; Device B's private key never leaves it. The server relays a blob it cannot decrypt.

## Account migration flow

Triggered when a user wants to move their entire account from their current node to another node (e.g. because their previous node operator decided to shut down).

```
POST /api/session/migration/start        # on the source node
  → signed export blob + target_node URL

POST /api/session/migration/receive      # on the target node
  body = export blob
  → re-register the user + restore their keys, rooms (via pull federation), bots

POST /api/session/migration/finalize     # on the source node
  → mark source account as migrated; future requests redirect.
```

Messages, files, and room memberships are re-pulled from the rooms themselves (clients in those rooms re-send what they have). The migration does not require the old node to remain online after finalize.

## Why separate from `authentication/`

- `authentication/` is stateless proofs (password, key sig, 2FA).
- `session/` is **stateful, cross-device** — it assumes you're already authenticated on at least one device and want to extend or move that trust.
- Mixing them would push too much complexity into the login path; every auth handler would have to also consider "am I a handoff target?".

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
