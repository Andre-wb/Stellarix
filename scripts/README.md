# `scripts/` — Build, Docs, and Integrity

All operator-side tooling that doesn't run inside the node. Most are Python; a couple are shell / PowerShell for platform-specific packaging.

## Build

| Script                      | Produces                                                                               |
| --------------------------- | -------------------------------------------------------------------------------------- |
| `build-linux.sh`            | Linux tarball + .deb via `Dockerfile.build-linux`. Bundles the wizard + node into one. |
| `build-windows.ps1`         | Windows portable zip + installer stub. Invokes PyInstaller on `vortex-wizard.spec`.    |
| `Dockerfile.build-linux`    | Reproducible Linux build image (Debian slim + Python 3.10 + Rust + Node).              |

See `BUILD.md` for the full operator walkthrough — prerequisites, signing flow, CI matrix.

## Docs generators

Every script here writes into the locale JSON files under `static/locales/` (and into the iOS `ios/Modules/Sources/I18N/Resources/locales/`). They are **pure data generators** — no network calls, deterministic output.

| Script                         | Produces                                                                                      |
| ------------------------------ | --------------------------------------------------------------------------------------------- |
| `build_vortex_docs.py`         | First-generation top-level Vortex docs tree.                                                  |
| `build_vortex_docs_v2.py`      | Mid-round extension: adds sub-chapters under deep reference.                                  |
| `build_vortex_docs_v3.py`      | Current generator for the Vortex root of the docs site. Produces every non-deep-reference chapter with full Description / How it works / History / Formula sections. |
| `build_docs_expand.py`         | Expands accordion sub-sections (`_a/_b/_c/_f`) across the whole tree. Owns the BMP history entry that credits the Vortex team. |
| `build_architex_docs.py`       | Architex root tree — overview, language, components, runtime, examples.                       |
| `build_architex_arxd.py`       | Architex deep reference (`arxd`) leaf keys — one per language construct.                      |
| `convert_gx_docs_i18n.py`      | Migrates legacy `gxd` Gravitix docs into the canonical `hN/hN_a/hN_b/hN_c/hN_f` scheme.       |
| `build_api_glossary.py`        | Rebuilds `apiSurface` (540+ REST endpoints × 6 panels each) and `glossary` (37 terms A–Z). Run after adding or renaming any endpoint. |

All generators are idempotent — re-running does not duplicate keys, and locale overrides in non-English files survive regeneration unless the English key is deleted.

## Integrity

- `integrity_repo.py` — signs and verifies the **repo-wide** integrity manifest (`INTEGRITY.repo.json` at the repo root). Usage:

  ```bash
  python scripts/integrity_repo.py sign   --key keys/integrity.key
  python scripts/integrity_repo.py verify
  ```

  The controller's `IntegrityGateMiddleware` loads this same file at boot; the wizard exposes `/wizard/integrity` which calls this script via `importlib` so "Sign repo" / "Verify" work inside the PyInstaller bundle.

## Running a generator

From the repo root:

```bash
python scripts/build_api_glossary.py
python scripts/build_vortex_docs_v3.py
python scripts/build_docs_expand.py
```

The generators read/write `static/locales/en.json` as the canonical source; translation scripts (`translate_cloud.py`, `translate_locales.py` at the repo root) propagate new English keys into the other 145 locales via external providers.

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
