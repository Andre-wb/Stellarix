# `vortex_controller/docs/` — Controller Operator Docs

Hand-written Markdown for controller operators. Shorter-lived than the user-facing docs site — specific to one role (running the controller service).

## Files

| File            | Audience               | Content                                                                                       |
| --------------- | ---------------------- | --------------------------------------------------------------------------------------------- |
| `DEPLOY.md`     | Operator               | Full deployment walkthrough: PostgreSQL setup, pubkey pinning, Tor onion, Cloudflare tunnel, systemd unit. |
| `INTEGRITY.md`  | Operator / security    | How the integrity manifest is built, signed, and verified; what `INTEGRITY_STRICT=1` enforces; how to rotate the integrity key. |
| `SOLANA.md`     | Operator               | How the controller cross-checks the on-chain `vortex_registry`; RPC selection; what to do when the program is upgraded. |

## Relation to the locale docs

Controller-specific docs don't have a home in the user-facing locale tree — they're operator-only. Kept here as Markdown so operators reading the repo find them next to the code.

If an operator doc ever becomes useful for end users, migrate the content into `static/locales/en.json` (`vortexDocs.*`) and delete the Markdown — avoid two sources of truth.

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
