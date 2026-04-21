# vortex-test

Standalone local preview of the `vortexx.sol` controller website,
populated with fake data covering every state the UI can show:

- **Entry URLs**: Cloudflare tunnel, Tor `.onion`, IPFS, direct
- **Mirrors**: healthy / dead / unchecked / no-Tor-proxy / IPFS
- **Peers**: sealed+fresh (weight 1.0), sealed+stale (0.8 / 0.5 / 0.2),
  unsealed (capped 0.5), Solana-only dual-verified, controller-only,
  unverified bootstrap
- **Integrity**: verified build with 158 files, real Ed25519 signature

Nothing connects to the real network — every HTTP response comes from
`serve.py` and is signed with a throwaway key generated at startup.

## Run

```bash
cd vortex-test
pip install fastapi uvicorn cryptography
python serve.py
# → open http://localhost:7700
```

## Files

```
vortex-test/
├── serve.py      # mock FastAPI server + fake data
├── public/       # copied-verbatim controller website
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   ├── i18n.js
│   ├── favicon.ico
│   ├── icons/
│   └── locales/  # 130+ languages
└── README.md
```

## What to look at

- Open in Safari / Chrome — the signature check in `app.js` verifies
  every envelope against the pubkey shown in the fingerprint card.
- Pick a language from the top-right picker to see RTL + Cyrillic + CJK
  variations.
- Ctrl-click → Inspect → Network to see the shape of every mock JSON
  response (useful for frontend work).
- Edit `serve.py` → change `ENTRY_URLS`, `MIRRORS`, `PEERS` → reload.

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
