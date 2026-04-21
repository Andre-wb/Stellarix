# `vortex_wizard/web/admin/` — Operator Dashboard Pages

Pages shown after first-run setup completes — the operator dashboard. Accessible from the wizard's main menu once a node is configured and running.

## Typical pages

- `overview.html`   — live stats: requests/sec, errors/sec, peer count, connected WS, DB health.
- `settings.html`   — live settings editor (calls `/api/settings/*`).
- `peers.html`      — discovered + trusted-federation peers; manual pin + unpin.
- `security.html`   — BMP / stealth / Tor / WAF live toggles, secret rotation.
- `backup.html`     — run now / schedule / restore.
- `database.html`   — vacuum, reindex, table sizes, slow-query snapshot.
- `logs.html`       — tail + grep.
- `diagnostics.html`— profile, hardware probe, env dump.
- `seed.html`       — BIP39 derive demo, Shamir split, key-backup vault status.
- `multidevice.html`— device-linking flow.
- `audit.html`      — append-only action log inside the wizard.
- `about.html`      — version + integrity report + credits.

## Convention

- Pages auth against the node's admin token (saved once during setup into the OS keychain).
- Long-running operations (big backup, integrity re-sign) dispatch to `../../api/ops_jobs.py` and poll progress via SSE.
- Never store secrets in `localStorage`; use the platform keychain bridge exposed by pywebview.

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
