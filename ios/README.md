# Vortex — iOS (SwiftUI + SPM)

Swift / SwiftUI client. Mirrors the Android client's 20-wave plan,
same SOLID split (`api/` protocols + `impl/` concrete types + feature DI
via an explicit composition root at `App/AppEnvironment.swift`).

## Status

**Wave 1 / 20 — project scaffold.** Swift Package with 22 feature
targets + an iOS app target that boots a placeholder `HomeScreen`.

## Requirements

- Xcode 15.4+
- iOS 16 deployment target
- [xcodegen](https://github.com/yonaskolb/XcodeGen) (one-time):
  `brew install xcodegen`

## First-time setup

```bash
cd ios
xcodegen           # produces Vortex.xcodeproj from project.yml
open Vortex.xcodeproj
```

Xcode resolves SPM dependencies (GRDB, Argon2Swift) on first open.
Then `⌘R` launches the app on the simulator.

## Layout

```
ios/
├── Modules/              ← Swift Package, one target per feature
│   ├── Package.swift
│   └── Sources/
│       ├── App/          ← composition root + root screens
│       ├── VortexCrypto/ ← crypto primitives (Wave 2)
│       ├── Bootstrap/    ← vortexx.sol probe (Wave 3)
│       └── ...           ← Net, Auth, Identity, DB, Rooms, Keys,
│                           WS, Chat, Files, Stickers, Calls, Push,
│                           Federation, Search, Spaces, Bots,
│                           Threads, Feeds, Settings, I18N
├── VortexApp/            ← iOS app target (@main, Info.plist, Assets)
├── project.yml           ← xcodegen spec → Vortex.xcodeproj
└── README.md
```

## Wave plan

Same 20 waves as the Kotlin client. Each wave adds `api/` protocols,
one or more `impl/` types, optionally UI, and tests — and keeps the
whole thing compilable so you can `⌘R` after every step.

| # | Wave |
|---|------|
| 1 | Scaffold (current) — SPM + brand screen |
| 2 | Crypto (X25519, Ed25519, AES-GCM, HKDF, Argon2id) |
| 3 | Bootstrap: vortexx.sol probe + manual URL |
| 4 | HTTP + JWT (URLSession) |
| 5 | Auth (Keychain-backed JWT) |
| 6 | Identity (BIP39 seed) |
| 7 | Local DB (GRDB) |
| 8 | Rooms |
| 9 | Keys (ECIES + Variant-B) |
| 10 | WebSocket (URLSessionWebSocketTask) |
| 11 | Messaging |
| 12 | Chat UI |
| 13 | Reactions / replies / threads |
| 14 | File upload |
| 15 | File download + AVKit viewer |
| 16 | Stickers + voice (AVAudioRecorder) |
| 17 | Calls (WebRTC) |
| 18 | Push (APNs) |
| 19 | Federation |
| 20 | i18n + polish + TestFlight |

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
