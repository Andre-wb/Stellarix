# `static/css/` — Stylesheet Catalogue

41 stylesheets, one per concern. No preprocessor, no build step — vanilla CSS with custom properties. Loaded in order by `../../templates/base.html`.

## Core

| File              | Contents                                                                  |
| ----------------- | ------------------------------------------------------------------------- |
| `layout.css`      | CSS custom properties (colors, spacing, radii), global typography, reset. |
| `components.css`  | Shared primitive styles — buttons, inputs, chips, badges, toasts.         |
| `animations.css`  | Shared keyframes + motion durations / easings.                            |
| `responsive.css`  | Media-query breakpoints + mobile-first overrides.                         |
| `a11y.css`        | Accessibility utilities — screen-reader only, focus outlines, reduced motion. |
| `dark-rtl.css`    | Dark-mode palette + RTL flip rules.                                       |

## Feature stylesheets

One CSS file per major UI area:

`ai-text.css`, `article.css`, `auth.css`, `bot-constructor.css`, `chat.css`, `contact-sync.css`, `docs.css`, `emoji-picker.css`, `fingerprint.css`, `group-call.css`, `ide.css`, `lang-picker.css`, `marketplace.css`, `media-grid.css`, `media-viewer.css`, `menu.css`, `msg-status.css`, `network-status.css`, `onboarding.css`, `premium.css`, `profile.css`, `quickswitch.css`, `setup.css`.

Every file names its owner in the first comment (`/* chat.css — owned by static/js/chat.js, used by templates/screens/chat.html */`).

## Tokens (from `layout.css`)

```css
:root {
  --bg-0: #0b0c10;
  --bg-1: #11131a;
  --bg-2: #181b24;
  --fg-0: #e6e6ee;
  --fg-1: #a1a4b4;
  --accent: #7c3aed;
  --accent-soft: #a78bfa;
  --danger: #ef4444;
  --warning: #f59e0b;
  --ok: #22c55e;

  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 16px;
  --radius-pill: 999px;

  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
}
```

Feature stylesheets reference these variables; they **do not** hardcode colours or sizes.

## Conventions

- **No `!important`** outside `a11y.css` (where it's needed for reduced-motion override).
- **Class-only selectors** for shared components (`.btn`, `.chip`). IDs are forbidden except for singletons (`#app`).
- **BEM-ish** naming for per-feature widgets (`.chat-message`, `.chat-message__body`, `.chat-message--system`).
- **Dark mode first** — light palette is an override in `dark-rtl.css` triggered by `data-theme="light"` on `<html>`.
- **RTL** — logical properties (`margin-inline-start`, not `margin-left`) wherever possible.

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
