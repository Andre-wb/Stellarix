# `static/js/rooms/` — Rooms-UI Modules

Per-concern rooms UI. Attaches to `window.Rooms.<Namespace>`.

## Modules

- `list.js` — the left-side rooms list (pins, unread counters, drag-to-reorder).
- `create.js` — create-room wizard integration (the modal itself is in `../../../templates/modals/create_room.html`).
- `members.js` — member panel: list, add, remove, change role.
- `permissions.js` — per-role permission matrix editor.
- `theme.js` — room theme editor (background, accent, icon tint).
- `keys.js` — key-rotation UI, fingerprint verification, pending-delivery indicator.
- `invite.js` — invite-code + link generator, QR.
- `forum.js` — forum-topics layout for rooms in forum mode.

Used by `../../../templates/screens/chat.html` and `room_settings.html`.

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
