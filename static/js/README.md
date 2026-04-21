# `static/js/` — JavaScript Modules

65 top-level modules + nested packages. Classic scripts (no bundler), loaded by `../../templates/base.html` in dependency order. Each module attaches entry points to `window.<namespace>`.

## Top-level modules (selected)

### Bootstrap & infra

| File                          | Purpose                                                              |
| ----------------------------- | -------------------------------------------------------------------- |
| `main.js`                     | Boot glue — registers components, modals, focus-trap, global hotkeys.|
| `i18n.js`                     | Locale loader + `t("key")` helper, fallback chain.                   |
| `pwa.js`                      | Service-worker registration + install prompt.                        |
| `preferences.js`              | User preferences persistence (localStorage + sync).                  |
| `inline-handlers.js`          | Thin bridge used by `inline_scripts.html` (nonced bootstrap).        |
| `notification-sounds.js`      | Short audio notifications per-event kind.                            |
| `notifications.js`            | Cross-room notification aggregation.                                 |

### Auth & identity

| File                       | Purpose                                                                 |
| -------------------------- | ----------------------------------------------------------------------- |
| `auth.js`                  | Register / login / logout / refresh flow.                               |
| `phone_password.js`        | Phone + password auth variant.                                          |
| `crypto.js`                | Client-side crypto wrappers (WebCrypto + our thin helpers).             |
| `fingerprint.js`           | Key-fingerprint verification UI.                                        |
| `key_backup.js`            | Key-backup vault UI + round-trip.                                       |
| `panic.js`                 | Panic mode — trigger + confirm flow.                                    |

### Real-time

| File                       | Purpose                                                                 |
| -------------------------- | ----------------------------------------------------------------------- |
| `peers.js`                 | Peer discovery + connection state UI.                                   |
| `network_status.js`        | Online / offline / degraded banner.                                     |
| `e2e_media.js`             | E2E media pipeline — encrypt before upload, decrypt after download.     |
| `e2e_media_worker.js`      | Worker-thread media pipeline (non-blocking).                            |
| `photo_editor.js`          | In-browser photo editor — crop, rotate, filter, sticker overlay.        |
| `group_call.js`            | Group-call UI — tile grid, hand-raise, mute, screenshare.              |

### Transport / privacy

| File                       | Purpose                                                                 |
| -------------------------- | ----------------------------------------------------------------------- |
| `bmp-client.js`            | Client-side BMP — derive mailbox IDs, poll with cover traffic.           |
| `bmp-envelope.js`          | BMP envelope pack / unpack helpers.                                      |
| `architex-runtime.js`      | Architex UI DSL runtime shim used by Mini Apps in the browser.          |

### UI features

| File                 | Purpose                                  |
| -------------------- | ---------------------------------------- |
| `rooms.js`           | Room listing, create, join, leave.        |
| `contacts.js`        | Contact list UI.                          |
| `contact_sync.js`    | Contact-sync (hashed) flow.               |
| `onboarding.js`      | First-run onboarding screens.             |
| `lang-picker.js`     | Language switcher dropdown.               |
| `gestures.js`        | Touch gesture helpers.                    |
| `premium.js`         | Subscription status + upgrade flow.      |
| `bot-constructor.js` | Visual bot constructor UI.                |
| `a11y.js`            | Accessibility helpers (focus trap, SR announcements). |

### IDE

| File                 | Purpose                                               |
| -------------------- | ----------------------------------------------------- |
| `ide.js`             | Gravitix/Architex editor shell.                       |
| `ide-dev-settings.js`| IDE dev settings panel.                               |
| `ide-docs.js`, `ide-docs/` | In-IDE docs browser (mirrors `/docs.html`).     |

## Nested packages

| Path           | Contents                                                                   |
| -------------- | -------------------------------------------------------------------------- |
| `chat/`        | Message rendering, composer, reactions, threads, read-receipts, scheduled sends. |
| `ide/`         | Gravitix + Architex editor guts — syntax highlighting, autocompletion, lint, runner. |
| `ide-docs/`    | In-IDE docs browser supporting the same accordion scheme.                  |
| `rooms/`       | Sub-modules of the rooms UI (key status, theme editor, permissions).        |
| `lib/`         | Third-party shims kept small and vendored.                                  |
| `__tests__/`   | Headless browser unit tests for JS modules (run with jest).                 |

## Loading order

`../../templates/base.html` loads in this order:

1. Polyfills (if any) from `lib/`.
2. `i18n.js` — all subsequent modules may call `t("key")`.
3. `crypto.js` — needed by auth + messaging.
4. Core modules.
5. Feature modules.
6. `main.js` — last, wires everything.

Modules assume previous ones in the list are available — no deferred resolution.

## Testing

```bash
cd /Users/borismaltsev/RustroverProjects/Vortex
jest                        # runs __tests__ under static/js/
```

jest config lives at the repo root (`jest.config.js`) and uses `babel.config.js` only for ES2022 syntax — no React, no JSX.

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
