"""
app/docs/openapi_config.py — Auto-generated OpenAPI documentation configuration.

Provides comprehensive API documentation accessible at:
  /docs     — Swagger UI (interactive)
  /redoc    — ReDoc (readable)
  /openapi.json — raw OpenAPI 3.1 spec

Organized by tags matching the Vortex module structure.
"""
from __future__ import annotations


OPENAPI_TAGS = [
    {
        "name": "authentication",
        "description": "User registration, login (password/seed/QR/passkey), JWT token management, 2FA (TOTP), device management.",
    },
    {
        "name": "rooms",
        "description": "Room CRUD, join/leave, invite codes, room settings, member management, role-based access.",
    },
    {
        "name": "messages",
        "description": "E2E encrypted messaging, threads, reactions, pinning, editing, deletion, sealed sender.",
    },
    {
        "name": "files",
        "description": "Secure file upload/download with EXIF stripping, MIME validation, anomaly detection, edge caching.",
    },
    {
        "name": "peers",
        "description": "Peer discovery (UDP/gossip), peer registry, federated join, multihop join, peer status.",
    },
    {
        "name": "federation",
        "description": "Cross-node federation: guest-login, virtual rooms, relay WebSocket, federated room management.",
    },
    {
        "name": "calls",
        "description": "1-to-1 and group WebRTC calls, signaling, ICE relay, SFU, E2E media frame encryption.",
    },
    {
        "name": "keys",
        "description": "Key exchange (X25519), key backup (AES-256-GCM), device linking (ECIES), cross-signing, SSSS, key transparency log.",
    },
    {
        "name": "security",
        "description": "Post-quantum crypto (Kyber-768), panic mode, WAF, rate limiting, CSRF, sealed sender, steganography.",
    },
    {
        "name": "transport",
        "description": "Multi-transport layer: NAT traversal (STUN/ICE), WiFi Direct, BLE, pluggable transports, CDN relay.",
    },
    {
        "name": "privacy",
        "description": "IP privacy layer, Tor hidden service, anonymous registration, sealed push notifications.",
    },
    {
        "name": "moderation",
        "description": "Room moderation tools, ban/mute/warn, slow mode, content filtering via Gravitix bots.",
    },
    {
        "name": "contacts",
        "description": "Contact management, fingerprint verification, key change detection.",
    },
    {
        "name": "notifications",
        "description": "Push notifications (sealed), WebSocket notifications, SSE fallback, notification preferences.",
    },
    {
        "name": "admin",
        "description": "Node setup wizard, SSL management, system status, metrics.",
    },
]


def get_openapi_config() -> dict:
    """Return OpenAPI metadata for FastAPI app configuration."""
    return {
        "title": "Vortex Messenger API",
        "description": (
            "**Vortex** — decentralized, E2E-encrypted messenger with post-quantum cryptography.\n\n"
            "## Security Features\n"
            "- AES-256-GCM + X25519 ECDH end-to-end encryption\n"
            "- Kyber-768 (ML-KEM) post-quantum key exchange\n"
            "- Sealed sender (zero-knowledge message routing)\n"
            "- Full forward secrecy with ephemeral keys\n"
            "- EXIF stripping on all uploaded images\n\n"
            "## Transport Layer\n"
            "- Direct TCP, UDP hole punching, WiFi Direct, BLE, Federation relay\n"
            "- Pluggable transports (obfs4, domain fronting, shadowsocks-like)\n"
            "- Multi-CDN relay for IP masking\n"
            "- Distributed edge cache for media delivery\n\n"
            "## Authentication\n"
            "- JWT bearer tokens (cookie or Authorization header)\n"
            "- BIP39 seed phrase recovery\n"
            "- WebAuthn/Passkey support\n"
            "- TOTP 2FA\n"
        ),
        "version": "1.0.0",
        "contact": {"name": "Vortex Team"},
        "license_info": {"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
        "openapi_tags": OPENAPI_TAGS,
    }
