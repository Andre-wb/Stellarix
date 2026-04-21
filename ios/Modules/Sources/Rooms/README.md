# `ios/Modules/Sources/Rooms/` — Rooms

Room CRUD, members, themes, invite flow.

## Layout

```
Rooms/
├── api/     ← Swift protocols (no UIKit / Foundation-heavy deps)
├── impl/    ← concrete types (HTTP, DB, WebSocket, CoreBluetooth, …)
└── di/      ← helpers that register bindings in `AppEnvironment`
```

## Conventions

- Public API: `api/` protocols only. Cross-module imports never touch `impl/`.
- Pure Swift Concurrency (`async / await`). No `completionHandler`.
- Tests live in `../../Tests/RoomsTests/` (when the suite exists).

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
