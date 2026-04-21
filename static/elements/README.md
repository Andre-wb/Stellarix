# `static/elements/` — Inline SVG Icons

Inline SVG icons used by the web UI and the Liquid Glass PRO renderer. Kept as raw SVG files so we can either:

1. Inline them directly into markup via `{% include "../static/elements/<name>.svg" %}`, or
2. Embed them as CSS `mask-image:` for tintable icons.

## Files (selected)

| File                                  | Used in                                |
| ------------------------------------- | -------------------------------------- |
| `alert-sign-svgrepo-com.svg`          | Warnings, destructive confirm modals.  |
| `color-picker-svgrepo-com.svg`        | Room theme editor.                     |
| `delete-2-svgrepo-com.svg`            | Destructive actions.                   |
| `edit-svgrepo-com.svg`                | Inline edit affordances.               |
| `jellyfish-svgrepo-com.svg`           | Empty-state illustration.              |
| `player-pause-svgrepo-com.svg` / `player-play-svgrepo-com.svg` | Voice note + video player. |
| `reply-svgrepo-com.svg`               | Reply affordance in the chat composer. |
| `shark-danger-predator-angry-svgrepo-com.svg` | Anti-spam / moderation empty-state. |

## Conventions

- One file per icon. No sprite sheet — we rely on HTTP/2 multiplexing.
- All icons are authored at 24×24, with a `viewBox="0 0 24 24"`. Any size scaling happens via CSS.
- `fill="currentColor"` — every icon inherits the parent text colour unless explicitly overridden.
- No stroke icons; filled shapes only, to render cleanly at very small sizes.

## Licensing

Third-party icons are from [svgrepo.com](https://www.svgrepo.com/) under its permissive license. File stems preserve the `-svgrepo-com` suffix so their provenance stays traceable.

## Adding an icon

1. Drop the `.svg` here with a `kebab-case` name.
2. Prefer filled 24×24 with `fill="currentColor"`.
3. Reference it from markup or CSS; if it appears in more than one place, add it to a component template so all usages stay in sync.

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
