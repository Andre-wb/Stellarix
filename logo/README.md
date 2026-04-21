# `logo/` — Vortex Brand Assets

Primary brand logo in multiple formats + sizes. Consumed by web UI, wizard, Tauri shell, README banners.

## Files

Expected set:

- `logo.svg` — canonical vector source.
- `logo.png` (master 1024×1024).
- `logo-<size>.png` for common UI sizes (16, 32, 64, 128, 256, 512).
- `wordmark.svg` — horizontal logotype.
- `icon-mono.svg` — single-colour mask, tintable.
- `favicon.ico`.

## Usage

- Web UI picks `icon-mono.svg` and tints via CSS `mask-image`.
- Wizard bundle embeds `logo.png` in the `Vortex Wizard.app` bundle.
- Tauri reads platform-specific icons from `src-tauri/icons/` — do not move master assets there; keep them here and regenerate derivatives.

## Licensing

Brand assets are proprietary to Vortex — same Apache 2.0 licence as the code, but the logo itself is NOT a trademark-free grant. Don't ship a fork using the Vortex logo unless you're shipping Vortex.

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
