# `sol/vortexx/android/reactions/` — `reactions` feature

Android feature package for **reactions**. Internal layout:

- `api/` — Kotlin interfaces with no Android deps (easy to JVM-test).
- `impl/` — concrete types wired to Ktor / Room / Compose / Hilt.
- `di/`  — Hilt `@Module` bindings linking interfaces to impls.

Mirrors the iOS module of the same name under `../../../../../../../ios/Modules/Sources/Reactions/`.

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
