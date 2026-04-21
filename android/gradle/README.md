# `android/gradle/` — Gradle Tooling

Gradle's version catalog + wrapper live here.

## Files

| Path                            | Role                                                                 |
| ------------------------------- | -------------------------------------------------------------------- |
| `libs.versions.toml`            | Single source of truth for every dependency version — Compose BOM, Kotlin, Hilt, Room, Ktor, Firebase, WebRTC, test libs. |
| `wrapper/gradle-wrapper.jar`    | Wrapper JAR (NOT committed; generated on first `gradle wrapper` run).|
| `wrapper/gradle-wrapper.properties` | Gradle distribution URL + checksum.                              |

## Why a version catalog

- Every module (currently just `app`, but growing) references the same versions by alias (`libs.compose.bom`, `libs.hilt.android`, …). Upgrading a library is one TOML edit, not N.
- TOML is human-diffable, IDE-friendly, and Gradle's preferred format in 8.x.

## Bootstrapping

```bash
cd android
gradle wrapper --gradle-version 8.10     # once; produces wrapper/gradle-wrapper.jar + .properties
./gradlew --version                      # confirm bootstrap worked
```

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
