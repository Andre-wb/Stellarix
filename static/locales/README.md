# `static/locales/` — Locale JSON Files

**The canonical source of every translated string in the Vortex platform.** Shared verbatim by iOS, Android, web, the docs portal, and the controller site. **No backend round-trip** is ever needed to change language — every client loads the relevant JSON on boot and caches it.

## Layout

```
static/locales/
├── en.json        ← canonical English — the source of truth
├── ru.json        ← Russian
├── es.json        ← Spanish
├── …              ← 143 more translations
└── (146 files total)
```

## Numbers

- **146 locales** (English + 145 translations).
- **19,420 lines** total across all files.
- **Thousands of keys** per locale, grouped under nested namespaces: `auth.*`, `rooms.*`, `chat.*`, `apiSurface.*`, `glossary.*`, `deepReference.*`, `vortexDocs.*`, `gravitixDocs.*`, `architexDocs.*`, and more.

## Structure

Every locale file has the same shape:

```jsonc
{
  "meta": {
    "locale": "en",
    "name": "English",
    "nativeName": "English",
    "rtl": false,
    "completeness": 1.0
  },
  "auth": { "login": "Log in", "register": "Create account", … },
  "rooms": { "create": "Create room", … },

  // Generated — see scripts/build_api_glossary.py
  "apiSurface": {
    "auth": { "h1": "Authentication", "h1_a": "…Description…", "h1_b": "…", "h1_c": "…", "h1_f": "…" },
    …
  },

  // Generated — see scripts/build_vortex_docs_v3.py + build_docs_expand.py
  "vortexDocs": {
    "overview":     { "h1": "Overview", "h1_a": "…", "h1_b": "…", "h1_c": "…", "h1_f": "…" },
    "architecture": { "h1": "…", "h1_a": "…", "h1_b": "…", "h1_c": "…", "h1_f": "…" },
    …
  },
  "gravitixDocs":  { … },
  "architexDocs":  { … },
  "deepReference": { … }    // 422 subsystem entries
}
```

## The `hN / hN_a / hN_b / hN_c / hN_f` convention

Every accordion chapter has five sibling keys:

| Suffix | Shown as         | Content                                                 |
| ------ | ---------------- | ------------------------------------------------------- |
| `hN`   | Title bar        | Section name.                                           |
| `hN_a` | Description      | Plain-language overview.                                |
| `hN_b` | How it works     | Mechanism, data flow, wire shape.                       |
| `hN_c` | History          | Where the idea / protocol came from; Vortex's variation.|
| `hN_f` | Formula / shape  | Math (where relevant) or canonical wire-format snippet. |

Clients render this as a 4-panel accordion per chapter. See `../../../vortex-introduce-page/docs.html` for the web reader.

## English is the source

- Every non-English file's keys are a **subset or equal** to `en.json`. Missing keys fall back to English at runtime.
- The translation flow (`translate_locales.py` + `translate_cloud.py` at the repo root) propagates new keys from English into every other file via an LLM-backed machine-translation provider; human reviewers then override the generated strings where needed.
- Never add a new key to a non-English file first — it will be silently removed on the next regeneration.

## Who reads these

| Consumer                              | How                                                                  |
| ------------------------------------- | -------------------------------------------------------------------- |
| Web SPA                               | `static/js/i18n.js` fetches the active locale on boot.               |
| iOS client                            | Same files live at `ios/Modules/Sources/I18N/Resources/locales/`; currently hand-synced from web, future automation TBD. |
| Android client                        | Same files live at `android/app/src/main/assets/locales/`.           |
| Docs portal                           | `vortex-introduce-page/docs.js` fetches on locale change.            |
| Controller admin site                 | `vortex_controller/web/locales/` hosts a minimal subset (operator-focused). |

## Generators

- `scripts/build_vortex_docs.py`, `build_vortex_docs_v2.py`, `build_vortex_docs_v3.py`, `build_docs_expand.py` — Vortex docs tree.
- `scripts/build_architex_docs.py`, `build_architex_arxd.py` — Architex.
- `scripts/convert_gx_docs_i18n.py` — Gravitix docs migration.
- `scripts/build_api_glossary.py` — apiSurface + glossary.

All generators are idempotent — re-running does not duplicate keys, and locale overrides in non-English files survive regeneration unless their English key is removed.

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
