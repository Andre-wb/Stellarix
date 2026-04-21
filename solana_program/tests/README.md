# `solana_program/tests/` — Anchor Integration Tests

Integration tests for the `vortex_registry` program. `anchor test` spins up a local validator with the program pre-loaded and runs these TypeScript tests against it.

## Files

| File                   | Covers                                                                            |
| ---------------------- | --------------------------------------------------------------------------------- |
| `vortex_registry.ts`   | End-to-end suite for every instruction.                                           |

## Covered flows

- **Config init**: happy path, rejects re-initialisation, fee cap enforced.
- **Register**: without stake, with stake (≥ `MIN_STAKE_LAMPORTS`), rejects under minimum, rejects overflow near `MAX_STAKE_LAMPORTS`.
- **Update**: only owner; rejects if `is_sealed=true` and code_hash would change.
- **Checkin**: same hash (no-op event), changed hash (event + stored), past-deadline rejection.
- **Seal**: one-way; rejects re-seal with different hash; no-op re-seal with same hash.
- **Subscribe**: every tier (1/3/6/12 months); computes correct `paid_through_ts`; enforces current tier price; rejects downgrade during active period (unless admin policy allows).
- **Stake / unstake**: deposit, withdraw with cool-down, dust-attack rejection.
- **Rewards**: accrual math over several `checkin` cycles; claim with insufficient vault balance fails gracefully.
- **Deregister**: returns rent to owner; rejects if subscription active and admin policy forbids; cleans up related PDAs.
- **Admin fee update**: happy path; rejects above `MAX_REGISTER_FEE_LAMPORTS`; only admin key can call.

## Running

```bash
cd solana_program
npm install
anchor test                   # brings up a local validator, loads the program, runs tests
```

Takes ~30–60s on a modern laptop.

## Conventions

- Use `anchor.workspace.VortexRegistry` — do not hard-code the program id.
- Each test derives its own PDAs from `anchor.utils.publicKey.findProgramAddressSync`.
- Clean-up: tests intentionally do NOT call `deregister` at the end — Anchor wipes the validator between runs, so cleanup is unnecessary and makes tests faster.
- Assertions via `chai`.

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
