# `templates/screens/` — Full-page Screens

Top-level screen templates. Each one corresponds to a primary route. Every screen `{% extends "base.html" %}` and fills the page-specific `<main>` block.

## Files

| File                   | Route                                   | Content                                       |
| ---------------------- | --------------------------------------- | --------------------------------------------- |
| `welcome.html`         | `/`                                     | Landing + sign-up / sign-in entry points.     |
| `auth.html`            | `/auth`                                 | Register, login (password / seed / passkey / QR), 2FA challenge. |
| `chat.html`            | `/chat`                                 | The core chat UI — sidebar + active room + (optional) right panel. |
| `room_settings.html`   | `/room/<id>/settings`                   | Room settings — members, permissions, keys, themes, forum topics. |
| `bots.html`            | `/bots`                                 | Bot marketplace entry + my-bots listing.      |
| `ide.html`             | `/ide`                                  | The built-in IDE for Gravitix + Architex editing + live preview. |
| `calls.html`           | `/calls`                                | Call history + active-call panel.             |
| `voice_channel.html`   | `/space/<id>/voice/<channel>`           | Persistent voice channel view (always-on talk room). |
| `contacts.html`        | `/contacts`                             | Contact list + add / invite / sync flow.      |
| `settings.html`        | `/settings`                             | User settings — profile, privacy, security, notifications, themes, i18n. |
| `story_viewer.html`    | `/story/<id>`                           | Full-screen story viewer with tap-through + viewer-count. |

## Convention

Each screen includes the components it needs via `{% include "components/…" %}`. For example `chat.html` composes `sidebar.html`, `bottom_tabs.html`, `room_info_panel.html`, and `thread_panel.html` over a shared chat layout.

## Routing

Routes are defined on the Python side (`app/main.py` includes `*Jinja2Templates.TemplateResponse()` calls). The SPA then takes over after initial render — subsequent navigation is client-side history manipulation, no further template fetches unless the user follows a deep link.

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
