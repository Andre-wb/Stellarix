#!/usr/bin/env python3
"""
Rebuild `vortexDocs.apiSurface` and `vortexDocs.glossary` with their own
structures so every route / term is its own expandable tree leaf.

apiSurface shape:
  apiSurface.<group>.<slug> = {
    title, subtitle,
    h1 (Purpose)           + h1_a / h1_b / h1_c / h1_f
    h2 (Authentication)    + h2_a / h2_b / h2_c
    h3 (Request)           + h3_a / h3_f
    h4 (Response)          + h4_a / h4_f
    h5 (Errors)            + h5_a / h5_f
    h6 (Example)           + h6_a / h6_f
  }

glossary shape:
  glossary.<slug> = {
    title, subtitle,
    h1 (Definition) + h1_a (meaning) / h1_b (context) / h1_c (history) / h1_f (formula/example)
    h2 (Where used) + h2_a (modules/files)
    h3 (Related)    + h3_a (cross-refs)
  }
"""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("/Users/borismaltsev/RustroverProjects")
IOS_EN = ROOT / "Vortex/ios/Modules/Sources/I18N/Resources/locales/en.json"
WEB_LOCALES = sorted((ROOT / "vortex-introduce-page/locales").glob("*.json"))


def route(method: str, path: str, title: str, subtitle: str,
          purpose_desc: str, purpose_mech: str = "", purpose_hist: str = "",
          request_desc: str = "", request_schema: str = "",
          response_desc: str = "", response_schema: str = "",
          auth: str = "jwt", auth_hist: str = "",
          errors_desc: str = "", errors_table: str = "",
          example_desc: str = "", example_curl: str = "") -> dict:
    return {
        "title": f"{method} {path}",
        "subtitle": subtitle,
        "intro": f"{title} — auth: **{auth}**.",
        "h1": "Purpose",
        "h1_a": purpose_desc,
        "h1_b": purpose_mech or f"Handler for this route lives in the corresponding module under `app/`. The path pattern `{path}` is declared with `@router.{method.lower()}('{path}')`.",
        "h1_c": purpose_hist or f"Shipped in an early Vortex release as part of the `{title}` capability.",
        "h1_f": f"{method} {path}",
        "h2": "Authentication",
        "h2_a": f"Requires: **{auth}**. The middleware `app/security/middleware.py::auth_required` gates this route and rejects with `401 unauthenticated` if the required credential is missing or invalid.",
        "h2_b": (
            "- `none`  — unauthenticated (pre-login).\n"
            "- `jwt`   — Bearer JWT access token in the `Authorization` header.\n"
            "- `refresh` — Bearer JWT refresh token.\n"
            "- `admin` — JWT whose claims contain `is_admin: true`.\n"
            "- `peer-signed` — request body signed by a trusted peer's Ed25519 key."
        ),
        "h2_c": auth_hist or "The auth tier reflects the principle of least privilege: pre-login endpoints are strictly limited to account creation and recovery; everything behind a JWT sees a real user; admin endpoints show a badge in the UI so misuse is observable.",
        "h3": "Request",
        "h3_a": request_desc,
        "h3_f": request_schema,
        "h4": "Response",
        "h4_a": response_desc,
        "h4_f": response_schema,
        "h5": "Errors",
        "h5_a": errors_desc or "Standard Vortex error envelope `{error, status, path}`. `401` on bad credentials; `403` on insufficient privilege; `422` on validation; `429` on rate limit; `5xx` on internal error.",
        "h5_f": errors_table or (
            "401  unauthenticated        missing/invalid token\n"
            "403  forbidden              insufficient privilege\n"
            "422  validation_error       field constraint violated\n"
            "429  rate_limited           too many attempts\n"
            "500  internal_error         unexpected server fault"
        ),
        "h6": "Example",
        "h6_a": example_desc or f"Typical `{method}` call in curl:",
        "h6_f": example_curl or f"curl -X {method} 'https://node.example{path}' \\\n  -H 'Content-Type: application/json' \\\n  -H 'Authorization: Bearer $TOKEN'",
    }


def simple_route(method: str, path: str, subtitle: str, purpose: str, auth: str = "jwt") -> dict:
    return route(
        method=method, path=path,
        title=path.rsplit("/", 1)[-1] or path,
        subtitle=subtitle,
        purpose_desc=purpose,
        auth=auth,
    )


AUTH_GROUP = {
    "title": "Authentication",
    "subtitle": "Register, login, refresh, revoke — and the recovery paths.",
    "intro": "All routes under `/api/authentication/*`. The JWT that comes out of a successful login carries `{sub: user_id, jti: device_id, typ: access|refresh}` signed HS256 over the node's secret. Access lasts 15 min, refresh 30 days.",
    "register": route(
        method="POST", path="/api/authentication/register",
        title="Create account",
        subtitle="Create a new user with X25519 identity + Argon2id password.",
        auth="none",
        purpose_desc="Creates a new user account and issues an initial JWT pair. Binds the user's long-lived X25519 public key to the account from the very first call.",
        purpose_mech="Node validates all fields via Pydantic, checks username and x25519_public_key uniqueness, runs Argon2id (m=64MiB, t=3, p=4) on the password, inserts into `users`, `user_devices`, `push_subscriptions`, mints access + refresh JWTs.",
        purpose_hist="Shipped in v0.0.1 as the first endpoint. The X25519 pubkey parameter was added in v0.0.2 after realising identity and account need to be created atomically — otherwise the server could MITM a user between register and first key upload.",
        request_desc="JSON body with mandatory username + password + x25519_public_key; optional phone (E.164), email (RFC 5322 lite), display_name, avatar_emoji, invite_code, kyber_public_key.",
        request_schema=(
            "{\n"
            "  \"username\":          \"alice\",         // [a-z0-9_]{3,30}\n"
            "  \"password\":          \"…\",             // ≥ 8 chars\n"
            "  \"x25519_public_key\": \"<64-hex>\",      // 32 bytes hex\n"
            "  \"display_name\":      \"Alice\",         // optional\n"
            "  \"phone\":             \"+15551234567\",  // optional, E.164\n"
            "  \"email\":             \"a@example.com\", // optional\n"
            "  \"avatar_emoji\":      \"🦊\",            // optional, 1 emoji\n"
            "  \"invite_code\":       \"…\",             // optional if INVITE mode\n"
            "  \"kyber_public_key\":  \"<1184 hex>\"     // optional, for PQ\n"
            "}"
        ),
        response_desc="201 Created with the JWT pair and the new user's canonical profile.",
        response_schema=(
            "{\n"
            "  \"ok\":                 true,\n"
            "  \"access_token\":       \"eyJ…\",    // 15 min TTL\n"
            "  \"refresh_token\":      \"eyJ…\",    // 30 day TTL\n"
            "  \"user_id\":            42,\n"
            "  \"username\":           \"alice\",\n"
            "  \"display_name\":       \"Alice\",\n"
            "  \"avatar_url\":         null,\n"
            "  \"x25519_public_key\":  \"<64 hex>\",\n"
            "  \"kyber_public_key\":   \"<hex>\"\n"
            "}"
        ),
        errors_desc="Standard validation + two domain-specific rejections. `409 username_taken` when the name exists; `409 pubkey_reused` when the X25519 public key already registered to another account.",
        errors_table=(
            "409  username_taken        username collision\n"
            "409  pubkey_reused         X25519 pubkey already used\n"
            "422  validation_error      field constraint violated\n"
            "429  rate_limited          >5 registrations/min/IP\n"
            "403  registration_closed   node is in INVITE mode and code missing"
        ),
        example_desc="Minimal curl without phone/email:",
        example_curl=(
            "curl -X POST 'https://node.example/api/authentication/register' \\\n"
            "  -H 'Content-Type: application/json' \\\n"
            "  -d '{\n"
            "    \"username\":\"alice\",\n"
            "    \"password\":\"correct horse battery staple\",\n"
            "    \"x25519_public_key\":\"8ef8e663…\",\n"
            "    \"display_name\":\"Alice\",\n"
            "    \"avatar_emoji\":\"🦊\"\n"
            "  }'"
        ),
    ),
    "login": route(
        method="POST", path="/api/authentication/login",
        title="Sign in",
        subtitle="Verify username + password, return JWT pair.",
        auth="none",
        purpose_desc="Exchanges credentials for a JWT pair. The password is verified against the Argon2id hash in `users.password_hash`. Timing is constant-time even for unknown usernames to resist enumeration.",
        purpose_mech="Looks up the user by lowercased username, runs `argon2.PasswordHasher.verify(stored, submitted)`. If the user doesn't exist, verifies against a pre-computed dummy hash to equalise timing. Success → issue JWT + `user_devices` row.",
        purpose_hist="Shipped with register in v0.0.1. Constant-time dummy hashing added in v0.0.2 after researchers showed timing enumeration on the initial design.",
        request_schema=(
            "{\n"
            "  \"username\": \"alice\",\n"
            "  \"password\": \"correct horse battery staple\",\n"
            "  \"totp\":     \"123456\"     // required if 2FA enabled\n"
            "}"
        ),
        response_schema=(
            "on success:  201 + JWT envelope (same shape as register)\n"
            "on 2FA needed: 200 { \"needs_2fa\": true } (no JWT yet)\n"
            "on failure:   401 { \"error\":\"invalid_credentials\" }"
        ),
        errors_table=(
            "401  invalid_credentials    bad username or password\n"
            "401  account_suspended      account is suspended\n"
            "401  totp_required          supply totp and retry\n"
            "429  rate_limited           >10 attempts/min/IP"
        ),
        example_curl=(
            "curl -X POST 'https://node.example/api/authentication/login' \\\n"
            "  -H 'Content-Type: application/json' \\\n"
            "  -d '{\"username\":\"alice\",\"password\":\"…\"}'"
        ),
    ),
    "refresh": route(
        method="POST", path="/api/authentication/refresh",
        title="Refresh access token",
        subtitle="Trade a refresh JWT for a fresh access JWT.",
        auth="refresh",
        purpose_desc="Mints a fresh 15-minute access token without asking the user for the password again. Used when the current access token is near expiry or has just returned a 401.",
        purpose_mech="Decodes and validates the refresh token (signature, exp, not-revoked), mints a new access JWT with the same `jti`. If `ROTATE_REFRESH=true`, also issues a new refresh.",
        purpose_hist="Follows RFC 6749 OAuth 2.0. Refresh rotation is off by default to avoid races when multiple clients refresh concurrently.",
        request_schema="{ \"refresh_token\": \"eyJ…\" }",
        response_schema=(
            "{\n"
            "  \"access_token\":  \"eyJ…\",\n"
            "  \"refresh_token\": \"eyJ…\"      // only if ROTATE_REFRESH=true\n"
            "}"
        ),
        errors_table=(
            "401  token_expired          refresh has expired\n"
            "401  token_revoked          device was revoked\n"
            "401  token_malformed        JWT parse failure"
        ),
    ),
    "logout": simple_route(
        "POST", "/api/authentication/logout",
        "End current session",
        "Marks the current device as revoked. Subsequent refreshes with the now-revoked device_id return 401.",
    ),
    "devices": simple_route(
        "GET", "/api/authentication/devices",
        "List active devices",
        "Returns the list of `user_devices` rows with `revoked_at IS NULL` belonging to the current user.",
    ),
    "revoke": simple_route(
        "POST", "/api/authentication/devices/{id}/revoke",
        "Revoke a specific device",
        "Sets `revoked_at = NOW()` on the target device row. Any refresh attempt with that device's refresh token then fails.",
    ),
    "passwordChange": simple_route(
        "POST", "/api/authentication/password-change",
        "Rotate password",
        "Verifies the current password, re-hashes the new one with Argon2id, updates `users.password_hash`.",
    ),
    "passwordReset": simple_route(
        "POST", "/api/authentication/password-reset",
        "Start password reset flow (none auth)",
        "Sends a one-time reset link to the email on file. Noop if the email doesn't match any user (to avoid enumeration).",
        auth="none",
    ),
    "avatarUpload": simple_route(
        "POST", "/api/authentication/avatar",
        "Upload avatar photo",
        "Multipart upload; server enforces ≤5 MB, resizes to 256×256 JPEG q=85, stores as `uploads/avatars/<hex>.jpg`, updates `users.avatar_url`.",
    ),
    "totpSetup": simple_route(
        "POST", "/api/authentication/2fa/setup",
        "Begin TOTP enrolment",
        "Generates a random 160-bit secret, returns base32 string + otpauth URI for QR scanning. User must verify a sample code via /2fa/verify to finalise.",
    ),
    "totpVerify": simple_route(
        "POST", "/api/authentication/2fa/verify",
        "Finalise TOTP enrolment",
        "Verifies a sample 6-digit code against the pending secret; on success, persists the secret and returns 12 backup codes.",
    ),
    "totpDisable": simple_route(
        "DELETE", "/api/authentication/2fa",
        "Disable TOTP",
        "Verifies current password + current TOTP; on success, deletes the secret.",
    ),
    "profile": simple_route(
        "GET", "/api/authentication/profile",
        "Full profile for the current user",
        "Returns every non-sensitive column from `users` plus aggregates (room count, unread count, premium tier).",
    ),
    "profilePatch": simple_route(
        "PATCH", "/api/authentication/profile",
        "Edit profile fields",
        "Updates `display_name`, `phone`, `email`, `avatar_emoji`, `bio`. Phone/email trigger verification flows if changed.",
    ),
    "challenge": simple_route(
        "POST", "/api/authentication/challenge",
        "X25519 challenge (multi-account)",
        "Issues a nonce bound to the user's X25519 public key. Client signs to prove possession.",
        auth="none",
    ),
    "challengeVerify": simple_route(
        "POST", "/api/authentication/challenge/verify",
        "Verify X25519 challenge",
        "Accepts the signed nonce, verifies against the stored X25519 pubkey, issues JWT.",
        auth="none",
    ),
    "passkeyBegin": simple_route(
        "POST", "/api/authentication/passkey/begin",
        "Begin passkey authentication",
        "Server issues a 32-byte challenge the authenticator will sign.",
        auth="none",
    ),
    "passkeyFinish": simple_route(
        "POST", "/api/authentication/passkey/finish",
        "Complete passkey authentication",
        "Server verifies the authenticator's signed attestation and issues JWT.",
        auth="none",
    ),
    "qrBegin": simple_route(
        "POST", "/api/authentication/qr/begin",
        "Issue QR pairing nonce",
        "Bound to the current user; TTL 60 s; one-shot. The nonce is embedded in a QR displayed on the current device.",
    ),
    "qrVerify": simple_route(
        "POST", "/api/authentication/qr/verify",
        "Accept QR on new device",
        "The new device posts the scanned nonce and its X25519 pubkey; server associates them with the original user; issues JWT to the new device.",
        auth="none",
    ),
}


ROOMS_GROUP = {
    "title": "Rooms",
    "subtitle": "List, create, join, leave, edit — plus members, invites, messages pagination.",
    "intro": "All routes under `/api/rooms/*`. A room is a bag of members plus a shared secret; the same endpoints cover DM / private group / public group / channel.",
    "list": simple_route("GET", "/api/rooms",
        "List the caller's rooms",
        "Returns every `rooms` row where the caller has a `room_members` entry. Paginated via `?cursor=` + `?limit=`."),
    "create": simple_route("POST", "/api/rooms",
        "Create a new room",
        "Accepts `{type, name, is_private, is_channel, members}`. Creator becomes owner; members added in a single transaction; first root_key envelope minted client-side then POSTed as a second call."),
    "get": simple_route("GET", "/api/rooms/{id}",
        "Fetch room metadata",
        "Returns the `rooms` row plus member count, last message id, pinned message ids. Requires membership."),
    "patch": simple_route("PATCH", "/api/rooms/{id}",
        "Edit room metadata",
        "Owner / admin only. Accepts `name`, `description`, `avatar_url`, `is_private`. Changes emit a system message in the room so members see them."),
    "delete": simple_route("DELETE", "/api/rooms/{id}",
        "Delete room",
        "Owner only. Cascades to `room_members`, `messages`, `reactions`, `read_receipts`. Federated peers notified to purge their copies."),
    "members": simple_route("GET", "/api/rooms/{id}/members",
        "Member list",
        "Returns (user_id, role, joined_at, muted_until). Large rooms paginate via `?cursor=` + `?limit=`."),
    "invite": simple_route("POST", "/api/rooms/{id}/invite",
        "Create invite code",
        "Admin only. Accepts optional `max_uses`, `expires_at`, `assign_role`. Returns a 32-hex-char code."),
    "join": simple_route("POST", "/api/rooms/join",
        "Join via invite code",
        "Server validates the code (not revoked, not expired, used < max_uses), increments `used_count`, inserts `room_members`, returns full room metadata."),
    "leave": simple_route("POST", "/api/rooms/{id}/leave",
        "Leave a room",
        "Deletes the caller's `room_members` row. If the caller was the owner, transfers ownership to the earliest-joined admin. Triggers key rotation for remaining members."),
    "avatarUpload": simple_route("POST", "/api/rooms/{id}/avatar",
        "Upload room avatar",
        "Admin only; same constraints as user avatar — ≤ 5 MB, resized to 256×256 JPEG."),
    "messages": simple_route("GET", "/api/rooms/{id}/messages?since=&limit=",
        "Paginated message fetch",
        "Returns at most `limit` messages with id > `since`, newest first. Default limit 50, max 500. Deleted rows include `deleted_at` and null ciphertext."),
    "messagesPost": simple_route("POST", "/api/rooms/{id}/messages",
        "Send a new message",
        "Accepts `{ciphertext, nonce, reply_to?, thread_id?}`. Node generates message_id, persists row, fans out over WebSocket."),
    "read": simple_route("POST", "/api/rooms/{id}/read",
        "Mark messages read up to id",
        "UPSERTS `read_receipts(room_id, user_id, message_id, read_at)`. Broadcast `{type:\"r\"}` to other subscribers unless caller opted out of read receipts."),
    "draftPut": simple_route("PUT", "/api/rooms/{id}/draft",
        "Save draft",
        "Upserts `drafts(room_id, user_id, text, updated_at)`. Draft is server-visible plaintext — deliberately, so it syncs across devices."),
    "draftGet": simple_route("GET", "/api/rooms/{id}/draft",
        "Fetch saved draft",
        "Returns the draft text or 204 if none."),
    "draftDelete": simple_route("DELETE", "/api/rooms/{id}/draft",
        "Clear draft",
        "Deletes the row. Typical when the user sends the message."),
    "pin": simple_route("POST", "/api/rooms/{id}/pin",
        "Pin a message",
        "Admin only. Up to 10 pinned messages per room. Inserts into `room_pins`; broadcast `{type:\"m\", event:\"pinned\"}`."),
    "unpin": simple_route("DELETE", "/api/rooms/{id}/pin/{message_id}",
        "Unpin a message",
        "Admin only. Deletes the row; broadcast `{type:\"m\", event:\"unpinned\"}`."),
}


MESSAGES_GROUP = {
    "title": "Messages",
    "subtitle": "Edit, delete, react, thread, context.",
    "intro": "Routes scoped to a single message id. Most checks enforce ownership (only the sender can edit their own); admin overrides apply where noted.",
    "edit": simple_route("PATCH", "/api/messages/{id}",
        "Edit own message",
        "Replaces `ciphertext` + `nonce` in place; sets `edited_at = NOW()`. Only the original sender can edit."),
    "delete": simple_route("DELETE", "/api/messages/{id}",
        "Delete message",
        "Soft-delete: sets `deleted_at = NOW()` and nulls `ciphertext`. Owner deletes their own; admin can delete any; row stays for reply-chain integrity."),
    "react": simple_route("POST", "/api/messages/{id}/react",
        "Add reaction",
        "Inserts `reactions(message_id, user_id, emoji)`; idempotent on duplicate. Broadcasts aggregated reactions."),
    "unreact": simple_route("DELETE", "/api/messages/{id}/react/{emoji}",
        "Remove reaction",
        "Deletes the row; broadcasts updated aggregate."),
    "thread": simple_route("POST", "/api/messages/{id}/thread",
        "Create thread",
        "Creates a pseudo-room rooted at the message; its root key is derived from the parent room's key with `info=\"thread:<parent_id>\"`."),
    "context": simple_route("GET", "/api/messages/{id}/context",
        "Surrounding messages",
        "Returns the 20 messages before and 20 after. Used when a search hit opens into a room."),
}


FILES_GROUP = {
    "title": "Files",
    "subtitle": "Upload, resumable, download, thumbnails.",
    "intro": "File bytes are client-encrypted before POST; the server never holds plaintext. The 5 MB single-shot cap is enforced at the receive buffer; larger files use the resumable protocol.",
    "upload": simple_route("POST", "/api/files",
        "Single-shot upload (≤5 MB)",
        "Multipart with fields `file`, `plain_blake3`, `mime_type`. MIME is re-checked with python-magic against a deny list."),
    "resumeInit": simple_route("POST", "/api/files/resumable/init",
        "Initialise resumable upload",
        "Accepts `{filename, size, chunk_size_hint}`; returns `{upload_id, chunk_size}`. Upload_id TTL is 24 h."),
    "resumeChunk": simple_route("PUT", "/api/files/resumable/{id}/chunk/{offset}",
        "Upload a chunk",
        "Raw body is the ciphertext for this chunk. Offset must be multiple of chunk_size. Missing offsets can be posted in any order."),
    "resumeFinalise": simple_route("POST", "/api/files/resumable/{id}/finalise",
        "Assemble uploaded chunks",
        "Verifies all offsets present, plain_blake3 matches expected, stores; returns `{file_id, url}`."),
    "download": simple_route("GET", "/api/files/{id}",
        "Download encrypted file",
        "Returns the raw ciphertext stream. Recipient holds the file_root key (sent in the referencing room message) for decryption."),
    "thumb": simple_route("GET", "/api/files/{id}/thumb",
        "Download thumbnail",
        "Same envelope as the main file; encrypted under the same file_root with a different nonce."),
}


CALLS_GROUP = {
    "title": "Calls",
    "subtitle": "WebRTC signalling — offer, answer, candidate; TURN credentials.",
    "intro": "Node is signalling-only. Once peers exchange SDP and ICE candidates, media flows directly (or through coturn if NAT traversal fails).",
    "start": simple_route("POST", "/api/calls/{room_id}/start",
        "Initiate call",
        "Allocates a `call_id`, broadcasts `{type:\"c\", kind:\"invite\"}` to every socket in the room."),
    "accept": simple_route("POST", "/api/calls/{call_id}/accept",
        "Accept incoming call",
        "Records participant as accepted; broadcasts `{kind:\"accepted\"}` so the caller can send its offer."),
    "end": simple_route("POST", "/api/calls/{call_id}/end",
        "Hang up",
        "Any participant can end. Records duration, codec used, packet loss, in `call_records`. Broadcasts `{kind:\"ended\"}`."),
    "signal": simple_route("POST", "/api/calls/{call_id}/signal",
        "Forward SDP / ICE",
        "Generic passthrough for offer/answer/candidate frames. Node does only light validation (no private-IP SDP leaks, no bypass TURN)."),
    "turn": simple_route("GET", "/api/calls/{call_id}/turn",
        "Fetch short-lived TURN credentials",
        "Generates HMAC-signed `username = <expiry>:<user_id>`, `password = base64(HMAC-SHA1(server_secret, username))`. TTL 24 h."),
}


PUSH_GROUP = {
    "title": "Push",
    "subtitle": "APNs / FCM / Web Push subscriptions.",
    "intro": "Clients register once per device. Payloads are sealed with a recipient-specific X25519 pubkey so the push provider only sees an opaque blob.",
    "subscribe": simple_route("POST", "/api/push/subscribe",
        "Register device for push",
        "Upserts `push_subscriptions(user_id, endpoint, p256dh, auth, platform, last_refreshed_at)`. Clients re-subscribe on every app launch."),
    "unsubscribe": simple_route("POST", "/api/push/unsubscribe",
        "Unregister device",
        "Deletes the row. Typical on logout or explicit user \"disable push\"."),
}


FEDERATION_GROUP = {
    "title": "Federation",
    "subtitle": "Peer discovery, signed message delivery.",
    "intro": "The thin external surface each node exposes to its federation peers. All POSTs require a valid Ed25519 signature from a trusted peer.",
    "info": simple_route("GET", "/federation/info",
        "Node pubkey + capabilities",
        "Returns `{pubkey, version, features, supported_curves}`. Pre-auth because prospective peers need it to pin.",
        auth="none"),
    "deliver": simple_route("POST", "/federation/deliver",
        "Inbound cross-node envelope",
        "Accepts `{envelope, sig}`; verifies sig against the source_node's pubkey in `federations`; unwraps the inner envelope and persists to `messages`.",
        auth="peer-signed"),
}


ADMIN_GROUP = {
    "title": "Admin",
    "subtitle": "Operator-only routes for metrics, audit, peer management, user moderation.",
    "intro": "All routes require `admin` JWT. The admin UI at `/admin` calls these; direct curl works too with a valid admin token.",
    "metrics": simple_route("GET", "/api/admin/metrics",
        "Prometheus metrics",
        "Standard Prometheus exposition format. Covers RED + USE signals across the stack.",
        auth="admin"),
    "audit": simple_route("GET", "/api/admin/audit",
        "Audit log",
        "Returns hash-chained rows from `audit_log`, newest first, paginated.",
        auth="admin"),
    "peersAdd": simple_route("POST", "/api/admin/peers",
        "Add trusted peer",
        "Inserts into `federations`; requires the operator to sign the admin request with the release key.",
        auth="admin"),
    "peersRemove": simple_route("DELETE", "/api/admin/peers/{pubkey}",
        "Remove trusted peer",
        "Soft-delete (`revoked_at = NOW()`). Federated traffic from that pubkey is rejected.",
        auth="admin"),
    "userSuspend": simple_route("POST", "/api/admin/user/{id}/suspend",
        "Suspend account",
        "Sets `users.is_active = false`; invalidates all refresh tokens.",
        auth="admin"),
    "userUnsuspend": simple_route("POST", "/api/admin/user/{id}/unsuspend",
        "Re-enable account",
        "Sets `users.is_active = true`. Refresh tokens had to be manually re-issued by the user.",
        auth="admin"),
}


BMP_GROUP = {
    "title": "BMP",
    "subtitle": "Blind Mailbox Protocol — anonymous store-and-forward.",
    "intro": "Two routes only. Deposit is public; pickup requires the recipient's JWT. Mailbox id is a one-way hash of the recipient pubkey so middle nodes can't identify recipients.",
    "deposit": simple_route("POST", "/bmp/deposit",
        "Deposit a blob",
        "Accepts `{mailbox_id: 32B, blob: ≤1 MB}`. Stores for up to 7200 s; announces mailbox_id in the next gossip Bloom filter.",
        auth="none"),
    "messages": simple_route("GET", "/bmp/messages",
        "Pull mailbox contents",
        "Returns every blob whose mailbox_id matches one the authenticated user's clients computed from their pubkey.",
        auth="jwt"),
}


API_SURFACE = {
    "title": "API surface",
    "subtitle": "Every HTTP endpoint the node exposes, grouped by area.",
    "intro": "This is the authoritative list of public routes. Each endpoint card expands to show purpose, auth tier, request / response schemas, error table, and a curl example. Internal housekeeping routes under `/internal/*` are omitted by policy.",
    "auth":       AUTH_GROUP,
    "rooms":      ROOMS_GROUP,
    "messages":   MESSAGES_GROUP,
    "files":      FILES_GROUP,
    "calls":      CALLS_GROUP,
    "push":       PUSH_GROUP,
    "federation": FEDERATION_GROUP,
    "admin":      ADMIN_GROUP,
    "bmp":        BMP_GROUP,
}


def term(title: str, subtitle: str,
        definition: str, context: str, history: str,
        formula: str = "",
        usage: str = "", related: str = "") -> dict:
    return {
        "title": title,
        "subtitle": subtitle,
        "intro": definition,
        "h1": "Definition",
        "h1_a": definition,
        "h1_b": context,
        "h1_c": history,
        "h1_f": formula or "(no formula — conceptual term)",
        "h2": "Where used in Vortex",
        "h2_a": usage or "This term appears throughout the codebase and documentation; grep for the lowercase form in `app/` and the language clients to see every call site.",
        "h3": "Related terms",
        "h3_a": related or "See the rest of the Glossary chapter for connected concepts.",
    }


GLOSSARY = {
    "title": "Glossary",
    "subtitle": "Every term used in the Vortex docs, spelled out.",
    "intro": "Alphabetical reference. Each term card expands into a full definition, where it is used, its history, and a formula or example when applicable.",

    "aead": term("AEAD", "Authenticated Encryption with Associated Data.",
        definition="AEAD (Authenticated Encryption with Associated Data) is a cryptographic primitive that combines confidentiality and integrity in one call. Given a key, nonce, plaintext, and optional associated data (AAD), it produces ciphertext + authentication tag such that any tampering with either plaintext, ciphertext, or AAD fails verification.",
        context="Vortex's AEAD is always AES-256-GCM. The AAD slot carries context the recipient must know to decrypt correctly (room id, file id, offset). Binding AAD prevents cross-context replay — a ciphertext from room A can't be decrypted as room B.",
        history="AEAD as a named primitive traces to Rogaway 2002. GCM (Galois/Counter Mode) was standardised by NIST in SP 800-38D (2007). Became the default AEAD in TLS 1.3 (RFC 8446, 2018). Every modern secure protocol uses an AEAD.",
        formula="AEAD.Enc(k, n, pt, aad) = (ct, tag)     // ct = len(pt) bytes, tag = 16 bytes\nAEAD.Dec(k, n, ct, tag, aad) = pt  or  ⊥",
        usage="`app/security/crypto.py::aes_gcm_encrypt`, iOS `VortexCrypto.AEAD`, Android `crypto/aead/AesGcmAead`.",
        related="AES-GCM, HKDF, nonce, tag"),

    "alembic": term("Alembic", "Database migration tool for SQLAlchemy.",
        definition="Alembic is the canonical migration framework for SQLAlchemy. Each migration is a Python file with `upgrade()` and `downgrade()` functions that describe schema changes as SQL or ORM operations.",
        context="Vortex uses Alembic with linear revision history (no branching). `alembic upgrade head` runs on every Docker container start. `alembic downgrade -1` reverts one step for rollback. Dev mode uses `create_all + ALTER TABLE fallback` so local iteration doesn't need migrations on every rebase.",
        history="Alembic was written by Mike Bayer (author of SQLAlchemy) in 2011 as the successor to `sqlalchemy-migrate`. Django's built-in migrations (2014) borrowed the core model. Alembic stayed ahead on features — rollback, autogenerate, branching — though Vortex doesn't use branches.",
        formula="alembic/versions/\n  20240101_<revision>_<slug>.py    each with upgrade()/downgrade()",
        usage="`alembic.ini`, `alembic/versions/*`. Managed via `make db-migrate`.",
        related="SQLAlchemy, Postgres, SQLite, schema"),

    "apns": term("APNs", "Apple Push Notification service.",
        definition="APNs is Apple's push-notification service for iOS, iPadOS, macOS, watchOS, tvOS. Apps register a device token and providers send notification payloads to APNs which fans them out to devices.",
        context="Vortex uses APNs with sealed-push envelopes: the node encrypts each notification payload for the recipient's X25519 pubkey; APNs sees only an opaque blob. The iOS client's Notification Service Extension decrypts in a separate process before the banner renders.",
        history="APNs launched with iOS 3.0 (2009). Sealed push / mutable content support came with iOS 10 (2016). Token-based auth (.p8) replaced certificate-based auth as the default in 2016. Vortex uses token auth with 60-minute provider tokens.",
        formula="POST https://api.push.apple.com/3/device/<device_token>\nHeaders: apns-topic: <bundle_id>, apns-push-type: alert, apns-collapse-id: room:42\nBody:    {aps: {alert: {title, body}}, data: <sealed>}",
        usage="`app/services/sealed_push.py`, iOS `Push/impl/APNsPushSubscriber.swift`.",
        related="FCM, Web Push, sealed push, Notification Service Extension"),

    "argon2id": term("Argon2id", "Memory-hard password hash (RFC 9106).",
        definition="Argon2id is a memory-hard, side-channel-resistant password hashing function. Parameters: memory size (m), time cost (iterations, t), parallelism (lanes, p), and hash length. The 'id' variant mixes data-independent (Argon2i) and data-dependent (Argon2d) passes.",
        context="Vortex uses Argon2id with m=64MiB, t=3, p=4, hashLen=32. This takes ~0.5 s on an iPhone X (our slowest supported device) and roughly 5 ms on a high-end ASIC — the 100× speedup is negligible compared to SHA-256-based hashes where ASICs win by millions.",
        history="Argon2 won the 2015 Password Hashing Competition organised by Dmitry Khovratovich and Alex Biryukov. Standardised as RFC 9106 in 2021. Used by 1Password, Bitwarden, LastPass. Vortex's parameters come from OWASP 2023 recommendations.",
        formula="Argon2id(password, salt, m, t, p, hashLen) → hash\ndefault: m=64MiB, t=3, p=4, hashLen=32\ncost ≈ 0.5s on iPhone X; ~5ms on ASIC (100× attacker speedup)",
        usage="`app/security/crypto.py::hash_password`, iOS `VortexCrypto.Argon2idHasher`, Android `crypto/hash/Argon2idHasher`.",
        related="password hashing, AEAD, HKDF, salt"),

    "blake3": term("BLAKE3", "Fast cryptographic hash.",
        definition="BLAKE3 is a cryptographic hash function descended from BLAKE2 and BLAKE. Produces arbitrary-length output from arbitrary input; 10× faster than SHA-256 on large blobs thanks to internal tree hashing.",
        context="Vortex uses BLAKE3 for file integrity: each uploaded file carries a `plain_blake3` hash of its decrypted content so recipients can verify after download + decrypt. The DB column is historically named `sha256` for migration compatibility but contains BLAKE3 output.",
        history="BLAKE3 was released by Jack O'Connor et al. in 2020. Descended from BLAKE, which was a SHA-3 finalist in 2012. The tree-hashing design lets BLAKE3 scale with cores for huge inputs. SHA-256 is still faster for small inputs; BLAKE3 dominates on anything > 4 KiB.",
        formula="BLAKE3(bytes) = 32 bytes   // default output\nBLAKE3(bytes, len) = len bytes (XOF)\nthroughput: ~3 GB/s on Apple Silicon vs SHA-256 ~500 MB/s",
        usage="`vortex_chat` Rust extension, iOS `VortexCrypto.Blake3Hasher`, Android `crypto/hash/Blake3Hasher`.",
        related="SHA-256, file integrity, tag"),

    "bmp": term("BMP", "Blind Mailbox Protocol.",
        definition="BMP is Vortex's anonymous store-and-forward layer. Senders deposit encrypted blobs at any gossip-enabled node, keyed by a one-way hash of the recipient's pubkey. Blobs ride gossip until the recipient's node pulls.",
        context="BMP provides three independent privacy properties: sender-hiding (TLS + optional onion), recipient-hiding (mailbox_id is opaque to middle nodes), content-hiding (blob is already E2E-encrypted). Max blob 1 MB, per-node cap 500 MB, deposit rate 10/min/IP, TTL 7200 s.",
        history="BMP was designed from scratch by the Vortex team. We built it because no mainstream messenger was willing to pay the engineering cost of hiding metadata end-to-end — they encrypt content but leak the social graph. Our position from day one was that a secure messenger that leaks who-talks-to-whom is only half secure. BMP closes that half by making sender, recipient, and content independently opaque, on top of Vortex's own gossip mesh rather than bolted-on infrastructure.",
        formula="mailbox_id = HKDF(recipient_pubkey, info=\"bmp-v1\", len=32)\nDeposit:  POST /bmp/deposit  {mailbox_id, blob ≤1MB}\nPickup:   GET  /bmp/messages  (auth'd)",
        usage="`app/transport/blind_mailbox.py`.",
        related="gossip, onion service, sealed sender, Pond"),

    "cbor": term("CBOR", "Concise Binary Object Representation.",
        definition="CBOR (RFC 8949) is a binary data format designed for small code size and fast encoding. Superset of JSON's data model, binary-encoded, strictly deterministic.",
        context="Vortex uses CBOR as the payload format inside AES-GCM envelopes. ~30 % smaller than JSON on unicode-heavy chat; strict parsing (no whitespace ambiguity) resists parser-differential attacks; schema-free so adding a field doesn't require a .proto recompilation.",
        history="CBOR was standardised as RFC 7049 in 2013, updated to RFC 8949 in 2020. Used by Signal (internal framing since 2017), Matrix's state-resolution layer, WebAuthn (attestation objects). Picked by Vortex in v0.0.2 after comparing against JSON and protobuf.",
        formula="CBOR encoding: {major_type (3 bits), argument (5 bits), [data]}\nmap:    type=5   pairs\narray:  type=4   elements\ntext:   type=3   bytes\nbytes:  type=2   raw",
        usage="Every message envelope, every sealed-push payload, every federation envelope.",
        related="JSON, protobuf, AEAD"),

    "controller": term("Controller", "Vortex's attestation + discovery service.",
        definition="The controller is a separate Python process (`vortex_controller`) whose only job is publishing the signed manifest (`INTEGRITY.sig.json`) and entry URLs. Clients pin the controller's Ed25519 pubkey at release time.",
        context="Exposes a tiny API surface (~12 routes). The narrow surface is deliberate — it's the highest-value attack target once clients pin. Mirrors run the same code with the same release key; DNS/SNS/IPFS publish lists of mirrors.",
        history="Introduced in v0.0.3 after the early monolith version tied node attestation to the node itself (a compromised node could lie about its own code). Splitting attestation into a separate process modeled after Debian's Release.gpg + Chrome's root store.",
        formula="GET /v1/integrity  → {status, signed_by, matched, mismatched, …}\nGET /v1/health     → {status, version, pubkey, stats}\nGET /v1/entries    → [{protocol, url}, …]\nGET /v1/mirrors    → [controller_url, …]",
        usage="`vortex_controller/main.py`, `keys/release.key`, `INTEGRITY.sig.json`.",
        related="integrity manifest, release key, mirror, trusted_nodes"),

    "doubleRatchet": term("Double Ratchet", "Signal's per-DM forward-secrecy protocol.",
        definition="The Double Ratchet combines a Diffie-Hellman ratchet with a symmetric-key chain. Each message advances its chain; periodic DH ratchets re-key the root. Delivers forward secrecy (past messages safe after compromise) and post-compromise security (future messages safe after re-ratchet).",
        context="Vortex uses Double Ratchet for direct-message chains. Group rooms use a simpler sender-key scheme keyed off the room root. Chain length capped at 1000 messages before forced re-ratchet; skipped-key cache up to 1000 out-of-order messages; header encryption on by default.",
        history="Designed by Trevor Perrin and Moxie Marlinspike in 2013; deployed in Signal 2014; adopted by WhatsApp (2016), Facebook Secret Conversations, Skype Private Conversations. Public spec 2016. Vortex's implementation is a direct port.",
        formula="sending chain:    CK_send → HKDF(CK_send, \"step\") → CK_send'\n                    MK         → HKDF(CK_send, \"msg\")\nreceiving chain:  CK_recv → HKDF(CK_recv, \"step\") → CK_recv'\nDH ratchet:       RK, CK = HKDF(DH(our_eph, their_eph), RK_prev)",
        usage="`app/security/double_ratchet.py`, iOS `Chat/impl/DoubleRatchet.swift`.",
        related="forward secrecy, post-compromise security, X25519"),

    "ech": term("ECH", "Encrypted Client Hello (RFC 9460).",
        definition="ECH hides the SNI (Server Name Indication) on TLS 1.3 by wrapping the inner ClientHello inside an outer ClientHello encrypted under a public key published in the DNS HTTPS record.",
        context="Vortex nodes publish ECHConfigs in their DNS HTTPS records. Clients with ECH support use the outer hostname (e.g. `vortex-public.cloudflare.com`) as the visible SNI; passive observers see only that generic outer name. DPI can't tell a Vortex client from any other Cloudflare customer.",
        history="ECH went through 5 IETF drafts before standardisation as RFC 9460 in 2024. Earlier variants: ESNI (2018-2019, abandoned), ECH draft-00 to draft-13 (2020-2024). Chrome enabled ECH by default in 2023; Firefox in 2024. Vortex supports it since v0.0.9.",
        formula="outer SNI:  \"public.cloudflare.com\"  ← visible to observers\ninner SNI:  \"node.vortex.example\"   ← encrypted\nECHConfig:  published in DNS HTTPS record of the outer domain",
        usage="`app/transport/stealth_level3.py`.",
        related="TLS 1.3, DoH, SNI, domain fronting"),

    "ed25519": term("Ed25519", "EdDSA signature over edwards25519 (RFC 8032).",
        definition="Ed25519 is an elliptic-curve signature scheme. 32-byte public keys, 64-byte signatures, deterministic signing by default. Fast verification (~200 µs on a modern CPU), batch-verifiable.",
        context="Vortex signs every federation envelope, every integrity manifest, every node attestation, and every bot message with Ed25519. Apple's CryptoKit on iOS 17+ uses the randomised RFC 8032bis variant; Vortex accepts either — any compliant verifier handles both.",
        history="Ed25519 was published by Bernstein, Duif, Lange, Schwabe, Yang in 2011. Standardised as RFC 8032 in 2017. Adopted by OpenSSH 6.5 (2014), TLS 1.3, Apple Keychain, signal-protocol. Deterministic signing was explicitly chosen over ECDSA to avoid the ECDSA RNG-reuse vulnerability class.",
        formula="Sign(d, m):   r = SHA-512(d ∥ m)\n              R = r · G\n              c = SHA-512(R ∥ A ∥ m)\n              S = r + c · a\n              return (R, S)\nVerify: c = SHA-512(R ∥ A ∥ m);  R + c·A ≟ S·G",
        usage="`app/security/crypto.py::sign`, iOS `VortexCrypto.Ed25519Signer`, release key in `keys/release.key`.",
        related="X25519, ECDSA, signature, forward secrecy"),

    "fanout": term("Fan-out", "Broadcasting an event from one source to many subscribers.",
        definition="Fan-out is the architectural pattern where one producer emits an event and N consumers receive it. In Vortex's WebSocket layer, one message POST triggers N socket sends — one per subscriber in the room.",
        context="Implemented as a per-room set of WebSocket handles guarded by an asyncio.Lock. Write acquires, copies the set, releases, then iterates copy awaiting `ws.send_bytes(payload)` with per-socket 1 s timeout. Slow consumers have a 256-frame queue before frames drop.",
        history="Fan-out goes back to publish/subscribe systems in the 1980s (POP, TIBCO). Modern designs (Kafka, Redis pub/sub, NATS) scale the pattern to millions of subscribers. Vortex's per-room in-memory fan-out is minimal because it doesn't need cross-node replication in single-node mode; Redis pub/sub activates in multi-node clusters.",
        formula="broadcast(room_id, payload):\n  subs = fanout[room_id]         # O(1) dict lookup\n  for ws in snapshot(subs):      # copy to iterate safely\n      await ws.send_bytes(payload, timeout=1s)",
        usage="`app/chats/fanout.py`, the hottest path for every message, reaction, typing event, call signal.",
        related="WebSocket, subscriber, Redis pub/sub, queue"),

    "fcm": term("FCM", "Firebase Cloud Messaging.",
        definition="FCM is Google's push-notification service for Android, iOS, web. Replaced the older Google Cloud Messaging (GCM) in 2016. Accepts OAuth2 service-account auth.",
        context="Vortex uses FCM in `data` mode (not `notification` mode) so the app's FirebaseMessagingService runs on arrival and decrypts the sealed-push payload before deciding whether to show a banner. Silent-delivery wake-ups also use FCM data messages.",
        history="FCM launched in 2016 replacing GCM. The legacy HTTP endpoint was deprecated in 2024; Vortex uses the HTTP v1 endpoint with OAuth2. Token rotation every hour is automated via bundled service-account credentials.",
        formula="POST https://fcm.googleapis.com/v1/projects/<project>/messages:send\nAuthorization: Bearer <oauth2_token>\nBody: {message: {token: <device>, data: {...sealed...}, android: {collapse_key}}}",
        usage="`app/services/sealed_push.py`, Android `push/impl/VortexMessagingService.kt`.",
        related="APNs, Web Push, sealed push, OAuth2"),

    "federation": term("Federation", "Mutual-trust message delivery between independent Vortex nodes.",
        definition="Federation is a mutual-trust link between two node operators. Each adds the other's Ed25519 pubkey to its `federations` table. Users on node A can message users on node B by routing envelopes through a signed `POST /federation/deliver`.",
        context="Opt-in per operator: there is no \"any node can federate\" default. Adding a peer requires an operator-signed admin action. Health scores (AIMD ±1) pause federation to misbehaving peers. Outbox retries failed deliveries with exponential backoff up to 14 days.",
        history="Federation was Matrix's killer feature (2014) and before that XMPP/Jabber (1999). Vortex's design draws from both: signed envelopes (Matrix), explicit trust anchors (neither — we're stricter), health scores (AIMD from TCP). Added in v0.0.5.",
        formula="envelope = {source_node, target_user, inner_ct, inner_nonce, sent_at}\nsig      = Ed25519-Sign(source_priv, CBOR(envelope))\nPOST /federation/deliver {envelope, sig}\nB verifies: sig against federations[source_node].pubkey",
        usage="`app/federation/`, `federations` table, `federation_outbox` table.",
        related="gossip, Ed25519, trusted_nodes, peer"),

    "fts5": term("FTS5", "SQLite's full-text-search virtual table.",
        definition="FTS5 is SQLite's fifth-generation full-text search extension. Creates a virtual table that stores tokenised indexes for fast LIKE / MATCH queries.",
        context="Vortex mirrors plaintext tokens (client-encrypted as opaque tags) into an FTS5 virtual table so search hits `O(log n)` instead of `O(n)` scans. On Android's Room, FTS4 is used with triggers that keep the virtual table in sync. Postgres deployments use `tsvector` / `tsquery` for the same purpose.",
        history="FTS goes back to SQLite 3.7 (2010). FTS5 shipped in SQLite 3.9 (2015). Widely adopted; every local-first messaging app on iOS / Android uses it. Postgres has had `tsvector` since 8.3 (2008).",
        formula="CREATE VIRTUAL TABLE messages_fts USING fts5(\n  content,       -- tokenised column\n  room_id UNINDEXED,\n  tokenize = 'unicode61 remove_diacritics 2'\n);\nquery:  SELECT rowid FROM messages_fts WHERE content MATCH 'foo'",
        usage="`app/database.py` (Postgres tsvector), iOS `Search/impl/Fts5SearchRepository`, Android Room `@Fts4`.",
        related="GRDB, Room, tsvector, search"),

    "gossip": term("Gossip", "Periodic peer-list exchange between Vortex nodes.",
        definition="Gossip is a bandwidth-efficient protocol where each node periodically exchanges summarised knowledge with a random peer. Over time every node converges to the same view without a central directory.",
        context="Vortex nodes gossip every 60 seconds. Each exchange is a 256-bit Bloom filter summarising known peers; the other side replies with peers missing from the filter plus its own filter. Bandwidth is O(new peers × 32 B), typically under 1 KiB per round.",
        history="Bloom-filter gossip dates to Cornell's 1998 bimodal multicast paper. Apache Cassandra uses it for membership; Bitcoin for transaction relay; IPFS for DHT maintenance. The O(log N) convergence is what makes it practical for large networks.",
        formula="exchange(A, B):\n  A → B: filter_A = insert_all(peers_A, k=5, m=256)\n  B → A: new_peers_for_A = {p ∈ peers_B : p ∉ filter_A}, filter_B\n  A extracts similarly\nrate limit: 1 exchange per peer per 30 s",
        usage="`app/transport/gossip_security.py`, `app/transport/global_transport.py`.",
        related="Bloom filter, bootstrap, federation, peer"),

    "gravitix": term("Gravitix", "Vortex's DSL for writing bots.",
        definition="Gravitix is a domain-specific language designed for writing Vortex bots. Event-driven handlers (`on /start { emit \"hi\" }`), built-in state, minimal boilerplate. Compiled to bytecode and run in a sandboxed interpreter.",
        context="Alternative to the Python SDK. Gravitix bots can't access the filesystem or arbitrary network — only Vortex's API surface. Compiler produces bytecode; the Rust runtime in `Gravitix/` interprets. Full reference in the Gravitix docs chapter.",
        history="Designed during v0.0.6 after observing that most bot code was 80 % SDK boilerplate around a small kernel of actual logic. A DSL lets the logic shine and sandboxes risks. Similar in spirit to Hubot (2011) but with stricter sandboxing and native Vortex integration.",
        formula="on /start { emit \"Welcome, {ctx.first_name}\" }\non /add <item> {\n  state.list = (state.list or []) + [ctx.args.item]\n  emit \"Added: {ctx.args.item}\"\n}",
        usage="`Gravitix/` repo root, bot code field in `POST /api/bots`.",
        related="bot, marketplace, sandbox, Architex"),

    "hkdf": term("HKDF", "HMAC-based Key Derivation Function (RFC 5869).",
        definition="HKDF is a two-step key derivation function: Extract compresses the input key material into a pseudo-random key (PRK); Expand stretches the PRK into output key material of any length, separated by info labels.",
        context="Vortex uses HKDF-SHA256 everywhere: splitting X25519 shared secrets into encryption + MAC + header keys, deriving per-chunk file keys, deriving backup keys from Argon2id output. Info strings always carry a version prefix (e.g. \"v1:encryption\") so the whole key hierarchy can rotate by bumping v1 → v2.",
        history="Published by Hugo Krawczyk at EUROCRYPT 2010; standardised as RFC 5869 the same year. Used by TLS 1.3 for its schedule, Signal for Double Ratchet, WireGuard for session keys.",
        formula="Extract:  PRK = HMAC-SHA256(salt, IKM)\nExpand:   T(1) = HMAC-SHA256(PRK, info ∥ 0x01)\n          T(i) = HMAC-SHA256(PRK, T(i-1) ∥ info ∥ i)\n          OKM = T(1) ∥ T(2) ∥ … truncated to len",
        usage="`app/security/crypto.py::hkdf`, iOS `VortexCrypto.HKDF`, Android `crypto/kdf/Hkdf`.",
        related="HMAC, X25519, AES-GCM, Double Ratchet"),

    "hmac": term("HMAC", "Hash-based Message Authentication Code (RFC 2104).",
        definition="HMAC is a construction that turns any cryptographic hash (SHA-256, SHA-512) into a MAC. Provides integrity and authentication given a shared secret.",
        context="Vortex uses HMAC-SHA256 in HKDF, for JWT signatures (HS256), for sender_pseudo derivation in rooms, and for coturn TURN credential signing. Constant-time comparison is required on the verification side — `hmac.compare_digest` in Python.",
        history="HMAC was introduced by Bellare, Canetti, Krawczyk in 1996. Standardised as RFC 2104 (1997) and FIPS 198 (2002). Became the default MAC in TLS, IPsec, SSH. Signal, Matrix, Discord, Slack all use HMAC-SHA256 for their JWT and session tokens.",
        formula="HMAC(key, msg) = H( (key ⊕ opad) ∥ H( (key ⊕ ipad) ∥ msg ) )\n  where opad = 0x5c repeated, ipad = 0x36 repeated, block size matches H",
        usage="Everywhere in the crypto stack. Grep for `hmac_sha256` or `HKDF`.",
        related="HKDF, JWT, SHA-256, constant-time compare"),

    "ice": term("ICE", "Interactive Connectivity Establishment (RFC 8445).",
        definition="ICE is the WebRTC mechanism for finding a network path between two peers behind NATs. Peers enumerate candidates (host, server-reflexive, relay), exchange them, and try pairs until one succeeds.",
        context="Vortex's node brokers ICE candidate exchange via WebSocket signalling. coturn provides STUN (for srflx discovery) and TURN (for relay when direct paths fail). Short-lived HMAC credentials are issued per call.",
        history="ICE was standardised as RFC 5245 (2010) and refreshed as RFC 8445 (2018). Behind carrier-grade NAT, direct paths fail ~15 % of the time — TURN relay is unavoidable. WebRTC made ICE mainstream; every video-call product uses it.",
        formula="candidates:\n  host   : rtp://192.168.1.5:49152   (local IP)\n  srflx  : rtp://203.0.113.5:49152   (STUN-discovered public address)\n  relay  : rtp://turn.vortex:49153   (TURN-allocated relay)\npair check: STUN Binding Request; first pair to succeed = selected",
        usage="`app/calls/`, client-side WebRTC config.",
        related="WebRTC, TURN, STUN, coturn, NAT traversal"),

    "jwt": term("JWT", "JSON Web Token (RFC 7519).",
        definition="JWT is a compact token format consisting of three base64-url-encoded parts: header, payload (claims), signature. Used for stateless session authentication.",
        context="Vortex uses HS256 (HMAC-SHA256) JWTs. Access token carries `{sub: user_id, jti: device_id, typ: access, exp}`, 15 min TTL. Refresh token `typ: refresh`, 30 d TTL. Signed over a 64-byte secret from `.env`. No sensitive claims beyond user_id.",
        history="JWTs were standardised as RFC 7519 (2015). OAuth 2.0 had popularised them since 2012. Decade of criticism: alg-confusion attacks, lack of revocation. Vortex mitigates: HS256 only (no RS/ES confusion), device-keyed jti (revocable via user_devices).",
        formula="HEADER.PAYLOAD.SIGNATURE\nheader  = base64url({alg: \"HS256\", typ: \"JWT\"})\npayload = base64url({sub, jti, typ, exp})\nsig     = base64url(HMAC-SHA256(secret, header + \".\" + payload))",
        usage="`app/security/auth_jwt.py`, iOS `Auth/impl/AuthRepositoryImpl`.",
        related="HMAC, OAuth 2.0, refresh token, access token"),

    "kyber": term("Kyber-768", "Post-quantum key encapsulation (FIPS 203).",
        definition="Kyber-768 (officially ML-KEM-768) is NIST's standardised post-quantum key encapsulation mechanism. 1184-byte public keys, 1088-byte ciphertexts, 32-byte shared secrets. Security reduces to Module-LWE, believed quantum-hard.",
        context="Vortex uses Kyber optionally in a hybrid: `session_key = HKDF(x25519_out ∥ kyber_out, info=\"session-v1\")`. If either half holds, the session is safe. Opt-in in v0.1, on-by-default planned for v0.2. Cost: ~2 KB extra per session handshake; latency negligible.",
        history="Kyber was one of ~70 submissions to NIST's PQ competition (2016). Selected for standardisation in July 2022; finalised as FIPS 203 in August 2024. Chrome enabled hybrid Kyber in TLS 1.3 in 2024. Signal added it to their protocol the same year.",
        formula="KeyGen():       (pk ∈ Zq^k,     sk ∈ Zq^k)      pk = 1184 B, sk = 2400 B\nEncaps(pk):     (ct ∈ Zq^k,   ss ∈ {0,1}²⁵⁶)   ct = 1088 B\nDecaps(sk,ct):  ss ∈ {0,1}²⁵⁶\nhybrid = HKDF(x25519_out ∥ kyber_out, \"session-v1\")",
        usage="`app/security/post_quantum.py`, iOS `VortexCrypto.KyberKEM`, Android `crypto/pqc/KyberKEM`.",
        related="X25519, HKDF, quantum-resistant, hybrid KEM"),

    "mailbox": term("Mailbox", "Recipient-addressed storage slot in BMP.",
        definition="A mailbox is BMP's abstraction for \"place where messages for a given recipient wait\". Identified by a 32-byte `mailbox_id` derived from the recipient's pubkey via HKDF.",
        context="Only the sender (who knows recipient_pubkey) and the recipient (who knows their own pubkey) can compute a given mailbox_id. Middle nodes see only the opaque 32-byte identifier. Each mailbox has TTL 7200 s and storage cap 500 MB per node.",
        history="The term is from classical email. BMP borrows the metaphor but makes the mailbox recipient-derived rather than server-provisioned — no \"mailbox creation\" step, no server knowing which addresses exist.",
        formula="mailbox_id = HKDF(recipient_pubkey, info=\"bmp-v1\", len=32)\nonly sender (knows recipient_pk) and recipient (knows own pk) can compute",
        usage="`app/transport/blind_mailbox.py`, gossip Bloom filter.",
        related="BMP, gossip, HKDF, sealed sender"),

    "nonce": term("Nonce", "Number used once — a one-time-use value.",
        definition="A nonce is a value that must never repeat under a given key. In Vortex every AES-GCM operation uses a fresh 96-bit random nonce. Re-using a nonce with the same key destroys confidentiality and authenticity — an attacker with two ciphertexts under the same (key, nonce) can recover plaintext XORs.",
        context="Vortex generates nonces with the OS CSPRNG (`secrets.token_bytes`, `SecRandom`, `java.security.SecureRandom`). Birthday bound with 96 bits: ~2^32 messages before collision becomes plausible, far more than any room key sees in its lifetime. Defensive duplicate-nonce tracking on the node as belt-and-suspenders.",
        history="The nonce concept is ancient in cryptography; the word itself is from Old English \"for the once\". GCM's 96-bit recommendation is from NIST SP 800-38D. The Adobe 2013 breach famously recovered plaintext from repeated nonces on client-side RSA.",
        formula="P(collision) at 10⁹ AES-GCM nonces = ~10⁻¹⁹\nbirthday bound: first collision expected around 2⁴⁸ nonces per key\nGCM safety: 2³² random nonces per key before bound degrades",
        usage="Every AES-GCM call. Counter tracks defensively in `app/security/crypto.py`.",
        related="AES-GCM, CSPRNG, birthday bound, AEAD"),

    "ohttp": term("OHTTP", "Oblivious HTTP (RFC 9458).",
        definition="OHTTP is a protocol for relayed HTTP requests where no single party sees both the request and the response. The client sends through a relay that strips identifying headers; the relay forwards to the gateway which decrypts and responds.",
        context="Vortex uses OHTTP as a Layer-5 stealth fallback. Combined with onion service and BMP, OHTTP provides a last-resort path when TLS is fully blocked. The relay is a trust-separated party (typically Cloudflare or Apple's privacy-relay infrastructure).",
        history="OHTTP was standardised as RFC 9458 in 2024, co-authored by Cloudflare, Apple, Mozilla. Apple's iCloud Private Relay (2021) is an early OHTTP-adjacent deployment. Vortex added OHTTP fallback support in v0.0.9.",
        formula="client → relay:     Encrypt_gateway_pub(request) + random-routing info\nrelay → gateway:    forwards, strips client-identifying headers\ngateway → response: decrypt, process, Encrypt_client_pub(response)\nrelay → client:     forwards response",
        usage="`app/transport/stealth_level5.py`.",
        related="Tor, onion service, BMP, ECH"),

    "onion": term("Onion service", "Tor hidden service.",
        definition="An onion service is a TCP service accessible via Tor's rendezvous protocol. Identified by an onion address (56-character base32 of an Ed25519 pubkey on v3). No public IP, no DNS, no central registry.",
        context="Every Vortex node exposes itself as `.onion` as well as its normal HTTPS endpoint. Clients with Tor support fall through to onion when everything else fails. Bandwidth is ~10× slower but reachable inside fully-restricted networks.",
        history="Onion services date back to Tor 2004 (v1). Rebuilt as v3 onion services in 2017 with Ed25519 keys. Used by SecureDrop, New York Times, Facebook, ProPublica, all major crypto-aware organizations. Signal added onion-service delivery in 2022.",
        formula="address = base32(Ed25519_pubkey ∥ checksum ∥ version_byte) ∥ \".onion\"\n          = 56 characters on v3 onion",
        usage="`/etc/tor/torrc` in `deploy/`, published via controller `/v1/mirrors`.",
        related="Tor, Snowflake, BMP, pluggable transport"),

    "prekey": term("Prekey", "Ephemeral pubkey published ahead of time for bootstrap of new DMs.",
        definition="A prekey is an X25519 keypair published to the node ahead of need so new contacts can start encrypted conversations without a roundtrip. Each user uploads a batch (10 prekeys by default); server serves them on demand; client uploads more when low.",
        context="Vortex's prekey bundle is signed by the device's long-term identity key so an attacker can't swap forged prekeys even with node-level access. New DMs use a one-round Diffie-Hellman against a fresh prekey before the Double Ratchet kicks in.",
        history="Prekeys are from Signal's 2013 protocol design (X3DH). Before X3DH, encrypted bootstrap required synchronous roundtrips — bad for asynchronous messaging. Every modern secure messenger uses a prekey-style bootstrap.",
        formula="bundle = {\n  identity_pk,\n  signed_prekey_pk,\n  signed_prekey_sig = Ed25519-Sign(identity_priv, signed_prekey_pk),\n  one_time_prekeys: [pk_0, pk_1, ..., pk_9]\n}",
        usage="`app/keys/prekeys.py`, iOS `Keys/impl/PrekeyBundle`, Android `keys/impl/PrekeyBundle`.",
        related="X25519, Double Ratchet, X3DH, key exchange"),

    "reality": term("Reality", "TLS-within-TLS masquerade stealth transport.",
        definition="Reality is a stealth transport that masquerades as TLS to a real big-tech origin (typically www.microsoft.com). Outer handshake targets Microsoft; inner handshake is Vortex. Active probes directed at the outer get forwarded to the real origin so probing reveals nothing.",
        context="Vortex supports Reality as a Level-4 pluggable transport. Config specifies the masquerade target, short IDs, and the Vortex X25519 public key. Server validates incoming clients by short-ID match; non-matching probes get real-origin responses.",
        history="Reality was published in 2022 as a response to China's Great Firewall detecting previous TLS-based transports (V2Ray's VMess, Trojan). Adopted by XrayCore in 2023. Vortex added support in v0.0.9.",
        formula="outer handshake:   TLS to Microsoft, SNI=www.microsoft.com\ninner (if auth ok): Vortex traffic over a data channel\nprobe response:    real microsoft.com response forwarded to attacker\n                    ⇒ observer sees only \"yeah, it's microsoft.com\"",
        usage="`app/transport/stealth_level4.py::reality`.",
        related="stealth, pluggable transport, Trojan, VMess"),

    "rbac": term("RBAC", "Role-Based Access Control.",
        definition="RBAC is an access-control model where permissions are granted to roles and users are assigned roles. Vortex uses three-tier RBAC per room: owner > admin > member.",
        context="Cascade: owners have every admin power plus the unique ability to delete the room or transfer ownership. Admins invite, kick, mute, edit room settings. Members send messages, react, edit their own messages. Role changes are recorded as system messages so every member sees them.",
        history="RBAC as a formal model dates to NIST's 1992 paper by Ferraiolo & Kuhn. Became mainstream in enterprise IAM (AWS, Azure) in the 2010s. Room-level RBAC is standard in chat products — IRC's ops/voice/user (1988), Discord's roles (2015), Slack's admin/member/guest.",
        formula="roles:   owner ⊃ admin ⊃ member\ntransfer: owner sets new_owner_id → old owner demoted to admin\nrevoke:  admin can demote a member; owner can demote an admin",
        usage="`room_members.role`, checked in every write route via `app/chats/permissions.py`.",
        related="authentication, room, admin"),

    "sfu": term("SFU", "Selective Forwarding Unit.",
        definition="An SFU is a middlebox that mixes media in group calls. Each participant uploads one stream; the SFU forwards it to the others. Replaces the full-mesh topology (each peer encodes N-1 streams) where scaling is O(N²).",
        context="Vortex's SFU is implemented in Rust for performance. Simulcast-aware: each caller encodes three resolutions concurrently; the SFU picks the right one per viewer's reported downlink. Audio-only groups up to 100 participants; video groups up to 32 (v0.3 roadmap).",
        history="SFU architecture dates to Jitsi's Videobridge (2013). Before SFU, WebRTC group calls were full-mesh. Zoom, Google Meet, Jitsi, Signal group calls all use SFU. Vortex audio-only groups shipped in v0.0.8.",
        formula="full mesh (N peers): each sends N-1 streams  → O(N²) uplink\nSFU      (N peers): each sends 1 stream    → O(N)  uplink per peer\nsimulcast:      L1 (low) + L2 (mid) + L3 (high) concurrent encodings\nSFU picks layer per viewer based on BWE-reported downlink",
        usage="`app/calls/sfu/` Rust crate.",
        related="WebRTC, simulcast, ICE, TURN"),

    "snowflake": term("Snowflake", "Tor volunteer-relay transport over WebRTC.",
        definition="Snowflake is Tor Project's pluggable transport where volunteer browsers act as WebRTC relays. Users install a browser extension and their browser becomes a relay while they have a tab open.",
        context="Vortex accepts Snowflake as a Layer-4 fallback when TLS and primary transports are blocked. No infra required on our side — we just need Snowflake bridges published in well-known locations. Volunteers running the extension provide cover.",
        history="Snowflake launched in 2020 as Tor Project's replacement for obfs4 (which had become fingerprint-able). The WebRTC transport is hard to block because doing so would break a lot of legitimate video calls. Vortex added support in v0.0.9.",
        formula="client → Snowflake broker: \"I need a proxy\"\nbroker matches with volunteer browser running extension\nvolunteer → Tor entry: forwards client traffic over WebRTC\nadvantage: WebRTC traffic is everywhere; blocking breaks video calls",
        usage="`app/transport/stealth_level4.py::snowflake`.",
        related="Tor, pluggable transport, WebRTC, obfs4"),

    "tls13": term("TLS 1.3", "Transport Layer Security, version 1.3 (RFC 8446).",
        definition="TLS 1.3 is the current version of the TLS protocol. Removes unsafe primitives (RSA key exchange, CBC MACs, static ECDH), simplifies handshake to one round-trip, mandates forward secrecy.",
        context="Every HTTPS + WSS + federation connection in Vortex uses TLS 1.3. We match Chrome 120's ClientHello byte-for-byte so DPI can't fingerprint us as non-browser. ECH (encrypted SNI) is opt-in via the outer-SNI config.",
        history="TLS 1.3 was standardised as RFC 8446 in August 2018 after 4 years and 28 drafts. Chrome, Firefox, Safari shipped support in 2018. Microsoft added it to Windows in 2020. By 2022 it was the majority of web traffic.",
        formula="handshake (1-RTT):\n  Client → Server: ClientHello (key_share, SNI?, ALPN, …)\n  Server → Client: ServerHello + EncryptedExtensions + Cert + CertVerify + Finished\n  Client → Server: Finished  + Application Data",
        usage="Every TLS connection. Fingerprint matching in `app/transport/stealth_level1.py`.",
        related="ECH, TLS fingerprint, JA4, forward secrecy"),

    "totp": term("TOTP", "Time-based One-Time Password (RFC 6238).",
        definition="TOTP is a one-time password derived from a shared secret and the current time. Default parameters: 30-second time step, 6-digit code, SHA-1 HMAC.",
        context="Vortex's 2FA uses TOTP with the RFC defaults. Users scan a QR at enrolment; the generated code from their Authenticator app matches the server's expected code. Rate-limited to 5 attempts per 5 minutes per user.",
        history="TOTP (RFC 6238, 2011) by Mark Pei built on HOTP (RFC 4226, 2005). Before that, RSA SecurID used a proprietary algorithm. Google Authenticator (2010) popularised TOTP; every 2FA app now uses it.",
        formula="TOTP(k, t) = HOTP(k, ⌊t / 30⌋)\nHOTP(k, c) = truncate( HMAC-SHA1(k, c) ) mod 10⁶\nwindow: ±1 step tolerated for clock skew",
        usage="`app/authentication/two_factor.py`.",
        related="HMAC, 2FA, authenticator, backup codes"),

    "turn": term("TURN", "Traversal Using Relays around NAT (RFC 8656).",
        definition="TURN is a protocol for relaying UDP / TCP traffic through a public server when direct peer-to-peer paths fail. Used as the fallback path when ICE's host and server-reflexive candidates don't work.",
        context="Vortex ships a coturn instance with every node. Credentials are short-lived (24 h), HMAC-signed, issued per call. When NAT traversal fails — typically behind symmetric NAT or strict firewall — all call media flows through TURN.",
        history="TURN was first standardised as RFC 5766 (2010), updated to RFC 8656 (2020). Used by every WebRTC deployment for ~15 % of calls where direct paths fail. coturn is the reference open-source implementation.",
        formula="username  = \"{expiry_unix}:{user_id}\"\npassword  = base64(HMAC-SHA1(server_secret, username))\nTTL       = 24 h\ncoturn validates HMAC on every AUTH; rejects after expiry",
        usage="`deploy/coturn/`, issued via `/api/calls/{id}/turn`.",
        related="ICE, STUN, WebRTC, NAT traversal"),

    "vapid": term("VAPID", "Voluntary Application Server Identification (RFC 8292).",
        definition="VAPID is a pair of Ed25519 keys an application server uses to identify itself to Web Push providers. Eliminates the \"who's allowed to send push\" question for Web Push deployments.",
        context="Vortex's web client subscribes to Web Push using the node's VAPID public key. Payloads are encrypted with the separate sealed-push key (p256dh) per subscription. Rotation: the VAPID key is long-lived but signed payloads have short JWT-style expiry.",
        history="VAPID was standardised as RFC 8292 in 2017. Before VAPID, Web Push required either FCM-brokered subscriptions or a separate auth mechanism. VAPID simplifies self-hosted deployments — no Firebase project needed.",
        formula="VAPID keys: Ed25519 keypair per node\nsign JWT: {aud: push_service_origin, exp: now + 12h, sub: mailto:ops@example}\npush request headers: Authorization: vapid t=<jwt>, k=<vapid_public_key>",
        usage="`app/services/sealed_push.py::web_push`, published via controller `/v1/health` for diagnosis.",
        related="Web Push, sealed push, Ed25519, JWT"),

    "waf": term("WAF", "Web Application Firewall.",
        definition="A WAF is middleware that inspects HTTP requests and blocks known-malicious patterns (SQL injection, path traversal, template injection) before they reach application code.",
        context="Vortex's WAF runs as `app/security/middleware.py::WAFMiddleware`. ~50 regex checks against URL, query, body. Blocks `UNION SELECT`, `../`, `{{ config }}`, `$where`, known XSS patterns. Also enforces global rate limits (1000 req/s), per-route limits (login 10/min, register 5/min), per-user limits.",
        history="WAFs date to mod_security (2002). Cloudflare's WAF (2014) commoditised the pattern. Every modern web framework ships a default set of checks. Vortex's regex list was compiled from OWASP Top 10 signatures.",
        formula="on every request:\n  for pattern in SQLI_PATTERNS:  if pattern.search(url + query + body): reject\n  for pattern in TRAVERSAL:      if pattern.search(url):                reject\n  for pattern in TEMPLATE:       if pattern.search(body):               reject\nrate-limit keyed by (IP, route, user_id)",
        usage="`app/security/middleware.py`, `app/security/limits.py`.",
        related="rate limiting, audit log, OWASP, SQL injection"),

    "x25519": term("X25519", "Elliptic-curve Diffie-Hellman over Curve25519 (RFC 7748).",
        definition="X25519 is elliptic-curve Diffie-Hellman over Curve25519 in its Montgomery form. 32-byte private and public keys, 32-byte shared secret. Used for key agreement.",
        context="Every static device identity, every ephemeral session key, every sealed-push subscription in Vortex uses X25519. The Montgomery-ladder implementation is constant-time and immune to the class of side-channel attacks that plagued earlier curves.",
        history="Curve25519 was published by Bernstein (2005); standardised as RFC 7748 (2016) with the name X25519 for the DH variant. Adopted by Signal, WhatsApp, OpenSSH, WireGuard, Apple iMessage, Chrome (post-quantum hybrid). Ubiquitous in modern applied cryptography.",
        formula="private key: a ∈ [0, 2²⁵⁵)   (32 bytes little-endian, clamped)\npublic key:  A = a · G            (32-byte compressed point)\nshared:      s = a · B = b · A    (32 bytes, → HKDF input)\nperformance: ~100 µs per DH on an iPhone 11",
        usage="`app/security/crypto.py::x25519_shared_secret`, iOS `VortexCrypto.X25519KeyAgreement`, Android `crypto/dh/X25519KeyAgreement`.",
        related="Ed25519, HKDF, Curve25519, Signal protocol"),
}


def splice_targets():
    yield IOS_EN
    yield from WEB_LOCALES


def process(p):
    with p.open("r", encoding="utf-8") as f:
        d = json.load(f)
    vd = d.setdefault("vortexDocs", {})
    vd["apiSurface"] = API_SURFACE
    vd["glossary"] = GLOSSARY
    with p.open("w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main():
    for p in splice_targets():
        if not p.exists():
            continue
        process(p)
        print(f"wrote {p}")


if __name__ == "__main__":
    main()
