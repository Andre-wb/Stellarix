# `ios/Modules/Sources/` — Swift Package Sources

Source trees for every target declared in `../Package.swift`. One folder per target; each target is a feature module (`Auth`, `Chat`, `Rooms`, …) with its own `api` / `impl` / `di` split internally.

Every folder has a matching target in the Swift Package manifest. Adding a new feature:

1. Create `Sources/<NewFeature>/`.
2. Add `api/` (protocols), `impl/` (concrete types), optional `di/` (composition helpers).
3. Add a `.target(name: "<NewFeature>", …)` entry in `../Package.swift`.
4. Wire the feature into `AppEnvironment` inside `Sources/App/`.

See the parent [`Modules/README.md`](../README.md) for the full target list and conventions.

## Layout inside a target

```
Sources/Rooms/
├── api/
│   ├── RoomsService.swift        ← protocol
│   ├── RoomMember.swift
│   └── RoomKind.swift
├── impl/
│   ├── HttpRoomsService.swift    ← concrete, talks to node over REST + WS
│   └── RoomsCache.swift
└── di/
    └── RoomsAssembly.swift       ← registers bindings in the composition root
```

## I18N

The `I18N` target ships the locale JSON under `Resources/locales/` — **the same 146 files** used by the web and Android clients, kept in sync manually until automated sync lands.

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
