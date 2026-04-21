# `vortex_controller/web/locales/` — Controller Site Locales

Locale JSON files for the controller public site. Smaller than the main app's locale tree — this site is operator-focused, not chat-focused.

## Shape

```jsonc
{
  "meta":       { "locale": "en", "name": "English", "rtl": false },
  "nav":        { "home": "Home", "nodes": "Nodes", "entries": "Entries", "mirrors": "Mirrors", "security": "Security", "admin": "Admin" },
  "home":       { … landing copy … },
  "nodes":      { … table headers + empty state … },
  "entries":    { … },
  "mirrors":    { … },
  "security":   { … integrity copy … },
  "admin":      { … token prompt + revenue dashboard labels … }
}
```

## Scope

- No user-facing chat strings — those live in `../../../static/locales/`.
- No `apiSurface` / `glossary` / `deepReference` — those are read only on the main site's `/docs.html`.

## Fallback

English is the source of truth. Non-English files fall back to English for missing keys at runtime (same convention as the main app).

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
