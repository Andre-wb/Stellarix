# `static/` — Frontend Static Assets

Vanilla-JS single-page application. Zero build step — every file here is shipped as-is to the browser. The node mounts this directory at `/static/*`, and the templated HTML pages under `../templates/` reference these assets by absolute URL.

## Layout

| Path          | Role                                                                                   |
| ------------- | -------------------------------------------------------------------------------------- |
| `css/`        | 41 stylesheets — one per feature area. `layout.css` + `components.css` are the core.   |
| `js/`         | 65 top-level modules + nested `chat/`, `ide/`, `ide-docs/`, `rooms/`, `lib/` packages. |
| `elements/`   | Inline SVG icons used by the glass/liquid UI.                                          |
| `icons/`      | Static PNG/SVG icons for the manifest + UI.                                           |
| `logo/`       | Brand logo (SVG + raster sizes).                                                       |
| `sounds/`     | Notification / call / ringtone assets.                                                 |
| `vendor/`     | Third-party JS / CSS pinned to exact versions (no npm).                                |
| `locales/`    | **146 locale JSON files**. Canonical English + 145 translations. Shared verbatim with iOS, Android, docs, controller. |
| `uploads/`    | User-generated files (runtime, gitignored). Served via signed URLs only.              |
| `manifest.json` | PWA manifest — app name, icons, theme color, shortcuts, share target.                |
| `favicon.ico` | Favicon.                                                                               |

## Conventions

- **One file = one concern.** `chat.css` styles chat; `premium.css` styles premium; no shared god file.
- **CSS variables** are declared once in `layout.css` (colors, spacing, radii) and consumed everywhere.
- **JS modules** are classic scripts (no bundler), loaded in order by `templates/base.html`. Each module attaches its entry points to `window.<namespace>`.
- **Locales** are loaded lazily — `i18n.js` fetches the selected locale on boot and keeps English as fallback for missing keys.

## Subdirectories

See the per-folder READMEs:

- `static/css/README.md` — stylesheet catalogue.
- `static/js/README.md` — JavaScript module map.
- `static/elements/README.md` — inline SVG icon set.
- `static/locales/README.md` — locale system, generator scripts, translation flow.

## Service worker + PWA

- `js/pwa.js` registers the service worker and handles install prompts.
- The service worker file lives at the repo root (`sw.js`, mounted at `/sw.js`) so it can scope the whole site — not inside `static/`.
- `manifest.json` declares the app as installable; the share target sends shared content to `/api/dm/share` via POST.

## Don't put here

- Anything that needs to be secret — everything under `/static/*` is public.
- Build artefacts from other directories — this is source.
- Per-user runtime data (that's `uploads/`, which is gitignored).

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
