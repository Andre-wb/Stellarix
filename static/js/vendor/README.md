# `static/js/vendor/` — Vendored Third-party Libraries (JS)

Full third-party JavaScript libraries vendored at a specific version. Distinct from `../lib/` (which holds small shims + polyfills) — this folder is for complete, license-preserved copies of external code.

## Conventions

- Every vendored library lives in its own subfolder.
- Each subfolder keeps the original `LICENSE` file alongside the JS.
- Every file carries a top comment stating `// Source: <URL>, version <X>, vendored <YYYY-MM-DD>`.
- No modifications. If a bug needs fixing, vendor the patched upstream tag; never edit in place.

## Upgrading

1. Download the new release into a sibling folder `_pending/`.
2. Run the smoke tests (Playwright + Jest) to make sure nothing broke.
3. Swap folders; update the top-comment vendored date.
4. Commit in one step.

## Why vendored

- Reproducible builds without npm / CDN dependency.
- CSP compatibility — every script lives at a known path on our origin.
- Survives third-party outages.

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
