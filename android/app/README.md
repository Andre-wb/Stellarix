# `android/app/` — Android App Module

The Gradle `app` module — the single Android application target. Everything else is organised inside as Kotlin packages (no separate feature modules — the `api/impl/di` split is **within** `app/`).

## Layout

```
android/app/
├── build.gradle.kts          ← module build script (Compose, Hilt, Room, Ktor versions)
├── proguard-rules.pro        ← R8 rules for release builds
└── src/
    └── main/
        ├── AndroidManifest.xml
        ├── java/sol/vortexx/android/
        │   ├── VortexApp.kt                ← @HiltAndroidApp
        │   ├── MainActivity.kt
        │   ├── ui/                          ← Compose theme + screens + components
        │   └── <36 feature packages>/       ← api/ + impl/ + di/ per feature
        └── res/                             ← strings, icons, theme XML
```

## Feature packages

36 feature folders, all under `sol.vortexx.android.*`:

`accounts`, `auth`, `backup`, `bootstrap`, `bots`, `calls`, `chat`, `contacts`, `crypto`, `db`, `drafts`, `emoji`, `federation`, `feeds`, `files`, `folders`, `i18n`, `identity`, `keys`, `multidevice`, `net`, `premium`, `push`, `reactions`, `rooms`, `savedgifs`, `scheduled`, `search`, `settings`, `spaces`, `stickers`, `threads`, `ui`, `ws`.

Each feature has:

- `api/` — Kotlin interfaces with no Android dependencies (easier to test).
- `impl/` — concrete implementations that bind to Android / Hilt / Room / Ktor.
- `di/` — Hilt `@Module` wiring that binds the interface to the impl.

## Build

```bash
cd android
gradle wrapper --gradle-version 8.10        # first time only
./gradlew assembleDebug                     # → app/build/outputs/apk/debug/app-debug.apk
./gradlew installDebug                      # push to a connected device
```

## Dependencies (selected)

- Jetpack Compose (BOM pinned in `../gradle/libs.versions.toml`).
- Hilt (DI).
- Room (SQLite DB, schema v4, 12 tables).
- Ktor client (HTTP + WebSocket).
- WebRTC binary (via Maven).
- Libsodium / built-in `javax.crypto` + Rust JNI bridge for the primitives that need `vortex_chat` parity.
- Firebase Messaging (optional — gated behind a build flavor for Google-free forks).

## Flavors

- `goog` — includes FCM.
- `foss` — no FCM; uses UnifiedPush via `services/unified_push.py` path.

## Min / target

- Min SDK: 26 (Android 8.0).
- Target SDK: 34 (Android 14).
- Compile SDK: 34.

## Testing

```bash
./gradlew test                 # unit tests
./gradlew connectedAndroidTest # instrumented tests (needs emulator / device)
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
