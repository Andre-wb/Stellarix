# `node_setup/templates/partials/` — Per-step Form Fragments

Jinja fragments, one per wizard step. Included from `../setup.html` based on the wizard's current state.

## Fragments (typical)

- `network.html`    — port + bind address.
- `identity.html`   — seed generate / paste.
- `ssl.html`        — self-signed vs ACME vs import.
- `database.html`   — DB backend + test connection.
- `peer.html`       — controller pubkey + mirror URLs.
- `extras.html`     — Tor / BMP / stealth toggles.
- `finalize.html`   — review + commit.
- `done.html`       — success screen + redirect.

## Convention

- Each fragment renders one form.
- The form POSTs to `/setup/<step>` — handled by `../../wizard_routes.py`.
- No JavaScript required — each step is usable as a plain HTML form.

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
