# `app/peer/` — Peer Discovery & Cross-node Routing

Everything about **finding other nodes** and **talking to them opportunistically** (without setting up a full federation link). Four discovery channels feed into a single `peer_registry` that the rest of the node reads from.

Endpoints live under `/api/peer/*`.

## Files

### Discovery

| File                 | Role                                                                               |
| -------------------- | ---------------------------------------------------------------------------------- |
| `peer_discovery.py`  | Orchestrator. Merges signals from every source, de-duplicates, scores by health.   |
| `peer_registry.py`   | In-memory + DB-backed registry. Survives restarts; flushed to `peer_*` DB tables. |
| `peer_p2p.py`        | LAN UDP broadcast (port 4200) — zeroconf-style "I am a Vortex node".              |
| `controller_client.py` | Polls `vortex_controller/` for signed entry URLs and a random set of approved nodes. Verifies the controller signature before accepting anything. |
| `controller_proxy.py`| Lightweight proxy exposed on the node so LAN-local clients that can't reach the controller domain directly can still get entry URLs via their own node. |
| `sns_resolver.py`    | Resolves `vortexx.sol` via Solana Name Service — the canonical bootstrap name.    |
| `solana_registry.py` | Reads on-chain peer PDAs (see `../../solana_program/`). Applies trust-decay to stale nodes. |
| `redis_pubsub.py`    | Cluster-wide discovery sync. Optional — enables multi-node deployments behind the same controller to share a live peer set. |

### Models

| File                 | Role                                                                               |
| -------------------- | ---------------------------------------------------------------------------------- |
| `peer_models.py`     | SQLAlchemy rows for discovered peers, heartbeats, trust scores.                    |
| `peer_public_keys.py`| Known pubkey pins per peer — prevents swap-and-spoof.                              |

### Cross-node routing

| File                | Role                                                                                |
| ------------------- | ----------------------------------------------------------------------------------- |
| `_router.py`        | Private entry point; wires the remaining files into a single FastAPI router.        |
| `peer_routes.py`    | Public read-only endpoints: list peers, per-peer status, traceroute-style probe.   |
| `peer_federation.py`| Fanout path for channels / public rooms. Distinct from pairwise federation in `../federation/` — this one is best-effort, not guaranteed. |
| `edge_cache.py`     | Local LRU for publicly-cacheable responses (sticker packs, bot avatars, channel posts) served to LAN peers. |

### Integrity

| File                 | Role                                                                               |
| -------------------- | ---------------------------------------------------------------------------------- |
| `integrity_cross.py` | Cross-node integrity probe — asks a peer for its `INTEGRITY.sig.json` hash and compares to its on-chain `code_hash`. Flags divergences. |

## Discovery channels — summary

| Channel           | Reach              | Latency       | Trust source                        |
| ----------------- | ------------------ | ------------- | ----------------------------------- |
| UDP broadcast     | Same L2 broadcast  | <1s           | Weak (LAN only); pubkey verified on first connect. |
| Controller        | Global             | ~seconds      | Pinned controller Ed25519 key.      |
| Solana registry   | Global, censored-network friendly | ~seconds | On-chain, permissionless.           |
| Redis pubsub      | Cluster            | sub-second    | Cluster-internal (shared secret).   |

## Related

- `../transport/` — how we actually talk to peers once we've found them (obfuscation, BMP, Tor, BLE).
- `../federation/` — opt-in, trust-linked node-to-node exchange.
- `../../vortex_controller/` — the control plane itself.
- `../../solana_program/` — on-chain registry.

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
