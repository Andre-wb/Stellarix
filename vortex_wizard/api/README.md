# `vortex_wizard/api/` — Wizard Backend Routers

FastAPI routers that back every page in the desktop wizard UI. Each module is mounted under `/api/<name>` by `vortex_wizard/server.py`.

See the top-level [`../README.md`](../README.md) for the full module table. This README is a one-stop index for picking the right handler when adding a feature.

## Responsibility split

| Layer                     | Where                               |
| ------------------------- | ----------------------------------- |
| UI (HTML + JS)            | `../web/`                           |
| API endpoints             | `./` (this folder)                  |
| Backing node operations   | The actual Vortex node lives in `../../app/` and `../../vortex_controller/`. The wizard talks to them via local HTTP + shell shims. |

Handlers in this folder are intentionally thin — they parse request bodies, call into the node's live endpoints or the operator helpers, and return shaped JSON.

## Module groupings

### Setup / onboarding

`setup_api.py`, `onboarding.py`, `settings_api.py`, `seed_tools.py`, `seed_derive.py`

### Operator tools

`operator.py`, `admin_api.py`, `supervisor.py`, `ops_jobs.py`, `scheduler.py`, `alerts.py`, `audit.py`

### Diagnostics

`monitoring.py`, `metrics.py`, `hardware.py`, `logs_tools.py`, `profiler.py`, `devex.py`

### Security

`security_api.py`, `secrets_mgr.py`, `backup_api.py`, `backup_plus.py`

### Network

`advanced_net.py`, `peer_advanced.py`, `peer_tools.py`

### Database

`db_api.py`, `db_ops.py`, `db_tools.py`

### Misc

`ai_setup.py`, `multidevice.py`, `deploy_gen.py`

## Conventions

- One router (`router = APIRouter(prefix="/api/<name>", tags=["wizard:<name>"])`) per module.
- All endpoints return `{ "ok": true, "data": … }` or `{ "ok": false, "error": { "code", "message" } }` — the wizard UI unwraps this uniformly.
- Long-running operations (backup, integrity re-sign, cert renewal) return a job id immediately and push progress through `ops_jobs.py`.
- Destructive actions require the admin token even inside the wizard.

## Testing

The wizard has a lightweight pytest harness at `../tests/` (not bundled into PyInstaller). Each module has a happy-path and error-path test.

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
