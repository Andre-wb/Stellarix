# `node_setup/static/js/setup/` — Setup Step Validators

Per-step JS validators for the server-side first-run wizard. Each module binds to its step's form and validates client-side before the POST, to give the operator immediate feedback.

- `network.js` — port range check, bind-address syntax.
- `identity.js` — seed checksum validation.
- `ssl.js` — ACME domain format, self-signed toggle visual feedback.
- `database.js` — DSN syntax + `/setup/db/test` probe on blur.
- `peer.js` — controller pubkey hex length.

Each is a plain `<script>` — no framework, no module system. Fails gracefully if JS is off.

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
