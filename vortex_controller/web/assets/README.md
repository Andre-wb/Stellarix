# `vortex_controller/web/assets/` — Controller Site CSS + JS

CSS + JS assets served at `/static/*` by the controller site.

Typical layout:

```
assets/
├── css/
│   ├── theme.css           ← palette tokens
│   ├── layout.css          ← shell layout (header, nav, page body)
│   └── page-<name>.css     ← one stylesheet per page
├── js/
│   ├── controller.js       ← shared helpers + signed-response verification
│   ├── page-<name>.js      ← per-page behaviour (nodes table, admin dashboard, etc.)
│   └── sig.js              ← Ed25519 signature verification (vanilla WebCrypto + small helper)
└── img/                    ← static imagery referenced by pages
```

## Signed-response verification

`sig.js` verifies every `/v1/*` response against the controller's pubkey pinned at build time. Pages **must** call `controller.fetchSigned(url)` instead of raw `fetch()` — an unsigned or wrong-signature response is rejected before it reaches the renderer, so a hostile MITM can't spoof node URLs.

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
