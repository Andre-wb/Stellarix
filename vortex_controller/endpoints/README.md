# `vortex_controller/endpoints/` — Controller HTTP Surface

FastAPI routers for the controller. Mounted by `../main.py`. Everything here is **control plane** — discovery, registration, entry URLs, mirror health, integrity, admin. **No messaging traffic.**

## Files

| File             | Purpose                                                                                       |
| ---------------- | --------------------------------------------------------------------------------------------- |
| `register.py`    | `POST /v1/register`, `POST /v1/heartbeat`. Verifies the node's Ed25519 signature, writes to storage, enforces auto-approve policy. |
| `nodes.py`       | `GET /v1/nodes/random?count=N`, `GET /v1/nodes/lookup/{pubkey}`. Returns controller-signed responses so clients can verify authenticity even when TLS is broken. |
| `entries.py`     | `GET /v1/entries`. Signed list of bootstrap URLs for clients that can't resolve the controller domain (e.g. `trycloudflare` tunnels). |
| `mirrors.py`     | `GET /v1/mirrors`, mirror registration + health status. Uses `../mirror_health.py` under the hood. |
| `integrity.py`   | `GET /v1/integrity`. Returns the controller's own integrity report (file hashes vs. signed manifest). |
| `health.py`      | `GET /v1/health`. Liveness + basic stats (approved nodes, mirror count, uptime).              |
| `admin.py`       | `/admin/*` routes — bearer-token-guarded. Revenue dashboard data, node approve / deny, force re-verification, treasury overview. |
| `backup.py`      | Controller key-backup endpoints. The controller's Ed25519 keypair can be sharded via Shamir; these routes handle join + restore by the operator. |

## Response envelope

All read endpoints return:

```json
{
  "data": { … },
  "signature": "<ed25519 hex>",
  "signed_at": "2026-04-21T09:12:03Z",
  "controller_pubkey": "<ed25519 hex>"
}
```

Clients verify `signature` over `canonical_json(data) || signed_at` using the pinned controller pubkey **before** trusting any field.

## Auth

- Public endpoints: `/v1/*` except `/admin/*`.
- Node endpoints (`register`, `heartbeat`): prove pubkey ownership via payload signature.
- Admin endpoints: `Authorization: Bearer <ADMIN_TOKEN>`. The token is set via env var at boot — not derivable from the pubkey, not persisted in the DB.
- Controller itself doesn't issue JWTs. Every request is either self-signed by the node or bearer-token-protected.

## Rate limits

Every router is behind a simple token-bucket keyed by (IP, pubkey). Register + heartbeat are rate-limited **per-pubkey** (so a burst of nodes behind the same NAT doesn't DOS each other); read endpoints are rate-limited **per-IP**.

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
