# `vortex_wizard/web/locales/` — Wizard UI Locales

Locale JSON for the desktop wizard UI. Operator-focused — smaller than the main-site locale tree.

## Shape

Similar to the controller site's locales, focused on operator terminology: setup, identity, SSL, database, mirrors, security, diagnostics, backup, seed, admin.

## Fallback

English is canonical. Missing keys fall back to English at runtime.

## Adding a key

1. Add to `en.json` first.
2. Run the project-wide translate flow (`../../../translate_locales.py`) against this directory to propagate machine translations.
3. Review + commit.

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
