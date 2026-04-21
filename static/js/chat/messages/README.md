# `static/js/chat/messages/` — Message Renderer Submodules

Per-kind renderers for the chat message list. One file per message kind so the renderer dispatcher in `../renderer.js` can lazy-load kinds on demand.

## Typical files

- `text.js` — plain text with link + emoji parsing.
- `image.js` — image bubble with tap-to-open-gallery.
- `video.js`, `audio.js` — media players.
- `file.js` — file attachment card.
- `poll.js` — poll renderer with vote state.
- `card.js` — generic rich card (title + body + buttons + image).
- `miniapp.js` — embedded Architex Mini App renderer.
- `system.js` — server-issued system messages (joined, left, renamed).
- `fallback.js` — "unknown kind" tile with raw hex dump.

## Conventions

- Every renderer exports `render(messageDOM, payload)` and `teardown(messageDOM)`.
- No cross-file imports — talk to `../bus`.

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
