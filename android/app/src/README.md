# `android/app/src/` — Android App Sources

Gradle's standard `src/` layout for the single `app` module.

## Layout

```
src/
├── main/
│   ├── AndroidManifest.xml
│   ├── java/sol/vortexx/android/       ← Kotlin sources (36 feature packages)
│   ├── res/                             ← strings, icons, themes
│   └── assets/                          ← locale JSON files + embedded brand assets
├── test/                                ← JVM unit tests (JUnit)
└── androidTest/                        ← instrumented tests (runs on device/emulator)
```

## Feature packages

Each feature under `java/sol/vortexx/android/<name>/` follows the same pattern:

```
<feature>/
├── api/             ← interfaces, no Android deps
├── impl/            ← concrete implementations (Room, Ktor, Compose)
└── di/              ← Hilt @Module bindings
```

This split keeps `api/` unit-testable on the JVM without dragging Android, and keeps Hilt wiring isolated so DI changes don't touch feature code.

## Tests

- `src/test/` — unit tests. Run via `./gradlew test`.
- `src/androidTest/` — instrumented tests that need a real Android runtime. Run via `./gradlew connectedAndroidTest` (requires a device or emulator).

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
