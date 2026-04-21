# `vortex_controller/web/` — Controller Public Site

Static multi-page site served by the controller on `:8800`. Each page is a plain HTML shell backed by the controller's signed `/v1/*` API — no framework, no build step.

## Pages

| Path                | Served file       | Content                                                            |
| ------------------- | ----------------- | ------------------------------------------------------------------ |
| `/`                 | `index.html`      | Landing — stats, "how it works", download entry.                  |
| `/nodes`            | `nodes.html`      | Approved-node browser (pubkey, endpoints, last seen, code_hash).  |
| `/entries`          | `entries.html`    | Signed bootstrap URLs.                                             |
| `/mirrors`          | `mirrors.html`    | Mirror health status (plain HTTP + Tor).                          |
| `/security`         | `security.html`   | Controller integrity status + trust model explainer.              |
| `/admin`            | `admin.html`      | Revenue dashboard (bearer-token guarded on the API side).         |

## Assets

```
web/
├── *.html                   ← one per page
├── favicon.ico
├── icons/                   ← site icons
├── assets/
│   ├── css/
│   ├── js/                  ← per-page behaviour
│   └── img/
└── locales/                 ← operator-facing strings (fewer than the main app)
```

All paths are mapped in `vortex_controller/main.py` via explicit `add_api_route` calls — no wildcard static routing for HTML so we always know what the controller is serving.

## API calls from the frontend

Every page hits the controller's own `/v1/*` endpoints via `fetch`. Responses are signed; the page verifies signatures **client-side** against the pinned pubkey baked into `assets/js/controller.js` before rendering — so even a MITM of the static HTML can't spoof data fields.

## i18n

The controller site ships a smaller locale subset than the main app. Keys live under `locales/<lang>.json` and cover operator-facing strings only (stats labels, table headers, explainer copy).

## Admin page

`/admin` renders a token prompt on first visit. All data fetches include `Authorization: Bearer <token>`. The page itself contains no secrets — the token lives in `sessionStorage` only. Closing the tab kills the session.

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
