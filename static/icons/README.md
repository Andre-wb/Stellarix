# `static/icons/` — PWA / Browser Icons

Icons referenced by `../manifest.json` and the HTML `<link rel="icon">` / Apple touch-icon chain.

## Files

Typical set (adjust to the actual directory listing):

- `icon-192.png`, `icon-512.png` — required PWA sizes.
- `icon-192-maskable.png`, `icon-512-maskable.png` — Android maskable icons (bleed into safe zone).
- `apple-touch-icon.png` — iOS home-screen (180×180).
- `favicon-32.png`, `favicon-16.png` — desktop browsers.
- `badge.png` — notification badge.

## Regenerating

Icons derive from `../logo/logo.png` (1024×1024 master). Any image-resize tool works:

```bash
# macOS / ImageMagick
magick static/logo/logo.png -resize 192x192 static/icons/icon-192.png
magick static/logo/logo.png -resize 512x512 static/icons/icon-512.png
```

## Constraints

- PNGs only (`manifest.json` requires PNG for installability).
- Maskable icons must have the safe-zone padding so Android's circle/squircle clipping doesn't eat content.
- Apple touch icon must be 180×180 and without alpha.

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
