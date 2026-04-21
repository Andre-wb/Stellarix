# `static/js/lib/` — Vendored Third-party Shims

Small vendored third-party libraries. Kept here instead of via npm/CDN so the site keeps working without a package manager and without third-party uptime dependencies.

## Contents (typical)

- Tiny DOM utilities that pre-date modern browsers' built-ins.
- Crypto helper polyfills for older WebView environments.
- Small MIME / base58 / base64url helpers.

## Conventions

- **Every vendored file names its source + version** in the top comment.
- **No transitive dependencies.** If a library imports three others, we don't vendor it.
- **Never patch in-place.** If a bug needs fixing, keep the original + a sibling `<name>.patch.js` that monkeypatches on load. Makes audits easy.

## Why not npm

- Deterministic byte-for-byte builds across hosts without needing `node_modules`.
- No Supply-chain surface area — every file here was reviewed before commit.
- Site works fine with CSP'd no-eval / no-inline environments that would trip up modern bundler output.

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
