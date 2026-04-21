# `rust_utils/tests/` — Integration Tests

Rust-side integration tests for the `rust_utils` crate. Compiled as separate binaries that link against the crate as an external dependency — so they exercise only the public API, not module-internal helpers.

## Files

| File                  | Covers                                                                 |
| --------------------- | ---------------------------------------------------------------------- |
| `messages_tests.rs`   | Wire-envelope pack/unpack round-trip, CBOR stability, version bumps, corrupt-input refusal. |

(Unit tests for individual modules live inline with the source in `../src/<file>.rs` under `#[cfg(test)] mod tests`.)

## Running

```bash
cd rust_utils
cargo test                   # runs both unit tests and integration tests
cargo test --test messages_tests -- --nocapture   # just the integration tests, with println! output
```

## Adding a test

1. Add a file here named `<topic>_tests.rs`.
2. Use `use rust_utils::…;` — only public items are reachable.
3. Each test is `#[test] fn test_<name>()`.
4. Keep each test self-contained — no `setup.rs` helper file across tests.

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
