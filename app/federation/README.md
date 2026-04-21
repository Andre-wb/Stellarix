# `app/federation/` — Node-to-node Federation

Everything that carries data **between Vortex nodes**. The node-to-client plane uses `chats/` + WebSocket; the node-to-node plane lives here.

Federation is strictly **opt-in** and uses a **trusted-node list** — nodes exchange payloads only with peers they've explicitly accepted, and only for rooms whose owners have opted into replication.

## Files

| File                 | Role                                                                                   |
| -------------------- | -------------------------------------------------------------------------------------- |
| `federation.py`      | FastAPI router at `/api/federation/*`. Envelope POST in, ack out. Verifies peer signature, enforces rate limits, dispatches to `replication.py`. |
| `replication.py`     | Pull-and-push replication engine. Lazy: we don't pre-push messages, peers fetch what they need by `(room_id, message_id_range)` and we verify they're authorised to have it. |
| `trusted_nodes.py`   | CRUD for the trusted-node list. Every add requires a challenge-response handshake so both sides prove they control the claimed Ed25519 identity. |

## Trust flow

```
Admin on Node A clicks "Add peer node-B":
  → GET  https://node-b/.well-known/vortex-peer  (pubkey, endpoints, controller-signed)
  → POST https://node-b/api/federation/link-challenge  { nonce, sig_A(nonce) }
  → Node B signs back with its own identity + stores Node A in its trusted list
  → Both sides persist the link; either can revoke it at any time
```

After the link is established, federation payloads are **POST /api/federation/envelope** with:

- `from_pubkey`, `to_pubkey` — the two node identities.
- `seq` — monotonic per-link sequence number.
- `payload_ct` — AES-GCM ciphertext of the actual federation message (message batch, room-key offer, presence update).
- `sig` — Ed25519 over `(from, to, seq, payload_ct)`.

Each node keeps a local `seen_seqs` table to reject replays.

## Replication model

- **Eventual** — we do not block a user's send path on federation. Outbox-style queue, retries with backoff, drops messages older than `FEDERATION_MAX_AGE_DAYS`.
- **Room-scoped** — replication respects E2E boundaries. Peer nodes relay ciphertext; they cannot decrypt unless they're also a room member.
- **Authoritative per message** — every message carries the author's signature over its plaintext hash, so any node can verify origin regardless of which path the message took.

## Settings

| Setting                         | Default | Purpose                                                 |
| ------------------------------- | ------- | ------------------------------------------------------- |
| `FEDERATION_ENABLED`            | `true`  | Master switch.                                          |
| `FEDERATION_MAX_PEERS`          | 64      | Hard cap on trusted peers.                              |
| `FEDERATION_MAX_AGE_DAYS`       | 14      | Messages older than this are not re-replicated.         |
| `FEDERATION_RATE_PER_SEC`       | 50      | Per-peer inbound envelope rate limit.                   |
| `FEDERATION_REQUIRE_CONTROLLER_SIG` | `true` | Reject peers not currently approved by the controller. |

## Not federation

- **Cross-node reads** without a trust link are handled by `../peer/_router.py` (opportunistic, read-only, rate-limited).
- **Mass-delivery to subscribers** of a channel uses `../peer/peer_federation.py` (fanout, not pairwise).

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
