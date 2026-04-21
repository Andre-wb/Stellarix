# `android/gradle/wrapper/` — Gradle Wrapper

Standard Gradle wrapper files. `gradle-wrapper.jar` is **NOT committed** — regenerate it on first checkout.

## Files

- `gradle-wrapper.jar` — wrapper runtime (gitignored).
- `gradle-wrapper.properties` — pinned distribution URL + SHA-256.

## Bootstrap

```bash
cd android
gradle wrapper --gradle-version 8.10
# or, without a system Gradle:
curl -L -o gradle/wrapper/gradle-wrapper.jar \
  https://raw.githubusercontent.com/gradle/gradle/v8.10.0/gradle/wrapper/gradle-wrapper.jar
```

After that, `./gradlew <task>` works for everyone regardless of system Gradle version.

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
