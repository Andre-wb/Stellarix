# `src-tauri/icons/` — Desktop App Icons

Platform-specific app icons bundled into the Tauri release.

## Files

| File               | Platform          | Notes                                                       |
| ------------------ | ----------------- | ----------------------------------------------------------- |
| `icon.icns`        | macOS             | Contains every required size from 16×16 up to 1024×1024.    |
| `icon.ico`         | Windows           | Multi-resolution ICO (16, 24, 32, 48, 64, 128, 256).        |
| `*.png` (sizes)    | Linux             | `32x32.png`, `128x128.png`, `128x128@2x.png`, `icon.png`.   |

## Regenerating

```bash
# From a single 1024×1024 master PNG
cargo tauri icon path/to/icon-master.png
```

This writes every required file into this directory. Run it whenever the brand icon changes.

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
