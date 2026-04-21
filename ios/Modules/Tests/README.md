# `ios/Modules/Tests/` — XCTest Suites

Unit + integration tests for the Swift Package targets. One test target per feature module.

## Running

```bash
cd ios
xcodebuild test \
  -project Vortex.xcodeproj \
  -scheme VortexApp \
  -destination "platform=iOS Simulator,name=iPhone 15"
```

Or from inside Xcode: `⌘U`.

## Layout

```
Tests/
├── VortexCryptoTests/
├── AuthTests/
├── RoomsTests/
├── ChatTests/
├── I18NTests/
└── …                         ← one test target per Sources/<module>
```

Each test target depends only on the corresponding `api/` + `impl/` from `../Sources/` — **not** on other feature modules. Cross-feature integration is exercised in `AppTests`.

## Conventions

- `XCTestCase` subclasses. One class per production type.
- Prefer `async throws` test methods — mirrors the production async surface.
- No `import XCTest; import UIKit` together — keep UI concerns inside SwiftUI previews.
- Network-touching tests use `URLProtocol` stubs, not real HTTP.
- Crypto tests include known-answer tests — not just round-trips — so a regression in a primitive is caught immediately.

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
