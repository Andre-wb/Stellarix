# `vortex-test/public/` — Test Harness Static Site

Static assets for the standalone Vortex test harness. `vortex-test/` is a trimmed-down site used for automated browser tests (Playwright) and for demoing specific flows in isolation without booting the full web client.

## Layout

```
public/
├── index.html         ← minimal shell
├── assets/            ← per-scenario CSS + JS
├── icons/             ← tiny icon set
└── locales/           ← trimmed locale JSON (scenario-specific copies)
```

## Usage

```bash
cd vortex-test
python -m http.server 5555
# open http://localhost:5555/
```

## When to use

- You want a Playwright test that exercises a specific flow (e.g. just the auth UI) without loading the full 65-JS-module main client.
- You're reproducing a bug that requires a minimal page with known-good fixtures.
- You're iterating on a single component without the rest of the app in the way.

## When NOT to use

- Anything customer-facing — use `../../static/` + `../../templates/` instead.
- Integration tests that span multiple features — use the full app.

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
