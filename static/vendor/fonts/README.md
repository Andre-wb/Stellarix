# `static/vendor/fonts/` — Vendored Web Fonts

Web fonts served to the browser. Every font here is licensed for redistribution.

## Formats

- `.woff2` — preferred (Brotli-compressed, universally supported).
- `.woff` — fallback for older browsers where present.

## Conventions

- One folder per family: `fonts/<family-name>/`.
- Each family folder carries its upstream `LICENSE` file.
- `@font-face` declarations live in `../../css/layout.css` — all `src: url("../vendor/fonts/...")`.

## Constraints

- **No webfonts from third-party CDNs at runtime.** Everything is first-party. Simpler CSP, no privacy surprise.
- **No webfonts that contain personally-identifying glyph variants** that could fingerprint users beyond standard Unicode ranges.
- **Subsetted** where feasible — Latin + Cyrillic basic + the handful of CJK codepoints we actually use in the UI chrome. Body text relies on system fonts in CJK locales to avoid a giant blocking payload.

## Adding a family

1. Drop the `.woff2` + original `LICENSE` into a new subfolder.
2. Add the `@font-face` in `../../css/layout.css`.
3. Reference the family via the `--font-*` custom properties.
4. Run Playwright — every screen must still render on browsers without font-loading (disable network requests in DevTools).

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
