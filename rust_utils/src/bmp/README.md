# `rust_utils/src/bmp/` — BMP (Blind Mailbox Protocol)

Rust implementation of Vortex's metadata-obfuscation layer. See `RESEARCH-BMP.md` at the repo root for the design document.

## What's here

- `mailbox_id(shared_secret, epoch_seconds, period)` — derives the current mailbox ID:
  ```
  mailbox_id(t) = HMAC-SHA256(S_AB, floor(t / T))[0:16]
  ```
- `generate_covers(real_ids, count)` — wraps real mailbox IDs with `count` cryptographically random decoys and shuffles the result.
- Helpers for epoch math and envelope packing.

## Exposed to Python

```python
import rust_utils

mid    = rust_utils.bmp_mailbox_id(shared_secret, time.time(), period=3600)
poll   = rust_utils.bmp_generate_covers(real_ids=[mid], count=50)
```

## Performance

- Mailbox derivation: ~0.5µs per call (HMAC-SHA256 throughput dominated).
- Cover generation: O(n) in decoy count; single BLAKE3 + Fisher–Yates shuffle.

## Tests

Round-trip test: two parties derive the same mailbox ID from their own private key + the other's public key. Also verifies epoch rollover (one party querying at `t - 1s`, the other at `t + 1s`, both still agreeing within the same epoch).

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
