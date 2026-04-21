# `app/security/` — Crypto, Auth, Privacy, Compliance

The security layer of the node. Crypto primitives, JWT, post-quantum handshake, double ratchet, sealed sender, key backup, WAF, IP privacy, GDPR, panic mode, warrant canary, and more. Everything here is called by feature code — never called by end-users directly except through a few operator-only routes.

## Files

### Crypto primitives

| File                | Role                                                                               |
| ------------------- | ---------------------------------------------------------------------------------- |
| `crypto.py`         | Thin Python wrappers around `vortex_chat` (Rust) and `rust_utils`. The single place that Python code calls into Rust for crypto. |
| `double_ratchet.py` | Signal-style forward-secrecy ratchet. Per-message chain keys, header encryption.   |
| `post_quantum.py`   | Kyber-768 hybrid KEM — combined with X25519 for handshake so a future quantum attacker with the stored ciphertext still can't recover plaintext. |
| `key_exchange.py`   | X3DH-like session setup using the keys stored in `../keys/`.                       |
| `key_backup.py`     | Client-encrypted key vault. Passphrase-derived wrapper key; Shamir split optional. |
| `seed_phrase.py`    | BIP39 seed → identity keys (X25519 + Ed25519). Used during register / restore.    |

### Auth

| File              | Role                                                                               |
| ----------------- | ---------------------------------------------------------------------------------- |
| `auth_jwt.py`     | JWT mint + verify. Short-lived access + rotating refresh.                          |
| `middleware.py`   | `TokenRefreshMiddleware` — transparently rotates access tokens near expiry.        |
| `limits.py`       | Per-route rate limits. Token-bucket, IP + user keyed. Plugs into WAF on burst.     |
| `premium_check.py`| Guards feature routes behind subscription state (verified against `../../solana_program/`). |

### Privacy

| File                   | Role                                                                          |
| ---------------------- | ----------------------------------------------------------------------------- |
| `sealed_sender.py`     | Sender identity is hidden from the server; recipient verifies via an inner signature. |
| `ip_privacy.py`        | IP truncation for logs, sticky-rotation for avatar fetches, Tor-exit-safe cache keys. |
| `privacy.py`           | User privacy toggles — hide online state, hide last-seen, read-receipt policy.|
| `privacy_routes.py`    | REST surface for the toggles above.                                           |
| `canary.py`            | Warrant canary — signed timestamp republished daily; absence is the signal.   |
| `panic.py`             | "Burn" mode — wipes local DB + keys on an admin-only / duress-password signal.|
| `zero_knowledge.py`    | Zero-knowledge proofs for group membership without revealing identity (experimental). |
| `gdpr.py`              | Data export (JSON + media zip), erasure, portability requests.                |

### Network protection

| File                     | Role                                                                        |
| ------------------------ | --------------------------------------------------------------------------- |
| `waf/`                   | Built-in web application firewall — signatures, captcha, route-level rules. See its README. |
| `blockchain_verify.py`   | Verifies tipping payments on Solana / TRON / Ethereum / BSC / TON / BTC.    |
| `tor_hidden_service.py`  | Manages an embedded Tor hidden-service listener. Requires tor daemon on the host. |
| `ssl_context.py`         | Builds the uvicorn SSL context — cert chain, key, cipher suites, OCSP stapling. |
| `secure_upload.py`       | Content-type sniffing, MIME allow-list, size caps for uploads.              |
| `security_validate.py`   | Pydantic validators reused across routes (anti-SSRF, anti-path-traversal).  |

## Conventions

- **No raw `subtle` API**. Every crypto call goes through `crypto.py` so we have one place to change the implementation.
- **Timing** — all comparisons on MACs / HMAC-derived ids use `hmac.compare_digest`.
- **Nonces** — always random, never counter-derived in this folder. Counter-derived nonces live inside `double_ratchet.py` where the ratchet guarantees uniqueness.
- **Errors** — never expose the difference between "unknown user" and "wrong password" from the error body.

## Related

- `../../rust_utils/` — low-level helpers called through `crypto.py`.
- `../keys/` — server-side public key storage.
- `../transport/` — BMP, cover traffic, obfuscation live separately because they are transport concerns, not crypto ones.

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
