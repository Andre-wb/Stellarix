# `docs/` — Human-written Documentation

Hand-written Markdown files that don't fit the generated locale-driven docs site. Intended for developers working in a shell, not end users.

For the navigable multi-root docs portal (Vortex / Gravitix / Architex with accordions) see [`../vortex-introduce-page/docs.html`](../../vortex-introduce-page/docs.html).

## Files

| File                  | Audience                 | What's inside                                                                           |
| --------------------- | ------------------------ | --------------------------------------------------------------------------------------- |
| `QUICKSTART.md`       | New operator             | Install → first boot → first message in ~5 minutes. Bare-metal path, no Docker.         |
| `API_REFERENCE.md`    | Third-party integrator   | Flat API reference. The authoritative copy is the generated `apiSurface` in the locale JSON, but this file is kept for users who want a single Markdown page. |
| `BOT_DEVELOPMENT.md`  | Bot author               | End-to-end Gravitix walkthrough: install CLI → first handler → publish to marketplace. Cross-references the full Gravitix reference at `../Gravitix/README.md`. |

## How these relate to the locale docs

- Locale JSON (`static/locales/*.json`) is the **canonical** doc source — it drives the iOS app, Android app, and `docs.html` simultaneously.
- Everything here in `docs/` is either:
  - a shortcut for terminal users (`QUICKSTART.md`), or
  - a living PR-reviewable copy of something that is otherwise hard to review in JSON form (`API_REFERENCE.md`, `BOT_DEVELOPMENT.md`).
- If the two ever disagree, **trust the locale JSON** — it's what clients actually render.

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
