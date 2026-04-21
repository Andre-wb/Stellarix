# `app/utilites/` — Pure Utility Helpers

Miscellaneous helper functions with no external dependencies. Deterministic, side-effect-free, unit-tested.

> The folder name is spelled `utilites` (missing `i`). This is intentional — renaming would break every import. A fresh project would pick `utils/`; this one keeps the original typo to avoid a footgun migration.

## Files

| File        | Role                                                                               |
| ----------- | ---------------------------------------------------------------------------------- |
| `utils.py`  | Catch-all helpers — string shaping, time formatting, byte-size formatters, safe JSON round-trip, ID generation, batch chunking, random token mint, async-retry decorator. |

## What belongs here

Anything that is:

- **Pure**: given the same input, returns the same output. No I/O, no global state mutation.
- **Widely reusable**: needed from 3+ feature packages.
- **Cheap**: a few lines, no external deps.

## What doesn't

- Anything that talks to the DB — goes in the feature package that owns the model.
- Crypto — goes in `../security/crypto.py`.
- HTTP clients — goes next to the feature that uses them.
- Anything with per-request state — goes in the request scope, not a module-level helper.

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
