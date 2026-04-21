# `static/logo/` — Brand Logo (served from `/static/logo/*`)

Runtime-served copies of the brand logo. Originals / masters live in `../../logo/` (repo root); this folder is a lightweight mirror so the web server doesn't have to reach outside `static/` at runtime.

## Contents

- `logo.svg`
- `logo.png` at common sizes (64, 128, 256, 512).
- `wordmark.svg`.

## Keeping in sync

If you add or update a size in `../../logo/`, mirror it here. The masters live outside `static/` so that server-side tools (Tauri bundle, iOS / Android asset pipeline, README badge assets) can read them without dragging the whole `static/` tree.

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
