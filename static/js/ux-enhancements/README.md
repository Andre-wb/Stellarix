# `static/js/ux-enhancements/` — Optional UX Polish Modules

Modules that improve the feel of the app but are not required for core functionality. Every one is lazy-loaded and fails gracefully — the site works identically if a module fails to load.

## Typical modules

- `skeleton.js` — skeleton placeholders while data loads.
- `ripple.js` — Material-style ripple effect on buttons.
- `haptics.js` — vibration API wrapper (mobile browsers).
- `scroll_memory.js` — remembers scroll position per room / per page.
- `shortcuts.js` — global keyboard shortcuts + help overlay.
- `anim.js` — shared easing presets for micro-interactions.
- `toast.js` — corner-toast notifications.
- `progressive_blur.js` — animated background blur on scroll.

## Conventions

- Every module exports `install(rootElement)` and does nothing if its prerequisites (e.g. `navigator.vibrate`) aren't available.
- Failing to load a single module **must not** cascade — the site's main bundle never imports from here synchronously.

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
