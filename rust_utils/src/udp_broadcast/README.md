# `rust_utils/src/udp_broadcast/` — LAN Broadcast Extensions

Advanced discovery modes on top of `udp_broadcast.rs` (flat file at `../`). The flat file handles the basic "I am a Vortex node" broadcast on UDP/4200 — this folder adds multicast, multi-subnet, and replay protection.

## What's here

- **Multicast** variant for networks where broadcast is filtered but multicast (e.g. `239.x.y.z`) is allowed.
- **Multi-subnet** fan-out — send the same announce on every locally-connected interface, not just the default.
- **Replay protection** — each announce carries a monotonic counter + short-lived signature; receivers reject duplicates or future-dated announces.
- **Compact payload** — packs pubkey + endpoint + version flags into a single UDP datagram that fits within the default MTU.

## Why not in `udp_broadcast.rs`?

The single-file version is <200 lines and covers 80% of setups. Anything beyond that (multicast config, multi-NIC policy, signed replay window) adds enough state to deserve its own `mod.rs` + helpers.

## Tests

End-to-end tests spin up a mock "network" via `tokio::net::UdpSocket` loopback and exercise announce + receive across both transports.

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
