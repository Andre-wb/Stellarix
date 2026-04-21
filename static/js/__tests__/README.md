# `static/js/__tests__/` — JavaScript Unit Tests

Jest suites for the vanilla-JS modules under `../`. Runs headless; no browser needed.

## Running

```bash
cd /Users/borismaltsev/RustroverProjects/Vortex
jest                          # all JS tests
jest static/js/__tests__/crypto.test.js
jest --watch                  # TDD loop
```

Config lives at the repo root (`jest.config.js`, `babel.config.js`) — only ES2022 syntax support, no JSX, no React.

## Coverage

The suite covers the modules with non-trivial logic: `crypto.js`, `bmp-client.js`, `bmp-envelope.js`, `i18n.js`, `architex-runtime.js`, and their submodules. Pure-presentation modules (theme.css-adjacent glue) are not covered here — Playwright catches those end-to-end.

## Conventions

- Each test file is named `<module>.test.js`.
- One `describe` per module; one `it` per behaviour.
- Never import from the DOM — modules that touch `document` are tested via `jsdom`, loaded automatically by `jest.config.js`.

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
