# `playwright-tests/tests/` — E2E Spec Files

One `*.spec.js` per feature area. Runs against a live Vortex node; uses the fixtures from `../fixtures.js`.

## Selected specs

| File                      | Covers                                                       |
| ------------------------- | ------------------------------------------------------------ |
| `auth.spec.js`            | Register + login (password / seed / passkey), 2FA, QR login. |
| `rooms.spec.js`           | Create / join / leave / rename / delete room, key delivery.  |
| `chat.spec.js`            | Send / edit / delete / react / reply / thread / pin / search.|
| `files.spec.js`           | Upload (single + resumable), download, media viewer.         |
| `calls.spec.js`           | 1-to-1 voice, small group voice, screenshare handshake.     |
| `federation.spec.js`      | Two-node round-trip (requires `NODE2_URL`).                 |
| `i18n.spec.js`            | Language switch persists + English fallback for missing keys.|
| `bots.spec.js`            | Bot create / publish / install / message delivery.           |
| `pwa.spec.js`             | Service worker install + offline dashboard + update flow.    |

## Conventions

- One `test.describe` per feature; one `test` per user-visible outcome.
- Use fixtures — do not re-register users inside test bodies. `fixtures.js` provides `loggedInPage`, `createdRoom`, `pairOfClients`.
- Use role-based selectors (`getByRole`, `getByLabel`) before CSS selectors.
- Never sleep; always `await expect(locator).toBeVisible()` or `await page.waitForResponse(...)`.
- Each spec must clean up after itself unless the test is explicitly marked `@cleanup:manual`.

## Running a single spec

```bash
cd playwright-tests
npx playwright test tests/chat.spec.js --project=chromium --headed
```

## Adding a spec

1. Create `tests/<feature>.spec.js`.
2. Import fixtures: `const { test, expect } = require("../fixtures");`.
3. Cover the happy path + one failure path.
4. Keep run time under 30s per spec; if it's longer, split.

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
