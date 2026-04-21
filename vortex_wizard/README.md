# `vortex_wizard/` — Desktop Setup + Node Runner

A single executable that ships the **node backend** and a **native-looking setup GUI** in one bundle. End-users don't need to know about Python, venvs, or config files — they double-click and answer questions.

## Two modes of the same binary

```bash
# 1. Default — launches the pywebview wizard
./dist/vortex-wizard

# 2. Run the node backend instead (re-exec of run.py inside the bundle)
./dist/vortex-wizard --run-node
```

When the wizard finishes configuration, it spawns its own `--run-node` child and opens a browser-like webview onto `https://localhost:<port>`.

## Layout

| Path                   | Role                                                                           |
| ---------------------- | ------------------------------------------------------------------------------ |
| `__main__.py`          | Entry point. Dispatches between wizard and `--run-node`. Injects the bundled node tree into `sys.path` via `sys._MEIPASS`. |
| `app.py`               | Wizard application class — holds webview window, FastAPI sub-process, shared state. |
| `server.py`            | Local FastAPI server that powers the wizard UI (handlers under `api/`).       |
| `vortex-wizard.spec`   | PyInstaller spec. Bundles `app/`, `vortex_controller/`, `run.py`, `alembic/`, `static/`, `templates/`, `logo/`, integrity manifests, and every hidden import needed by FastAPI / SQLAlchemy / webview / cryptography / vortex_chat. |
| `requirements.txt`     | Pinned deps for local development (outside the bundle).                        |
| `api/`                 | FastAPI routers that back each wizard page (setup, peers, DB, security, …).   |
| `web/`                 | Vanilla-JS front-end (HTML + CSS + JS served by `server.py`).                 |

### `api/` — Wizard backend (32 modules)

Each module is a FastAPI router mounted under `/api/<name>`. They implement the endpoints the UI calls when an operator clicks "Run diagnostics" / "Generate seed" / "Build backup" / etc.

| Module              | Surface                                                                |
| ------------------- | ---------------------------------------------------------------------- |
| `setup_api.py`      | Core onboarding flow — port, identity, SSL, DB, mirrors.               |
| `settings_api.py`   | Live settings editor for a running node.                               |
| `admin_api.py`      | Admin-only actions (reset, wipe, reindex).                             |
| `security_api.py`   | Security knobs — BMP toggle, stealth level, WAF rules, Tor HS setup.   |
| `secrets_mgr.py`    | Rotates JWT + CSRF + controller-token secrets.                         |
| `backup_api.py`     | Signed config backup / restore.                                        |
| `backup_plus.py`    | Extended backup — message DB, room keys, federation state.             |
| `seed_derive.py`    | BIP39 seed → X25519 + Ed25519 derivation demo and sanity checks.       |
| `seed_tools.py`     | Shamir split, key backup vault status, passphrase strength meter.      |
| `multidevice.py`    | Device linking, per-device key rotation, revocation.                   |
| `onboarding.py`     | "Out-of-box" experience — language picker, theme, restore-from-cloud.  |
| `advanced_net.py`   | NAT traversal, UPnP, port-forward advice, IPv6 detection.              |
| `peer_advanced.py`  | Manually pin peers, run a controller preflight.                        |
| `peer_tools.py`     | Gossip traceroute, peer health snapshot.                               |
| `db_api.py`         | Pick DB backend, test connectivity, run migrations.                    |
| `db_ops.py`         | Vacuum, re-index, table sizes, slow-query snapshot.                    |
| `db_tools.py`       | Export schema + integrity check.                                       |
| `deploy_gen.py`     | Generates a `docker-compose.yml` / systemd unit for the current config.|
| `hardware.py`       | CPU / RAM / disk probe; OS & Python version.                           |
| `logs_tools.py`     | Tail, grep, rotate, archive node logs.                                 |
| `metrics.py`        | Basic Prometheus scrape for the wizard itself.                         |
| `monitoring.py`     | Live charts — req/s, error rate, peer count.                           |
| `profiler.py`       | One-shot py-spy / `sys.settrace` sampler.                              |
| `supervisor.py`     | Start / stop / restart the node sub-process.                           |
| `scheduler.py`      | Periodic tasks (backup, integrity re-sign, cert renew).                |
| `alerts.py`         | Desktop notifications on critical events.                              |
| `audit.py`          | Append-only action log (who clicked what in the wizard).               |
| `ai_setup.py`       | AI provider picker (OpenAI-compat / Qwen local).                       |
| `operator.py`       | Misc operator helpers — restart, backup now, export report.            |
| `ops_jobs.py`       | Long-running background jobs (big backups, re-signs).                  |
| `devex.py`          | Developer-only knobs — hot reload, Python debugger bridge.             |

## Building

```bash
cd /Users/borismaltsev/RustroverProjects/Vortex
pip install -r requirements.txt          # + PyInstaller
pyinstaller vortex_wizard/vortex-wizard.spec --clean --noconfirm
```

Produces:

- `dist/vortex-wizard/` — raw folder bundle
- `dist/Vortex Wizard.app` — macOS app (only on darwin)

On Linux / Windows the bundle is a folder with the launcher inside.

## Integrity

The bundle ships `INTEGRITY.sig.json` and `INTEGRITY.repo.json`. `scripts/integrity_repo.py` is imported via `importlib` from inside the bundle so "Sign repo" / "Verify" buttons in the wizard work without a dev checkout.

## macOS quirks

- `NSAppTransportSecurity` allows local networking and arbitrary loads (we host our own TLS on `localhost`).
- Cloudflare-tunnel mirror mode forces `--protocol http2` — QUIC tunnels time out reliably on macOS.
- `LSUIElement=False` so the wizard shows up in the Dock.

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
