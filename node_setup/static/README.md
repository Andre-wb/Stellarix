# `node_setup/static/` — First-run Wizard Assets (CSS + JS)

Static assets for the **server-side** first-run wizard (see `../README.md`). Served at `/setup/static/*` while the node has no `config.yaml`; after first successful finish, the setup routes and this directory stop being served.

## Layout

```
static/
├── css/            ← wizard-specific stylesheets (setup form, progress ribbon)
└── js/             ← step validators, form helpers, SSE progress updates
```

## Why it's separate from `../../static/`

- The main web UI (`../../static/`) is large — 41 CSS files, 65+ JS modules, 146 locale files, vendored third-party libs. Loading it for a 5-minute setup flow is overkill.
- The setup wizard must work **without** a configured database or any of the feature modules — so it can't depend on any asset that assumes the node is bootstrapped.
- Keeping the setup UI self-contained also means operators running `python -m node_setup` manually get a predictable experience without any hidden dependency on the main site.

## Conventions

- Vanilla JS, no framework.
- Each step's JS module binds to the form on that step only; no shared state across steps beyond what the server persists.
- Minimal styling — system fonts, no custom icon fonts.

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
