# `app/push/` — Push Notifications

Out-of-band message notifications. Two paths:

1. **Web Push** (standard VAPID) — desktop browsers, Android Chrome.
2. **BMP Push Proxy** — metadata-hiding delivery that decouples the recipient's identity from the push service (FCM / APNs).

iOS (APNs) and Android (FCM) native clients prefer the BMP path when it's available; they fall back to direct push-service endpoints otherwise. Web clients always use VAPID.

## Files

| File                 | Role                                                                                      |
| -------------------- | ----------------------------------------------------------------------------------------- |
| `web_push.py`        | VAPID Web Push: subscribe endpoint, subscription store, dispatch on message. Uses `pywebpush`. |
| `bmp_push_proxy.py`  | Blinded push — the server delivers a tiny envelope `{ blinded_id, ct }` to an obfuscated mailbox ID; the client polls its own mailboxes over BMP. The push service (FCM/APNs) never sees the recipient's identity or room id. |

## Why BMP push?

Traditional push services terminate TLS and routinely retain metadata: "device X received a message from sender Y about room Z". The BMP push proxy strips all of that:

- Recipient is addressed by a per-epoch `blinded_id` derived from a shared secret with the sender.
- Payload is AES-GCM ciphertext under the room key the client already has.
- The push service sees only `{ opaque_id, random-looking 128-byte blob }`.

## Endpoints

| Method | Path                              | Purpose                               |
| ------ | --------------------------------- | ------------------------------------- |
| POST   | `/api/push/subscribe`             | VAPID Web Push subscription.          |
| POST   | `/api/push/unsubscribe`           | Remove a subscription.                |
| POST   | `/api/push/device`                | Register an APNs / FCM device token.  |
| POST   | `/api/push/test`                  | Operator-only — send a test push.     |
| GET    | `/api/push/bmp/mailbox/<id>`      | BMP mailbox poll (cover-traffic-mixed).|

## Configuration

| Env var                 | Purpose                                            |
| ----------------------- | -------------------------------------------------- |
| `VAPID_PUBLIC_KEY`      | Web Push public key (served to clients).           |
| `VAPID_PRIVATE_KEY`     | Corresponding private key.                         |
| `VAPID_CONTACT`         | `mailto:` URI required by push services.            |
| `FCM_SERVER_KEY`        | FCM server key (if you operate your own FCM project). |
| `APNS_KEY_ID` + `APNS_TEAM_ID` + `APNS_KEY_PATH` | APNs auth. |
| `BMP_PUSH_ENABLED`      | Enable the blind proxy (default `true`).           |
| `BMP_PUSH_POLL_INTERVAL_SECONDS` | Client poll period hint.                  |

## Related

- `../services/sealed_push.py` — sealed-sender variant for DMs.
- `../services/unified_push.py` — [UnifiedPush](https://unifiedpush.org/) path for Android users who refuse FCM.
- `../transport/blind_mailbox.py` — the core BMP transport used by the proxy.

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
