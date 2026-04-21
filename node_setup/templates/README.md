# `node_setup/templates/` — First-run Wizard Templates

Jinja2 templates for the server-side first-run wizard (see `../README.md`).

## Files

| File                   | Role                                                                           |
| ---------------------- | ------------------------------------------------------------------------------ |
| `setup.html`           | Shell for the whole wizard — progress ribbon + step container.                 |
| `partials/`            | Per-step fragments included from `setup.html` based on current wizard state.   |

## Partials

Each partial is a self-contained form for one step:

- `network.html`      — port + bind address.
- `identity.html`     — generate or paste seed.
- `ssl.html`          — pick SSL path (self-signed / ACME / import).
- `database.html`     — pick backend + test connection.
- `peer.html`         — controller pubkey + mirror URLs.
- `extras.html`       — Tor / BMP / stealth toggles.
- `finalize.html`     — review + commit.
- `done.html`         — success screen, redirects to the main UI.

(Exact file list may vary — check the directory listing for the shipped set.)

## Convention

- Partials only accept the current state via the Python-side `wizard.py` state machine; they don't fetch anything of their own.
- Every form POSTs back to `/setup/<step>`; `wizard_routes.py` validates, updates state, and re-renders the next step.
- No JS dependencies — these pages are usable in `curl` + `w3m` if needed.

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
