# `static/js/ide-docs/` — IDE Docs Browser

Mini docs browser embedded inside the IDE. Same locale JSON source as `/docs.html` (`../../locales/`), but rendered in the IDE's side panel so users can learn the language without leaving the editor.

## Modules

- `renderer.js` — accordion renderer (the `hN / hN_a / hN_b / hN_c / hN_f` scheme).
- `search.js` — in-tree text search across the active root.
- `nav.js` — tree sidebar + route sync with the editor (hover a Gravitix keyword → auto-scroll to its reference entry).
- `bridge.js` — thin bridge between the editor and the docs panel (click a symbol → open its entry; drag a code sample → insert into the editor).

## Relation to `../../../vortex-introduce-page/docs.js`

This folder is a **subset** — it only renders the accordion chapter content and side navigation. It does not ship the home-page wrapping, locale picker, or marketing chrome. Both readers consume the same locale JSON and the same `hN / hN_a / hN_b / hN_c / hN_f` convention, so content stays in sync.

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
