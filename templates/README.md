# `templates/` — Jinja2 HTML Templates

Server-rendered HTML shells. FastAPI's `Jinja2Templates` renders `base.html` on initial page load; everything after that is client-side JavaScript talking to the JSON API.

## Layout

| Path              | Role                                                                                   |
| ----------------- | -------------------------------------------------------------------------------------- |
| `base.html`       | Global shell — head, meta, preloads, loads every CSS + JS from `../static/`, injects i18n bootstrap data, renders the `<main>` placeholder that later SPA code fills. |
| `index.html.bak`  | Historic single-file index. Kept as a reference while the site is split into per-screen shells. Not served. |
| `screens/`        | Full-page screens. Each corresponds to a top-level route.                             |
| `components/`     | Re-usable fragments included across screens.                                          |
| `modals/`         | Pop-up fragments — lazy-loaded by the SPA as needed.                                  |

### `screens/`

| File                   | Route                                    |
| ---------------------- | ---------------------------------------- |
| `welcome.html`         | `/` — landing before auth.               |
| `auth.html`            | `/auth` — login + register + 2FA flows.  |
| `chat.html`            | `/chat` — main chat UI (rooms + messages).|
| `room_settings.html`   | `/room/<id>/settings`                    |
| `bots.html`            | `/bots` — bot marketplace + IDE entry.   |
| `ide.html`             | `/ide` — Gravitix + Architex editor.     |
| `calls.html`           | `/calls` — voice/video room view.        |
| `voice_channel.html`   | Voice-channel sub-view inside a space.   |
| `contacts.html`        | `/contacts`                              |
| `settings.html`        | `/settings`                              |
| `story_viewer.html`    | `/story/<id>`                            |

### `components/`

Cross-screen fragments loaded by one or more screens:

`sidebar.html`, `bottom_tabs.html`, `room_info_panel.html`, `thread_panel.html`, `stream.html`, `group_call.html`, `profile_modal.html`, `user_profile_modal.html`, `fingerprint_modal.html`, `lang_picker.html`, `pin_lock.html`, `contact_sync.html`, `birthday_picker.html`, `doc_viewer.html`, `page_viewer.html`, `inline_scripts.html`.

### `modals/`

Lazy-loaded pop-ups, one per feature:

`create_room.html`, `create_voice.html`, `files.html`, `folders.html`, `gallery.html`, `gif_picker.html`, `hidden_rooms.html`, `stickers.html`, `status.html`, `story_create.html`, `poll.html`, `report.html`, `payment.html`, `settings.html`, `bot_marketplace.html`, `contacts.html`, `spaces.html`.

## Conventions

- **No logic in templates.** Anything more complex than `{% if logged_in %}` lives in JavaScript.
- **Localisation** — strings come from `i18n.js` at runtime via `{{ t("key.name") }}`. Templates never hard-code user-visible English.
- **CSP-safe** — no inline styles, no inline `<script>` except the bootstrap block in `base.html` that injects the initial state (nonced).
- **Shared includes** — every screen extends `base.html` and composes its page-specific `<main>` block from `components/` fragments with `{% include "components/..." %}`.
- **Accessibility** — each modal has `role="dialog"` + focus trap wired up in `static/js/main.js`; every button has a real text label (visually hidden if icon-only).

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
