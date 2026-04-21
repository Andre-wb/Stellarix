# `static/js/chat/` — Chat-UI Modules

Per-concern chat-UI modules. Each attaches to `window.Chat.<Namespace>` via the loader in `../main.js`.

## Modules

- `composer.js` — message composer: text input, attachment bar (mic + file), scheduled-send picker, slash-command autocomplete.
- `renderer.js` — message bubble renderer — text, media, polls, cards, Architex Mini App embeds, fallback "unknown kind" tile.
- `reactions.js` — react / long-press menu, reaction picker, animated counters.
- `read_receipts.js` — "seen by N" pill under outgoing bubbles.
- `typing.js` — typing indicator over composer.
- `threads.js` — thread side panel + thread creation.
- `presence.js` — online / typing / read state from the shared presence channel.
- `scheduled.js` — scheduled-send queue UI.
- `voice.js` — voice-note player / recorder integration.

## Conventions

- Each module binds on `init(rootElement)` and unbinds on `teardown()` — the chat screen's owner calls both on route change.
- No direct DOM mutation outside the rooted element.
- No cross-module imports — communicate via `window.Chat.bus.emit/on`.

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
