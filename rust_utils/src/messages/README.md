# `rust_utils/src/messages/` — Message Wire Helpers

Higher-level helpers for Vortex's message envelopes — fragmentation, attachments, CBOR version negotiation.

## What's here

- `fragment(msg, max_size)` → `Vec<Fragment>` — split an oversized envelope into ordered chunks.
- `reassemble(fragments)` → `Result<Msg>` — deterministic reassembly, rejects out-of-order or overlapping.
- `envelope_version(bytes) -> u8` — read the version byte without fully decoding.
- `migrate_v<N>_to_v<N+1>(bytes)` — opt-in on-the-fly upgrades during read.

Used primarily by the node's message router (`app/chats/messages/`) and by the iOS / Android client decoders (via `vortex_chat`).

## Relation to `messages.rs`

`messages.rs` (flat file at `../`) carries the **current** envelope format's pack/unpack. This folder holds everything that sits *around* that — fragmenter, version shims, attachment helpers that are larger than a single file warrants.

## Tests

`../../tests/messages_tests.rs` covers round-trips, corruption, version-mixing, and fragmentation edge cases.

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
