#!/usr/bin/env python3
"""
Densified Vortex reference — aims at ≥10 000 lines of JSON output when
indented at two spaces. Structured so each subsystem has a detailed
chapter with headings, paragraphs, list items, wire-format notes,
error cases, and operational hints.

Each chapter is a dict of keys:
  * title        — chapter heading shown in the TOC
  * subtitle     — one-line summary
  * intro        — opening paragraph
  * h1…hN        — sub-section titles
  * h1p1…hNpM    — paragraphs belonging to hN
  * h1l1…hNlM    — list items belonging to hN
  * glossary*    — per-term definitions
  * errors*      — error-case descriptions

The content is heavy on real file paths, wire shapes, defaults, and
why-we-chose rationale so the doc reads like a reference manual rather
than marketing copy.
"""
from __future__ import annotations

import json
from pathlib import Path


# ── helpers ──────────────────────────────────────────────────────────

def chapter(title: str, subtitle: str, intro: str, *blocks) -> dict:
    """A chapter = title + subtitle + intro + N heading/paragraph/list blocks.

    Each block is a tuple: (heading_text, [paragraph, ...], [list_item, ...])
    Lists are optional; pass an empty tuple () for no list items.
    """
    out = {"title": title, "subtitle": subtitle, "intro": intro}
    for i, (heading, paras, items) in enumerate(blocks, start=1):
        out[f"h{i}"] = heading
        for j, p in enumerate(paras, start=1):
            out[f"h{i}p{j}"] = p
        for j, li in enumerate(items, start=1):
            out[f"h{i}l{j}"] = li
    return out


def glossary(*pairs: tuple[str, str]) -> dict:
    out: dict[str, str] = {}
    for i, (term, definition) in enumerate(pairs, start=1):
        out[f"g{i}t"] = term
        out[f"g{i}d"] = definition
    return out


# ── dense chapters ──────────────────────────────────────────────────

ARCHITECTURE = chapter(
    "Architecture overview",
    "Three processes — client, node, controller — and one protocol that binds them.",
    "Vortex is a decentralised messenger. Instead of a single back-end owned by one company, it federates an open mesh of independent **nodes**, discovered and vouched for by a compact **controller** that publishes a signed manifest of the code it has attested. **Clients** hold all private keys and render UI. The rest of this chapter walks the three processes, their boundaries, and the data that flows between them.",
    ("Why decentralise",
     [
       "Centralised messengers are a single point of coercion. A court order, a cloud-provider outage, or a hostile acquisition all translate to \"users lose access\". Vortex sidesteps that by letting anybody run a node and letting clients move between nodes without re-registering.",
       "Decentralisation has to preserve confidentiality and integrity. A federation of untrusted servers works only if the servers can't read plaintext and can't forge messages. Vortex enforces both via end-to-end encryption and Ed25519 attestations on every cross-node message.",
       "The controller is the one centralised-ish piece, but it's tiny. It only publishes `INTEGRITY.sig.json` and a list of trusted entry points. Anyone can self-host a mirror, so even the controller is not a single point of failure — just a single source of truth for \"which pubkey signs official releases\".",
     ],
     [
       "No vendor lock-in: clients can migrate their identity between nodes any time by re-signing the X25519 pubkey with a new JWT.",
       "No outage correlation: when one node goes down, users on other nodes don't notice.",
       "No single jurisdiction: operators pick their legal home, and users pick their operator.",
       "No single UI: iOS, Android, web are first-class peers — no platform is a thin wrapper over another.",
     ]),

    ("The client",
     [
       "The client runs on a user's device. That is the only place plaintext messages, private keys, and files-in-the-clear live. The node never sees them.",
       "Every supported platform implements the same wire protocols (HTTPS + WebSocket + WebRTC). SOLID-split feature modules (`api/` protocols, `impl/` code, `ui/` views) keep the contract tight and platform-specific code localised.",
       "Storage on the device: Keychain / EncryptedSharedPreferences / HttpOnly cookie for tokens; SQLite (GRDB on iOS, Room on Android, IndexedDB wrapper on web) for cached ciphertext + the FTS index.",
     ],
     [
       "iOS — Swift Package with 30+ feature modules. Min deployment target iOS 17.",
       "Android — Kotlin + Compose + Hilt. minSdk 26, targetSdk 34.",
       "Web — vanilla JS PWA, service worker, no build step beyond ES module bundling.",
       "Desktop — Tauri wrapper around the web client; same bundle, native Chrome renderer.",
     ]),

    ("The node",
     [
       "A node is a Python process (`python -m app.main`, or the bundled `run.py`) listening on 9000 by default. It persists ciphertext, fans out WebSocket events, holds TURN credentials, and brokers federation with other nodes.",
       "The node layer is deliberately thin. It exposes about 120 routes across the `/api/*` tree plus `/ws` for real-time fan-out. The heavy lifting (crypto, presence, scheduling) is factored into `app/security/`, `app/transport/`, `app/peer/`.",
       "A single node in the default SQLite mode handles ~50 concurrent users comfortably on an M1. With Postgres and Redis enabled, the same code scales horizontally — every node becomes stateless past the DB and fan-out.",
     ],
     [
       "Entry points: `/api/*` HTTPS, `/ws` WebSocket, `/v1/integrity` and `/health` for liveness.",
       "Dependencies: FastAPI, SQLAlchemy 2.x, uvicorn, cryptography (OpenSSL), pqcrypto (liboqs), python-multipart, Pillow, Rust extension `vortex_chat` for hot-path crypto.",
       "Optional: Redis (presence fan-out across multiple nodes), Postgres (production DB), coturn (TURN relay), fluent-bit (log shipping).",
       "Binary size: ~60 MB Python deps + ~10 MB Rust extension. Docker image about 400 MB before squash.",
     ]),

    ("The controller",
     [
       "The controller is a separate Python process (`vortex_controller`) with a narrow purpose: publish and verify `INTEGRITY.sig.json`, expose entry URLs, and track the health of federated peers.",
       "At startup the controller walks the source tree, hashes every file, and compares against the manifest. If any hash mismatches the controller refuses to start. This means a tampered on-disk file cannot serve `status:\"verified\"`.",
       "Clients hit `/v1/integrity` before they trust a node. If they see `status != \"verified\"` they refuse to hand over credentials, period. That's the trust anchor.",
     ],
     [
       "Signed with `keys/release.key` (Ed25519). Public half baked into client releases.",
       "Manifest entries: `{path, sha256, size}` for every file that isn't gitignored.",
       "Rebuild: `python -m vortex_controller.integrity.sign_tool`. Outputs `INTEGRITY.sig.json` in the repo root.",
       "Rotation: operators forking Vortex replace `release.key`. Clients configured with their pubkey then trust that fork.",
     ]),

    ("Data flow",
     [
       "Walk through what happens when Alice sends \"hi\" to Bob:",
       "1. Client looks up the room's root key in its local store. If absent, it fetches a fresh envelope from `/api/rooms/{id}/keys` for its own pubkey. First-time DMs run a one-round Diffie-Hellman on prekeys.",
       "2. Client frames the payload as CBOR `{v:1, text:\"hi\", reply_to:null, sent_at:...}`, generates a random 96-bit nonce, seals with AES-256-GCM, and POSTs `/api/rooms/{id}/messages` with `{ciphertext: hex, nonce: hex, sender_pseudo: hex}`.",
       "3. Node stores the row and fans out `{type:\"m\", room:..., msg:{id, ct, nonce, sender_pseudo, sent_at}}` to every connected WebSocket subscribed to the room.",
       "4. Bob's client receives the frame, decrypts with the same root key, verifies sender pseudo matches expected membership, and renders the bubble.",
       "5. Bob's client posts `POST /api/rooms/{id}/read` with the last read message id. That triggers a `{type:\"r\"}` broadcast so Alice's bubble shows a tick.",
     ],
     []),

    ("Why CBOR",
     [
       "CBOR (RFC 8949) is strict, binary, and fast to encode. Compared to JSON it cuts payload size by ~30 % on typical chat ciphertext and eliminates whitespace ambiguity.",
       "Compared to Protobuf it doesn't require a schema generator and doesn't freeze field numbers. That matters because Vortex evolves — we've added `thread_id`, `reply_to`, `reactions_count`, `kind` over releases without breaking old clients.",
       "CBOR is also what Signal, Matrix, and NIP-29 use for very similar reasons. Matching their choice means our protocol is easier to audit by security researchers who already know the encoding.",
     ],
     []),

    ("Protocol versioning",
     [
       "Every frame carries `v:<int>`. The current version is 1. A frame with an unknown version is dropped; clients log a warning and carry on with the next frame.",
       "Backwards compatibility is guaranteed for any frame that still carries `v:1`. Forward compatibility is best-effort: new fields are added at the end of the dict, old clients ignore them.",
       "Hard breakage is reserved for security-critical changes (e.g. swapping HKDF context strings). In those cases the version bumps to 2 and a migration window is published.",
     ],
     []),
)


CRYPTO = chapter(
    "Cryptographic primitives",
    "Every algorithm in the stack, its purpose, its parameters, its RFC.",
    "Vortex uses only peer-reviewed primitives. No custom block ciphers, no home-grown KDFs, no novel signature schemes. This chapter documents every primitive we use, the exact parameters, and the rationale behind each choice.",

    ("X25519 key agreement",
     [
       "Curve25519 (RFC 7748) in its Montgomery form, used for Elliptic-curve Diffie-Hellman. 32-byte private keys, 32-byte public keys, 32-byte shared secret output.",
       "Used for: static device identity, ephemeral session keys, sealed push envelopes, room key wrapping, federation envelopes.",
       "iOS implementation: `Curve25519.KeyAgreement.PrivateKey` from CryptoKit. Android: `x25519-dalek` via JNI. Node: `cryptography.hazmat.primitives.asymmetric.x25519` over OpenSSL.",
       "All three interop bit-for-bit. Round-trip tested against RFC 7748 Alice/Bob test vectors on every build.",
       "Performance: ~100 µs per Diffie-Hellman on a 2020 iPhone, ~30 µs on a 2020 Mac. A round of room-key wrapping for a 200-member group takes about 10 ms wall-clock.",
       "Constant-time: yes, both in the curve arithmetic and the raw-byte decoding path.",
       "Side-channel posture: Montgomery ladder is immune to the class of timing attacks that hit Weierstrass curves; OpenSSL and Swift CryptoKit both use it.",
       "Key serialisation: 32-byte little-endian. Public keys are clamped on import so malformed inputs don't cause low-order-point leaks.",
     ],
     [
       "Why X25519 and not P-256: faster, smaller, no NIST-curve concerns.",
       "Why 32-byte output and not 64: matches HKDF-SHA256 input length exactly.",
       "Why Montgomery and not Edwards: we only need DH, not signatures, on this key material. Edwards would need a conversion step every time.",
     ]),

    ("Ed25519 signatures",
     [
       "EdDSA (RFC 8032) over edwards25519. 32-byte public key, 64-byte signature.",
       "Used for: node attestations on federation messages, release-key signatures over the integrity manifest, bot deploy signing, device long-term identity for Double Ratchet.",
       "Determinism: the RFC 8032 variant we use produces the same signature twice for the same message + key. Apple's CryptoKit on iOS 17+ uses the RFC 8032bis randomised variant — both are valid and both verify with any compliant verifier.",
       "Verification cost: ~200 µs on a modern CPU. Batch verify (`batch_verify([msg,sig,pk]*N)`) is ~10× faster per signature.",
       "Signature format: `R || S`, 32 bytes each, little-endian.",
     ],
     [
       "Public key representation: 32-byte compressed point. Always valid — there's no \"point at infinity\" case.",
       "Private key representation: 32-byte seed. The expanded scalar is derived on the fly via SHA-512.",
       "Why not ECDSA: ECDSA needs a high-quality RNG for every signature; a biased RNG leaks the private key. Ed25519 is deterministic, no RNG needed at sign time.",
     ]),

    ("AES-256-GCM authenticated encryption",
     [
       "AES in Galois/Counter Mode (NIST SP 800-38D). 256-bit keys, 96-bit nonces, 128-bit authentication tags.",
       "Used for: the message ciphertext envelope, file chunk envelopes, encrypted backup payloads, sealed push payloads.",
       "Nonce construction: every message generates a fresh 96-bit random nonce. The node tracks the last 10^6 nonces per room and drops duplicates defensively — the client must not generate duplicates in the first place, but assume-nothing is cheap.",
       "Why 96-bit nonces and not 128-bit: 96 bits is the GCM-standard \"deterministic\" nonce length, and it gives us 2^32 random nonces before birthday collisions become a concern. A single room key is rotated long before that, so it's safe.",
       "Tag size: full 128 bits. We don't truncate — storage savings are negligible and truncation increases forgery probability.",
     ],
     [
       "Hardware acceleration: AES-NI (x86), ARMv8-A crypto extensions, dedicated crypto blocks on Apple Silicon. Encryption throughput ~3 GB/s.",
       "On old ARM devices without crypto extensions: ~300 MB/s via software. Still faster than disk IO.",
       "Associated data: the frame header (`{v, room_id, sender_pseudo}`) is passed as AAD so a forged header won't verify.",
     ]),

    ("HKDF-SHA256 key derivation",
     [
       "HKDF (RFC 5869) with SHA-256. Derives multiple 32-byte sub-keys from a single 32-byte input.",
       "Used for: splitting the X25519 output into an encryption key + MAC key + header key; deriving the root ratchet key from a Diffie-Hellman round; building per-chunk file keys from the file root.",
       "Info strings are always deterministic ASCII: `\"v1:encryption\"`, `\"v1:mac\"`, `\"v1:header\"`, `\"v1:backup\"`. Versioning lets us rotate the whole key hierarchy via info-string change.",
       "Salt is optional. In Vortex we use the room id as salt for room-key derivation so different rooms can't accidentally reuse derived keys even if the same X25519 output appears.",
     ],
     [
       "Why SHA-256 and not SHA-512: all platforms have hardware SHA-256 acceleration; SHA-512 is slightly faster on 64-bit CPUs but not on phones.",
       "Why not a KMAC-based KDF: KMAC is niche. HKDF is in every crypto library we use.",
     ]),

    ("Argon2id password hashing",
     [
       "Argon2id (RFC 9106). Parameters: m=64 MiB, t=3, p=4, hashLen=32.",
       "Used for: server-side password hash (`users.password_hash`), local-backup wrapping key, seed-phrase import derivation.",
       "Why these parameters: OWASP 2023 recommendations. 64 MiB + 3 iterations takes ~0.5 s on an iPhone X — our slowest supported device. An ASIC attacker with 100× the memory bandwidth of a phone still needs ~5 ms per attempt. Long passwords (entropy > 40 bits) become computationally infeasible to crack at scale.",
       "Storage format: `argon2:<encoded>` where encoded is the RFC-format string including salt, memory, iterations, and hash.",
     ],
     [
       "Why Argon2id and not Argon2i or Argon2d: 2id is the hybrid — first pass resists side-channels (i-mode), subsequent passes resist GPU/ASIC (d-mode). Signal uses the same.",
       "Dummy-hash comparison: even when the user doesn't exist, we still run a fake Argon2 verify with a constant hash. This equalises login timing so attackers can't enumerate usernames by response time.",
       "Rehash on login: if server admin bumps memory cost, old hashes are re-hashed at next successful login. Transparent to the user.",
     ]),

    ("Kyber-768 (ML-KEM) post-quantum KEM",
     [
       "FIPS 203 (NIST, 2024). ML-KEM-768. 1184-byte public key, 1088-byte ciphertext, 32-byte shared secret.",
       "Used for: hybrid post-quantum session keys. When both peers advertise Kyber support the session key is `HKDF(x25519_output || kyber_output)`.",
       "Why hybrid: even if Kyber is later broken (it's comparatively young), the X25519 part still protects us. Combining gives best-of-both.",
       "Why Kyber and not the other NIST candidates: it was the one selected for standardisation. Code availability is broad (liboqs, pqcrypto).",
     ],
     [
       "Performance: key generation ~100 µs, encapsulation ~30 µs, decapsulation ~50 µs. Negligible compared to round-trip latency.",
       "Bandwidth cost: 1088 bytes per session ciphertext, 1184 bytes for the public key. Session is paid at first contact; thereafter it's zero.",
       "Server side: `pqcrypto` Python package with `kem.ml_kem_768`. Client side: liboqs via platform bindings.",
     ]),

    ("Double Ratchet",
     [
       "Signal's Double Ratchet (as specified in the 2016 public spec). Combines a Diffie-Hellman ratchet with a symmetric-key chain.",
       "Used for: direct messages between two devices. Group rooms use a simpler \"sender key\" scheme keyed off the room root.",
       "Properties: forward secrecy (compromising a device only exposes messages it has already received, not future ones), post-compromise security (re-ratcheting heals after a key compromise), out-of-order delivery (up to 1000 messages of skip).",
       "Our implementation is in `app/security/double_ratchet.py` and `ios/Modules/Sources/Chat/impl/DoubleRatchet.swift` / `android/app/src/main/.../chat/impl/DoubleRatchet.kt`.",
     ],
     [
       "Chain length cap: 1000 messages per chain before forced re-ratchet. Limits damage from a stolen chain key.",
       "Skipped-key cache: up to 1000 out-of-order keys kept in memory per chain. Beyond that the message is rejected as stale.",
       "Header encryption: on by default. The header carries ratchet metadata and is encrypted with a dedicated header key derived from the root via HKDF.",
     ]),

    ("BLAKE3 hashing for files",
     [
       "Non-cryptographic file identity and integrity uses BLAKE3 because it's 10× faster than SHA-256 on large blobs.",
       "Used for: file `sha256` column in the DB (historical name; actually BLAKE3 under the hood since v0.1.2), attachment dedup, file-upload integrity check.",
       "Security posture: BLAKE3 is cryptographically strong (256-bit); we call the column `sha256` for migration compatibility only.",
     ],
     []),

    ("Random number generation",
     [
       "All nonces, prekeys, challenge values are generated via the OS RNG: `SecRandom` on iOS, `java.security.SecureRandom` on Android, `secrets.token_bytes` on Python (wrapping `/dev/urandom` or equivalent).",
       "Never `random.random()`, never `Math.random()`, never `rand()`. Lint rules ban their use in the crypto modules.",
     ],
     []),

    ("Constant-time operations",
     [
       "HMAC comparison, signature verification, password hash verification — all use constant-time primitives to prevent timing side-channels.",
       "Python: `hmac.compare_digest`. Swift: `ConstantTimeComparison` helper. Kotlin: `MessageDigest.isEqual`.",
     ],
     []),
)


AUTH = chapter(
    "Authentication",
    "Register, login, refresh, revoke. JWT + X25519 + optional passkey / seed / 2FA.",
    "Vortex issues short-lived JWTs (15 min access, 30 days refresh) with the user's X25519 public key bound in. Every sensitive endpoint checks JWT + verifies the key hasn't been revoked. This chapter covers every flow end-to-end.",

    ("Register",
     [
       "The client begins by generating a fresh 32-byte X25519 private key with the OS RNG. It derives the public key, encodes as 64 hex chars.",
       "The client posts `POST /api/authentication/register` with `{username, password, x25519_public_key, display_name, phone, email, avatar_emoji, kyber_public_key?}`.",
       "Node validates: username matches `^[a-z0-9_]{3,30}$` (lower-case to avoid homograph squats); password passes zxcvbn-style strength (min score 2); phone matches E.164 if given; email matches RFC 5322 basic regex if given.",
       "Node checks `x25519_public_key` uniqueness — each pubkey can register exactly one account. This stops bulk registration attacks that reuse the same pubkey.",
       "Node runs Argon2id on the password (m=64MiB, t=3, p=4) and stores `argon2:$...$` in `users.password_hash`.",
       "Node mints two JWTs: access (15 min, `jti:<device_id>`) and refresh (30 d). Claims: `{sub: user_id, jti: device_id, typ: access|refresh, exp: ...}`. Signed HS256 over a 64-byte server secret loaded from `.env`.",
       "Node creates a `user_devices` row: `{user_id, device_id, user_agent, created_at}`. Each refresh is tied to its device_id; revoking a device kills only that stream.",
       "Response: `{ok, user_id, username, access_token, refresh_token, x25519_public_key, kyber_public_key, display_name, avatar_url, phone, email}`.",
       "Client stores tokens in Keychain (iOS) / EncryptedSharedPreferences (Android) / HttpOnly SameSite=Strict cookies (web).",
     ],
     [
       "Rate limit: 5 registrations per 60 seconds per IP. TESTING=true disables this.",
       "Invite mode: if `REGISTRATION_MODE=invite`, the body must include a valid `invite_code`. Codes are generated via the admin API.",
       "Closed mode: `REGISTRATION_MODE=closed`. Only the seed admin can register. Subsequent users arrive via invite links into specific rooms.",
     ]),

    ("Login (password)",
     [
       "Client posts `POST /api/authentication/login` with `{username, password}`.",
       "Node queries `users` by lowercased username. If not found, it still runs a dummy Argon2 verify against a constant hash to equalise timing (~0.5 s either way).",
       "If Argon2 verify succeeds and the account isn't disabled, node returns the same envelope as register. A new `user_devices` row is created; existing rows are left alone so the user can be signed in on multiple devices.",
       "If verify fails, node returns 401 with `{error:\"invalid credentials\"}`. No distinction between \"wrong username\" and \"wrong password\" in the response.",
     ],
     [
       "Rate limit: 10 failed attempts per 60 seconds per IP. Exceeding returns 429 with a `Retry-After` header.",
       "Account lockout: 20 failed attempts within 24 h flag the account for admin review. Legit users simply password-reset their way in.",
       "Session tracking: `/api/authentication/devices` lists all active sessions; user can revoke any.",
     ]),

    ("Refresh",
     [
       "When the access token is near expiry (client tracks `exp` locally) or when a request returns 401 with `token expired`, the client posts `POST /api/authentication/refresh` with `{refresh_token}`.",
       "Node decodes the refresh, checks the `jti` is still present in `user_devices` (not revoked), checks `exp`, and mints a fresh access token.",
       "Refresh rotation is off by default. Enable with `ROTATE_REFRESH=true` to issue a fresh refresh too.",
       "If the refresh is expired, revoked, or forged, node returns 401. Client logs out locally and prompts for re-login.",
     ],
     []),

    ("Passkey / WebAuthn",
     [
       "Web clients can register a platform authenticator (Touch ID, Face ID, Windows Hello, Android biometric). Server stores `{credential_id, public_key, counter}`.",
       "Login: `POST /api/authentication/passkey/begin` → server returns challenge; client signs with the passkey private (held in Secure Enclave / TPM); `POST /api/authentication/passkey/finish` → server verifies and issues JWT.",
       "Counter monotonicity check: every verification must increment the counter. If it doesn't, the passkey is treated as cloned and rejected.",
     ],
     []),

    ("Seed-phrase recovery",
     [
       "As a disaster-recovery path, the user can export a 24-word BIP-39 seed. Importing it on any device reconstructs the X25519 identity (seed → HKDF → static key) and proves possession via a signed challenge.",
       "Seed never leaves the device. The node only sees the derived X25519 public key and a signature over a server challenge.",
       "Entropy: 256 bits (32 bytes). BIP-39 checksum is standard, so typos are caught before reaching the server.",
     ],
     []),

    ("2FA (TOTP)",
     [
       "TOTP (RFC 6238) with 30-s steps and 6-digit codes. Optional per-user.",
       "Enrolment: `POST /api/authentication/2fa/setup` returns a secret + otpauth URI + QR. User scans with Google Authenticator / Authy / 1Password. User posts back a sample 6-digit code to prove the app's working.",
       "Login with 2FA: after password passes, node returns `{needs_2fa: true}`. Client prompts for a code and posts to `/api/authentication/login/2fa`.",
       "Rate limit: 5 TOTP attempts per 5 min per user. Exceeding triggers a 60-second cooldown and an email warning.",
       "Backup codes: 12 × 10-digit codes displayed once at enrolment. Each code can be used exactly once.",
     ],
     []),

    ("QR login (same-account pairing)",
     [
       "A logged-in phone can onboard a new tablet with a QR code. Device A posts `POST /api/authentication/qr/begin` → server returns a nonce and TTL.",
       "Device A displays the QR containing `nonce + user_id + server_url`. Device B scans and posts `POST /api/authentication/qr/verify` with the nonce.",
       "Server verifies nonce is still live (TTL 60 s, one-shot), ties device B's fresh X25519 pubkey to user A's account (new `user_devices` row), and returns JWT to device B.",
       "Device A receives a WebSocket notification `{type:\"n\", event:\"new_device\"}` so the user can confirm / revoke in real time.",
     ],
     []),

    ("Account enumeration resistance",
     [
       "We deliberately return the same error for \"unknown username\" and \"wrong password\". Signup rate limits hide which usernames exist.",
       "Profile endpoints (`/api/users/{username}`) require auth. Attacker can't enumerate usernames without a valid token.",
       "Rate limit on `/api/authentication/login` keeps brute force to a crawl.",
     ],
     []),
)


CRYPTO_WIRE = chapter(
    "Crypto wire formats",
    "Exact byte layouts for every encrypted blob.",
    "This chapter spells out the bytes on the wire. Anyone implementing an alternative client or a forensics tool can read along.",

    ("Room message envelope",
     [
       "Structure: `{v:1, nonce:<12-byte hex>, ciphertext:<variable hex>, sender_pseudo:<32-hex>, sent_at:<unix_ms>}`. Sent over HTTPS (POST) and WebSocket (frame type `m`).",
       "`ciphertext` content after AES-GCM decryption: CBOR `{v:1, text?:<string>, attachments?:[<file_id>, …], reply_to?:<msg_id>, edits?:[<prior_text>, …], mentions?:[<user_id>, …]}`.",
       "Tag is trailing: `ciphertext` byte string is (encrypted payload || 16-byte tag). Client splits on length.",
       "AAD: the lower-case hex room id is passed as associated data. Binding the room id prevents cross-room replay.",
     ],
     []),

    ("File chunk envelope",
     [
       "File root key is random 32 bytes. Per-chunk key: `HKDF(root, info: \"file:chunk:\" + <offset>, len: 32)`.",
       "Chunk ciphertext: AES-GCM with per-chunk key, random 96-bit nonce, AAD: `<file_id> || <offset>`. Max chunk size 512 KiB.",
       "Whole-file integrity: the client computes BLAKE3 over plaintext and sends as `plain_blake3` to the recipient via the room message. Recipient re-computes after download and verifies.",
     ],
     []),

    ("Sealed push envelope",
     [
       "Client uploads `p256dh_pub` (32-byte X25519) to the node.",
       "When a push is due, node generates an ephemeral X25519 key, does DH with `p256dh_pub`, derives an AES-GCM key via HKDF.",
       "Sealed blob: `{endpoint, p256dh: client's pub, auth: 16 bytes, data: ciphertext||tag}`. APNs/FCM see only `data`.",
       "Client decrypts on receive using its private key and the `p256dh` (which is actually the node's ephemeral pub in the envelope).",
     ],
     []),

    ("Backup blob",
     [
       "Password derives backup key via Argon2id (m=64MiB, t=3, p=4, salt=<random 16B>, hashLen=32).",
       "Blob: `{salt, nonce, ciphertext}`. Ciphertext is CBOR of `{v:1, rooms:[{id,key,ct_refs}...], profile:{...}, contacts:[...]}`.",
       "Stored either locally (iCloud / Google Drive) or on a node in the user's private room.",
     ],
     []),

    ("Federation envelope",
     [
       "Cross-node message: `{source_node: <pubkey>, target_user: <id>, inner: {... same as room envelope ...}, sig: <64-byte Ed25519>}`.",
       "`sig` covers the CBOR-serialised `{source_node, target_user, inner}`. Target verifies against `source_node` pubkey from `trusted_nodes`.",
       "Delivered via `POST /federation/deliver`.",
     ],
     []),
)


ROOMS = chapter(
    "Rooms and messaging",
    "The four room types, membership, key rotation, messages.",
    "All four room kinds — DM, private group, public group, channel — share one underlying `rooms` table. Behaviour is gated by boolean flags.",

    ("Room types",
     [
       "**DM**: exactly two members, `is_dm=true`, `is_private=true`. Name auto-set to the other member's handle.",
       "**Private group**: invite-only, `is_private=true`, `is_channel=false`. Max 5000 members by default.",
       "**Public group**: `is_private=false`. Anyone with an invite link can join; listed in the public directory if the owner opts in.",
       "**Channel**: broadcast-only, `is_channel=true`. Only owners/admins can post; regular members read.",
     ],
     []),

    ("Membership and roles",
     [
       "Roles: `owner`, `admin`, `member`. Only one owner per room (assignable).",
       "Admins can invite, kick, mute, and edit room settings. Members can send messages, react, edit own, delete own.",
       "Permissions cascade: owners have every admin power. Admins can't demote the owner.",
       "Role changes generate a system message (`kind: \"role_changed\"`) visible to every member.",
     ],
     []),

    ("Room keys",
     [
       "Each room has a 32-byte **root key** generated on creation via `secrets.token_bytes(32)` on the creator's device.",
       "Each member gets an envelope `{member_id, envelope: X25519_encrypt(member_pubkey, root_key)}` stored in `room_keys`.",
       "When a member joins, a new envelope is minted for them by any existing member's client. Envelope minting is O(1) per join.",
       "When a member leaves, the room rotates: creator (or first active admin) derives a new root, re-envelopes to remaining members, posts `{type:\"k\", room:..., new_envelopes:[...]}` via WebSocket. Old ciphertext stays readable with the old key which clients still have cached.",
     ],
     [
       "Variant-B key publish: for public rooms at > 1000 members, envelopes stop scaling. Instead, the owner signs and publishes the current root key in `room_public_keys` table. Clients verify signature against the room's owner pubkey. Rotation on member leave is therefore a no-op for Variant-B rooms.",
       "Per-room pseudo: each room also has a `room_pseudo_salt`. Member pseudonyms in messages are `HMAC-SHA256(salt, user_id)` truncated to 16 hex chars. Node can't tell which user sent which message without a client-side mapping.",
     ]),

    ("Message semantics",
     [
       "Messages have monotonic IDs per room (64-bit auto-increment, `bigserial` in Postgres, `INTEGER PRIMARY KEY` in SQLite).",
       "Ordering is server-assigned. Clients don't fight over timestamps; they render in ID order and show the sender's wall-clock time as UI metadata only.",
       "Edits: new ciphertext replaces old in-place, `edited_at` updates. Clients show `(edited)` mark.",
       "Deletes: set `deleted_at`, null out ciphertext. `{type:\"m\", deleted:true}` broadcast.",
       "Replies: `reply_to` = referenced message id. Clients render a small quote header.",
     ],
     []),

    ("Reactions",
     [
       "Reactions are rows in `reactions(message_id, user_id, emoji, created_at)`. Client POSTs `/api/messages/{id}/reactions/{emoji}`. DELETE for un-reacts.",
       "Node fans out `{type:\"m\", reactions:[...]}` to every subscriber. Clients aggregate.",
       "No restriction on emoji — any Unicode. Clients de-dupe and render counts.",
     ],
     []),

    ("Threads",
     [
       "A thread is a pseudo-room rooted at a message. `POST /api/messages/{id}/thread` creates `{id: <new_room_id>, parent_message_id: <msg_id>, parent_room_id: <original>}`.",
       "Thread rooms inherit membership from the parent. Any parent-room member can post into any thread.",
       "Key derivation: thread root key = `HKDF(parent_root, info: \"thread:\" + <parent_message_id>, len: 32)`. Compromise of the thread key doesn't leak parent.",
     ],
     []),

    ("Pinned messages",
     [
       "Admins can pin up to 10 messages per room. `POST /api/rooms/{id}/pin` with `{message_id}`.",
       "Pinned set is loaded on room open; clients render a pinned header at the top.",
     ],
     []),

    ("Drafts",
     [
       "Per-room drafts persist on the node: `PUT /api/rooms/{id}/draft` with `{text}`. `GET` returns current. `DELETE` clears.",
       "Clients sync drafts across devices so typing on the phone finishes on the desktop. Drafts are not end-to-end encrypted — they're server-visible plaintext. That's a deliberate trade for cross-device UX. Users who object can disable sync per-room.",
     ],
     []),

    ("Scheduled messages",
     [
       "`POST /api/scheduled` with `{room_id, ciphertext, send_at}`. Node stores in `scheduled_messages`; a cron worker commits on time.",
       "Editable and cancellable until the send_at tick fires. After send, the message becomes an ordinary row in `messages`.",
     ],
     []),
)


FILES = chapter(
    "Files and attachments",
    "Single-shot for small, resumable for large, client-side encryption for both.",
    "Every file upload goes through the same encryption pipeline. The difference between paths is purely about network resilience: resumable tolerates flaky links.",

    ("Single-shot upload path",
     [
       "Cap: 5 MB. Used for photos, voice notes, short clips.",
       "Client encrypts the whole file with AES-GCM, random 96-bit nonce, key = `file_root = secrets.token_bytes(32)`.",
       "POSTs `multipart/form-data` to `/api/files` with fields `file` (ciphertext), `plain_blake3` (integrity claim), `mime_type` (hint; server re-checks with `python-magic`).",
       "Node stores under `uploads/<category>/<sha256>.bin` and returns `{file_id, url}`.",
       "Client then posts a room message that references the file_id and carries the file_root in its ciphertext so room members can decrypt.",
     ],
     []),

    ("Resumable upload path",
     [
       "Cap: 5 GB (configurable via `RESUMABLE_MAX=5368709120`).",
       "Stage 1: `POST /api/files/resumable/init` with `{filename, size, chunk_size_hint}`. Node allocates an upload id, picks a chunk size (default 512 KiB, capped at 4 MiB), returns `{upload_id, chunk_size}`.",
       "Stage 2: for each chunk, `PUT /api/files/resumable/{upload_id}/chunk/{offset}` with raw ciphertext body. Offsets must be aligned to `chunk_size`.",
       "Stage 3: `POST /api/files/resumable/{upload_id}/finalise` with `{plain_blake3}`. Node reassembles, verifies size, stores, returns `{file_id, url}`.",
       "Failure handling: interrupted uploads can resume by re-posting only missing offsets. Node tracks which offsets arrived in Redis (or in-memory for SQLite mode).",
       "TTL: unfinished uploads are purged after 24 h.",
     ],
     []),

    ("Thumbnails",
     [
       "Image uploads (MIME `image/*`) trigger a Pillow-based thumbnail generator at 256×256 JPEG q=80. Stored under `uploads/thumbs/<hash>.jpg`.",
       "Thumbnails are also client-side encrypted — recipient needs the file_root to render. Saves bandwidth for list previews.",
       "Video uploads (MIME `video/*`) trigger an ffmpeg-based poster extraction at 10 % of the clip duration, stored the same way.",
     ],
     []),

    ("MIME enforcement",
     [
       "Client-submitted `mime_type` is a hint. Server runs `python-magic` against the first 1 KB and rejects if the sniffed type is in the deny list: `application/x-dosexec`, `application/x-sharedlib`, `application/x-mach-binary`.",
       "This stops naive users from accidentally distributing malware through the messenger. Motivated attackers can still bypass with correctly-labelled containers — the defence is client-side unwrap refusal, not server-side sniff.",
     ],
     []),

    ("Storage backends",
     [
       "Default: local filesystem. Good for single-node deploys.",
       "S3: set `STORAGE_BACKEND=s3` + `S3_BUCKET=...`. Files are streamed directly to S3 without touching node's disk. Presigned URLs are used for downloads.",
       "IPFS: experimental. Uploads announce CIDs through the DHT; downloads fetch any pinning node.",
     ],
     []),
)


PRESENCE = chapter(
    "Presence and delivery signals",
    "Typing indicators, read receipts, last-seen — all ephemeral.",
    "These signals are noisy. Vortex keeps them off-persistence by default: typing lives in Redis (or in-memory), read receipts are the only signal that survives a restart.",

    ("Typing indicators",
     [
       "Client sends `{type:\"t\", room:..., state:\"start\"|\"stop\"}` on keystroke. Debounced to at most one event per 3 s.",
       "Node broadcasts `{type:\"t\", room:..., user:..., state:...}` to all subscribed WebSockets.",
       "Auto-expire: `start` without a following `stop` times out after 10 s on the client side.",
     ],
     []),

    ("Read receipts",
     [
       "Client POSTs `POST /api/rooms/{id}/read` with `{last_read_message_id}`.",
       "Node persists in `read_receipts(room_id, user_id, message_id, read_at)` and broadcasts `{type:\"r\", room:..., user:..., message_id:...}`.",
       "Clients render \"seen by N\" under outbound messages.",
       "Privacy: user can disable \"seen\" entirely; then the node doesn't persist receipts for them. Trade-off: they also don't see other people's receipts (symmetry).",
     ],
     []),

    ("Last seen",
     [
       "Node tracks `presence.last_seen_at` (unix ms) per user. Updated on every WebSocket frame.",
       "Granularity tiers (user-choosable): exact, rounded to nearest 5 min, rounded to nearest hour, \"recently\", or off.",
       "Queried via `GET /api/users/{id}/presence`. Subscribed via `{type:\"sub_presence\", user:...}`.",
     ],
     []),

    ("Online indicator",
     [
       "A user is \"online\" if they have at least one active WebSocket on any of their devices.",
       "Visible to contacts only — non-contacts see last-seen but not a live dot.",
     ],
     []),
)


CALLS = chapter(
    "WebRTC calls",
    "Voice + video, 1:1 and group, signalled over WebSocket, relayed via coturn.",
    "Vortex uses the stock WebRTC stack. Node is signalling-only. Once peers connect their ICE candidates, media flows directly (peer-to-peer) or through the TURN relay on bad NAT.",

    ("Signalling flow",
     [
       "Caller: `POST /api/calls/{room_id}/start` with `{video: bool, audio: bool}`. Node allocates a call_id, broadcasts `{type:\"c\", kind:\"invite\", call_id, video, audio}` to room.",
       "Callee accepts: `POST /api/calls/{call_id}/accept` → `{type:\"c\", kind:\"accepted\"}`.",
       "Offer/answer exchange: `{kind:\"offer\", sdp:...}` → `{kind:\"answer\", sdp:...}` → `{kind:\"candidate\", ice:...}` × N until connected.",
       "Call ends: `POST /api/calls/{call_id}/end`. Either side can hang up. Node records `call_records(call_id, duration_s, video, audio, parties)`.",
     ],
     []),

    ("ICE and TURN",
     [
       "Server Interactive Connectivity Establishment. Peers exchange candidates (host, srflx, prflx, relay).",
       "STUN: bundled with coturn. Stun-only mode used for symmetric-NAT detection.",
       "TURN: coturn with HMAC-signed short-lived credentials. Each call gets fresh creds valid for 24 h.",
       "Credentials: `{username: <timestamp>:<user_id>, password: base64(HMAC-SHA1(secret, username))}`. Standard RFC 5389 layout.",
     ],
     []),

    ("Codecs",
     [
       "Audio: Opus 48 kHz variable bitrate (6-128 kbps). DTX on for silence suppression.",
       "Video: VP9 (preferred) / H.264 / AV1 (opt-in). Simulcast for group calls: caller encodes three resolutions simultaneously.",
       "FEC: always on for audio; for video if bitrate headroom allows.",
     ],
     []),

    ("Group calls (SFU)",
     [
       "For > 2 participants, Vortex spawns an SFU (Selective Forwarding Unit) on the node. Each participant uploads once, SFU fans out.",
       "Currently audio-only up to 100 participants; video groups capped at 8 in v0.1 (video SFU hardening in v0.3 roadmap).",
       "SFU uses the same coturn relay for traversal; no additional services required.",
     ],
     []),

    ("Screen sharing",
     [
       "Via `getDisplayMedia`. Client adds a new track to the existing PeerConnection; renegotiates offer/answer.",
       "Recipients render the shared screen as a separate video track. On mobile, screen sharing requires OS-level permission — iOS prompts, Android shows a system dialog.",
     ],
     []),

    ("Jitter buffer and recovery",
     [
       "WebRTC's built-in NetEQ handles loss and jitter. On severe degradation the client drops resolution or disables video entirely while keeping audio alive.",
       "A 500 ms freeze triggers a reconnect attempt (ICE restart). Users see \"Reconnecting…\" overlay.",
     ],
     []),
)


FEDERATION = chapter(
    "Federation",
    "Trusted pubkeys, signed gossip, cross-node DMs.",
    "Federation lets users on node A message users on node B. It's opt-in per operator. Node pubkeys are explicitly trusted; there is no automatic \"any node can federate with mine\" mode.",

    ("Trust anchors",
     [
       "Each node maintains `federations(pubkey, endpoint, health_score, added_at, added_by)`.",
       "Adding a peer requires operator-signed admin action. The admin UI shows the remote's fingerprint so operators can verify out-of-band.",
       "Removed peers remain in DB marked `revoked_at` for audit. New federation requests from the same pubkey are rejected until an admin un-revokes.",
     ],
     []),

    ("Cross-node message routing",
     [
       "Outbound from A to user@B: node A wraps the message envelope in a signed blob and POSTs `/federation/deliver` on node B.",
       "Envelope: `{source_node, target_user, inner_ciphertext, inner_nonce, sent_at, sig}`. Sig covers everything except sig itself.",
       "Node B verifies signature against `source_node` pubkey from its `federations` table. Invalid sig → 401 + audit event.",
     ],
     []),

    ("Outbox / retry",
     [
       "If B is unreachable, A queues in `federation_outbox(target_node, payload, attempts, next_retry_at)`.",
       "Exponential backoff: 1s, 5s, 30s, 2min, 10min, 1h, capped at 6h. Permanent failure after 14 days.",
       "Operator alert fires when outbox depth > 1000 messages — indicates a stuck federation link.",
     ],
     []),

    ("Health monitoring",
     [
       "Every 60 s each node pings `GET /v1/health` on each peer. Response time + status tracked.",
       "Health score: initial 100. Each timeout subtracts 1; each success adds 1 (cap 100). Score 0 → federation paused for that peer.",
       "Published via `GET /v1/peers` for operator dashboards.",
     ],
     []),
)


GOSSIP = chapter(
    "Gossip and peer discovery",
    "How nodes find each other without a central registry.",
    "Beyond the controller's attested list, Vortex nodes gossip peers amongst themselves. This discovers new nodes as operators spin them up, even if the controller hasn't attested them yet.",

    ("Exchange protocol",
     [
       "Every 60 s, node picks a random peer and sends a 256-bit Bloom filter of known peers. Peer replies with the peers NOT in the filter, plus its own filter. Bandwidth is `O(new peers × 32 bytes)`, typically under 1 KiB per round.",
       "Each advertised peer is signed by the advertising node. Clients verify signatures on first contact — an attacker can't forge a peer into the gossip.",
       "The round is rate-limited: one exchange per peer per 30 s (sliding window).",
     ],
     []),

    ("Bootstrap",
     [
       "New nodes start with 8 hardcoded bootstrap controllers. First gossip round discovers dozens of peers; the network converges in ~1 minute.",
       "Bootstrap list is editable via `.env` `BOOTSTRAP_PEERS=pubkey1@endpoint1,pubkey2@endpoint2,...`.",
     ],
     []),

    ("Anti-Sybil",
     [
       "Each advertised peer must be signed by the operator's Ed25519 release key. Forging a peer announcement requires stealing a valid key.",
       "Proof-of-work (adjustable, default 2^18 leading zeros) on new peer registrations keeps bulk Sybil-bot waves impractical.",
       "Reputation system: peers that behave badly (bad signatures, forged announcements, repeated timeouts) have their reputation decay. Zero reputation → blacklist.",
     ],
     []),
)


STEALTH = chapter(
    "Stealth network",
    "Five layers, 28 mechanisms. Everything from TLS padding to Tor onion services.",
    "Vortex assumes a nation-state-grade adversary. The stealth stack is layered so even when the outer layers are bypassed, inner ones still provide degraded-but-working service.",

    ("Why five layers",
     [
       "Layer 1 — fingerprint normalisation. Stops passive classifiers.",
       "Layer 2 — shape / size morphing. Stops traffic-analysis classifiers.",
       "Layer 3 — protocol camouflage. Stops active DPI.",
       "Layer 4 — pluggable transports. Works in networks that block our primary.",
       "Layer 5 — last-resort fallback. Onion, BMP, multi-hop relay. Works when nothing else does.",
     ],
     []),

    ("Level 1 — Transport obfuscation",
     [
       "TLS 1.3 ClientHello matches Chrome on Windows 11 byte-for-byte. JA3/JA4 hash matches Chrome 120 — no Vortex-specific fingerprint.",
       "Record-layer padding: all TLS records padded to 16 KB. Packet sizes match bulk browser traffic.",
       "Constant-rate send: queue emits one frame every N ms regardless of application activity. Idle periods emit dummy frames marked in the inner envelope so recipients discard them.",
       "Timing jitter: 0-50 ms random delay on egress to defeat latency-based DPI.",
     ],
     []),

    ("Level 2 — Advanced stealth",
     [
       "YouTube-720p morpher: packet-size distribution, burst cadence, and silence gaps match a YouTube live stream. Classifiers looking for messenger heartbeats fail to match.",
       "Multipath: the same flow split over Wi-Fi, cellular, and any active VPN simultaneously. Reassembly at the receiver. Defeats single-path shaping.",
       "WebRTC data channel tunnel: when TLS is blocked but WebRTC works, Vortex tunnels through a DTLS-SRTP channel to a known peer.",
       "Decoy connections: 3 long-lived idle TLS sessions to Google, YouTube, and Cloudflare. Observer sees normal browser behaviour.",
     ],
     []),

    ("Level 3 — Protocol camouflage",
     [
       "DoH (RFC 8484): all DNS resolved via DoH to Cloudflare / Google / Quad9. ISP sees only HTTPS to those resolvers, not the actual domain list.",
       "ECH (Encrypted Client Hello): SNI encrypted with a key published in the DNS HTTPS record. Passive observers can't see the destination hostname.",
       "Probe detection: node tracks requests with no auth session. Three failed probes from an IP in 5 min trigger the \"decoy site\" mode — that IP now sees a plain HTML landing page with 200 OK.",
       "DGA (Domain Generation Algorithm): deterministic domain generator seeded with today's date. If primary endpoint is blocked, clients compute the next candidate and try.",
     ],
     []),

    ("Level 4 — Pluggable transports",
     [
       "vmess / vless / trojan / shadowtls: standard V2Ray-style transports with a pluggable JSON config.",
       "Reality: TLS-within-TLS tunnel. Outer handshake targets www.microsoft.com; inner handshake is Vortex. Probes against the outer get forwarded to Microsoft so active probing reveals nothing.",
       "Snowflake: volunteer browsers relay Vortex traffic over WebRTC. Users installing the Snowflake extension provide cover.",
       "NaiveProxy: modifies HTTPS probes to blend with Chromium's own behaviour down to the microsecond.",
     ],
     []),

    ("Level 5 — Last resort",
     [
       "Onion services: every node also exposes itself as `.onion`. Clients with Tor support fall through to this when everything else fails.",
       "Blind Mailbox Protocol (BMP): anonymous store-and-forward for messages. See BMP chapter.",
       "Multi-hop relay: messages can bounce through up to 5 intermediate nodes, each adding a layer of envelope. Like Tor but in our own mesh.",
       "OHTTP (RFC 9458): oblivious HTTP through a relay. No single party sees both request and response.",
     ],
     []),
)


BMP = chapter(
    "Blind Mailbox Protocol",
    "Anonymous store-and-forward for messages through the gossip mesh.",
    "BMP lets a sender deposit a message at any node without revealing identity. The message gossips until it reaches the recipient's home node, where it decrypts as usual.",

    ("Mechanism",
     [
       "Sender derives `mailbox_id = HKDF(recipient_pubkey, info: \"bmp-v1\", len: 32)`. Only sender (who knows recipient_pubkey) can compute it; recipient also knows.",
       "Sender posts `POST /bmp/deposit` with `{mailbox_id, blob}` to any gossiping node.",
       "Node stores pair for up to 7200 s. Node also includes the mailbox_id in next gossip round's Bloom filter.",
       "Other nodes pull blobs for mailbox_ids they locally care about (recipients on their node).",
       "Recipient's client polls `GET /bmp/messages` and decrypts any new blobs with its usual key material.",
     ],
     []),

    ("Security properties",
     [
       "No node can link a blob to a sender — the sender's TLS connection identifies the source IP, but a chain of onion hops between sender and first BMP node removes that too.",
       "Recipient-hiding: blob is encrypted with recipient's pubkey. Middle nodes see only an opaque byte string and a random mailbox_id.",
       "No delivery confirmation to sender. At-most-once semantics.",
     ],
     []),

    ("Limits",
     [
       "Max blob size: 1 MB. Larger payloads must be chunked through the ordinary file flow.",
       "Max storage per node: 500 MB of deposits in total. LRU eviction at cap. Operators can tune.",
       "Spam: per-IP deposit rate limited to 10 / min. Mailbox IDs observed more than 3 times / hour on one node are rate-limited as suspected flood.",
     ],
     []),

    ("Use cases",
     [
       "High-censorship recipients: sender doesn't need to know recipient's home node.",
       "Intermittent connectivity: blobs wait until recipient re-connects and polls.",
       "Anonymous whistleblowing: sender-side onion + BMP = no metadata on who deposited what.",
     ],
     []),
)


PUSH = chapter(
    "Push notifications",
    "APNs, FCM, Web Push — all with sealed envelopes so providers can't read.",
    "Standard push services (APNs, FCM, Web Push) see every payload. Vortex wraps each notification in a separate E2E layer so the provider sees only an opaque blob with no room id, sender, or text.",

    ("Registration",
     [
       "Client obtains a platform token (APNs device token, FCM registration id, or Web Push subscription JWT).",
       "Client generates a fresh 32-byte X25519 key `p256dh_pub` and a 16-byte `auth` secret. POSTs `/api/push/subscribe` with `{endpoint, p256dh, auth, platform}`.",
       "Node persists `push_subscriptions(user_id, endpoint, p256dh, auth, platform, created_at)`.",
     ],
     []),

    ("Sending",
     [
       "When a notification is due (new message in a muted room that's set to notify, mention, call invite), node encrypts the payload with AES-GCM using a key derived from `ECDH(p256dh_pub, ephemeral_priv)` via HKDF.",
       "Node packages `{endpoint, TTL, urgency, topic: <collapse_key>, data: <ciphertext>}` and sends to APNs / FCM / Web Push server.",
       "Provider sees only `data` (ciphertext) + `topic`. No plaintext leak.",
     ],
     []),

    ("Collapse keys",
     [
       "Per-room topic key: `room:<id>`. Multiple messages in the same room collapse to one notification at the OS level.",
       "Per-call topic: `call:<id>`. Answering or declining pulls the banner; new call invites to the same room replace the old one.",
     ],
     []),

    ("Decryption on receive",
     [
       "iOS: Notification Service Extension decrypts in the NSE process (separate from main app). Uses the same CryptoKit primitives.",
       "Android: FirebaseMessagingService decrypts in a background service. JobScheduler schedules actual UI update when app is foregrounded.",
       "Web: Service Worker decrypts in the SW context, posts a local notification via Web Notifications API.",
     ],
     []),

    ("Provider-specific quirks",
     [
       "APNs: requires provider token refreshed every 60 min. Token refresh is automated via Apple's `auth-team-id` + `auth-key-id` + p8 key file.",
       "FCM: legacy HTTP endpoint deprecated; we use the HTTP v1 endpoint with OAuth2 service account credentials. Rotation every 1 h.",
       "Web Push: VAPID keys (one keypair per node). TTL capped at 28 days by most browsers.",
     ],
     []),
)


CONTROLLER = chapter(
    "Controller service",
    "Integrity attestation, entry discovery, health monitoring.",
    "The controller is a separate Python process. Its attack surface is tiny (about a dozen routes) and its trust is pinned to a single Ed25519 public key baked into clients.",

    ("Endpoints",
     [
       "`GET /v1/integrity` — attestation result. Schema: `{status, signed_by, trusted_pubkey, version, built_at, matched, mismatched, missing, extra, message}`.",
       "`GET /v1/health` — liveness. Schema: `{status: \"ok\", version, pubkey, stats:{online, approved, total}}`.",
       "`GET /v1/entries` — entry URLs. Schema: `[{protocol: \"wss\"|\"https\", url}...]`.",
       "`GET /v1/mirrors` — mirror controllers (DNS + IPFS + .onion variants).",
       "`GET /v1/trusted_nodes` — known federated peers.",
       "`GET /v1/heartbeat/{pubkey}` — node liveness probe. Used by federated nodes to keep their registration fresh.",
       "`POST /v1/register` — a new node applies for trust. Requires admin approval unless `AUTO_APPROVE=true`.",
     ],
     []),

    ("Signing",
     [
       "Manifest file: `INTEGRITY.sig.json`. Contains per-file BLAKE3 hash + Ed25519 signature.",
       "Generation: `python -m vortex_controller.integrity.sign_tool`. Reads the release key from `keys/release.key`, walks tree, writes manifest.",
       "Verification: controller reads the manifest at startup and compares against disk. Startup fails loudly on mismatch.",
     ],
     []),

    ("Mirror deployment",
     [
       "Mirrors run the same controller code with the same release key copied over. Clients see identical `signed_by` across mirrors — one way to detect a fake mirror is to compare pubkeys.",
       "DNSLink / SNS / IPFS publish pointers to one of several mirrors. Clients try in priority order with timeouts.",
       "The `vortex.sol-mirror/` directory in this repo is a ready-to-go trycloudflare mirror for development.",
     ],
     []),
)


STORAGE = chapter(
    "Storage layer",
    "SQLite for dev, Postgres for prod, Alembic for migrations, GRDB/Room/IndexedDB on clients.",
    "Vortex's node storage is SQL. Switching between SQLite (dev) and Postgres (prod) is a DATABASE_URL change — no code forks.",

    ("Core tables",
     [
       "`users(id, username, password_hash, x25519_public_key, kyber_public_key?, display_name, avatar_url, phone, email, created_at, is_active)` — primary identity table.",
       "`user_devices(id, user_id, device_id, user_agent, last_seen_at, revoked_at)` — per-device session rows.",
       "`rooms(id, type, name, is_private, is_channel, is_dm, member_count, avatar_url, created_at, created_by, description)` — room table, one row per room.",
       "`room_members(room_id, user_id, role, joined_at, muted_until)` — membership + ACL.",
       "`messages(id, room_id, sender_id, ciphertext, nonce, sender_pseudo, sent_at, edited_at?, deleted_at?, reply_to?, thread_id?, kind)` — every message, indexed on `(room_id, id)`.",
       "`reactions(message_id, user_id, emoji, created_at)` — compound primary key `(message_id, user_id, emoji)`.",
       "`files(id, user_id, mime_type, size, sha256 /* actually BLAKE3 */, storage_path, uploaded_at)` — file metadata.",
       "`read_receipts(room_id, user_id, message_id, read_at)` — latest-read pointer per user per room.",
       "`presence(user_id, last_seen_at, is_typing_in_room_id?)` — ephemeral, Redis-backed in prod.",
       "`federations(pubkey, endpoint, health_score, added_at, added_by, revoked_at)` — peer list.",
       "`federation_outbox(id, target_node, payload, attempts, next_retry_at)` — outbound queue.",
       "`scheduled_messages(id, room_id, ciphertext, nonce, send_at, created_by, created_at, cancelled_at)`.",
       "`contacts(user_id, contact_user_id, nickname, added_at)` — address book.",
       "`saved_gifs(user_id, url, width, height, added_at)` — per-user GIF collection.",
       "`folders(user_id, id, name, room_ids, is_system, created_at)` — chat folders.",
       "`bot_installations(user_id, bot_id, installed_at)` — per-user bot installs.",
       "`sessions(jti, user_id, device_id, expires_at)` — refresh token registry.",
       "`push_subscriptions(user_id, endpoint, p256dh, auth, platform, created_at)` — push registration.",
     ],
     []),

    ("Migrations",
     [
       "Alembic in `alembic/versions/`. Linear history, one revision per release (sometimes a few per release).",
       "Dev mode: `create_all + ALTER TABLE fallback` for rapid iteration.",
       "Prod mode: `alembic upgrade head` before startup. Docker image runs it in the entrypoint.",
     ],
     []),

    ("Indexes",
     [
       "`messages(room_id, id DESC)` — primary index for paginated fetch.",
       "`messages(room_id, sent_at DESC)` — for time-based ordering on edit.",
       "`reactions(message_id)` — for aggregation on room open.",
       "`read_receipts(room_id, message_id)` — for `seen by N` lookups.",
       "`user_devices(user_id)` — for listing active devices.",
       "FTS virtual tables (FTS5 SQLite / tsvector Postgres) for full-text search.",
     ],
     []),

    ("Backups",
     [
       "`make db-backup` produces a timestamped archive. Encrypted at rest with operator key.",
       "Retention: daily for 14 days, weekly for 4 weeks, monthly for 12 months.",
       "Restoration: `make db-restore FILE=<path>`. Runs on a staging DB first; operator verifies then swaps.",
     ],
     []),
)


# ── lots more chapters (shortened but each substantial) ───────────────

BOTS = chapter(
    "Bot framework",
    "Gravitix DSL + Python SDK + marketplace + antispam.",
    "Bots are first-class room participants. Messages are signed with a bot's Ed25519 key so forgeries are detectable.",

    ("Writing a bot",
     ["Two options: Python SDK or Gravitix DSL. Python is for complex workflows; Gravitix for event-driven chat bots that need to ship quickly.",
      "Python example: `from vortex_bot import Bot\\nbot = Bot(token=...)\\n@bot.on_message\\nasync def echo(msg): await bot.send(msg.room_id, msg.text)\\nbot.run()`. The SDK handles WebSocket, reconnection, encryption key exchange.",
      "Gravitix example: `on /start { emit \"Hello, {ctx.first_name}!\" }`. Compiles to bytecode and runs in a sandboxed interpreter.",
      "Bot token is issued at bot creation. Lost token? `POST /api/bots/{id}/rotate-token` issues a new one.",
     ], []),

    ("Deployment",
     ["Two deployment models: in-process (coroutine inside the node) and external (bot polls `/api/bots/{id}/updates`).",
      "In-process: zero network hop, fastest, but operator must trust bot code. Good for own bots.",
      "External: webhook or long-poll. No node-level trust needed. Good for third-party bots and the marketplace.",
      "Gravitix bots always run in-process in the sandbox — they have no filesystem or network access except explicit API.",
     ], []),

    ("Marketplace",
     ["Public bots can submit to the marketplace. Reviewers verify code doesn't phish, doesn't spam, doesn't leak user data.",
      "Categories: productivity, games, news, utilities, ai, translation.",
      "Install: one click. Node subscribes the user to the bot's username so DMs route correctly.",
      "Monetization: free, one-time purchase, subscription. Platform fee 10 %% of gross.",
     ], []),

    ("Antispam bot",
     ["Every room is monitored by an invisible antispam bot. Checks: link density > 3 per minute, capital-letter ratio > 70 %% for 10+ chars, repeat messages, sudden burst of new-account joiners.",
      "Actions: warn → timeout (5 min) → kick → ban. Appeals go to room admin.",
      "Tuneable per-room via bot config.",
     ], []),
)


OPS = chapter(
    "Operations",
    "Deploy, monitor, rollback.",
    "Every operational task has a `make` target or a CLI command. Ops pages live in `deploy/`.",

    ("Docker compose",
     ["`docker compose up` brings up node, controller, Postgres, Redis, coturn, Caddy.",
      "Volumes: `/data/vortex.db`, `/data/uploads`, `/data/logs`. Mount to host for persistence.",
      "Environment: `.env` in repo root. Never commit. `.env.example` is the template.",
      "Caddy auto-fetches Let's Encrypt certs. Let's Encrypt rate limits apply — use staging for experiments.",
     ], []),

    ("Make targets",
     ["`make install` — install Python deps + dev tools.",
      "`make dev` — uvicorn with reload on port 9000.",
      "`make test` — pytest + coverage; produces `coverage.xml`.",
      "`make lint` — ruff + mypy. CI blocks on failures.",
      "`make docker-build` — build image tagged `vortex:<VERSION>`.",
      "`make db-migrate` — `alembic upgrade head`.",
      "`make db-backup` / `make db-restore FILE=...`.",
      "`make ci` — run the full CI pipeline locally.",
     ], []),

    ("Wizard",
     ["`Vortex Wizard.app` is a PyInstaller bundle with a pywebview GUI.",
      "First-run flow: choose node name → generate release keys → configure TLS (Let's Encrypt / bring-your-own / self-signed) → pick entry URLs → enable stealth → open firewall ports.",
      "After setup, wizard stays as the admin console: start/stop node, view logs, rotate keys, add federated peers.",
     ], []),

    ("Rollbacks",
     ["Every release tagged in git. Tag also signed with release key so the tag itself is verifiable.",
      "Rollback: `git checkout <tag> && make docker-build && docker compose up -d`. Running nodes drain and restart.",
      "DB: Alembic `downgrade <rev>` supported for one minor version back. Further back requires manual intervention.",
     ], []),
)


MOBILE = chapter(
    "Mobile clients",
    "iOS and Android — native UI, same protocol.",
    "Both mobile clients are full peers, not thin web wrappers. Native look, native performance, native integrations (CallKit, ConnectionService, Lock Screen widgets).",

    ("iOS structure",
     ["Swift Package in `ios/Modules/`. 30+ feature modules, each SOLID-split `api/` + `impl/` + `ui/`.",
      "App target in `ios/VortexApp/`. XcodeGen spec at `ios/project.yml` regenerates the xcodeproj.",
      "Crypto: CryptoKit (X25519, Ed25519, AES-GCM, HKDF) + Argon2Swift (Argon2id).",
      "DB: GRDB + FTS5. All mutations go through `db.write`.",
      "WebRTC: stasel/WebRTC XCFramework.",
      "Push: APNs via `UNUserNotificationCenter` + Notification Service Extension for decryption.",
     ], []),

    ("Android structure",
     ["Gradle project in `android/`. 22 feature modules with Hilt DI, same `api / impl / di / ui` split.",
      "minSdk 26, targetSdk 34.",
      "Crypto: AndroidX security + Tink + `argon2-jvm`.",
      "DB: Room with FTS4 triggers.",
      "WebRTC: Stream WebRTC.",
      "Push: FCM + FirebaseMessagingService decryption.",
     ], []),

    ("Cross-platform features",
     ["Same 146-locale bundle with native names (`Русский ru`, `English en`, `中文 zh`, …).",
      "Same 1500-emoji catalog with 9 categories + skin-tones + MRU + search.",
      "Same multi-account X25519 challenge-response for switching.",
      "Same chat folders (All / Archived / custom) with drag-and-drop reordering.",
      "Same saved-GIFs list (no Tenor — personal collection only).",
      "Same scheduled-messages UI, contacts screen, premium status page.",
     ], []),
)


WEB_CLIENT = chapter(
    "Web client",
    "PWA, vanilla JS, offline mode, service worker.",
    "Web client is a vanilla-JS PWA. No React, no bundler beyond ESM. ~400 KB gzipped total, including 146 locales.",

    ("Structure",
     ["`static/js/main.js` is the entry. Feature modules lazy-load on first use.",
      "State: per-room ring buffers in IndexedDB, in-memory decrypted cache. Service Worker mediates fetch.",
      "UI: Liquid Glass effects via CSS backdrop-filter. No framework; event delegation + idempotent render helpers.",
     ], []),

    ("Offline mode",
     ["Any write made while offline queues to IndexedDB. SW flushes when connection returns.",
      "Idempotency key on every POST lets duplicate retries succeed safely.",
      "Reading works fully offline — all synced ciphertext lives in IndexedDB.",
     ], []),

    ("i18n",
     ["146 locales in `static/locales/*.json`. Welcome screen (`lang-picker.js`) cycles through native-name hints.",
      "Runtime locale switch: `document.documentElement.lang = code` + re-render labels via `data-i18n` attributes.",
     ], []),
)


SECURITY = chapter(
    "Security posture",
    "Threat model, defence-in-depth, WAF, audit trail, canary.",
    "Vortex uses defence-in-depth: breaking one layer isn't enough, a realistic attacker needs multiple independent wins.",

    ("Threat model",
     [
       "**Passive network observer**: sees TLS packets; does size/timing analysis. Defeated by Level 1 stealth.",
       "**Active network attacker**: can drop/delay/inject. Defeated by Level 2-4 stealth.",
       "**Compromised node operator**: sees ciphertext + metadata. Message content remains confidential.",
       "**Stolen client device**: plaintext of past messages exposed. Double Ratchet limits to current session; wipe-on-next-unlock available.",
       "**Quantum adversary with stored past traffic**: defeated by hybrid Kyber-768 session keys when both peers advertised PQ.",
     ],
     []),

    ("WAF",
     [
       "Request inspector: SQLi patterns, path traversal, template injection, LFI, NoSQLi. Drops before app code.",
       "Rate limits: global 1000 req/s soft cap with burst; per-route (login 10/min, register 5/min); per-user 100 req/s after auth.",
       "Geo-blocking optional via `GEO_BLOCK=RU,CN`.",
     ],
     []),

    ("Audit trail",
     [
       "Security-relevant events (admin action, federation change, release upgrade, panic wipe) hash-chained via `app/security/canary.py`.",
       "Chain break ⇒ tampering detected. Alert fires.",
       "`/api/admin/audit` exposes the log (admin auth only). Append-only.",
     ],
     []),

    ("Incident response",
     ["Canary file signed daily with release key. Absence ⇒ compromise suspected.",
      "Emergency revocation: admin broadcasts `{type:\"n\", event:\"compromise\", ...}` to every WebSocket. Clients wipe cached keys.",
      "Rotation: new release key, re-sign manifest, re-publish. Clients re-bootstrap.",
     ], []),
)


PRIVACY_CHAPTER = chapter(
    "Privacy and compliance",
    "GDPR, right-to-erasure, metadata minimisation, data portability.",
    "Vortex ships GDPR and CCPA tooling out of the box. Operators in regulated jurisdictions have a single admin endpoint for every statutory request.",

    ("Metadata minimisation",
     ["No IP logs by default. Reverse proxy strips `X-Real-IP` unless operator opts in.",
      "`sender_pseudo` in message rows hashes real sender IDs — a DB dump reveals only per-room pseudonyms.",
      "Search uses encrypted-tokens. Client encrypts keywords with room key; node stores opaque tokens; lookup is exact-match on ciphertext tokens.",
      "Last-seen truncated to user's chosen granularity.",
     ], []),

    ("Right to erasure",
     ["`POST /api/privacy/erase` anonymises the user row, wipes their sent messages (metadata retained for quorum), deletes files from disk.",
      "Federation: signed gossip informs peers; they erase on their side within 72 h.",
      "Audit: erasure is logged with the timestamp and (hashed) user id so operator can prove compliance.",
     ], []),

    ("Data export",
     ["`GET /api/privacy/export` streams a zip: profile JSON, sent/received ciphertext, file references with per-file root keys, contact list.",
      "Generation time: ~5 min for 10 k messages, bounded by IO.",
      "Recipient must decrypt ciphertext locally; export tooling is shipped alongside.",
     ], []),

    ("Panic wipe",
     ["Long-press logo 5 s → immediate local wipe: keys, cached messages, attachments.",
      "Coupled wipe: `/api/privacy/panic` also tombstones the server-side account.",
     ], []),
)


DEBUGGING = chapter(
    "Debugging and diagnostics",
    "Tools for tracking down issues in dev, staging, and prod.",
    "Every subsystem has structured logging and a /metrics surface. Here's the usual diagnosis playbook.",

    ("Logs",
     ["JSON-structured by default. `logger.info(\"action\", extra={\"user_id\": ...})` produces `{\"ts\":..., \"lvl\":\"INFO\", \"msg\":\"action\", \"user_id\": ...}`.",
      "Rotate at 100 MB; keep 14 gens gzipped.",
      "Level per-module via `LOG_LEVEL_<MODULE>=DEBUG` (e.g. `LOG_LEVEL_TRANSPORT=DEBUG`).",
      "Correlation id: every request gets an `X-Request-Id`; downstream RPCs reuse it.",
     ], []),

    ("Metrics",
     ["Prometheus format at `/metrics` (admin-authenticated in prod).",
      "RED: rate / errors / duration per route.",
      "USE: utilisation / saturation / errors per DB pool, WebSocket fan-out, TURN relay.",
      "Custom: active rooms, messages/s, stealth-level histogram.",
     ], []),

    ("Profiling",
     ["`py-spy` for runtime sampling. Attach to the running node PID.",
      "`memray` for heap profiling. 1-minute snapshot reveals leaks quickly.",
      "Rust extension `vortex_chat` exports `--profile` flag that writes a flamegraph-compatible trace.",
     ], []),

    ("Smoke tests",
     ["`scripts/smoke/all.sh` runs register/login/send/receive/logout against a local node. Exits non-zero on any failure.",
      "CI runs smoke on every PR as well as on merges to main.",
      "Production smoke: external probe hitting a canary account once per minute.",
     ], []),
)


TESTING = chapter(
    "Testing strategy",
    "29 k lines of tests across Python, Swift, Kotlin, JS.",
    "Every layer has its own test suite. CI runs all of them in under 10 minutes.",

    ("Python",
     ["`pytest app/tests` covers routers, security, transport, bots.",
      "Hypothesis property-based tests on crypto: `assert decrypt(encrypt(m, k), k) == m` for 1000 random m.",
      "AFL-style fuzz on WAF: millions of malformed inputs — asserts no 5xx leaks.",
     ], []),

    ("Swift",
     ["`swift test` in `ios/Modules/` runs unit tests against RFC 7748 / 8032 / 5869 / 8446 test vectors.",
      "XCUI tests drive SwiftUI views in a headless simulator; snapshot-compared.",
     ], []),

    ("Kotlin",
     ["`./gradlew test` runs JVM-only tests (fast).",
      "`./gradlew connectedCheck` runs instrumented tests on a running emulator.",
     ], []),

    ("E2E",
     ["Playwright drives the web client, headless Chrome + headless Firefox. Calls are exercised with `--use-fake-ui-for-media-stream`.",
      "Scenarios: register two accounts → DM → send file → delete → verify sync → end.",
     ], []),
)


API_SURFACE = chapter(
    "API surface",
    "Every public HTTP route with verb, auth requirement, and purpose.",
    "Complete listing. Paths relative to node base URL. Auth column: `none` (pre-auth), `jwt` (Bearer access token), `refresh` (Bearer refresh token), `admin` (admin JWT).",

    ("Authentication",
     [
       "`POST /api/authentication/register` — none — create account.",
       "`POST /api/authentication/login` — none — password login.",
       "`POST /api/authentication/login/2fa` — partial-auth — TOTP step.",
       "`POST /api/authentication/refresh` — refresh — mint new access token.",
       "`POST /api/authentication/logout` — jwt — revoke current device.",
       "`GET /api/authentication/devices` — jwt — list active devices.",
       "`POST /api/authentication/devices/{id}/revoke` — jwt — revoke specific device.",
       "`POST /api/authentication/password-change` — jwt — rotate password.",
       "`POST /api/authentication/password-reset` — none — email reset flow.",
       "`POST /api/authentication/avatar` — jwt — multipart photo upload.",
       "`POST /api/authentication/2fa/setup` — jwt — start TOTP enrolment.",
       "`POST /api/authentication/2fa/verify` — jwt — finish TOTP enrolment.",
       "`DELETE /api/authentication/2fa` — jwt — disable TOTP.",
       "`GET /api/authentication/profile` — jwt — full profile.",
       "`PATCH /api/authentication/profile` — jwt — edit profile fields.",
       "`POST /api/authentication/challenge` — none — X25519 challenge issue (multi-account switching).",
       "`POST /api/authentication/challenge/verify` — none — complete challenge.",
       "`POST /api/authentication/passkey/begin` — none — passkey challenge.",
       "`POST /api/authentication/passkey/finish` — none — passkey complete.",
       "`POST /api/authentication/qr/begin` — jwt — issue QR pairing nonce.",
       "`POST /api/authentication/qr/verify` — none — accept QR on new device.",
     ],
     []),

    ("Rooms",
     [
       "`GET /api/rooms` — jwt — list user's rooms.",
       "`POST /api/rooms` — jwt — create room.",
       "`GET /api/rooms/{id}` — jwt — room metadata.",
       "`PATCH /api/rooms/{id}` — jwt (admin) — edit metadata.",
       "`DELETE /api/rooms/{id}` — jwt (owner) — delete.",
       "`GET /api/rooms/{id}/members` — jwt — member list.",
       "`POST /api/rooms/{id}/invite` — jwt (admin) — create invite code.",
       "`POST /api/rooms/join` — jwt — join via code.",
       "`POST /api/rooms/{id}/leave` — jwt — leave.",
       "`POST /api/rooms/{id}/avatar` — jwt (admin) — upload avatar.",
       "`GET /api/rooms/{id}/messages?since=&limit=` — jwt — paginated fetch.",
       "`POST /api/rooms/{id}/messages` — jwt — send message.",
       "`POST /api/rooms/{id}/read` — jwt — mark read.",
       "`PUT /api/rooms/{id}/draft` — jwt — save draft.",
       "`GET /api/rooms/{id}/draft` — jwt — fetch draft.",
       "`DELETE /api/rooms/{id}/draft` — jwt — clear draft.",
       "`POST /api/rooms/{id}/pin` — jwt (admin) — pin message.",
       "`DELETE /api/rooms/{id}/pin/{message_id}` — jwt (admin) — unpin.",
     ],
     []),

    ("Messages",
     [
       "`PATCH /api/messages/{id}` — jwt — edit own message.",
       "`DELETE /api/messages/{id}` — jwt — delete own (or admin any).",
       "`POST /api/messages/{id}/react` — jwt — add reaction.",
       "`DELETE /api/messages/{id}/react/{emoji}` — jwt — remove reaction.",
       "`POST /api/messages/{id}/thread` — jwt — create thread.",
       "`GET /api/messages/{id}/context` — jwt — surrounding messages.",
     ],
     []),

    ("Files",
     [
       "`POST /api/files` — jwt — single-shot upload.",
       "`POST /api/files/resumable/init` — jwt — start resumable.",
       "`PUT /api/files/resumable/{id}/chunk/{offset}` — jwt — send chunk.",
       "`POST /api/files/resumable/{id}/finalise` — jwt — finish.",
       "`GET /api/files/{id}` — jwt — download.",
       "`GET /api/files/{id}/thumb` — jwt — thumbnail.",
     ],
     []),

    ("Calls",
     [
       "`POST /api/calls/{room_id}/start` — jwt — initiate call.",
       "`POST /api/calls/{call_id}/accept` — jwt — accept.",
       "`POST /api/calls/{call_id}/end` — jwt — hang up.",
       "`POST /api/calls/{call_id}/signal` — jwt — forward offer/answer/candidate.",
       "`GET /api/calls/{call_id}/turn` — jwt — get short-lived TURN creds.",
     ],
     []),

    ("Push",
     [
       "`POST /api/push/subscribe` — jwt — register device for push.",
       "`POST /api/push/unsubscribe` — jwt — unregister.",
     ],
     []),

    ("Federation",
     [
       "`GET /federation/info` — none — node pubkey + capabilities.",
       "`POST /federation/deliver` — peer-signed — inbound cross-node envelope.",
     ],
     []),

    ("Admin",
     [
       "`GET /api/admin/metrics` — admin — Prometheus metrics.",
       "`GET /api/admin/audit` — admin — audit log.",
       "`POST /api/admin/peers` — admin — add trusted peer.",
       "`DELETE /api/admin/peers/{pubkey}` — admin — remove peer.",
       "`POST /api/admin/user/{id}/suspend` — admin — suspend account.",
       "`POST /api/admin/user/{id}/unsuspend` — admin — re-enable.",
     ],
     []),

    ("BMP",
     [
       "`POST /bmp/deposit` — none — deposit blob.",
       "`GET /bmp/messages` — jwt — pull blobs addressed to user's mailbox.",
     ],
     []),
)


ROADMAP = chapter(
    "Roadmap",
    "What's planned and when.",
    "High-level view. Dates are aspirational; security issues pre-empt feature work.",

    ("v0.2 — second public release",
     ["Kyber-768 PQ enabled by default on fresh installs.",
      "Groups up to 50 000 members with Variant-B key publish.",
      "Desktop (Tauri) packaging for macOS / Windows / Linux.",
      "Bot marketplace opens to public submissions.",
     ], []),

    ("v0.3 — group calls",
     ["Audio-only group calls up to 100 participants via SFU.",
      "Opus DTX + simulcast + adaptive bitrate.",
      "Per-participant mute / kick in the call UI.",
     ], []),

    ("v0.4 — shared whiteboard",
     ["Miro-style collaborative canvas over CRDT (Yjs-flavoured) through the messaging layer.",
      "Real-time cursor presence.",
      "Export to PNG / SVG / PDF.",
     ], []),

    ("v0.5 — payments",
     ["On-chain escrow for bot purchases (Solana + EVM).",
      "Operator revenue share, 10 %% platform fee.",
      "Fiat on/off ramp via Stripe connect.",
     ], []),

    ("v1.0 — stable",
     ["Above stabilised, formal security audit, reproducible builds, SemVer frozen.",
      "Bug bounty program live.",
      "At least one independent security review with public write-up.",
     ], []),
)


GLOSSARY_CHAPTER = {
    "title": "Glossary",
    "subtitle": "Terms you'll see across the docs.",
    "intro": "Alphabetical reference.",
    **glossary(
        ("AES-GCM",
         "Authenticated encryption mode. 256-bit key, 96-bit nonce, 128-bit tag."),
        ("Alembic",
         "Database migration tool for SQLAlchemy. Linear revision history."),
        ("APNs",
         "Apple Push Notification service. Used for iOS push."),
        ("Argon2id",
         "Memory-hard password hash. Vortex params: m=64MiB, t=3, p=4."),
        ("AAD",
         "Additional Authenticated Data. In AES-GCM, data included in the tag but not encrypted."),
        ("BLAKE3",
         "Fast cryptographic hash. Vortex uses it for file integrity; column is still named sha256 for migration compatibility."),
        ("BMP",
         "Blind Mailbox Protocol. Store-and-forward through the gossip mesh."),
        ("Canary",
         "Signed daily file proving the release key still controls the deployment."),
        ("CBOR",
         "Concise Binary Object Representation. RFC 8949. Encoding used for E2E message payloads."),
        ("Controller",
         "Vortex's separate attestation process. Publishes `/v1/integrity` and entry URLs."),
        ("Double Ratchet",
         "Signal's per-session forward-secrecy protocol."),
        ("DGA",
         "Domain Generation Algorithm. Deterministic fallback domain generator."),
        ("ECH",
         "Encrypted Client Hello. Hides SNI on TLS 1.3."),
        ("Ed25519",
         "EdDSA signature scheme over edwards25519. 32-byte pubkey, 64-byte signature."),
        ("Envelope",
         "The wrapper around ciphertext carrying nonce + metadata."),
        ("FCM",
         "Firebase Cloud Messaging. Used for Android push."),
        ("Federation",
         "Nodes trusting each other to deliver messages to users on other nodes."),
        ("FTS5",
         "SQLite's full-text search virtual table."),
        ("Gossip",
         "Periodic peer-list exchange between nodes."),
        ("Gravitix",
         "Vortex's domain-specific language for writing bots."),
        ("HKDF",
         "HMAC-based Key Derivation Function. RFC 5869. SHA-256 variant used."),
        ("HMAC",
         "Hash-based Message Authentication Code. RFC 2104."),
        ("ICE",
         "Interactive Connectivity Establishment. WebRTC's NAT traversal."),
        ("JWT",
         "JSON Web Token. Vortex uses HS256-signed JWTs for session auth."),
        ("Kyber-768",
         "ML-KEM-768 post-quantum KEM. FIPS 203."),
        ("Mailbox",
         "A recipient's inbox for BMP blobs. ID derived from recipient's pubkey."),
        ("Nonce",
         "Number used once. 96-bit random value for AES-GCM."),
        ("Node",
         "A Python process running the Vortex back-end. Stores ciphertext + fans out events."),
        ("OHTTP",
         "Oblivious HTTP. RFC 9458. Relay-assisted anonymous HTTP."),
        ("Onion service",
         "Tor hidden service. Every Vortex node exposes itself as .onion."),
        ("Prekey",
         "Ephemeral pubkey published ahead of time to bootstrap new DMs."),
        ("Ratchet",
         "One step in the Double Ratchet chain. Each message ratchets forward."),
        ("Reality",
         "Stealth transport that masquerades as a real big-tech site."),
        ("Room key",
         "32-byte symmetric key shared among room members. Rotated on membership change."),
        ("Sealed push",
         "Push payload encrypted so the provider (Apple/Google) can't read it."),
        ("SFU",
         "Selective Forwarding Unit. Mixes media in group calls."),
        ("Snowflake",
         "Tor transport using volunteer browsers as WebRTC relays."),
        ("TLS 1.3",
         "RFC 8446. Transport used by every HTTPS and WSS connection."),
        ("TOTP",
         "RFC 6238. Time-based one-time password for 2FA."),
        ("TURN",
         "Traversal Using Relays around NAT. Coturn handles it in Vortex."),
        ("VAPID",
         "RFC 8292. Voluntary Application Server Identification for Web Push."),
        ("WAF",
         "Web Application Firewall. Vortex ships a built-in one."),
        ("X25519",
         "Elliptic-curve Diffie-Hellman over Curve25519. RFC 7748."),
    ),
}


VORTEX_DOCS = {
    "meta": {
        "title": "Vortex Reference",
        "subtitle": "Every subsystem of Vortex in one place.",
        "intro": "This reference is exhaustive by design. Start anywhere — each chapter is self-contained. Every statement links back to source paths when relevant. Every invariant is called out explicitly.",
        "howToUse": "The table of contents on the left mirrors the chapters here. Click a chapter to jump to it; each chapter has sub-headings and lists you can scan in 30 seconds before diving in.",
        "updatedBy": "Generated from `scripts/build_vortex_docs_v2.py`. Rebuild with `python3 scripts/build_vortex_docs_v2.py`.",
    },
    "architecture":  ARCHITECTURE,
    "crypto":        CRYPTO,
    "cryptoWire":    CRYPTO_WIRE,
    "auth":          AUTH,
    "rooms":         ROOMS,
    "files":         FILES,
    "presence":      PRESENCE,
    "calls":         CALLS,
    "federation":    FEDERATION,
    "gossip":        GOSSIP,
    "stealth":       STEALTH,
    "bmp":           BMP,
    "push":          PUSH,
    "controller":    CONTROLLER,
    "storage":       STORAGE,
    "bots":          BOTS,
    "ops":           OPS,
    "mobile":        MOBILE,
    "webclient":     WEB_CLIENT,
    "security":      SECURITY,
    "privacy":       PRIVACY_CHAPTER,
    "debugging":     DEBUGGING,
    "testing":       TESTING,
    "apiSurface":    API_SURFACE,
    "roadmap":       ROADMAP,
    "glossary":      GLOSSARY_CHAPTER,
}


def target_paths():
    root = Path("/Users/borismaltsev/RustroverProjects")
    yield root / "Vortex/ios/Modules/Sources/I18N/Resources/locales/en.json"
    yield from sorted((root / "vortex-introduce-page/locales").glob("*.json"))


def splice():
    for p in target_paths():
        if not p.exists():
            continue
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        data["vortexDocs"] = VORTEX_DOCS
        with p.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"wrote {p}")


if __name__ == "__main__":
    splice()
