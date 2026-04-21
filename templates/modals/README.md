# `templates/modals/` — Pop-up Fragments

Lazy-loaded modal fragments. The shell (`base.html` + active screen) ships without these; the SPA fetches them via `GET /modal/<name>` on first open and caches them in-memory.

## Files

| File                    | What it contains                                                      |
| ----------------------- | --------------------------------------------------------------------- |
| `create_room.html`      | New-room wizard — kind (private / public / sealed / voice), name, invite policy, theme preset. |
| `create_voice.html`     | New voice channel (persistent talk room).                             |
| `files.html`            | Room-scoped file gallery + filters + search.                          |
| `folders.html`          | User's folders (client-managed room organisation).                    |
| `gallery.html`          | Full-screen media viewer — swipe / zoom / pan / download.             |
| `gif_picker.html`       | GIF search (feeds from saved GIFs + public endpoint).                |
| `hidden_rooms.html`     | Hidden-room listing (rooms the user joined but chose to hide).        |
| `stickers.html`         | Sticker pack browser + subscribe flow.                                |
| `status.html`           | Post / view short statuses.                                           |
| `story_create.html`     | Story composer — image / video / text, 24h TTL.                       |
| `poll.html`             | Poll composer — question, options (up to 10), anonymous toggle.       |
| `report.html`           | Report flow — pick reason, free-text, routes to moderators.           |
| `payment.html`          | Donation / tip flow — pick chain, enter amount, sign with connected wallet. |
| `settings.html`         | In-modal view of settings (full screen also exists at `../screens/settings.html`). |
| `bot_marketplace.html`  | Search + install + rate bots from the marketplace.                    |
| `contacts.html`         | Contact picker for invites / DMs.                                     |
| `spaces.html`           | Spaces browser — switch, join, create.                                |

## Convention

- Every modal starts with `<div class="modal" role="dialog" aria-modal="true">` — the focus-trap in `../../static/js/main.js` binds on this attribute.
- Modals never include `<script>` — their JS lives in `../../static/js/` and attaches via `data-modal="<name>"`.
- Closing is handled centrally — click on backdrop, `Escape` key, or the shared close button. Individual modals don't implement their own dismiss.

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
