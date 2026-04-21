# `static/js/ide/` — In-browser IDE

The Gravitix + Architex editor hosted at `/ide`. Vanilla JS, no framework, no bundler.

## Modules

- `editor.js` — core text editor (CodeMirror 6 style behaviour, written from scratch): line numbers, caret, selection, Undo/Redo, soft-wrap, find/replace.
- `highlight.js` — syntax highlighter shared by Gravitix and Architex (pluggable grammars).
- `completion.js` — autocomplete: stdlib, local identifiers, modifier names for Architex.
- `lint.js` — inline diagnostics from parse errors and budget warnings.
- `runner.js` — runs the current project via `POST /api/bots/ide/run` (Gravitix) or mounts in a sandboxed iframe (Architex).
- `preview.js` — live preview pane for Architex.
- `monitor.js` — log tail + stack samples for running bots.
- `projects.js` — project explorer, create / rename / delete / publish.
- `console.js` — REPL-like evaluator for quick language experiments.
- `dev_settings.js` — dev-only knobs (hot reload, raw AST dump, token dump).

## Loaded from

`../../templates/screens/ide.html` — which loads `ide/*.js` in declared order before calling `IDE.init(rootElement)`.

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
