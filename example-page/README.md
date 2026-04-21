# `example-page/` — Minimal Embedded Vortex Client

A 3-file standalone page that shows how to embed the Vortex chat UI (or a lightweight shim over it) in any plain-HTML site. Zero build step, zero dependencies, drop-in.

## Files

| File         | Role                                                                             |
| ------------ | -------------------------------------------------------------------------------- |
| `index.html` | Page shell. Loads `style.css` + `script.js`. A single `<div id="app">` host.     |
| `style.css`  | Self-contained styling — no framework, no variables from the main app.           |
| `script.js`  | Demo logic. Uses the Vortex HTTP API (`/api/authentication/login`, `/api/rooms`, `/api/chat`) over plain `fetch`. |

## Running

Serve it from any static host:

```bash
cd example-page
python -m http.server 7777
# open http://localhost:7777/
```

By default `script.js` points at `https://localhost:8000` — edit the `NODE_URL` constant at the top of the file to target a real node.

## What it demonstrates

- A minimal registration + login flow against the REST API.
- Receiving messages over WebSocket (`wss://<node>/ws/chat/<room_id>`) with JWT from login.
- How to do client-side X25519 key derivation and AES-256-GCM message decryption using `window.crypto.subtle` — no external crypto library.

## What it is NOT

- Not a polished UI. Use `../static/` + `../templates/` if you want the full experience.
- Not a demo of federation, streams, calls, BMP, or any advanced feature.
- Not production-ready — it trusts the node's TLS cert without pinning.

Intended as a 200-line reference for "can I really call Vortex from plain JS?". Yes.

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
