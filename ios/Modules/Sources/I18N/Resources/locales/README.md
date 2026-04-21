# `ios/Modules/Sources/I18N/Resources/locales/` — iOS Locale JSON

The **146 locale JSON files** shipped with the iOS app. Mirrors `static/locales/` in the repo root — same canonical English + 145 translations + same `hN / hN_a / hN_b / hN_c / hN_f` accordion convention.

## Keeping in sync

The web copy is authoritative. After regenerating locales with any `scripts/build_*` generator, copy the output here so the iOS app picks up new keys on the next build. Automation lives in `scripts/` (planned — currently manual).

## Runtime loader

`I18N/impl/LocaleLoader.swift` reads the active locale from `UserDefaults`, falls back to the system locale, and falls back to `en.json` for missing keys. No network round-trip — the language switch is instant.

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
