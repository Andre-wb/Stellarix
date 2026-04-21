# `solana_program/programs/vortex_registry/src/` — Program Source

Single-file Anchor program. **1,317 lines** in `lib.rs` covering Phases 5 (basic registry), 7 (code-integrity pinning), C (staking), and D (subscriptions + rewards).

## Files

| File     | Role                                                              |
| -------- | ----------------------------------------------------------------- |
| `lib.rs` | Program entry — `declare_id!`, constants, PDAs, instructions, accounts structs, events, errors. |

See [`../README.md`](../README.md) for the phase breakdown and deploy flow. Constants are at the top of `lib.rs` — fee caps, tier prices, min stake, seeds.

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
