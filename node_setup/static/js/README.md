# `node_setup/static/js/` — First-run Wizard JS

Minimal JavaScript for the server-side first-run wizard. One file per step validator + shared helpers.

Typical modules: `setup.js` (form submit glue), `ssl.js` (SSL-step specifics, ACME progress polling), `peer.js` (controller pubkey validation), `progress.js` (SSE connector for long-running steps).

## Conventions

- Vanilla JS, no framework.
- Plain `fetch` calls — no extra HTTP wrapper.
- Fail gracefully: the wizard stays usable as a pure HTML form when JS is disabled.

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
