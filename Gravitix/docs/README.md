# `Gravitix/docs/` — Legacy Documentation

Older hand-written Markdown docs for Gravitix. The **canonical** documentation source today is the locale JSON under `../../static/locales/*.json` (keys `gravitixDocs.*`) rendered by the docs portal at `/docs.html`. This folder is kept for tooling that expects plain Markdown.

## Files

Typical contents (exact list in the directory):

- `syntax.md` — quick syntax reference.
- `stdlib.md` — list of built-in functions.
- `bot-guide.md` — first-bot walkthrough.
- `flows.md` — flow / FSM primer.
- `pattern-matching.md` — deep dive on `match` + guards.

## Relation to the locale docs

- Content here was migrated to the locale tree by `../../scripts/convert_gx_docs_i18n.py`.
- Further edits should go to the **English locale** (`static/locales/en.json`, `gravitixDocs.*`). The translate scripts propagate to the other 145 locales.
- If something in this folder disagrees with the locale tree, **trust the locale**.

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
