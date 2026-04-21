# `app/security/waf/` — Web Application Firewall

Built-in WAF that runs as FastAPI middleware. Not a replacement for a reverse-proxy WAF (ModSecurity, Cloudflare, …) — it's a last-line, application-layer filter tuned to Vortex's specific threat model.

## Files

| File            | Role                                                                                      |
| --------------- | ----------------------------------------------------------------------------------------- |
| `engine.py`     | Core rule engine. Loads signatures, evaluates per-request, stores counters, emits verdicts. |
| `middleware.py` | ASGI middleware. Calls `engine.py` per request, short-circuits on block, forwards otherwise. |
| `signatures.py` | Signature set — regex + semantic rules. SQLi, XSS patterns, command injection, path traversal, unusual `Content-Type`, suspicious auth-header shapes. |
| `captcha.py`    | On-suspicion challenge. Hash-cash-style proof-of-work or visual captcha, depending on configured mode. |
| `routes.py`     | Operator endpoints at `/api/waf/*` — live rule stats, temporarily toggle rules, clear a user's challenge state. |

## What WAF catches

- **Protocol abuse** — payloads that pretend to be our format but parse suspiciously (oversized JSON, nested arrays > 100, malformed multipart).
- **Known attack shapes** — classic OWASP signatures; tuned to avoid false positives on legitimate E2E ciphertext (which looks "random" but has deterministic structure in our envelopes).
- **Volumetric abuse** — per-IP + per-user token buckets hooked into `../limits.py`. Bursts trigger captcha; repeat offenders get auto-blocked for an escalating window.
- **Federation garbage** — unsigned envelopes, wrong-seq, unknown `from_pubkey`.

## What it explicitly does NOT do

- It does not inspect E2E ciphertext payloads. They look like high-entropy noise to the WAF by design.
- It does not terminate TLS (that's nginx or the load balancer).
- It does not block based on country / ASN. We assume censorship-resistance users are connecting from exactly those places.

## Rule flow

```
request → engine.evaluate()
            │
            ├── per-route signature set   (signatures.py)
            ├── per-IP + per-user limits  (../limits.py)
            ├── body shape checks          (json depth, multipart limits)
            └── decision:
                   ALLOW      → continue
                   CHALLENGE  → captcha.issue()
                   BLOCK      → 403 + audit log
                   TARPIT     → hold connection, drip-slow response
```

## Configuration

| Env var                | Purpose                                                     |
| ---------------------- | ----------------------------------------------------------- |
| `WAF_ENABLED`          | Master switch (default `true`).                             |
| `WAF_MODE`             | `monitor` (log only) / `enforce` (default).                 |
| `WAF_CAPTCHA_KIND`     | `pow` (default) / `image`.                                  |
| `WAF_BLOCK_TTL_SEC`    | Initial block duration for confirmed abuse (default 300).   |
| `WAF_SIGNATURE_OVERRIDES` | JSON map for toggling individual rules in ops.           |

## Logging

Every verdict writes a row to the `moderation_audit` table — who, when, which rule, what action. Operator dashboard surfaces a live tail via `/api/waf/feed`.

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
