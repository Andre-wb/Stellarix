# `app/media/` — SFU Bridge

Selective Forwarding Unit (SFU) integration for group voice / video / streaming. A one-module package that only wraps the external SFU — the SFU itself lives out-of-process (it can be `mediasoup`, `Janus`, `livekit`, or any server that speaks a compatible signalling protocol).

## Files

| File            | Role                                                                          |
| --------------- | ----------------------------------------------------------------------------- |
| `sfu_bridge.py` | Creates short-lived scoped JWTs for clients, proxies signalling messages, tears down stale sessions. Enforces room membership before issuing a token. |

## Why an SFU

- **1-to-1 calls** go fully peer-to-peer over WebRTC. No SFU needed.
- **Small groups** (≤4) can still mesh P2P.
- **5+ participants** or broadcast streams route media through the SFU — fan-out is O(n) bandwidth per uplink instead of O(n²).

## Flow

```
client                    node                         SFU (external)
  │ POST /api/voice/join   │                              │
  │  { room_id }           │                              │
  │                        │ verify membership + perms    │
  │                        │ POST /admin/room (new)       │──▶
  │                        │ POST /admin/token (per user) │──▶
  │ ◀─────── { sfu_url, token, ice } ─────────────────────│
  │                                                       │
  │ wss://sfu/signal ──────────────────────────────────▶ │
  │ (WebRTC negotiation + media)                         │
```

The Vortex node **never proxies media bytes** — it only hands out scoped tokens and cleans up rooms when the last member leaves.

## Configuration

| Env var                  | Purpose                                           |
| ------------------------ | ------------------------------------------------- |
| `SFU_URL`                | Admin endpoint of the SFU (e.g. `http://sfu:7880`). |
| `SFU_API_KEY`, `SFU_API_SECRET` | Shared HMAC secret for minting tokens.     |
| `SFU_JWT_TTL_SECONDS`    | Token validity window (default 300).              |
| `SFU_RECORDINGS_DIR`     | Where the SFU stores recordings (if enabled).     |

## Related

- `app/chats/sfu.py` — thin router that exposes the bridge to clients.
- `app/chats/voice.py`, `app/chats/group_calls.py`, `app/chats/stream.py` — feature code that actually calls the bridge.
- `deploy/k8s/vortex.yaml` — includes an optional SFU sidecar/deployment example.

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
