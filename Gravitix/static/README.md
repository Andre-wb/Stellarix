# `Gravitix/static/` — Static Assets for the Gravitix Demo Site

Assets used by the standalone Gravitix demo site (see `../run.py`). The main Vortex web client does NOT consume these — it has its own assets under `../../static/`.

## What's here

- `index.html` shell + supporting CSS + JS for a minimal "try Gravitix in the browser" page.
- Syntax-highlighter styles for the `.grv` grammar.
- A tiny WASM-compiled lexer/parser slice, if present, so the page can preview code without a server round-trip.

## Running the demo site

```bash
cd Gravitix
python run.py                  # serves on http://localhost:7787/
```

Useful when hacking on Gravitix itself without booting the full Vortex backend.

## Keep separate

- **Do not** copy these files into the main site — the main client has different styling tokens and a different layout.
- If you want to share snippet highlighters across Vortex and Gravitix, factor them into `../src/` and expose via the CLI / WASM build; don't duplicate CSS.

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
