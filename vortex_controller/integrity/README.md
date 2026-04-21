# `vortex_controller/integrity/` — Integrity Verification

Controller-side logic for generating and verifying the signed manifest that locks the controller binary to a known build.

## Files

| File            | Role                                                                                    |
| --------------- | --------------------------------------------------------------------------------------- |
| `manifest.py`   | Builds `INTEGRITY.sig.json` — walks the controller's source tree, BLAKE3-hashes every file, signs the resulting canonical JSON with an offline Ed25519 key. |
| `sign_tool.py`  | CLI wrapper around `manifest.py`. Used by operators and CI to (re-)sign a build: `python -m vortex_controller.integrity.sign_tool sign --key ~/keys/integrity.key`. |
| `verify.py`     | Boot-time verification. Called from `main.py`'s lifespan hook. Produces a `Report(status, message, mismatched[], missing[])` that the middleware consults before accepting traffic. |

## Statuses

| Status            | Meaning                                                                    |
| ----------------- | -------------------------------------------------------------------------- |
| `verified`        | All files match the signed manifest.                                        |
| `no_manifest`     | No manifest bundled; development mode. Ships with a loud warning.          |
| `tampered`        | One or more files differ from the manifest.                                 |
| `bad_signature`   | Manifest signature doesn't verify against the pinned pubkey.                |
| `wrong_key`       | Manifest signed by an unknown key.                                          |

## Enforcement

- **Default** — a loud warning on any status other than `verified` or `no_manifest`, but the controller keeps running.
- **`INTEGRITY_STRICT=1`** — any non-verified status aborts startup with exit code 2.

## Related

- `../integrity_gate.py` — middleware that consults the report per-request.
- `../../scripts/integrity_repo.py` — the **repo-wide** sign/verify tool (this folder only covers the controller). The wizard loads that script via `importlib` so its "Sign repo" / "Verify" buttons work from inside the PyInstaller bundle.

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
