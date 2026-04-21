# `static/vendor/` — Vendored Third-party Static Assets

Non-JS third-party static assets (fonts, icon packs, external stylesheets) vendored at pinned versions. Distinct from `../js/vendor/` which holds JS libraries.

## What typically lives here

- `fonts/` — font families licensed for redistribution (see its README).
- `*.css` — vendored external stylesheets (e.g. a third-party icon font).
- `*.woff2` — direct font files if the font isn't under `fonts/`.

## Conventions

- Each vendored asset preserves its original license file next to it.
- Each folder's README names the source + version.
- No modifications — if you need custom tweaks, layer your overrides in `../css/`.

## Why vendored

Same reasons as `../js/vendor/`: reproducibility, CSP cleanliness, offline-safety, audit clarity.

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
