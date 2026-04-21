# `test-controller/web/` — Test Controller Static Site

Static site for the lightweight test controller harness (`../server.py` serves it). A stripped-down copy of `vortex_controller/web/` used by the test suite to exercise the node's controller-client flow without needing a real controller running.

## Layout

```
web/
├── index.html               ← minimal landing
├── nodes.html, entries.html ← pages the node may hit
├── locales/                 ← minimal locale JSON
├── icons/                   ← minimal icon set
└── assets/                  ← CSS + JS
```

## When used

- Playwright / pytest integration tests that need a stub controller responding to `/v1/*`.
- Local dev without wanting to run a full PostgreSQL-backed controller.

## Differences from the real controller

- No signed responses — returns plain JSON. Good enough for tests that don't verify signatures. Tests that DO verify pin a fixed keypair instead.
- Reduced endpoint set — only the paths the test actively hits.
- No admin dashboard.

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
