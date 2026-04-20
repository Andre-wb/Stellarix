"""
app/models/user.py — User models, device models, and Pydantic authentication schemas.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.base import Base
from app.security.crypto import hash_password, verify_password

_PHONE_RE = re.compile(r"^\+?[1-9]\d{9,14}$")
_USER_RE  = re.compile(r"^[a-zA-Z0-9_]{3,30}$")
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


class User(Base):
    __tablename__ = "users"

    id               = Column(Integer,     primary_key=True, index=True)
    # nullable=True: phone is optional — users can register with username alone.
    # unique constraint preserved: if provided, phone must be globally unique.
    phone            = Column(String(20),  unique=True, nullable=True,  index=True)
    username         = Column(String(50),  unique=True, nullable=False, index=True)
    password_hash    = Column(String(512), nullable=False)
    display_name     = Column(String(100), nullable=True)
    avatar_emoji     = Column(String(10),  default="👤")
    avatar_url       = Column(String(255), nullable=True)
    reply_color      = Column(String(20),  nullable=True)   # Custom color for reply bubbles (hex, e.g. "#7c3aed")
    reply_icon       = Column(String(10),  nullable=True)   # Custom emoji icon for reply bubbles

    # X25519 public key of the user — generated ON THE CLIENT during registration.
    # Server never sees the private key.
    x25519_public_key = Column(String(64), nullable=True, index=True)  # hex(32 bytes)

    # Kyber-768 (ML-KEM) public key — for hybrid post-quantum key exchange.
    kyber_public_key = Column(Text, nullable=True)

    # Rich status: custom text + emoji + presence
    custom_status = Column(String(100), nullable=True)
    status_emoji  = Column(String(10),  nullable=True)
    presence      = Column(String(20),  default="online")  # online, away, dnd, invisible

    email    = Column(String(255), unique=True, nullable=True, index=True)
    last_ip  = Column(String(45),  nullable=True)

    # Solana wallet linked to this account for Vortex Premium. Optional —
    # users who haven't linked one stay on the free tier. Base58 Pubkey
    # encoding is 32-44 chars; 48 gives headroom.
    wallet_pubkey = Column(String(48), nullable=True, index=True)

    # Profile card
    bio          = Column(String(300), nullable=True)
    birth_date   = Column(String(10),  nullable=True)
    profile_bg   = Column(String(120), nullable=True)
    profile_icon = Column(String(50),  nullable=True)

    network_mode = Column(String(10), default="local")

    # 2FA (TOTP)
    totp_secret  = Column(String(64), nullable=True)
    totp_enabled = Column(Boolean, default=False)

    # Seed phrase (BIP39) — Argon2id hash for anonymous account recovery
    seed_phrase_hash = Column(String(512), nullable=True)

    # WebAuthn / Passkey
    passkey_credential_id = Column(String(512), nullable=True, index=True)
    passkey_public_key    = Column(Text,        nullable=True)
    passkey_sign_count    = Column(Integer,     default=0)

    is_bot      = Column(Boolean,  default=False)
    is_active   = Column(Boolean,  default=True)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen   = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Moderation
    global_muted_until = Column(DateTime, nullable=True)
    banned_until       = Column(DateTime, nullable=True)
    strike_count       = Column(Integer,  default=0)
    auto_delete_days   = Column(Integer,  default=0)  # 0 = disabled
    show_last_seen     = Column(Boolean,  default=True)  # show last seen time

    room_memberships = relationship(
        "RoomMember", back_populates="user", cascade="all, delete-orphan"
    )

    def set_password(self, password: str) -> None:
        self.password_hash = hash_password(password)

    def check_password(self, password: str) -> bool:
        return verify_password(password, self.password_hash)

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username}>"


class UserDevice(Base):
    """Active user device/session."""
    __tablename__ = "user_devices"

    id                 = Column(Integer,     primary_key=True, autoincrement=True)
    user_id            = Column(Integer,     ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_name        = Column(String(255), nullable=False)
    device_type        = Column(String(50),  default="web")
    ip_address         = Column(String(45),  nullable=True)
    last_active        = Column(DateTime,    default=lambda: datetime.now(timezone.utc))
    created_at         = Column(DateTime,    default=lambda: datetime.now(timezone.utc))
    refresh_token_hash = Column(String(64),  nullable=True, index=True)
    device_pub_key     = Column(String(64),  nullable=True)            # per-device X25519 pub (hex, 32 bytes)

    user = relationship("User", backref="devices")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id          = Column(Integer,     primary_key=True)
    user_id     = Column(Integer,     nullable=False, index=True)
    token_hash  = Column(String(64),  unique=True, nullable=False)
    expires_at  = Column(DateTime,    nullable=False)
    revoked_at  = Column(DateTime,    nullable=True)
    created_at  = Column(DateTime,    default=lambda: datetime.now(timezone.utc))
    ip_address  = Column(String(45),  nullable=True)
    user_agent  = Column(String(512), nullable=True)


class KeyBackup(Base):
    """Encrypted key vault — client encrypts all keys with passphrase-derived AES key."""
    __tablename__ = "key_backups"

    id         = Column(Integer,     primary_key=True, autoincrement=True)
    user_id    = Column(Integer,     ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    vault_data = Column(Text,        nullable=False)   # hex: nonce(12) + AES-256-GCM(keys_json)
    vault_salt = Column(String(64),  nullable=False)   # hex salt for PBKDF2
    kdf_params = Column(Text,        nullable=False)   # JSON: {"alg":"PBKDF2","iter":600000,"hash":"SHA-256"}
    version    = Column(Integer,     default=1)
    created_at = Column(DateTime,    default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime,    default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="key_backups")


class DeviceLinkRequest(Base):
    """Cross-device key transfer request (new device → existing device)."""
    __tablename__ = "device_link_requests"

    id              = Column(Integer,     primary_key=True, autoincrement=True)
    user_id         = Column(Integer,     ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    link_code_hash  = Column(String(64),  nullable=False, index=True)
    new_device_pub  = Column(String(64),  nullable=False)   # X25519 ephemeral pub of new device (hex)
    status          = Column(String(20),  default="pending") # pending, approved, expired
    encrypted_keys  = Column(Text,        nullable=True)     # ECIES encrypted key bundle (set on approve)
    created_at      = Column(DateTime,    default=lambda: datetime.now(timezone.utc))
    expires_at      = Column(DateTime,    nullable=False)

    user = relationship("User", backref="link_requests")


class SyncEvent(Base):
    """Encrypted sync event — opaque blob pushed by one device for others to pull.

    Types: 'key_update' (new/changed room keys), 'history' (encrypted message batch).
    Server stores ONLY encrypted data — cannot distinguish keys from noise.
    """
    __tablename__ = "sync_events"

    id         = Column(Integer,     primary_key=True, autoincrement=True)
    user_id    = Column(Integer,     ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id  = Column(Integer,     nullable=False)         # source device
    event_type = Column(String(20),  nullable=False)         # key_update | history
    payload    = Column(Text,        nullable=False)         # hex: ECIES-encrypted blob
    seq        = Column(Integer,     nullable=False, default=0)  # monotonic per user
    created_at = Column(DateTime,    default=lambda: datetime.now(timezone.utc))


class SecretShare(Base):
    """Shamir's Secret Sharing — M-of-N key recovery share.

    Client splits master key into N shares (Shamir over GF(256)),
    encrypts each share for a specific recipient (ECIES),
    and uploads encrypted blobs. Server cannot reconstruct the key.
    """
    __tablename__ = "secret_shares"

    id              = Column(Integer,     primary_key=True, autoincrement=True)
    owner_id        = Column(Integer,     ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient_id    = Column(Integer,     ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    share_index     = Column(Integer,     nullable=False)          # 1..N
    encrypted_share = Column(Text,        nullable=False)          # ECIES-encrypted share (hex)
    threshold       = Column(Integer,     nullable=False)          # M (min to reconstruct)
    total_shares    = Column(Integer,     nullable=False)          # N
    label           = Column(String(100), nullable=True)           # e.g. "Alice"
    status          = Column(String(20),  default="active")        # active, used, revoked
    created_at      = Column(DateTime,    default=lambda: datetime.now(timezone.utc))

    owner     = relationship("User", foreign_keys=[owner_id], backref="owned_shares")
    recipient = relationship("User", foreign_keys=[recipient_id], backref="held_shares")


class DeviceCrossSign(Base):
    """Cross-signing record: device A vouches for device B's public key."""
    __tablename__ = "device_cross_signs"

    id              = Column(Integer,     primary_key=True, autoincrement=True)
    user_id         = Column(Integer,     ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    signer_device   = Column(Integer,     nullable=False)    # device_id that signed
    signed_device   = Column(Integer,     nullable=False)    # device_id being vouched for
    signature       = Column(Text,        nullable=False)    # hex: HMAC-SHA256(signer_key, signed_device_pub)
    signer_pub_hash = Column(String(64),  nullable=False)    # SHA-256(signer pub) for verification
    signed_pub_hash = Column(String(64),  nullable=False)    # SHA-256(signed pub) for verification
    created_at      = Column(DateTime,    default=lambda: datetime.now(timezone.utc))


class FederatedBackupShard(Base):
    """Encrypted backup shard stored on a federation peer.

    User's backup is split (Shamir) and each shard encrypted (ECIES)
    for the peer's node X25519 pubkey. Peers hold shards they cannot decrypt
    without the user's passphrase.
    """
    __tablename__ = "federated_backup_shards"

    id              = Column(Integer,     primary_key=True, autoincrement=True)
    user_id         = Column(Integer,     ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    shard_index     = Column(Integer,     nullable=False)          # 1..N
    peer_ip         = Column(String(45),  nullable=False)
    peer_port       = Column(Integer,     nullable=False)
    encrypted_shard = Column(Text,        nullable=False)          # ECIES(node_pub, shard_data) hex
    shard_hash      = Column(String(64),  nullable=False)          # SHA-256(plaintext shard) for integrity
    status          = Column(String(20),  default="placed")        # placed, verified, lost
    threshold       = Column(Integer,     nullable=False)          # M
    total_shards    = Column(Integer,     nullable=False)          # N
    created_at      = Column(DateTime,    default=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="federated_shards")


class KeyTransparencyEntry(Base):
    """Append-only log of public key changes — verifiable key history.

    Each entry chains to the previous via prev_hash (Merkle-like).
    Server signs each entry with HMAC-SHA256(server_key, entry_data).
    Clients verify the chain to detect unauthorized key insertions.
    """
    __tablename__ = "key_transparency_log"

    id            = Column(Integer,     primary_key=True, autoincrement=True)
    user_id       = Column(Integer,     ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    key_type      = Column(String(30),  nullable=False)            # x25519, kyber, device
    pub_key_hash  = Column(String(64),  nullable=False)            # SHA-256(pubkey_hex)
    prev_hash     = Column(String(64),  nullable=True)             # SHA-256(prev entry) — chain
    signature     = Column(Text,        nullable=False)            # HMAC-SHA256(server_key, entry_data)
    device_id     = Column(Integer,     nullable=True)             # which device registered key
    seq           = Column(Integer,     nullable=False, default=0) # monotonic per user
    created_at    = Column(DateTime,    default=lambda: datetime.now(timezone.utc))


class UserStatus(Base):
    """24-hour ephemeral status/story posts."""
    __tablename__ = "user_statuses"

    id         = Column(Integer,     primary_key=True, index=True)
    user_id    = Column(Integer,     ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    text       = Column(String(500), nullable=True)
    media_url  = Column(String(255), nullable=True)
    created_at = Column(DateTime,    default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime,    nullable=False)


# ══════════════════════════════════════════════════════════════════════════════
# Pydantic schemas
# ══════════════════════════════════════════════════════════════════════════════

class RegisterRequest(BaseModel):
    phone:             str | None = Field(None, max_length=20)
    username:          str = Field(..., min_length=3,  max_length=30)
    password:          str = Field(..., min_length=8,  max_length=128)
    display_name:      str = Field("",  max_length=100)
    avatar_emoji:      str = Field("👤", max_length=10)
    email:             str | None = Field(None, max_length=255)
    invite_code:       str | None = Field(None, max_length=64)
    x25519_public_key: str = Field(..., min_length=64, max_length=64,
                                   description="X25519 client public key in hex (32 bytes = 64 chars)")

    @field_validator("phone")
    @classmethod
    def v_phone(cls, v: str | None) -> str | None:
        if v is None or v.strip() == "":
            return None
        c = re.sub(r"[\s\-\(\)]", "", v)
        if not _PHONE_RE.match(c):
            raise ValueError("Invalid phone number format")
        return c

    @field_validator("username")
    @classmethod
    def v_username(cls, v: str) -> str:
        if not _USER_RE.match(v):
            raise ValueError("Only letters, digits and _ (3-30 characters)")
        return v.lower()

    @field_validator("email")
    @classmethod
    def v_email(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email format")
        return v.lower()

    @field_validator("x25519_public_key")
    @classmethod
    def v_pubkey(cls, v: str) -> str:
        try:
            key_bytes = bytes.fromhex(v)
            if len(key_bytes) != 32:
                raise ValueError("Key must be 32 bytes")
        except ValueError as e:
            raise ValueError(f"x25519_public_key: {e}") from e
        return v.lower()


class LoginRequest(BaseModel):
    phone_or_username: str = Field(..., min_length=3, max_length=128)
    password:          str = Field(..., min_length=1, max_length=128)


class KeyLoginRequest(BaseModel):
    """Passwordless login via X25519 challenge-response."""
    challenge_id: str = Field(..., min_length=32, max_length=32)
    pubkey:       str = Field(..., min_length=64, max_length=64)
    proof:        str = Field(..., min_length=64, max_length=64)

    @field_validator("pubkey", "proof")
    @classmethod
    def v_hex(cls, v: str) -> str:
        try:
            bytes.fromhex(v)
        except ValueError:
            raise ValueError("Field must be a hex string")
        return v.lower()


class UpdateProfileRequest(BaseModel):
    display_name:      str | None = Field(None, max_length=100)
    avatar_emoji:      str | None = Field(None, max_length=10)
    email:             str | None = Field(None, max_length=255)
    x25519_public_key: str | None = Field(None, min_length=64, max_length=64)


class UpdateRichStatusRequest(BaseModel):
    custom_status: str | None = Field(None, max_length=100)
    status_emoji:  str | None = Field(None, max_length=10)
    presence:      str | None = Field(None, max_length=20)

    @field_validator("presence")
    @classmethod
    def v_presence(cls, v: str | None) -> str | None:
        if v is not None and v not in ("online", "away", "dnd", "invisible"):
            raise ValueError("presence must be one of: online, away, dnd, invisible")
        return v


class PasswordStrengthRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=128)


class SeedLoginRequest(BaseModel):
    """Login by username + seed phrase (for anonymous accounts without a phone)."""
    username:    str = Field(..., min_length=3, max_length=30)
    seed_phrase: str = Field(..., min_length=10, max_length=512)

    @field_validator("username")
    @classmethod
    def v_username(cls, v: str) -> str:
        return v.lower().strip()


class TwoFAVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class TwoFALoginRequest(BaseModel):
    user_id: int
    code: str = Field(..., min_length=6, max_length=6)
