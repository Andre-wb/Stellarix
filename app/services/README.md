# `app/services/` — Cross-feature Glue

Small services that don't belong to a single feature — they sit above the feature packages and compose their behaviour. Keeping this code out of a feature folder prevents cross-feature imports (which would otherwise cause import cycles).

## Files

| File                | Role                                                                                 |
| ------------------- | ------------------------------------------------------------------------------------ |
| `chat_service.py`   | The orchestrator for an inbound message — attachments, moderation, flood, push, federation fanout, analytics. Feature routers delegate here after persisting. |
| `native_bridge.py`  | Contract the native iOS / Android clients target — uniform push-payload shape, unified keep-alive, transport-hint negotiation (plain HTTPS / BMP / Tor). |
| `sealed_push.py`    | Sealed-sender variant of push. Recipient's native client decrypts and attributes inside the OS notification extension; the push service never sees sender or content. |
| `unified_push.py`   | [UnifiedPush](https://unifiedpush.org/) delivery for Android users who don't have or want Google services. |
| `webhooks.py`       | Outbound webhook delivery. Used by bots (`../bots/bot_advanced.py`) and by integrations that want to react to events (new message, new member, room created). HMAC-signed body, retry with exponential backoff, dead-letter after 24h. |

## Why this folder exists

Without it, `chat_service.py` would live under `app/chats/` but depend on `app/security/`, `app/push/`, `app/federation/`, `app/bots/antispam_bot.py`, and `app/transport/blind_mailbox.py`. Moving the orchestrator out breaks the dependency fan.

Rule of thumb: **a feature package imports `services/`; `services/` imports features.** Never the other way around.

## Webhook security model

- Every webhook has an HMAC secret generated on creation.
- Every POST carries `X-Vortex-Signature: sha256=<hex>` over the exact body.
- Receivers MUST compare with `hmac.compare_digest`.
- We ship the signing secret once at creation (via one-time retrievable URL); the node only stores a hash afterwards.
- Rate-limited per-webhook to 600 requests / 10 min; excess events are queued then dropped.

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
