#!/usr/bin/env python3
"""
Build the exhaustive `vortexDocs` i18n block.

Produces a large JSON dictionary covering every subsystem of the Vortex
project: authentication, cryptography, transport, storage, federation,
bots, WebRTC calls, push, stealth network, operations. Writes the same
English content into every locale (the `architexDocs` sibling already
demonstrated that flow).

Structure: `vortexDocs.<section>.<item>` — section-level `title` and
`subtitle` live alongside numbered keys `h1`, `h2`, `h3` for inline
sub-headings and `p1…pN` for paragraphs. Lists use `li1…liN`, tables
use `td…` triplets (label/value/hint). Inspired by the existing `gxd`
structure in `vortex-introduce-page` so rendering stays consistent.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


# ── helpers ───────────────────────────────────────────────────────────

def section(title: str, subtitle: str, **items: str) -> dict:
    """Return {title, subtitle, **items} dict in a stable order."""
    out = {"title": title, "subtitle": subtitle}
    for k, v in items.items():
        out[k] = v
    return out


def paragraphs(*texts: str) -> dict:
    """Build {p1: "...", p2: "..."} from positional args."""
    return {f"p{i+1}": t for i, t in enumerate(texts)}


def list_items(*items: str) -> dict:
    return {f"li{i+1}": t for i, t in enumerate(items)}


# ── big sections ──────────────────────────────────────────────────────

ARCH = section(
    "Architecture overview",
    "Three processes, one protocol: client + node + controller.",
    intro="Vortex is a decentralised messenger that replaces the single back-end of classic apps with a mesh of independent nodes discovered through a verifiable controller. Each part has a narrow job: the controller attests which code is running, each node runs chat rooms and stores messages, each client holds keys and renders UI.",
    h1="The three processes",
    p1="The **client** is the app on your phone, browser, or desktop. It generates keys, encrypts messages, renders screens, and talks to a node through HTTPS and WebSockets. All plaintext stays here.",
    p2="A **node** is a Python process running `python -m app.main`. It stores encrypted ciphertext, fans out WebSocket events, records reactions and reads, serves files, and brokers WebRTC signalling. A node never holds plaintext; without the recipient's device key the ciphertext is opaque even to the operator.",
    p3="The **controller** is a separate Python process (`vortex_controller`) that publishes the signed manifest of all running node code. Clients hit `/v1/integrity` before trusting a node. If the file hashes don't match the signed manifest, the controller returns `status:\"mismatched\"` and the client refuses to connect.",
    h2="Why split node and controller",
    p4="Because the controller is a single pubkey. Clients pin that pubkey at release time, and the controller attests any new node it signs in. This lets volunteer operators run nodes without every release having to reship a hard-coded list. It also stops an attacker who compromises one node from also forging release signatures.",
    p5="The controller's storage is tiny (a SQLite file that lists trusted pubkeys and their health). Operators can easily back it up and mirror it — which is why we ship a dedicated `vortex_controller` package instead of bolting the endpoint onto the node.",
    h3="Transport layer",
    p6="Between the three processes, every wire hop is end-to-end encrypted either with TLS 1.3 (HTTPS / WSS) or, inside the E2E-crypto layer, with AES-256-GCM over an X25519 key-agreement result. For advanced adversaries, the transport layer has five stealth modes (domain fronting, meek, Snowflake, Reality/Trojan, WebRTC data channel) that live under the stable `/api/*` surface.",
    h4="Data flow for a single message",
    p7="Alice types a message. The client asks `Keys` for the current room key (deriving it via X25519+HKDF-SHA256 from her static key and the group's shared secret). The plaintext is framed as `{v:1, text:..., reply_to:...}`, encoded to CBOR, sealed with AES-256-GCM using a random 96-bit nonce, and posted as `{ciphertext: <hex>, nonce: <hex>, sender_pseudo: <short>}` to `/api/rooms/{id}/messages`. The node persists the ciphertext and broadcasts `{type:\"m\", room:..., msg:{...}}` over every connected WebSocket. Bob's client fetches the same room key, decrypts, renders the bubble.",
    h5="Why CBOR",
    p8="CBOR (RFC 8949) is strict, has no ambiguous whitespace, and produces compact binary payloads that survive a round-trip through any language. Plain JSON would need escaping and doubles the byte count on unicode-heavy chat; protobuf would pin us to a schema generator and make field evolution painful. CBOR splits the difference and matches what Signal and Matrix use on the wire.",
)


CRYPTO = section(
    "Cryptography primitives",
    "Every algorithm, its job, and why Vortex picked it.",
    intro="Vortex leans entirely on peer-reviewed primitives. No custom block ciphers, no \"we rolled our own\". The stack below is identical to Signal's, plus a post-quantum envelope from the NIST final round.",
    x25519_name="X25519",
    x25519_rfc="RFC 7748 (the core curve) + RFC 8418 (pairing for key agreement).",
    x25519_use="Static device keys (identity) and ephemeral session keys (forward secrecy).",
    x25519_why="Fast (≈ 100 µs on an iPhone 11), constant-time, and tiny — 32-byte keys, no Kangaroo discrete-log ambiguity. Being Montgomery form, it protects against the class of side-channels that plagued earlier curves.",
    x25519_impl="iOS uses CryptoKit's `Curve25519.KeyAgreement`, Android uses the `x25519-dalek` binding in Rust, the node uses `cryptography` (which wraps OpenSSL). All three interop bit-for-bit.",
    ed25519_name="Ed25519",
    ed25519_rfc="RFC 8032 (EdDSA).",
    ed25519_use="Signing: every message a node emits (integrity attestations, federation announcements) is Ed25519-signed with the node's static key. Clients sign profile changes and bot deploys.",
    ed25519_why="Deterministic, small signatures (64 bytes), hashing derived from the message so nonce-misuse is impossible. Apple's `Curve25519.Signing` uses randomised RFC 8032bis, which is also fine — the verifier doesn't care.",
    aes_name="AES-256-GCM",
    aes_rfc="NIST SP 800-38D.",
    aes_use="Symmetric envelope for every message, every attached file (per-chunk), every encrypted backup blob.",
    aes_why="Hardware accelerated on every modern CPU (AES-NI, ARMv8-A crypto extensions), wide industry adoption, tagged. 96-bit nonce means one room key can safely encrypt up to 2^32 messages — far more than any single room will ever see.",
    aes_nonce="Nonces are per-message random 96-bit values. Re-using a nonce with the same key breaks confidentiality and authenticity; we track the last 10^6 nonces per room and drop duplicates at the node, even though the client is required to avoid generating duplicates in the first place.",
    hkdf_name="HKDF-SHA256",
    hkdf_rfc="RFC 5869.",
    hkdf_use="Deriving multiple sub-keys (encryption key, MAC key, header-encryption key) from a single master X25519 output.",
    hkdf_why="Well-understood, covered by NIST, fast, and supported everywhere. 256-bit output is the ceiling we need.",
    argon_name="Argon2id",
    argon_rfc="RFC 9106.",
    argon_use="Hashing the user's password at the node, and deriving the key for any local encrypted backup.",
    argon_params="Cost params: `m=64 MiB`, `t=3 iterations`, `p=4 lanes`, `hashLen=32`. We verified these numbers against the OWASP 2023 recommendations and benchmarked them on the slowest device we support (iPhone X). One hash takes ~0.5 s — acceptable for login, too expensive for a brute-forcer at scale.",
    argon_why="Memory-hard, meaning ASIC and GPU attackers lose their typical 1000× speedup over a general-purpose CPU. Won the 2015 password hashing competition for this exact reason.",
    kyber_name="Kyber-768 (ML-KEM)",
    kyber_rfc="FIPS 203 (2024).",
    kyber_use="Optional post-quantum envelope. When both sides advertise Kyber support, the session key is derived via hybrid KEM: `session = HKDF(x25519_output || kyber_output)`.",
    kyber_why="NIST's selected PQ KEM. Adding it is cheap (≈ 1 ms per session), futures-proofing conversations against a harvest-now-decrypt-later adversary with a CRQC.",
    kyber_impl="`pqcrypto.kem.ml_kem_768` on the node side, `liboqs` on the client side. Shared secret is 32 bytes, matches HKDF input length exactly.",
    rachet_name="Double Ratchet",
    rachet_rfc="Signal Foundation spec (2016).",
    rachet_use="Per-DM session key evolution: each sent message advances the sending chain, each received message advances the receiving chain. Compromise of a single key only exposes the messages it directly encrypted.",
    rachet_why="Forward secrecy (past messages stay safe if a device is stolen) and post-compromise security (future messages recover from a compromise once both sides ratchet again).",
)


AUTH = section(
    "Authentication",
    "Register, login, refresh, logout — and what happens underneath.",
    intro="Vortex issues short-lived JWTs (15 min access, 30 days refresh), with the public half of a user's X25519 key bound into the token claims. A client that loses its access token can refresh without re-entering the password; a client that loses its refresh token has to re-authenticate from scratch.",
    register_flow="Register flow",
    r1="Client generates a 32-byte random X25519 private key, derives the public key, and encodes it as 64 hex chars.",
    r2="Client hashes the password client-side with a fast SHA-256 (not for security — just to avoid sending raw bytes over TLS; the real hash happens on the node).",
    r3="POST /api/authentication/register with `{username, password, x25519_public_key, display_name, phone, email, avatar_emoji}`. Fields are validated by Pydantic (`username` matches `^[a-z0-9_]{3,30}$`, password has zxcvbn-like strength check, phone matches E.164).",
    r4="Node runs Argon2id on the password (m=64MiB t=3 p=4) and stores `argon2:<hash>` in `users.password_hash`. The X25519 pubkey goes to `users.x25519_public_key` (unique constraint — you can't register the same key twice).",
    r5="Node creates a `user_devices` row with the device's User-Agent and a fresh device_id. JWT access and refresh tokens are minted with claims `{sub: user_id, jti: device_id, typ: access|refresh, exp: ...}`, signed with HS256 over the node's secret (not Ed25519 — JWTs are a node-internal concern).",
    r6="Response: `{access_token, refresh_token, user_id, username, x25519_public_key, kyber_public_key, display_name, avatar_url}`. Client stores tokens in Keychain (iOS) / EncryptedSharedPreferences (Android) / HttpOnly cookies (web).",
    login_flow="Login flow",
    l1="Client re-hydrates its X25519 public key from the Keychain.",
    l2="POST /api/authentication/login with `{username, password}`. The node looks up the user row, verifies the Argon2 hash (constant-time comparison — even if the user doesn't exist, a dummy hash is verified to equalise timing), and either returns the same envelope as register or rejects with 401.",
    l3="On failure the node increments a per-IP counter (10 attempts / 60 s for login, 5 / 60 s for register). Beyond the threshold the node returns 429; `TESTING=true` env var disables the limiter for automated runs.",
    refresh_flow="Refresh flow",
    f1="Access token has `exp` = now + 15 min. When a request returns 401 with `token expired`, the client posts the refresh token to `/api/authentication/refresh`.",
    f2="Node verifies the refresh, checks that the device row is still present and not revoked, and mints a fresh access token (same 15-min life). Refresh rotation is off by default but can be turned on with `ROTATE_REFRESH=true`.",
    f3="If refresh fails — token expired, device revoked, user deleted — the client logs out locally and prompts the user to sign in again.",
    passkey="Passkey / WebAuthn",
    pk1="For web clients, Vortex also supports WebAuthn platform authenticators (Touch ID, Face ID, Windows Hello, Android fingerprint). Registration stores the `credential_id` and `public_key` on the node; login is a challenge-response over the public key. No password needed after setup.",
    qrlogin="QR login",
    qr1="A logged-in device can share its session to a new one via QR. Device A generates a one-time challenge and displays it as a QR; device B scans, POSTs `/api/authentication/qr/verify`, and receives its own fresh tokens. The challenge is 128 bits of randomness and valid for 60 s.",
    seedlogin="Seed-phrase login",
    sl1="As a recovery path, users can export their 24-word BIP-39 seed. Re-importing it on any device reconstructs the X25519 identity and proves possession via an Ed25519 signature challenge. Seed is never sent to the server; the node only sees the derived public key.",
    twoFA="2FA (TOTP)",
    tfa1="Enabling 2FA adds a TOTP (RFC 6238) secret generated on-device. Login then requires `totp` field in the request. 5 attempts / 5 min per user, then a 429. Backup codes (12 × 10 digits) are shown once during setup.",
)


WEBSOCKET = section(
    "WebSocket protocol",
    "Every event that flows over `/ws` and how clients reconcile state.",
    intro="A client opens one WebSocket per node session. Frames are JSON; we chose JSON over CBOR for this layer because messages are thin envelopes around already-encrypted ciphertext, debuggability is more valuable than 10 % smaller headers.",
    handshake="Handshake",
    h1="Client sends `GET /ws?token=<access_jwt>` with `Upgrade: websocket`. Node validates the token in the HTTP layer and upgrades. Any non-2xx status closes the socket before handshake.",
    h2="First server frame: `{type:\"hello\", node_version, node_pubkey, features}`. `features` lists optional capabilities so the client can enable/disable Kyber, Double Ratchet, post-quantum handshake, etc.",
    ping="Ping / pong",
    pg1="Server sends `{type:\"p\"}` every 25 s. Client replies `{type:\"q\"}`. Three missed replies ⇒ the server closes the connection and frees its room subscriptions. Client reconnects with exponential backoff capped at 30 s.",
    events="Event types",
    e1="`m` — new message (or edit / delete / reaction).",
    e2="`t` — typing started / stopped for a user in a room.",
    e3="`r` — read-receipt update.",
    e4="`p` — presence change (online / offline / last-seen).",
    e5="`c` — call signalling envelope for WebRTC (offer, answer, candidate).",
    e6="`k` — key rotation — a room's shared key was rotated because a member left.",
    e7="`n` — system notification (room created, user joined, user banned).",
    e8="`e` — generic error payload; clients should surface it to the user.",
    subscribe="Subscribing to rooms",
    sub1="Client sends `{type:\"sub\", room: <id>}`. The node adds the socket to that room's fan-out set. Re-subscribing is idempotent.",
    sub2="On unsubscribe `{type:\"unsub\", room: <id>}` the socket leaves the set but stays connected.",
    backfill="Backfill after reconnect",
    b1="After a reconnect the client sends `{type:\"sub\", room: <id>, since: <message_id>}`. The node replays every message with `id > since`, then resumes live fan-out. `since` is inclusive of the last read message id — the client de-dups on its own side.",
)


ROOMS = section(
    "Rooms and messaging",
    "Public, private, DM, channel — one model covers them all.",
    intro="A room is a bag of members plus a shared secret. All four room types (DM, private group, public group, channel) are the same underlying table — differences are in ACL flags.",
    room_types="Room types",
    rt1="**DM** — exactly 2 members. `is_dm=true`, `is_private=true`. Each party's identity is the other's only metadata.",
    rt2="**Private group** — N ≤ 5 000 invite-only members. `is_private=true`. New keys are rotated whenever someone leaves.",
    rt3="**Public group** — unlimited members, anyone can join via invite link or public directory. `is_private=false`.",
    rt4="**Channel** — broadcast-only. Only owners and admins can post. `is_channel=true`.",
    key_mgmt="Key management",
    km1="Each room has a **shared root key** generated at creation. Each member's device receives an envelope `X25519(their_pubkey, root_key)` so they can decrypt historical messages.",
    km2="When a member leaves, the node rotates the root key and broadcasts new envelopes to remaining members. The departed device can't read new messages; old messages remain decryptable by the remaining members (but the departed device locally still has them).",
    km3="Variant-B public rooms: instead of per-member envelopes, the current key is posted signed by the owner into the node's public key store. Clients verify the signature against the room's owner pubkey. Scales to 100k members without O(N) envelope fan-out on every rotation.",
    invite="Invites",
    i1="Invite codes are 32 hex chars. They can be time-bounded (`max_uses`, `expires_at`), role-bound (`assign_role`), or revocable. The owner distributes them through any out-of-band channel; the node rejects a code that's exhausted or expired.",
    messages="Messages",
    m1="A message row stores `room_id, sender_id, ciphertext, nonce, sent_at, edited_at?, deleted_at?, reply_to?, thread_id?, kind`. `kind` differentiates text, image, file, voice note, call record, and system events.",
    m2="`ciphertext` is opaque to the node. `sender_pseudo` is stored in cleartext for routing (fan-out to the right WebSocket subscribers), but it's a short hash derived from `sender_id + room_id` so a node compromise doesn't leak who's active in which room to outside observers.",
    edits="Edits and deletes",
    ed1="Edits are new ciphertext posted to `/api/messages/{id}/edit` with the previous message's id. The old ciphertext is overwritten; the `edited_at` column flips to the current time so clients can render a subtle \"(edited)\" mark.",
    ed2="Deletes mark `deleted_at` and null out the ciphertext column. The message row itself stays so replies still make sense. \"Delete for everyone\" fans out `{type:\"m\", deleted:true, id:...}` to every open socket.",
    reactions="Reactions",
    rx1="A reaction is a row in a separate table keyed by `(message_id, user_id, emoji)`. Adding the same emoji twice no-ops; removing a reaction posts `DELETE /api/messages/{id}/reactions/{emoji}`. Clients aggregate on read.",
    threads="Threads",
    t1="A thread is a pseudo-room rooted at a message. `POST /api/messages/{id}/thread` creates a new room whose `parent_message_id` points back. Thread replies are ordinary messages posted into that sub-room.",
    t2="Clients navigate threads like rooms — same UI, same WebSocket sub. The sub-room's key chain is derived from the parent room's key with a context string `\"thread:{parent_id}\"` so a compromise of the thread key doesn't leak the parent.",
)


FILES = section(
    "Files and media",
    "Chunked, encrypted, resumable. 5 MB inline cap, 5 GB resumable cap.",
    intro="Files travel through two paths depending on size. Under 5 MB they ride a single-shot POST with the whole payload inline; over 5 MB they use the resumable protocol where the client uploads fixed-size chunks and can resume after network blips.",
    singleshot="Single-shot upload",
    s1="POST /api/files with `multipart/form-data`, field `file`. The node receives the stream, enforces the 5 MB cap, runs `python-magic` for MIME detection, and stores under `uploads/<category>/<hash>.<ext>`.",
    s2="Response: `{file_id, url, mime_type, size}`. The URL is public but the file is client-side encrypted — the node never held plaintext either. Only holders of the room key can make sense of the bytes.",
    resumable="Resumable upload",
    r1="Stage 1: `POST /api/files/resumable/init` with `{filename, size, sha256}`. Node allocates an upload id and returns chunk size (default 512 KiB).",
    r2="Stage 2: `PUT /api/files/resumable/{id}/chunk/{offset}` for each chunk. Offsets must be aligned to chunk size; mismatches 400. Chunks are AES-GCM-encrypted per chunk with a chain-of-keys derived from the file root.",
    r3="Stage 3: `POST /api/files/resumable/{id}/finalise`. Node reassembles, verifies the expected sha256 (re-computed over the decrypted chunks? no — over the uploaded ciphertext; the client sends a separate `plain_sha256` claim the recipient verifies).",
    r4="If a chunk fails, the client can retry that one offset without re-uploading the previous chunks. The node keeps partial uploads for 24 h; after that a cron cleans them up.",
    thumbs="Thumbnails",
    t1="For images the node generates a 256×256 JPEG thumb with Pillow during upload. The thumb is end-to-end encrypted the same way as the full file, so a recipient still needs the room key to render it.",
    t2="For video the node optionally runs ffmpeg-based key-frame extraction into a 512×512 poster JPG. This runs out-of-process behind a queue so a malicious upload can't DOS the web worker.",
)


CALLS = section(
    "WebRTC voice and video",
    "Signalling over WebSocket, media over SRTP, TURN fallback.",
    intro="Vortex uses the standard WebRTC stack. The node is signalling-only — once two peers have each other's ICE candidates, media flows directly between them or through a coturn TURN relay when NAT traversal fails.",
    signalling="Signalling",
    s1="Caller POSTs `/api/calls/{room_id}/start`, the node broadcasts `{type:\"c\", kind:\"offer\", sdp:...}` to every other socket in the room. Callees post back `{type:\"c\", kind:\"answer\", sdp:...}`, candidates are exchanged as `{kind:\"candidate\", ice:...}` until the PeerConnection reports `connected`.",
    s2="The node validates each SDP for obvious shenanigans (no private IPs in the offer, no external TURN servers not on our allow-list) before forwarding.",
    turn="TURN relay",
    t1="We ship a coturn instance bound to the node's public IP with short-lived credentials. The node mints `turn://user:password@node:3478` URLs signed with HMAC for each peer at call start.",
    t2="Credentials expire after 24 h and are revoked if the user logs out. Without a valid JWT the node refuses to hand out TURN URIs.",
    codecs="Codecs",
    c1="Audio: Opus @ 48 kHz. Video: VP9 baseline at launch, H.264 fallback for older hardware, AV1 opt-in for premium devices.",
    c2="Each codec negotiation goes through the host's WebRTC stack — we don't override, we just influence priorities through constraint objects.",
    callkit="CallKit / ConnectionService",
    ck1="iOS calls integrate with CallKit so the OS shows the native \"Vortex Call\" answer screen, supports Apple Watch, and participates in Do Not Disturb.",
    ck2="Android uses ConnectionService. The telecom framework manages headset state and Bluetooth routing for free.",
)


FED = section(
    "Federation between nodes",
    "Trusted pubkeys, health checks, cross-node message routing.",
    intro="Operators can link their nodes. Users on node A can DM users on node B; ciphertext flows through a signed gossip envelope and both nodes persist the relevant side.",
    trust="Trust model",
    t1="Every federated node has an entry in the controller's `trusted_nodes` table: `{pubkey, endpoint, health_score, last_seen}`. The controller exposes the list at `/v1/trusted_nodes` so clients can cache it for offline use.",
    t2="Adding a new node requires an operator-signed request through the controller admin API — the UI prompts the operator to double-check the pubkey fingerprint.",
    routing="Routing",
    r1="Messages addressed to `user@otherNode` get an extra envelope: the node wraps the already-encrypted payload in a signed `{source_node, target_node, cipher}` blob and POSTs `/federation/deliver` on the remote node.",
    r2="If the remote is unreachable, the sending node queues the blob in the outbox and retries with exponential backoff. Eventually (14 days) it gives up and marks the message as undeliverable.",
    health="Health monitoring",
    h1="Every 60 s each node pings every peer in its `trusted_nodes` list with `GET /v1/health`. Two successive timeouts drop `health_score` by 1 (minimum 0, maximum 100). Score 0 means the node is effectively de-federated until it recovers.",
    h2="Health scores are published in `GET /v1/peers` so operators can debug connectivity issues from a dashboard.",
)


GOSSIP = section(
    "Gossip and peer discovery",
    "The `global_transport` layer — how nodes find each other.",
    intro="Besides the controller-managed trusted_nodes list, nodes also gossip. Each node maintains a peer list and exchanges it with neighbours every 60 s using a signed digest.",
    exchange="Exchange protocol",
    e1="Node A sends its 256-bit Bloom filter summarising known peers. Node B replies with the ones missing from the filter plus its own filter. Bandwidth grows logarithmically with network size.",
    e2="Sybil protection: every advertised peer has to be signed by the node-of-origin. A malicious node can't advertise forged peers because clients verify the signature on first contact.",
    ratelimit="Rate limiting",
    rl1="One exchange per peer per 30 s (sliding window). This caps gossip bandwidth at O(peers × 2 exchanges/min) regardless of network churn.",
    bootstrap="Bootstrap",
    b1="New nodes start with a hardcoded bootstrap list of 8 well-known controllers. After the first exchange they can discover the rest of the network organically.",
)


STEALTH = section(
    "Stealth and censorship circumvention",
    "Five layered mechanisms to survive an adversarial network.",
    intro="Vortex assumes a class of adversary that can see your traffic, classify it by fingerprint, and block known apps. The stealth stack makes Vortex traffic look like ordinary browser traffic and, failing that, makes it unreachable by classifiers at all.",
    level1="Level 1 — Transport obfuscation",
    l11="Tightens the TLS fingerprint to match Chrome on Windows 11 (`tcp_fp=chrome_win11`). No Vortex-specific JA3 / JA4 hash, no client-hello giveaways.",
    l12="Enables TLS padding and constant-rate send so packet-size analysis can't tell a message from a heartbeat.",
    level2="Level 2 — Advanced stealth",
    l21="Morphs traffic shape to look like YouTube 720p streaming (`morpher=youtube_720p`). MultiPath connections fan the same stream across 3 links and reassemble on receive.",
    l22="WebRTC data channel tunnel as a backup transport when TLS is blocked but WebRTC gets through.",
    l23="Decoy connections — the node opens and maintains 3 idle connections to Google / YouTube / Cloudflare (every 45 s) so an observer sees a mix of traffic at any given time.",
    level3="Level 3 — Protocol camouflage",
    l31="DoH (DNS-over-HTTPS) for all DNS resolution, so ISPs can't see which domains you're asking for.",
    l32="ECH (Encrypted Client Hello) hides the SNI on TLS 1.3 — the only visible destination is the front-end IP.",
    l33="Probe detection: the node looks for `GET /api/*` attempts from an IP with no corresponding auth session within the last 5 min and returns a plain HTML page with a 200 OK so active probers walk away thinking they hit a static site.",
    l34="DGA — Domain Generation Algorithm mode: if the primary endpoint is blocked, the client can generate a new candidate domain from a shared seed and today's date, try it, fall through on failure. Deterministic so multiple clients converge on the same fallback.",
    level4="Level 4 — Pluggable transports",
    l41="vmess / vless / trojan / shadowtls — standard outbound transports with the right PT config. Supported as opt-in channels for operators in restrictive regions.",
    l42="Reality — TLS-within-TLS with a specific well-known target (like www.microsoft.com). Probes directed at the reality handshake get forwarded to the real target so active probing reveals nothing.",
    l43="Snowflake — browser volunteers relay Vortex traffic through WebRTC. Requires no infrastructure; relies on there being many browsers contributing as nodes.",
    l44="NaiveProxy — modifies HTTPS probes to blend with Chromium's own.",
    l45="IPFS — message payloads can be posted as IPFS objects and announced through DHT. Reader clients fetch and reassemble.",
    level5="Level 5 — Last resort",
    l51="OHTTP (Oblivious HTTP) — requests are double-encrypted so even the intermediary relay doesn't see the destination.",
    l52="Tor hidden-service endpoint — every node exposes itself as `.onion` as well. Clients with Tor support fall through to this if everything else fails.",
    l53="Store-and-forward through a blind mailbox — see the next section.",
)


BMP = section(
    "Blind Mailbox Protocol",
    "Messages queue server-side without the server knowing who sent them.",
    intro="BMP is a store-and-forward layer for high-censorship scenarios. A sender can drop an encrypted blob at any node — not just the recipient's home node — and the blob rides gossip until the recipient's device pulls it from a nearby mailbox.",
    mechanics="Mechanics",
    m1="Sender derives a 32-byte `mailbox_id` from `hkdf(recipient_pubkey, \"bmp-v1\")`. They POST `{mailbox_id, blob}` to any gossiping node. The node stores the pair for up to 7200 s.",
    m2="The node's BMP module periodically gossips a summary of mailbox_ids to peers. Peers who see a `mailbox_id` for one of their local users pull the blob.",
    m3="Recipient's node decrypts — it's actually just the pass-through of an already E2E-encrypted message. The sender's identity remains hidden: no one except the final recipient's client can correlate the blob to a user.",
    delivery="Delivery semantics",
    d1="At-most-once by default. At-least-once optional if the sender re-posts.",
    d2="Max blob size 1 MB. Anything larger has to be chunked through the ordinary file system.",
    batching="Batching",
    b1="Up to 100 blobs per gossip exchange. Compression saves bandwidth on small text-message blobs.",
)


PUSH = section(
    "Push notifications",
    "Sealed push so APNs/FCM can't learn anything about the message.",
    intro="Standard push services (APNs, FCM) see each payload. Vortex wraps each notification in a separate E2E layer so the provider only sees a fixed-size opaque blob.",
    flow="Sealed push flow",
    f1="Client registers its device token and a fresh X25519 `p256dh_pub` at the node.",
    f2="When a notification is due, the node encrypts the payload with AES-GCM using a key derived from `ECDH(p256dh_pub, ephemeral_priv)` and sends `{endpoint, p256dh, auth, data}` to APNs / FCM.",
    f3="Device receives, decrypts with its private key, shows the notification.",
    providers="Providers",
    p1="Apple Push Notification service for iOS. Tokens last ~30 days; we rotate on every app launch.",
    p2="Firebase Cloud Messaging for Android. Token rotation tied to `InstanceID` events.",
    p3="Web Push (VAPID) for browsers. Same sealed envelope; payload capped at 4 KB per RFC 8291.",
    tmcount="Notifications collapse-key",
    tc1="Per-room collapse-key ensures multiple messages from the same chat don't cascade into 20 banner notifications. The bar shows `(N messages)` instead.",
)


STORAGE = section(
    "Storage",
    "SQLite for dev, PostgreSQL for prod, Alembic for both.",
    intro="Vortex supports two SQL backends: SQLite for single-node dev and small self-hosted deployments, PostgreSQL for federated / production setups. SQL is accessed through SQLAlchemy 2.x async engine.",
    tables="Core tables",
    t1="`users` — `id`, `username`, `password_hash`, `x25519_public_key`, `kyber_public_key`, `display_name`, `avatar_url`, `phone`, `email`, `created_at`.",
    t2="`user_devices` — per-device tokens and revocation flags.",
    t3="`rooms` — `id`, `type`, `name`, `is_private`, `is_channel`, `is_dm`, `member_count`, `avatar_url`, `created_at`, `created_by`.",
    t4="`room_members` — `(room_id, user_id, role, joined_at, muted)`.",
    t5="`messages` — `(id, room_id, sender_id, ciphertext, nonce, sent_at, edited_at, deleted_at, reply_to, thread_id, kind)`.",
    t6="`reactions` — `(message_id, user_id, emoji, created_at)`.",
    t7="`files` — `id`, `user_id`, `mime_type`, `size`, `sha256`, `storage_path`, `uploaded_at`.",
    t8="`sessions` — `(jti, user_id, device_id, expires_at)` for refresh token validation.",
    t9="`federations` — trusted peer nodes with pubkeys and health scores.",
    t10="`scheduled_messages` — queued messages with their future `send_at` timestamps.",
    t11="`contacts` — per-user contact list.",
    t12="`saved_gifs` — per-user saved GIFs.",
    t13="`folders` — user-defined chat folders.",
    t14="`presence` — `(user_id, last_seen_at, is_typing_in_room_id)`.",
    migrations="Migrations",
    m1="Alembic is configured in `alembic.ini`. Revision history is linear (no branching). Every new release either adds a new revision or is a pure code change.",
    m2="Dev mode uses `create_all + ALTER TABLE fallback` so you can iterate quickly without running `alembic upgrade head` on every rebase.",
    m3="Prod mode requires `alembic upgrade head` as a pre-deploy step. Docker compose does it automatically from the entrypoint.",
    backups="Backups",
    b1="`make db-backup` dumps every table to a timestamped SQLite / pg_dump file. Encrypted at rest with the operator's key.",
    b2="Retention: 14 daily, 4 weekly, 12 monthly. Managed by a cron inside the node container.",
    fts="Full-text search",
    fts1="Messages are mirrored into an FTS5 virtual table for substring / prefix search. Both client (on-device) and node use FTS5 to keep UX consistent across platforms.",
    fts2="The FTS tables are populated by triggers, not by application code — this guarantees the search index never lags behind the main messages table even under concurrent writes.",
)


BOTS = section(
    "Bots framework",
    "Gravitix DSL + marketplace + antispam — every bit end-to-end encrypted.",
    intro="Vortex bots run as first-class participants in rooms. The framework supports both Python-flavoured definitions and the domain-specific Gravitix DSL. Every bot message is signed with the bot's ed25519 key so forgeries are detectable.",
    lifecycle="Bot lifecycle",
    l1="Create: owner POSTs `/api/bots` with the bot's username, display name, and initial code. The node returns a bot token.",
    l2="Run: either the bot runs in-process as a coroutine inside the node (convenient, single-operator), or externally by polling `/api/bots/{id}/updates` with the bot token (scalable, multi-operator).",
    l3="Deploy: code updates are signed by the owner and atomically swapped in. Running bots are drained gracefully.",
    gravitix="Gravitix DSL",
    g1="A tailored language for chat bots. `on /start { emit \"hi\" }` declares a handler. See the dedicated Gravitix reference for the full spec.",
    g2="Bots written in Gravitix get compiled to a small bytecode and run in a sandboxed interpreter — no filesystem or network access unless explicitly granted.",
    antispam="Antispam bot",
    as1="Every room gets an invisible bot that watches for flood patterns, too-many-links, repeated copy-paste, and suspicious account ages. Infractions trigger warnings, then auto-timeout, then report to admins.",
    as2="Tuneable via `config.yml` inside the room or globally at the node level.",
    marketplace="Marketplace",
    mk1="Public bots can be submitted to the marketplace. Reviewers verify the source doesn't phish. Users browse by category, install with one click (the node subscribes the user to the bot's `@botname` automatically).",
    mk2="Paid bots: one-time or subscription, payments routed through Stripe / crypto. Bot owners set the price; Vortex takes a 10 % transaction fee.",
)


CONTROLLER = section(
    "Controller",
    "Integrity attestation and entry discovery.",
    intro="The controller (`vortex_controller` package) is a separate process with a smaller surface than the node. Its only jobs: say \"this code is what was signed\", publish entry URLs, and track peer health.",
    endpoints="Endpoints",
    e1="`GET /v1/integrity` — returns `{status, signed_by, version, matched, mismatched, missing, extra, message}`. Clients call this first and refuse to proceed unless `status==\"verified\"`.",
    e2="`GET /v1/health` — returns `{status, version, pubkey, stats:{online, approved, total}}`.",
    e3="`GET /v1/trusted_nodes` — published list of federated nodes.",
    e4="`GET /v1/entries` — entry URLs (WS + HTTPS) for connecting to the network.",
    e5="`GET /v1/mirrors` — mirror controllers (secondary DNS + IPFS + .onion).",
    sign="Integrity signing",
    s1="`python -m vortex_controller.integrity.sign_tool` walks the source tree, hashes every file, produces `INTEGRITY.sig.json` signed with the release Ed25519 key (`keys/release.key`).",
    s2="At startup the controller verifies the manifest against the on-disk tree. If any file differs, the controller refuses to start and prints which file is bad.",
    s3="Operators who fork Vortex replace `release.key` with their own and re-sign. Clients configured with a different pubkey will then trust their fork.",
    mirrors="Mirror deployment",
    mr1="Each mirror runs the same binary plus the same release key. DNS / SNS / IPFS publish point to one of several mirrors; clients try them in priority order.",
    mr2="`vortex.sol-mirror/run.py` in this repo bootstraps a local mirror exposed via trycloudflare for development.",
)


STEALTH_LEVELS_DETAIL = section(
    "Stealth — detailed mechanism list",
    "Each of the 28 mechanisms and when it triggers.",
    intro="Detailed reference. Each mechanism is toggleable via `STEALTH_*` env vars; `LEVEL=4` enables everything up to and including Level 4.",
    mechanisms="Mechanisms by level",
    mech_padding="TLS padding — pads every record to 16 KB so payload size is indistinguishable from full-buffer browser activity.",
    mech_const_rate="Constant-rate sender — send queue emits one packet every N ms regardless of whether new data arrived. Buffered payloads wait; idle periods emit dummy packets. Traffic-analysis counters see a flat-line pattern.",
    mech_decoy="Decoy targets — three slow background streams to random HTTPS properties keep the node's fingerprint busy.",
    mech_jitter="Timing jitter — 0..50 ms random delay per egress packet to defeat latency-based DPI.",
    mech_morpher="Packet morpher — splits or coalesces packets to match YouTube 720p / Zoom / Netflix profiles.",
    mech_fp="Fingerprint override — client hello mimics Chrome 120 / Safari 17 / Firefox 120 depending on OS.",
    mech_ech="ECH — hides the SNI by wrapping it inside an ECHConfig-encrypted extension.",
    mech_doh="DoH — DNS-over-HTTPS to Cloudflare / Google / Quad9.",
    mech_dga="DGA — deterministic domain generation so clients find a fallback when the primary is blocked.",
    mech_cdn="CDN fronting — publishes the same endpoints behind Cloudflare / Fastly with host-header redirection.",
    mech_meek="Meek — domain fronting through a CDN by setting Host: example.com and routing via TLS SNI example.com but HTTP Host: vortexx.sol.",
    mech_snowflake="Snowflake — browser peers volunteer as WebRTC relays.",
    mech_vmess="VMess — outbound transport used by V2Ray-style deployments.",
    mech_vless="VLess — lightweight successor to VMess, OpenSSL-friendly.",
    mech_trojan="Trojan — looks like generic HTTPS to an uninformed inspector.",
    mech_reality="Reality — TLS-within-TLS masquerading as Microsoft / Apple / Google origins.",
    mech_shadow="ShadowTLS — separates the outer handshake from the data stream; probes see a real CDN response.",
    mech_naive="NaiveProxy — Chromium's own HTTPS pipeline as a transport.",
    mech_ipfs="IPFS — content-addressed payloads announced via DHT.",
    mech_tor="Tor — `.onion` endpoint for each node; optional for clients.",
    mech_ohttp="OHTTP — relay-assisted oblivious HTTP; no single entity sees both request and response.",
    mech_ble="BLE transport — offline peer-to-peer fallback over Bluetooth Low Energy (line-of-sight).",
    mech_multipath="Multipath — concurrent flows over Wi-Fi, cellular, and VPN; reassembly at the receiver.",
    mech_polymorph="Polymorphic encoding — occasional byte-level encoding changes defeat signatures.",
    mech_probe_detect="Probe detection — suspicious probers get a decoy static site back.",
    mech_schedule="Activity scheduling — limits high-bandwidth events to business hours in the user's timezone if they opt in.",
    mech_cover="Cover traffic — random idle traffic keeps the flow active even when the user is inactive.",
    mech_knock="Port knocking — three sequential TCP attempts with a shared secret unlock the real port.",
)


DEPLOY = section(
    "Deployment and operations",
    "Docker, Make, systemd, rollbacks.",
    intro="Vortex ships as a Python source tree that can run directly with `python run.py`, as a PyInstaller bundle (`Vortex Wizard.app`), or as a docker-compose stack with Postgres and Redis.",
    compose="Docker compose",
    c1="`docker compose up` brings up node, controller, postgres, redis, coturn, nginx. Volumes persist `/data/vortex.db` and `/data/uploads`.",
    c2="Healthchecks are wired in: node healthy only when `/health/ready` returns 200. Controller healthy only when `/v1/integrity` returns verified.",
    c3="Bring your own TLS certs or let Caddy handle Let's Encrypt automatically (`caddy.yml` profile).",
    make="Make targets",
    mk1="`make install` — `pip install -r requirements.txt` + dev deps.",
    mk2="`make dev` — uvicorn with reload on port 9000.",
    mk3="`make test` — pytest + coverage.",
    mk4="`make lint` — ruff + mypy.",
    mk5="`make docker-build` — build the image; tag with `VERSION`.",
    mk6="`make ci` — full CI pipeline locally (lint + test + migration sanity).",
    wizard="Setup wizard",
    w1="`Vortex Wizard.app` is a PyInstaller bundle that guides first-time operators through: choosing a node name, generating release keys, configuring TLS, picking entry URLs, enabling stealth, and opening firewall ports.",
    w2="Uses pywebview to host a local HTML/JS UI that talks to a bundled FastAPI admin API on 127.0.0.1.",
    rollbacks="Rollbacks",
    rb1="Every release is tagged. `git checkout <tag>` + `make docker-build` reproduces a prior release byte-for-byte.",
    rb2="DB migrations have downgrade scripts; `alembic downgrade <rev>` is supported for 1 minor version back.",
)


MOBILE = section(
    "Mobile clients",
    "iOS and Android — same protocol, different native UIs.",
    intro="The iOS and Android clients both speak the exact same HTTP / WebSocket API as the web client. They're full peers — neither platform has reduced features.",
    ios="iOS",
    i1="Swift Package with 30+ feature modules (`Bootstrap`, `Auth`, `Chat`, `Files`, `Calls`, etc). SOLID split: `api/` protocols, `impl/` concrete classes, `ui/` SwiftUI views.",
    i2="Crypto: CryptoKit for X25519 / Ed25519 / AES-GCM; Argon2Swift (revision-pinned) for Argon2id; Apple's own for HKDF.",
    i3="DB: GRDB (SQLite) with full-text search via FTS5, same as node.",
    i4="WebRTC: stasel/WebRTC binary XCFramework.",
    i5="Push: APNs with sealed-push wrapper.",
    android="Android",
    a1="Kotlin + Compose + Hilt. 22 feature modules following the same `api / impl / di` pattern.",
    a2="Crypto: AndroidX security + Tink for AES-GCM; Argon2 via the `argon2-jvm` binding to the reference C implementation.",
    a3="DB: Room with FTS4 triggers.",
    a4="WebRTC: Stream WebRTC Android.",
    a5="Push: FCM with sealed envelope.",
    shared="Shared contracts",
    s1="Both clients ship the same 146-locale JSON bundle (native names + hints per locale).",
    s2="Both clients implement the same 1500-emoji catalog with skin-tones, 9 categories, and MRU persistence.",
    s3="Multi-account switching uses X25519 challenge-response identically across platforms.",
)


WEBCLIENT = section(
    "Web client",
    "PWA with offline support, service worker, and liquid-glass UI.",
    intro="The web client is a vanilla-JS PWA. No React, no Vue, no build step beyond a simple bundler. Total JS shipped: ~400 KB gzipped.",
    shell="Shell",
    s1="`templates/base.html` + `static/js/main.js` bootstrap the app. Feature modules live in `static/js/<feature>/`.",
    s2="Service worker caches the shell, then lazy-loads feature JS on first need. Second visits are instant.",
    offline="Offline mode",
    o1="Any message posted while offline is queued in IndexedDB. On reconnect, the SW flushes the queue in order. Duplicates are caught by the server's idempotency key.",
    o2="Reading existing chats works fully offline — all already-synced ciphertext lives in IndexedDB and decrypts locally.",
    i18n="I18N",
    i1="146 languages in `static/locales/*.json`. The UI picks one at first launch via `lang-picker.js`; subsequent launches read the saved choice from `localStorage`.",
    i2="Typewriter animation on the welcome screen cycles through the localised \"Choose your language\" hint for every language.",
)


SECURITY = section(
    "Security posture",
    "Every layer of defence and what it costs an attacker.",
    intro="Vortex uses defence-in-depth. Breaking one layer isn't enough — a realistic attacker has to compromise multiple independent systems.",
    threats="Threat model",
    th1="**Passive network observer** — sees TLS-encrypted packets, can do traffic analysis. Defeated by Level 1-2 stealth (shape, size, timing).",
    th2="**Active network attacker (DPI)** — can drop / delay / inject plaintext. Defeated by Level 3-4 stealth (ECH, domain fronting, reality).",
    th3="**Compromised node operator** — sees ciphertext and metadata. Message contents remain confidential (E2E); metadata is minimised (sender pseudo, no IP logs).",
    th4="**Compromised client device** — sees plaintext of past messages stored locally. Forward secrecy via Double Ratchet limits damage to the current session.",
    th5="**Quantum-computing-enabled adversary with stored past traffic** — defeated by hybrid Kyber-768 + X25519 session key if both sides advertised PQ.",
    waf="WAF",
    w1="Request inspection: common SQL-i patterns, template-injection, path-traversal, LFI patterns dropped at the edge.",
    w2="Rate limits: global per-IP (1000 req/s ramp-up), per-route (login 10/min, register 5/min), per-user (avg 100 req/s after auth).",
    audit="Audit trail",
    a1="Security-relevant events (admin action, federation change, release upgrade) land in `app/security/canary.py` with a HMAC chain. Breaks in the chain indicate tampering.",
    a2="`/api/admin/audit` exposes the log to authenticated admins. Everything's append-only.",
)


PRIVACY = section(
    "Privacy and compliance",
    "GDPR, right-to-erasure, metadata minimisation.",
    intro="Vortex ships with GDPR and CCPA tooling out of the box. Operators in the EU can respond to right-to-erasure and data-export requests through a single admin endpoint.",
    minimisation="Metadata minimisation",
    m1="No IP logs. The reverse proxy strips `X-Real-IP` before the node sees it unless the operator opts in for rate limiting.",
    m2="`sender_pseudo` hashes real sender IDs so room-member lists on a server breach are opaque.",
    m3="Full-text search runs on ciphertext tokens only (clients encrypt keywords and send opaque tokens for lookup).",
    erasure="Right-to-erasure",
    e1="`POST /api/privacy/erase` triggers a node-wide purge: `users` row anonymised, `messages` sent by the user wiped of ciphertext (metadata kept for quorum), files purged from disk.",
    e2="Federated peers are notified via signed gossip; they run the same purge on their side within 72 h.",
    export="Data export",
    ex1="`GET /api/privacy/export` produces a zip of everything the node holds about the user: profile, sent / received ciphertext, file references (with decryption hints marked `user_must_decrypt_locally`).",
    ex2="ETA: generation takes ~5 minutes for a 10 k-message account, bounded by IO.",
    panic="Panic wipe",
    p1="Long-press on the Vortex logo for 5 s (client-side) triggers an immediate local wipe: all keys, all cached messages, all attachments. Irreversible.",
    p2="Optional coupled wipe: `/api/privacy/panic` also deletes the account server-side and federates the erasure.",
)


AI_FEATURES = section(
    "AI features",
    "Optional features that run on the node, not on a third party.",
    intro="All AI features are opt-in and run either on the node via a local small-model runtime or on the client's device. No prompt is ever sent to OpenAI / Anthropic unless the user explicitly enables a third-party tool inside the room.",
    models="Models bundled",
    m1="`Qwen3-8B` local model for chat suggestions — runs on CPU with ~1 tokens/s, on GPU with 15+. Optional.",
    m2="Sentence-transformers for semantic search across local messages.",
    features="Features",
    f1="Smart replies — three short suggestions based on the last 20 messages in the room. Runs entirely client-side for privacy.",
    f2="Summarise — collapse a long conversation into 3-5 bullet points. Runs on the node with a consented payload.",
    f3="Translate inline — leverages the 146-locale static dataset plus on-demand Google Translate (opt-in per-room).",
    disable="Disabling",
    d1="Ops flag `AI_ENABLED=false` at the node level turns the whole block off. Clients then hide the AI UI.",
)


MONITORING = section(
    "Monitoring and metrics",
    "Prometheus-compatible exporter, Grafana dashboards, log rotation.",
    intro="Every node exposes `/metrics` (guarded by auth in production). The metrics are Prometheus-compatible and cover request counts, latency histograms, active connections, DB pool saturation, and stealth-layer health.",
    exporters="Exporters",
    e1="Request count and status by route and method.",
    e2="DB query time histograms (p50 / p95 / p99).",
    e3="Active WebSocket connections and messages/s.",
    e4="Stealth module status: which levels are active, how many decoy streams, ECH cache size.",
    e5="Federation health — heartbeat success rate per peer.",
    logs="Log rotation",
    l1="Each log file rotates at 100 MB, 14 generations kept. Gzip after rotation. JSON structured logging by default.",
    l2="Log levels per-module via `LOG_LEVEL_<MODULE>=DEBUG` env vars. Default INFO.",
    alerting="Alerting",
    a1="Recommended Prometheus rules shipped in `deploy/alerts.yml`: node offline > 5 min, error rate > 5 %, DB pool saturation > 80 %, stealth level drop.",
)


TESTING = section(
    "Testing strategy",
    "Unit, integration, property-based, fuzz.",
    intro="Vortex has ~29 k lines of tests across Python (pytest), Kotlin (JUnit + Hilt-android-testing), Swift (XCTest), and JS (jest). CI runs the lot in under 10 minutes on a medium Github Actions runner.",
    python="Python tests",
    py1="`pytest app/tests` — covers every router, every security primitive, every transport module. ~80 % coverage.",
    py2="Property-based tests via Hypothesis on crypto primitives — e.g. `assert decrypt(encrypt(m)) == m` for 1000 random messages.",
    py3="Fuzz tests on WAF input handling — afl-style inputs checked against every endpoint.",
    swift="Swift tests",
    sw1="`swift test` runs crypto and parsing tests against the iOS module tree in under 1 s. RFC 7748 (X25519) and RFC 8032 (Ed25519) test vectors are part of the suite.",
    sw2="UI tests (`xcodebuild test`) drive SwiftUI previews in a headless simulator and compare snapshots.",
    kotlin="Kotlin tests",
    kt1="`./gradlew test` runs pure-JVM tests (no Android runtime) in a few seconds. Hilt-android-testing handles DI injection in tests.",
    kt2="Instrumented tests (`./gradlew connectedCheck`) run on an emulator and exercise end-to-end flows: login, send message, call.",
    e2e="End-to-end",
    ee1="Playwright tests in `playwright-tests/` drive the web client, spin up a throwaway node, and verify full flows including webrtc call with two headless Chromes.",
)


CLI = section(
    "CLI tools",
    "Scripts for operators under `scripts/` and the integrated `vortex` command.",
    intro="Operators rarely need to touch the codebase. Every administrative action is exposed either through the web admin at `/admin` or through a CLI subcommand.",
    cmds="Commands",
    c1="`python -m vortex_controller.integrity.sign_tool` — re-sign the integrity manifest after a code change.",
    c2="`python -m scripts.backup_db` — dump the DB to a timestamped archive, encrypt with the operator key.",
    c3="`python -m scripts.seed_sample_data` — populate a dev DB with 100 users / 200 rooms / 10 k messages for UI testing.",
    c4="`python -m scripts.rotate_release_key` — generate a new Ed25519 release key, re-sign manifest, publish new pubkey through the controller admin.",
    c5="`python run.py --status` — show node health, active stealth level, federation health.",
    c6="`python run.py --setup` — re-open the setup wizard for edits.",
)


EXTRAS = section(
    "Advanced topics",
    "Topics that deserve their own chapter but fit nowhere else.",
    intro="Small corners of the protocol that matter in production.",
    ratchet="Double Ratchet wire format",
    r1="Every DM message carries a 64-byte header with the sender's ratchet index, the receiving chain index, and the ephemeral public key. Headers are encrypted with a separate header key derived from the root key via HKDF info=\"hdr\".",
    r2="Chains reset every 1000 messages even if no ratchet has occurred, to cap the damage a key compromise could do.",
    prekeys="Prekeys",
    pk1="New contacts exchange prekeys published ahead of time through the node. A client uploads 10 ephemeral prekeys; the node serves them on demand. When running low (< 3 remaining) the client uploads another batch.",
    pk2="The prekey bundle is signed by the device's long-term identity key so an attacker can't swap in forged prekeys even with node-level access.",
    sync="Multi-device sync",
    s1="Each account can have up to 8 active devices. Devices share the root identity but each has its own per-device signing key.",
    s2="New device pairing uses QR code + Ed25519 challenge-response. Existing devices get notified and can revoke a new pairing if it wasn't initiated by them.",
    backups="Encrypted backups",
    bk1="Optional. Encrypted with a 32-byte key derived from the user's seed phrase. Backups are opaque to the node; only a client with the seed can decrypt.",
    bk2="Content: room keys + last 90 days of message ciphertext + contact list + profile. Excludes: local-only drafts, WebRTC call logs.",
)


NETWORKING = section(
    "Networking basics",
    "Ports, protocols, and how to expose a node to the open internet.",
    intro="A typical node listens on 443 (HTTPS/WSS), 3478-3479 (coturn STUN/TURN UDP+TCP), and 49152-65535 (TURN relay range). Firewall rules only need to allow inbound traffic on those ranges.",
    ports="Default ports",
    p1="9000 — HTTPS API + WebSocket (configurable via `PORT`).",
    p2="3478 — coturn STUN/TURN.",
    p3="49152-65535 — coturn relay range for ICE candidates.",
    p4="8800 — controller HTTPS (optional, if co-located).",
    p5="80 — HTTP ACME / Let's Encrypt challenges; redirected to 443 otherwise.",
    ipv6="IPv6",
    i1="Dual-stack by default. Clients on IPv6 connect over v6 directly; the node returns v6 AAAA records in `/v1/entries`.",
    reverse="Behind a reverse proxy",
    rp1="Caddy and nginx configs shipped in `deploy/`. Caddy handles cert auto-renewal; nginx expects an external certbot.",
    rp2="WebSocket upgrade headers are preserved. `X-Forwarded-For` is trusted only from RFC 1918 ranges unless `TRUSTED_PROXIES=...` is set.",
)


CODEBASE = section(
    "Codebase layout",
    "Where to find what.",
    intro="Vortex is a monorepo. Every piece of the system lives under the same git root.",
    layout="Directory map",
    app="`app/` — Python node. Subdirs: `authentication`, `chats`, `files`, `bots`, `federation`, `keys`, `peer`, `push`, `security`, `services`, `session`, `transport`, `utilites`.",
    controller="`vortex_controller/` — Python controller. Entry `main.py`, endpoints in `endpoints/`, integrity helpers in `integrity/`.",
    static="`static/` — web client JS/CSS/HTML. Organized by feature: `chat/`, `rooms/`, `auth/`, `calls/`, `files/`, `bots/`.",
    templates="`templates/` — Jinja2 server-side render for the initial shell. All dynamic behaviour is JS-driven from there.",
    ios="`ios/` — iOS client. `Modules/` is the Swift Package; `VortexApp/` is the app target; `project.yml` is the XcodeGen spec.",
    android="`android/` — Gradle-based Kotlin/Compose project. `app/` is the app module with 22 feature submodules.",
    gravitix="`Gravitix/` — Rust-backed Gravitix bot DSL runtime and compiler.",
    architex="`Architex/` — TypeScript DSL for Mini Apps (see Architex docs).",
    scripts="`scripts/` — operator-side shell and Python tooling.",
    docs="`docs/` and `ARCHITECTURE.md` — prose documentation.",
    alembic="`alembic/` — DB migrations.",
    deploy="`deploy/` — Dockerfiles, systemd units, nginx/Caddy configs, monitoring rules.",
    tests="`tests/` — test suites across all languages; `playwright-tests/` for browser E2E.",
    wizard="`vortex_wizard/` — operator setup GUI (pywebview + FastAPI).",
    mirror="`vortex-introduce-page/` — marketing site.",
    solana="`solana_program/` — on-chain components (name service, treasury).",
)


# Many more smaller sections — kept short-ish so the file stays maintainable.
ACCESSIBILITY = section(
    "Accessibility",
    "VoiceOver, TalkBack, Dynamic Type, RTL, high-contrast.",
    p1="Every interactive element has an accessibility label. Colour choices meet WCAG AA (4.5:1) on the dark theme.",
    p2="iOS: `@accessibilityLabel` on every Button / Image. Android: `contentDescription = ...` on every Composable.",
    p3="Web: `aria-label` / `aria-live` regions for incoming messages. Tab order is left-to-right / top-to-bottom, no keyboard traps.",
    p4="RTL languages (Arabic, Hebrew, Persian, Urdu) flip the whole UI. Chat bubbles mirror; icons mirror where meaningful.",
    p5="Dynamic Type / font scaling support up to 200 % without text clipping or overlap.",
    p6="High-contrast mode bumps border widths from 1 px to 2 px and strengthens accent colour saturation.",
)


ROADMAP = section(
    "Roadmap",
    "What's coming next.",
    p1="**v0.2** — full Kyber PQ handshake by default, dropped if peer doesn't support it.",
    p2="**v0.3** — audio-only group calls with up to 100 participants via SFU.",
    p3="**v0.4** — collaborative canvas / Miro-style shared board, using CRDT (Yjs-style) through the existing messaging layer.",
    p4="**v0.5** — built-in payments via on-chain escrow (Solana + EVM).",
    p5="**v1.0** — the above stabilised, formal security audit completed, reproducible builds across all platforms.",
)


# ── aggregate ─────────────────────────────────────────────────────────

VORTEX_DOCS = {
    "meta": {
        "title": "Vortex Reference",
        "subtitle": "Every subsystem of the Vortex messenger in one place.",
        "intro": "Vortex is a decentralised, end-to-end encrypted messenger. This reference goes from architecture to individual byte layouts so you can audit, extend, or re-implement any part.",
        "howToRead": "Each chapter is self-contained. Start anywhere. Every section links to the relevant source file paths inside the repo.",
        "updatedAt": "Rolling — rebuilt on every release.",
    },
    "architecture":         ARCH,
    "crypto":               CRYPTO,
    "auth":                 AUTH,
    "websocket":            WEBSOCKET,
    "rooms":                ROOMS,
    "files":                FILES,
    "calls":                CALLS,
    "federation":           FED,
    "gossip":               GOSSIP,
    "stealth":              STEALTH,
    "stealthDetail":        STEALTH_LEVELS_DETAIL,
    "bmp":                  BMP,
    "push":                 PUSH,
    "storage":              STORAGE,
    "bots":                 BOTS,
    "controller":           CONTROLLER,
    "deploy":               DEPLOY,
    "mobile":               MOBILE,
    "webclient":            WEBCLIENT,
    "security":             SECURITY,
    "privacy":              PRIVACY,
    "ai":                   AI_FEATURES,
    "monitoring":           MONITORING,
    "testing":              TESTING,
    "cli":                  CLI,
    "extras":               EXTRAS,
    "networking":           NETWORKING,
    "codebase":             CODEBASE,
    "accessibility":        ACCESSIBILITY,
    "roadmap":              ROADMAP,
}


# ── splicing ──────────────────────────────────────────────────────────

def target_paths() -> Iterable[Path]:
    root = Path("/Users/borismaltsev/RustroverProjects")
    yield root / "Vortex/ios/Modules/Sources/I18N/Resources/locales/en.json"
    yield from sorted((root / "vortex-introduce-page/locales").glob("*.json"))


def splice() -> None:
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
