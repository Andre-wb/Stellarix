# `app/files/` — File Upload & Download

All file-transfer endpoints. Both single-shot (small files) and resumable (large files with per-chunk recovery). Every byte is E2E-encrypted on the client; the node stores only ciphertext.

Endpoints live under `/api/files/*`.

## Files

| File                 | Role                                                                                          |
| -------------------- | --------------------------------------------------------------------------------------------- |
| `resumable.py`       | Resumable chunked upload. Client picks a `upload_id`, POSTs chunks independently, server stores them into `uploads/_chunks/<upload_id>/<seq>`, assembles on `finalize`. Recovers from network drops by re-reporting the `uploaded_ranges` array. |
| `files_advanced.py`  | Gallery, search, quota, thumbnails (server-side for already-decrypted previews the user opted in to), signed-URL issuance, delete flows. |

## Upload flows

### Single-shot (≤ 5 MB by default)

```
POST /api/files/upload   (multipart/form-data)
  file=<ciphertext blob>
  metadata={room_id, key_id, nonce, mime_hint}
  → 201 { file_id, sha256, size, url }
```

### Resumable (anything over the threshold, or on mobile where reliability matters)

```
POST  /api/files/upload/create    → { upload_id, chunk_size }
PUT   /api/files/upload/<id>/<seq>  (chunk bytes)
GET   /api/files/upload/<id>/status → { uploaded_ranges }
POST  /api/files/upload/<id>/finalize { total_sha256 }
  → 201 { file_id, url }
```

Chunks land under `uploads/_chunks/<upload_id>/`; the finalise step concatenates them, checks the total hash, and atomically moves the result into `uploads/<file_id>`.

## Download

- Short-lived signed URLs scoped to the viewer, expiring in minutes not days.
- The node serves raw ciphertext — no server-side decryption.
- `Content-Type` is deliberately `application/octet-stream` for every upload; the client decides rendering based on the E2E-included `mime_hint`.

## Edge cache

Popular public files (sticker packs, bot avatars) are lifted into `uploads/.edge_cache/` by `../peer/edge_cache.py` for LAN peers to pull without touching the origin node.

## Limits

| Setting                    | Default | Purpose                          |
| -------------------------- | ------- | -------------------------------- |
| `UPLOAD_MAX_SIZE_MB`       | 1024    | Hard cap per file.               |
| `UPLOAD_CHUNK_SIZE_KB`     | 512     | Resumable chunk size.            |
| `UPLOAD_MAX_CONCURRENT`    | 4       | Per-user in-flight upload cap.   |
| `UPLOAD_TTL_DAYS`          | 30      | Auto-cleanup for orphan chunks.  |

## Related

- `rust_utils/chunk_hash.rs` — rolling BLAKE3 used during finalise.
- `app/security/secure_upload.py` — content-type sniffing, MIME allow-list, WAF hooks.
- `app/chats/messages/files.py` — turns a completed upload into a message attachment.

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
