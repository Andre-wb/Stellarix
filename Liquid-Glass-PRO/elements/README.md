# `Liquid-Glass-PRO/elements/` — Liquid Glass Elements

Reusable HTML components that demonstrate the Liquid Glass PRO effect. Each file is a standalone snippet — drop it into any page that already loads `../liquid-glass-pro.js`.

## What's an element?

A piece of HTML with:

- A container `<div class="lg-…">` — the element root.
- Inline SVG filters or canvas-backed shaders — owned per element.
- Optional inline CSS bound to the effect's custom properties.

## Files

Each `.html` file in this folder contains one element. Selected: glass cards, refractive panels, fluid buttons, animated backdrops, layered dividers. See `../demo.html` for a rendered catalogue.

## Using an element

```html
<script src="/liquid-glass-pro.js"></script>
<link rel="stylesheet" href="/liquid-glass-pro.css">

<!-- Drop in the snippet -->
<include src="elements/glass-card.html"></include>
```

The runtime upgrades the container to the live shader version on `DOMContentLoaded`.

## Licensing

`Liquid-Glass-PRO` ships under its own MIT license (see the package `LICENSE`). It is included in Vortex as a first-party dependency because Vortex is its primary consumer — changes to both can land atomically.

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
