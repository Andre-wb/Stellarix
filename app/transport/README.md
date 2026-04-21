# `app/transport/` — Obfuscation, BMP, Covert Transport

Everything that shapes **how bytes leave the node**. This is where Vortex's censorship resistance lives: BMP (blind mailbox), cover traffic, Tor, CDN relay, BLE, Wi-Fi Direct, pluggable transports, stealth levels, steganography, HTTP-looking envelopes.

## Files

### BMP & metadata hiding

| File                 | Role                                                                               |
| -------------------- | ---------------------------------------------------------------------------------- |
| `blind_mailbox.py`   | BMP core. Derives per-epoch mailbox IDs from the shared secret (`HMAC-SHA256(S_AB, floor(t/T))[0:16]`), delivers ciphertext, polls for own mailboxes + ~50 decoys. See `../../RESEARCH-BMP.md`. |
| `cover_traffic.py`   | Periodic decoy traffic so an observer can't correlate real-message bursts with real conversations. |
| `metadata_padding` *(in rust_utils)* | Constant-length envelope padding. Called from here via `crypto.py`. |

### Pluggable / obfuscation

| File                  | Role                                                                              |
| --------------------- | --------------------------------------------------------------------------------- |
| `pluggable.py`        | Pluggable-transport abstraction (obfs4-style). Users can plug in an arbitrary byte-stream adapter. |
| `pluggable_routes.py` | REST surface for configuring pluggable transports at runtime.                     |
| `obfuscation.py`      | HTTP/HTTPS-looking envelopes; random-looking headers; ordering jitter.             |
| `stealth.py`, `stealth_http.py`, `stealth_level3.py`, `stealth_level4.py` | Four stealth levels, increasing in cost and in "looks-like-innocuous-traffic" fidelity. |
| `auto_stealth.py`     | Adaptive escalator — starts at stealth level 0, climbs when the current level stops working (RST, timeout, deep-inspection signatures). |
| `advanced_stealth.py` | Composition of multiple stealth techniques + randomised switching between them.    |
| `steganography.py`    | Hides ciphertext bytes inside cover images (LSB + whitenoise). Experimental.       |

### Transport channels

| File                  | Role                                                                              |
| --------------------- | --------------------------------------------------------------------------------- |
| `transport_manager.py`| Picks the best transport for a given outbound payload (HTTPS → HTTP/2 → Tor → BLE → Wi-Fi Direct) based on availability + user preference. |
| `ble_transport.py`    | Bluetooth Low-Energy data channel. For phones; LAN-friendly, no internet needed.   |
| `wifi_direct.py`      | Wi-Fi Direct transport. Higher throughput than BLE, same no-internet story.        |
| `nat_traversal.py`    | STUN/ICE, UPnP, and hole-punching helpers so two NATed nodes can connect.          |
| `cdn_relay.py`        | Relay Vortex traffic through an unwitting CDN endpoint (e.g. a static site) — domain fronting where available. |
| `sse_transport.py`    | Server-Sent Events fallback for environments that block WebSocket but allow long-poll. |

### Priority & routing

| File                     | Role                                                                           |
| ------------------------ | ------------------------------------------------------------------------------ |
| `priority_queue.py`      | Per-peer outbound queue with priority lanes — urgent (handshakes) > real-time (chat) > bulk (file chunks). |
| `smart_relay.py`         | Chooses intermediate peers for multi-hop routing when direct connection is impossible. |
| `store_forward.py`       | Offline store-and-forward — queues traffic until the recipient comes online.   |
| `knock.py`               | Port-knocking entry — hides the node's real listener behind a sequence of UDP pings. |
| `gossip_security.py`     | Anti-abuse guardrails on the gossip protocol — budget per peer, churn detection. |
| `global_transport.py`, `global_routes.py` | Top-level router + the cross-cutting decisions. Called by transport_manager. |
| `routes.py`              | Feature-scoped routes for diagnostics (traceroute a peer, ping over BLE, …).    |

## Stealth levels (summary)

| Level | Looks like                             | Cost                 | Use when                                    |
| ----- | -------------------------------------- | -------------------- | ------------------------------------------- |
| 0     | Plain HTTPS                            | 0                    | No censorship.                              |
| 1     | HTTPS + randomised headers             | ~5% overhead         | Mild DPI.                                   |
| 2     | HTTP/2 over a CDN-fronted domain       | latency +~50ms       | SNI-sniffing environments.                  |
| 3     | WebSocket wrapped as "video" stream    | ~15% overhead        | Protocol fingerprinting.                    |
| 4     | Steganographic image channel + padding | high (slow, expensive)| Active packet-inspection + rate-correlation.|

`auto_stealth.py` picks the lowest level that works and records escalations to an audit log.

## Related

- `../../rust_utils/` — the actual BMP / padding / stego implementations in Rust.
- `../peer/` — discovery. Once we have a peer, this folder decides how to talk to it.
- `../push/bmp_push_proxy.py` — uses `blind_mailbox.py` for push metadata hiding.
- `../security/tor_hidden_service.py` — orthogonal but complementary.

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
