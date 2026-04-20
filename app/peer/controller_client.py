"""Client for talking to a Vortex controller (vortexx.sol or custom).

Responsibilities:
    - Maintain an Ed25519 signing keypair for this node (separate from the
      X25519 DH key used in messaging).
    - Register with controller on startup (if NETWORK_MODE in global/custom).
    - Send periodic heartbeats.
    - Fetch lists of approved peers + verify controller signatures.

Signatures use canonical JSON (sort_keys=True, separators=(",",":")) — must
match the controller's ``canonical_json`` exactly.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.config import Config

logger = logging.getLogger(__name__)


# ── Canonical JSON (must match controller) ─────────────────────────────────

try:
    import vortex_chat as _vc_rust
    _HAS_RUST_CJSON = hasattr(_vc_rust, "canonical_json")
except ImportError:
    _HAS_RUST_CJSON = False


def _canonical(data) -> bytes:
    """Deterministic JSON for signing. Rust path ≈ 25× faster; Python
    fallback kept for builds without the compiled extension."""
    if _HAS_RUST_CJSON:
        return _vc_rust.canonical_json(data)
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


# ── Node Ed25519 signing key (persistent) ──────────────────────────────────

class NodeSigningKey:
    """Ed25519 keypair used to sign controller registrations/heartbeats."""

    _KEY_FILENAME = "ed25519_signing.bin"

    def __init__(self, priv: Ed25519PrivateKey):
        self._priv = priv

    @classmethod
    def load_or_create(cls, keys_dir: Path) -> "NodeSigningKey":
        keys_dir.mkdir(parents=True, exist_ok=True)
        path = keys_dir / cls._KEY_FILENAME
        if path.exists():
            raw = path.read_bytes()
            return cls(Ed25519PrivateKey.from_private_bytes(raw))

        priv = Ed25519PrivateKey.generate()
        raw = priv.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        path.write_bytes(raw)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        logger.info("Generated new Ed25519 signing keypair for controller")
        return cls(priv)

    def pubkey_hex(self) -> str:
        raw = self._priv.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return raw.hex()

    def sign(self, payload) -> str:
        return self._priv.sign(_canonical(payload)).hex()


# ── Verify controller responses with pinned pubkey ─────────────────────────

def verify_controller_signature(
    payload, signature_hex: str, controller_pubkey_hex: str
) -> bool:
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(controller_pubkey_hex))
        pub.verify(bytes.fromhex(signature_hex), _canonical(payload))
        return True
    except (ValueError, InvalidSignature):
        return False


# ── Main client ────────────────────────────────────────────────────────────

class ControllerClient:
    """Talks to a Vortex controller.

    Usage:
        client = ControllerClient(
            url="https://controller.example",
            controller_pubkey="abc123...",
            signing_key=NodeSigningKey.load_or_create(keys_dir),
            announce_endpoints=["wss://my.node:9000"],
            metadata={"name": "my-node", "version": "1.0"},
        )
        await client.start()   # registers + launches heartbeat task
        peers = await client.fetch_random_peers(count=5)
        await client.stop()
    """

    def __init__(
        self,
        url: str,
        controller_pubkey: str,
        signing_key: NodeSigningKey,
        announce_endpoints: list[str],
        metadata: Optional[dict] = None,
        heartbeat_sec: int = 60,
        proxy_urls: Optional[list[str]] = None,
        fallback_urls: Optional[list[str]] = None,
        expected_release_pubkey: Optional[str] = None,
    ):
        self.url = url.rstrip("/")
        self.controller_pubkey = controller_pubkey
        self.signing_key = signing_key
        self.announce_endpoints = announce_endpoints
        self.metadata = metadata or {}
        self.heartbeat_sec = max(10, heartbeat_sec)
        # Fallback proxies (Vortex nodes with /api/peers/controller-proxy).
        # If direct requests to ``url`` fail, try going through one of these.
        self.proxy_urls = [p.rstrip("/") for p in (proxy_urls or [])]
        # Additional direct controller URLs to try when the primary one's
        # /v1/integrity does NOT return status=="verified" or returns 503.
        self.fallback_urls = [u.rstrip("/") for u in (fallback_urls or [])]
        # Expected release pubkey — compared byte-for-byte with /v1/integrity's
        # ``signed_by``. If None, we accept any signature as long as status is
        # "verified" (useful for custom / self-hosted builds).
        self.expected_release_pubkey = (expected_release_pubkey or "").lower() or None
        self._hb_task: Optional[asyncio.Task] = None
        self._registered = False

    # ── Public API ──

    async def start(self) -> None:
        if not self.announce_endpoints:
            logger.warning(
                "ControllerClient: no announce endpoints — skipping registration"
            )
            return
        try:
            # First thing: pick a verified controller URL. If nothing verifies
            # (all configured URLs are tampered / wrong key / unreachable) we
            # refuse to register — NEVER fall back to a bad controller.
            await self.ensure_verified_url()
            await self._register()
            self._hb_task = asyncio.create_task(self._heartbeat_loop())
        except IntegrityRefusal as e:
            logger.error("ControllerClient: no verified controller found: %s", e)
        except Exception as e:
            logger.warning("ControllerClient: registration failed: %s", e)

    async def ensure_verified_url(self) -> str:
        """Walk ``self.url`` + ``self.fallback_urls`` in order and return the
        first one whose /v1/integrity says ``status == "verified"`` and
        (if configured) whose ``signed_by`` matches our pinned release key.

        Sets ``self.url`` to that URL so subsequent requests go there.
        Raises ``IntegrityRefusal`` if NONE pass — this is the whole point:
        we refuse to connect to any unverified controller.
        """
        candidates = [self.url, *self.fallback_urls]
        # Dedupe while preserving order
        seen, ordered = set(), []
        for c in candidates:
            c = c.rstrip("/")
            if c and c not in seen:
                seen.add(c)
                ordered.append(c)

        for candidate in ordered:
            verdict = await self._probe_integrity(candidate)
            if verdict is True:
                if self.url != candidate:
                    logger.info("ControllerClient: switched to verified %s", candidate)
                self.url = candidate
                return candidate
        raise IntegrityRefusal(
            f"none of {len(ordered)} controller URL(s) reported status=verified "
            f"with expected release key"
        )

    async def _probe_integrity(self, url: str) -> bool:
        """Return True if ``url`` serves a verified, trustworthy integrity report."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=8) as http:
                r = await http.get(f"{url}/v1/integrity")
                if r.status_code != 200:
                    logger.debug("integrity probe %s: HTTP %s", url, r.status_code)
                    return False
                data = r.json()
        except Exception as e:
            logger.debug("integrity probe %s: %s", url, e)
            return False

        if data.get("status") != "verified":
            logger.info(
                "skipping %s: integrity status=%s — %s",
                url, data.get("status"), data.get("message", ""),
            )
            return False

        if self.expected_release_pubkey:
            signed_by = (data.get("signed_by") or "").lower()
            if signed_by != self.expected_release_pubkey:
                logger.warning(
                    "skipping %s: release key mismatch (expected %s…, got %s…)",
                    url,
                    self.expected_release_pubkey[:16],
                    signed_by[:16] if signed_by else "none",
                )
                return False
        return True

    async def stop(self) -> None:
        if self._hb_task:
            self._hb_task.cancel()
            try:
                await self._hb_task
            except (asyncio.CancelledError, Exception):
                pass
            self._hb_task = None

    async def fetch_random_peers(self, count: int = 5) -> list[dict]:
        """Returns a list of approved peer dicts, signature-verified."""
        env = await self._request("GET", f"/v1/nodes/random?count={count}")
        if env is None:
            return []
        if not verify_controller_signature(
            env["payload"], env["signature"], self.controller_pubkey
        ):
            logger.warning("ControllerClient: signature mismatch on /nodes/random — rejecting")
            return []
        return env["payload"].get("nodes", [])

    async def fetch_entries(self) -> list[dict]:
        """Returns signed bootstrap entry URLs."""
        env = await self._request("GET", "/v1/entries")
        if env is None:
            return []
        if not verify_controller_signature(
            env["payload"], env["signature"], self.controller_pubkey
        ):
            logger.warning("ControllerClient: signature mismatch on /entries — rejecting")
            return []
        return env["payload"].get("entries", [])

    # ── Internal ──

    async def _register(self) -> None:
        payload = {
            "pubkey": self.signing_key.pubkey_hex(),
            "endpoints": self.announce_endpoints,
            "metadata": self.metadata,
            "timestamp": int(time.time()),
        }
        data = await self._request(
            "POST", "/v1/register",
            body={"payload": payload, "signature": self.signing_key.sign(payload)},
            raise_on_fail=True,
        )
        self._registered = bool(data.get("ok"))
        logger.info(
            "ControllerClient: registered (approved=%s)", data.get("approved"),
        )

    async def _heartbeat_once(self) -> None:
        payload = {
            "pubkey": self.signing_key.pubkey_hex(),
            "timestamp": int(time.time()),
        }
        body = {"payload": payload, "signature": self.signing_key.sign(payload)}
        try:
            await self._request("POST", "/v1/heartbeat", body=body, raise_on_fail=True)
        except _NotFound:
            logger.info("ControllerClient: 404 from heartbeat, re-registering")
            await self._register()

    # ── HTTP with direct → proxy fallback ──

    async def _request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        raise_on_fail: bool = False,
    ) -> Optional[dict]:
        """Try direct controller URL first; fall back to each proxy URL in turn.

        If the direct URL answers with 503 (tampered, overloaded, etc.) we
        re-verify integrity on it AND on fallback_urls — refusing to silently
        retry on a bad controller.

        Returns the decoded JSON body on success, or None on total failure
        (unless raise_on_fail=True, in which case raises).
        """
        import httpx

        # 1) Direct
        full = f"{self.url}{path}"
        try:
            async with httpx.AsyncClient(timeout=10) as http:
                if method == "GET":
                    r = await http.get(full)
                else:
                    r = await http.post(full, json=body or {})
                if r.status_code == 404 and path.startswith("/v1/heartbeat"):
                    raise _NotFound()
                if r.status_code == 503:
                    # Hot controller went bad. Find another *verified* one.
                    logger.info(
                        "ControllerClient: 503 from %s, re-verifying and failing over",
                        full,
                    )
                    try:
                        await self.ensure_verified_url()
                    except IntegrityRefusal:
                        if raise_on_fail:
                            raise RuntimeError(
                                "all configured controllers are unverified"
                            )
                        return None
                    # Retry once on the freshly-verified URL
                    retry_full = f"{self.url}{path}"
                    if retry_full != full:
                        async with httpx.AsyncClient(timeout=10) as http:
                            if method == "GET":
                                r = await http.get(retry_full)
                            else:
                                r = await http.post(retry_full, json=body or {})
                            if r.status_code == 404 and path.startswith("/v1/heartbeat"):
                                raise _NotFound()
                            r.raise_for_status()
                            return r.json()
                r.raise_for_status()
                return r.json()
        except _NotFound:
            raise
        except Exception as direct_err:
            logger.debug("ControllerClient: direct %s %s failed: %s", method, full, direct_err)

        # 2) Proxy fallbacks
        for proxy in self.proxy_urls:
            try:
                proxy_body = {
                    "method": method,
                    "path": path,
                    "controller_url": self.url,
                }
                if body is not None:
                    proxy_body["body"] = body
                async with httpx.AsyncClient(timeout=15) as http:
                    r = await http.post(f"{proxy}/api/peers/controller-proxy", json=proxy_body)
                    r.raise_for_status()
                    wrapped = r.json()
                    if wrapped.get("status_code") == 404 and path.startswith("/v1/heartbeat"):
                        raise _NotFound()
                    if 200 <= wrapped.get("status_code", 0) < 300:
                        logger.info("ControllerClient: request succeeded via proxy %s", proxy)
                        return wrapped.get("body")
            except _NotFound:
                raise
            except Exception as e:
                logger.debug("ControllerClient: proxy %s failed: %s", proxy, e)

        if raise_on_fail:
            raise RuntimeError(f"controller unreachable (direct and {len(self.proxy_urls)} proxies)")
        return None


class _NotFound(Exception):
    """Internal sentinel for controller 404 — triggers re-registration."""
    pass


class IntegrityRefusal(RuntimeError):
    """Raised when no candidate controller URL passes integrity verification.

    Intentional dead-stop: never auto-connect to an unverified controller,
    even under pressure. Callers should surface this to the operator.
    """
    pass

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_sec)
            try:
                await self._heartbeat_once()
            except Exception as e:
                logger.debug("ControllerClient: heartbeat failed: %s", e)


# ── Convenience: create client from Config ─────────────────────────────────

def client_from_config() -> Optional[ControllerClient]:
    """Build a ControllerClient from app.config.Config, or None if not configured."""
    if Config.NETWORK_MODE not in ("global", "custom"):
        return None
    if not Config.CONTROLLER_URL or not Config.CONTROLLER_PUBKEY:
        logger.warning(
            "NETWORK_MODE=%s but CONTROLLER_URL/CONTROLLER_PUBKEY unset — skipping",
            Config.NETWORK_MODE,
        )
        return None

    endpoints = [
        e.strip()
        for e in Config.NODE_ANNOUNCE_ENDPOINTS.split(",")
        if e.strip()
    ]
    if not endpoints:
        logger.warning("NODE_ANNOUNCE_ENDPOINTS is empty — nothing to register")
        return None

    # BOOTSTRAP_PEERS doubles as the proxy-fallback list: known Vortex nodes
    # that expose /api/peers/controller-proxy. Format: comma-separated URLs.
    proxy_urls = [
        p.strip() for p in Config.BOOTSTRAP_PEERS.split(",") if p.strip()
    ]

    # Optional: a comma-separated list of alternative controller URLs we're
    # allowed to fail over to if the primary is tampered or overloaded.
    fallback_urls = [
        u.strip()
        for u in getattr(Config, "CONTROLLER_FALLBACK_URLS", "").split(",")
        if u.strip()
    ]
    # Optional: pinned release pubkey. If unset we accept any signed_by that
    # reports status=="verified" — OK for custom / dev builds, NOT OK for prod.
    expected_release_pubkey = getattr(Config, "CONTROLLER_RELEASE_PUBKEY", "") or None

    signing_key = NodeSigningKey.load_or_create(Config.KEYS_DIR)
    return ControllerClient(
        url=Config.CONTROLLER_URL,
        controller_pubkey=Config.CONTROLLER_PUBKEY,
        signing_key=signing_key,
        announce_endpoints=endpoints,
        metadata={
            "name": Config.DEVICE_NAME or "vortex-node",
            "mode": Config.NETWORK_MODE,
            # Capability flags — controller uses these to weight nodes
            # when picking random peers for /v1/nodes/random. A node that
            # can answer AI requests locally gives users a better UX, so
            # the controller biases discovery toward such nodes.
            "ai_capable":  _ai_capable(),
        },
        heartbeat_sec=Config.CONTROLLER_HEARTBEAT_SEC,
        proxy_urls=proxy_urls,
        fallback_urls=fallback_urls,
        expected_release_pubkey=expected_release_pubkey,
    )


def _ai_capable() -> bool:
    """True iff AI is enabled on this node AND a reachable Ollama daemon
    exists on the loopback. Cached by callers is fine — the controller
    re-reads metadata every heartbeat.
    """
    if Config.AI_ENABLED is False:
        return False
    # Fast, non-blocking: rely on the env flag alone for registration.
    # A periodic wizard job can flip AI_ENABLED when the daemon crashes.
    return bool(Config.AI_ENABLED)
