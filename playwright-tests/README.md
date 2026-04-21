# `playwright-tests/` — End-to-end Browser Tests

Playwright-driven end-to-end tests for the web front-end. Runs a real browser against a live Vortex node and exercises the happy paths plus key regressions.

## Layout

| Path                   | Role                                                                    |
| ---------------------- | ----------------------------------------------------------------------- |
| `playwright.config.js` | Test runner config — browsers, retries, baseURL, reporter.              |
| `fixtures.js`          | Shared fixtures — pre-registered user, pre-created room, logged-in page, API client. |
| `tests/`               | One `*.spec.js` file per feature area.                                  |
| `package.json`         | `playwright` + `@playwright/test` + a tiny `crypto` helper dep.         |
| `playwright-report/`   | HTML report output (gitignored).                                        |
| `test-results/`        | Per-test artefacts — screenshots, videos on failure (gitignored).      |

## Running

```bash
cd playwright-tests
npm install
npx playwright install           # first time — downloads browser binaries

# Against a local node on http://localhost:8000
npx playwright test

# Headed mode, single spec, single browser
npx playwright test tests/rooms.spec.js --headed --project=chromium

# Debug — pauses on first failure
npx playwright test --debug
```

## What's covered

The test suite exercises the full user journey from first visit through encrypted messaging:

- **Auth** — register, login (password + seed + passkey), 2FA challenge, QR login.
- **Rooms** — create public / private / DM, join by invite, key delivery on join.
- **Chat** — send, edit, delete, react, reply, thread, pin, search.
- **Files** — image upload, chunked large upload, download round-trip.
- **Calls** — one-to-one voice, group voice, screenshare signal.
- **Federation** — two-node round-trip (requires second node via `NODE2_URL`).
- **i18n** — language switch persists, untranslated keys fall back to English.

## Environment

| Env var          | Purpose                                                        |
| ---------------- | -------------------------------------------------------------- |
| `NODE_URL`       | Primary node under test (default `http://localhost:8000`).     |
| `NODE2_URL`      | Second node for federation tests. Skipped if unset.            |
| `HEADLESS`       | `0` to disable headless even in CI.                            |
| `SLOW_MO_MS`     | Artificial delay between steps — useful for screencasting.     |

## CI

The suite runs on every PR via GitHub Actions. A fresh node is booted with `pytest`-compatible fixtures; the server's self-signed cert is trusted via `--ignore-https-errors`. Failing tests upload their trace + video as workflow artefacts.

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
