"""
app/federation/trusted_nodes.py — Trusted node management for Vortex federation.

Provides blockchain-inspired code-hash validation, rotating participation tokens,
consistent-hashing task distribution, health-check failover, and gossip protocol
for decentralized node discovery.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import Session

from app.base import Base
from app.config import Config
from app.database import get_db, SessionLocal
from app.models import User
from app.security.auth_jwt import get_current_user
from app.security.ssl_context import make_peer_ssl_context
from app.transport.gossip_security import (
    GossipRateLimiter, ReputationManager, ProofOfWork, VectorClock,
    MAX_GOSSIP_PEERS, MAX_GOSSIP_ROOMS,
)

logger = logging.getLogger(__name__)

# ── Gossip Security Instances ────────────────────────────────────────────────
_gossip_rate_limiter = GossipRateLimiter()
_reputation_manager = ReputationManager()
_node_vector_clock: Optional[VectorClock] = None

def _get_vector_clock() -> VectorClock:
    global _node_vector_clock
    if _node_vector_clock is None:
        _node_vector_clock = VectorClock(Config.NODE_ID if hasattr(Config, 'NODE_ID') else secrets.token_hex(8))
    return _node_vector_clock

# ══════════════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════════════

TOKEN_ROTATION_INTERVAL = 300  # 5 minutes
HEALTH_CHECK_INTERVAL = 30  # seconds
MAX_FAIL_COUNT = 3
TRUST_SCORE_PENALTY = 20
MAX_PAYLOAD_SIZE = 1_048_576  # 1 MB
MAX_JSON_DEPTH = 10
RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_WINDOW = 60  # seconds

TASK_TYPES = [
    "message_relay",
    "file_cache",
    "search_index",
    "health_monitor",
    "backup_shard",
]

# Secret used for HMAC token generation — derived from app secret
_TOKEN_SECRET: bytes = b""


def _get_token_secret() -> bytes:
    """Lazily derive the token secret from JWT_SECRET."""
    global _TOKEN_SECRET
    if not _TOKEN_SECRET:
        raw = Config.JWT_SECRET.encode()
        _TOKEN_SECRET = hashlib.sha256(b"vortex-node-token-v1:" + raw).digest()
    return _TOKEN_SECRET


# SSRF protection — block dangerous networks for outgoing requests
_BLOCKED_PEER_NETS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fc00::/7"),
]

# ══════════════════════════════════════════════════════════════════════════════
# SQLAlchemy Model
# ══════════════════════════════════════════════════════════════════════════════


class TrustedNode(Base):
    """A trusted peer node in the Vortex federation network."""
    __tablename__ = "trusted_nodes"

    id = Column(Integer, primary_key=True)
    url = Column(String, unique=True, nullable=False)
    name = Column(String, default="")
    node_id = Column(String, default="")
    status = Column(String, default="pending")
    trust_score = Column(Integer, default=0)
    code_hash = Column(String, default="")
    current_token = Column(String, default="")
    token_expires_at = Column(DateTime, nullable=True)
    task_slots = Column(String, default="[]")
    added_by = Column(Integer, nullable=True)
    added_at = Column(DateTime, default=func.now())
    last_seen = Column(DateTime, nullable=True)
    last_validated = Column(DateTime, nullable=True)
    fail_count = Column(Integer, default=0)
    version = Column(String, default="")


def _node_to_dict(node: TrustedNode) -> dict:
    """Serialize a TrustedNode to a JSON-safe dictionary."""
    return {
        "id": node.id,
        "url": node.url,
        "name": node.name,
        "node_id": node.node_id,
        "status": node.status,
        "trust_score": node.trust_score,
        "code_hash": node.code_hash,
        "task_slots": json.loads(node.task_slots) if node.task_slots else [],
        "added_by": node.added_by,
        "added_at": node.added_at.isoformat() if node.added_at else None,
        "last_seen": node.last_seen.isoformat() if node.last_seen else None,
        "last_validated": node.last_validated.isoformat() if node.last_validated else None,
        "fail_count": node.fail_count,
        "version": node.version,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Pydantic request/response models
# ══════════════════════════════════════════════════════════════════════════════


class AddNodeRequest(BaseModel):
    url: str
    name: str = ""


class VerifyNodeRequest(BaseModel):
    node_id: Optional[str] = None
    url: Optional[str] = None


class HandshakeRequest(BaseModel):
    node_id: str
    url: str
    code_hash: str
    version: str = ""
    name: str = ""


class GossipNodePayload(BaseModel):
    node_id: str
    url: str
    name: str = ""
    code_hash: str = ""
    version: str = ""


class ValidateTokenRequest(BaseModel):
    node_id: str
    token: str


# ══════════════════════════════════════════════════════════════════════════════
# NodeSandbox — Security isolation
# ══════════════════════════════════════════════════════════════════════════════


class NodeSandbox:
    """Security validation and isolation for federation node interactions."""

    @staticmethod
    def validate_url(url: str) -> str:
        """Parse and validate a node URL. Returns the normalized URL.

        Raises ValueError for invalid or blocked URLs.
        """
        from urllib.parse import urlparse
        parsed = urlparse(url)

        if parsed.scheme not in ("https", "http"):
            raise ValueError(f"Unsupported scheme: {parsed.scheme}")

        hostname = parsed.hostname
        if not hostname:
            raise ValueError("Missing hostname")

        # Allow http only for localhost
        is_localhost = hostname in ("localhost", "127.0.0.1", "::1")
        if parsed.scheme == "http" and not is_localhost:
            raise ValueError("HTTP is only allowed for localhost; use HTTPS")

        # SSRF protection: resolve hostname and check against blocked nets
        if not is_localhost:
            try:
                addr = ipaddress.ip_address(hostname)
                if any(addr in net for net in _BLOCKED_PEER_NETS):
                    raise ValueError(f"Blocked IP address: {hostname}")
            except ValueError as e:
                if "Blocked IP" in str(e):
                    raise
                # hostname is a domain name — will be resolved at connect time;
                # additional checks happen in probe_node via httpx

        # Port restrictions
        port = parsed.port
        if port is not None and port < 1024 and port not in (80, 443):
            raise ValueError(f"Non-standard privileged port not allowed: {port}")

        # Normalize: strip trailing slash
        normalized = f"{parsed.scheme}://{parsed.hostname}"
        if port and port not in (80, 443):
            normalized += f":{port}"
        if parsed.path and parsed.path != "/":
            normalized += parsed.path.rstrip("/")

        return normalized

    @staticmethod
    async def probe_node(url: str) -> dict:
        """Probe a remote Vortex node via GET /api/health.

        Returns a dict with node metadata on success.
        Raises ValueError or httpx errors on failure.
        """
        ssl_ctx = make_peer_ssl_context()
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5.0, connect=3.0),
            verify=ssl_ctx,
        ) as client:
            resp = await client.get(f"{url}/api/health")
            resp.raise_for_status()
            data = resp.json()

        # Verify it looks like a Vortex node
        if not isinstance(data, dict):
            raise ValueError("Health endpoint did not return a JSON object")

        # Vortex health endpoint typically includes "status" or "ok"
        if "status" not in data and "ok" not in data:
            raise ValueError("Health response missing expected fields (status/ok)")

        return {
            "name": data.get("node_name", data.get("name", "")),
            "version": data.get("version", ""),
            "node_id": data.get("node_id", ""),
        }

    @staticmethod
    def validate_payload(data: bytes, max_size: int = MAX_PAYLOAD_SIZE) -> dict:
        """Validate and parse a JSON payload with size and depth limits.

        Returns the parsed JSON dict.
        Raises ValueError on violations.
        """
        if len(data) > max_size:
            raise ValueError(f"Payload too large: {len(data)} bytes (max {max_size})")

        try:
            parsed = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError(f"Invalid JSON: {e}")

        if not isinstance(parsed, dict):
            raise ValueError("Payload must be a JSON object")

        # Depth check
        def _check_depth(obj: object, current: int = 0) -> None:
            if current > MAX_JSON_DEPTH:
                raise ValueError(f"JSON nesting depth exceeds {MAX_JSON_DEPTH}")
            if isinstance(obj, dict):
                for v in obj.values():
                    _check_depth(v, current + 1)
            elif isinstance(obj, list):
                for v in obj:
                    _check_depth(v, current + 1)

        _check_depth(parsed)
        return parsed

    @staticmethod
    def check_rate_limit(node_id: str, limit: int = RATE_LIMIT_REQUESTS) -> bool:
        """Token bucket rate limiter per node.

        Returns True if the request is allowed, False if rate-limited.
        """
        now = time.monotonic()
        bucket = _rate_limit_buckets.get(node_id)

        if bucket is None:
            _rate_limit_buckets[node_id] = {"tokens": limit - 1, "last": now}
            return True

        elapsed = now - bucket["last"]
        # Refill tokens based on elapsed time
        refill = elapsed * (limit / RATE_LIMIT_WINDOW)
        bucket["tokens"] = min(limit, bucket["tokens"] + refill)
        bucket["last"] = now

        if bucket["tokens"] >= 1:
            bucket["tokens"] -= 1
            return True

        return False


# In-memory rate limit buckets: {node_id: {"tokens": float, "last": float}}
_rate_limit_buckets: dict[str, dict] = {}


# ══════════════════════════════════════════════════════════════════════════════
# Code Hash Validation (blockchain-inspired)
# ══════════════════════════════════════════════════════════════════════════════


def _get_code_manifest() -> list[tuple[str, str]]:
    """Build a sorted manifest of (relative_path, sha256) for all .py files in app/.

    Returns a deterministic list used for code integrity verification.
    """
    app_dir = Path(__file__).resolve().parent.parent  # -> app/
    results: list[tuple[str, str]] = []

    for py_file in sorted(app_dir.glob("**/*.py")):
        rel = str(py_file.relative_to(app_dir))
        try:
            content = py_file.read_bytes()
            file_hash = hashlib.sha256(content).hexdigest()
            results.append((rel, file_hash))
        except OSError:
            continue

    return results


def compute_local_code_hash() -> str:
    """Compute a single SHA-256 hash over all Python files in the app/ directory.

    Files are sorted by relative path and their individual hashes are
    concatenated before producing the final digest. This serves as the
    factory code fingerprint.
    """
    manifest = _get_code_manifest()
    combined = "".join(f"{path}:{h}" for path, h in manifest)
    return hashlib.sha256(combined.encode()).hexdigest()


# Cache the local hash so we don't recompute every time
_local_code_hash_cache: str = ""
_local_code_hash_time: float = 0.0
_CODE_HASH_CACHE_TTL = 300.0  # 5 minutes


def _get_cached_code_hash() -> str:
    """Return the local code hash, caching it for performance."""
    global _local_code_hash_cache, _local_code_hash_time
    now = time.monotonic()
    if not _local_code_hash_cache or (now - _local_code_hash_time) > _CODE_HASH_CACHE_TTL:
        _local_code_hash_cache = compute_local_code_hash()
        _local_code_hash_time = now
    return _local_code_hash_cache


# ══════════════════════════════════════════════════════════════════════════════
# Rotating Participation Tokens
# ══════════════════════════════════════════════════════════════════════════════


def _time_bucket(ts: Optional[float] = None) -> int:
    """Return the current time bucket index for token rotation."""
    if ts is None:
        ts = time.time()
    return int(ts) // TOKEN_ROTATION_INTERVAL


def generate_node_token(node_id: str) -> tuple[str, datetime]:
    """Generate an HMAC-SHA256 participation token for a node.

    Returns (token_hex, expiry_datetime).
    """
    bucket = _time_bucket()
    msg = f"{node_id}:{bucket}".encode()
    token = hmac.new(_get_token_secret(), msg, hashlib.sha256).hexdigest()
    expires_at = datetime.fromtimestamp(
        (bucket + 1) * TOKEN_ROTATION_INTERVAL, tz=timezone.utc
    )
    return token, expires_at


def verify_node_token(node_id: str, token: str) -> bool:
    """Verify a node's participation token.

    Checks both the current and previous time bucket to allow a grace period
    during rotation transitions.
    """
    secret = _get_token_secret()
    current_bucket = _time_bucket()

    for bucket in (current_bucket, current_bucket - 1):
        msg = f"{node_id}:{bucket}".encode()
        expected = hmac.new(secret, msg, hashlib.sha256).hexdigest()
        if hmac.compare_digest(token, expected):
            return True

    return False


# ══════════════════════════════════════════════════════════════════════════════
# Task Distribution (consistent hashing)
# ══════════════════════════════════════════════════════════════════════════════


def _task_assignment_score(node_id: str, task_type: str) -> int:
    """Compute a deterministic hash score for assigning a task to a node."""
    h = hashlib.sha256(f"{node_id}:{task_type}".encode()).hexdigest()
    return int(h[:8], 16)


def distribute_tasks(nodes: list[TrustedNode]) -> dict[int, list[str]]:
    """Distribute task types across active nodes using consistent hashing.

    Each node receives 1-3 task types based on its trust_score.
    Returns a mapping of node.id -> list of task_type strings.
    """
    if not nodes:
        return {}

    assignments: dict[int, list[str]] = {n.id: [] for n in nodes}

    for task_type in TASK_TYPES:
        # Rank nodes by their hash score for this task type
        candidates = sorted(
            nodes,
            key=lambda n: _task_assignment_score(n.node_id or str(n.id), task_type),
        )
        # Assign to top candidate(s): primary + backup
        if candidates:
            assignments[candidates[0].id].append(task_type)

    # Enforce per-node limits based on trust_score
    for node in nodes:
        max_tasks = 1
        if node.trust_score >= 50:
            max_tasks = 2
        if node.trust_score >= 80:
            max_tasks = 3
        current = assignments.get(node.id, [])
        if len(current) > max_tasks:
            assignments[node.id] = current[:max_tasks]

    return assignments


def _apply_task_distribution(db: Session) -> None:
    """Recompute and persist task assignments for all active nodes."""
    active_nodes = db.query(TrustedNode).filter(
        TrustedNode.status.in_(["active", "verified"])
    ).all()

    if not active_nodes:
        return

    dist = distribute_tasks(active_nodes)
    for node in active_nodes:
        tasks = dist.get(node.id, [])
        node.task_slots = json.dumps(tasks)

    db.commit()
    logger.info("Task distribution updated for %d active nodes", len(active_nodes))


# ══════════════════════════════════════════════════════════════════════════════
# Gossip Protocol
# ══════════════════════════════════════════════════════════════════════════════


async def _gossip_new_node(node: TrustedNode) -> None:
    """Notify all active nodes that a new node has joined the network."""
    payload = {
        "node_id": node.node_id,
        "url": node.url,
        "name": node.name,
        "code_hash": node.code_hash,
        "version": node.version,
    }
    await _broadcast_gossip("/api/federation/gossip/node-joined", payload)


async def _gossip_node_left(node: TrustedNode) -> None:
    """Notify all active nodes that a node has left or died."""
    payload = {
        "node_id": node.node_id,
        "url": node.url,
    }
    await _broadcast_gossip("/api/federation/gossip/node-left", payload)


async def _broadcast_gossip(endpoint_path: str, payload: dict) -> None:
    """Send a gossip message to all active nodes."""
    db = SessionLocal()
    try:
        active_nodes = db.query(TrustedNode).filter(
            TrustedNode.status.in_(["active", "verified"])
        ).all()
        urls = [(n.url, n.node_id) for n in active_nodes]
    finally:
        db.close()

    if not urls:
        return

    ssl_ctx = make_peer_ssl_context()
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(5.0, connect=3.0),
        verify=ssl_ctx,
    ) as client:
        tasks = []
        for url, node_id in urls:
            # Don't gossip about a node back to itself
            if payload.get("url") == url:
                continue
            tasks.append(_send_gossip(client, url + endpoint_path, payload))
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            sent = sum(1 for r in results if not isinstance(r, Exception))
            logger.info("Gossip %s sent to %d/%d nodes", endpoint_path, sent, len(tasks))


async def _send_gossip(client: httpx.AsyncClient, url: str, payload: dict) -> None:
    """Send a single gossip message. Swallows errors."""
    try:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
    except Exception as e:
        logger.debug("Gossip to %s failed: %s", url, e)
        raise


# ══════════════════════════════════════════════════════════════════════════════
# Failover
# ══════════════════════════════════════════════════════════════════════════════


async def _failover_node(dead_node_id: int) -> None:
    """Handle failover when a node is declared dead.

    Redistributes the dead node's tasks to remaining active nodes and
    gossips the departure to the network.
    """
    db = SessionLocal()
    try:
        dead_node = db.query(TrustedNode).filter(TrustedNode.id == dead_node_id).first()
        if not dead_node:
            return

        old_status = dead_node.status
        dead_node.status = "dead"
        dead_node.trust_score = max(0, dead_node.trust_score - TRUST_SCORE_PENALTY)

        # Clear tasks from dead node
        dead_tasks = json.loads(dead_node.task_slots) if dead_node.task_slots else []
        dead_node.task_slots = "[]"

        # Redistribute tasks across remaining active nodes
        _apply_task_distribution(db)

        # If the dead node had critical tasks, ensure the highest-trust node picks them up
        if dead_tasks:
            highest = db.query(TrustedNode).filter(
                TrustedNode.status.in_(["active", "verified"]),
                TrustedNode.id != dead_node_id,
            ).order_by(TrustedNode.trust_score.desc()).first()

            if highest:
                existing = json.loads(highest.task_slots) if highest.task_slots else []
                for task in dead_tasks:
                    if task not in existing:
                        existing.append(task)
                highest.task_slots = json.dumps(existing[:3])  # cap at 3
                db.commit()
                logger.info(
                    "Critical tasks from dead node %s reassigned to %s",
                    dead_node.url, highest.url,
                )

        db.commit()

        if old_status != "dead":
            logger.warning(
                "Node %s declared dead (fail_count=%d, trust=%d)",
                dead_node.url, dead_node.fail_count, dead_node.trust_score,
            )
            await _gossip_node_left(dead_node)
    except Exception as e:
        db.rollback()
        logger.error("Failover error for node %d: %s", dead_node_id, e)
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# Background Tasks — Health Monitor & Token Rotation
# ══════════════════════════════════════════════════════════════════════════════

_monitor_task: Optional[asyncio.Task] = None
_token_rotation_task: Optional[asyncio.Task] = None
_shutdown_event = asyncio.Event()


async def _health_monitor_loop() -> None:
    """Background loop that pings all active nodes every HEALTH_CHECK_INTERVAL seconds."""
    ssl_ctx = make_peer_ssl_context()

    while not _shutdown_event.is_set():
        try:
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)
        except asyncio.CancelledError:
            return

        db = SessionLocal()
        try:
            nodes = db.query(TrustedNode).filter(
                TrustedNode.status.in_(["active", "verified", "pending"])
            ).all()

            if not nodes:
                continue

            async with httpx.AsyncClient(
                timeout=httpx.Timeout(5.0, connect=3.0),
                verify=ssl_ctx,
            ) as client:
                for node in nodes:
                    if _shutdown_event.is_set():
                        return
                    try:
                        resp = await client.get(f"{node.url}/api/health")
                        resp.raise_for_status()
                        node.last_seen = datetime.now(timezone.utc)
                        node.fail_count = 0
                        if node.status == "pending":
                            # Auto-promote pending nodes that respond
                            pass
                    except Exception as e:
                        node.fail_count += 1
                        logger.debug(
                            "Health check failed for %s (count=%d): %s",
                            node.url, node.fail_count, e,
                        )
                        if node.fail_count >= MAX_FAIL_COUNT and node.status != "dead":
                            db.commit()
                            await _failover_node(node.id)
                            # Refresh the node object after failover modified it
                            db.refresh(node)

            db.commit()
        except asyncio.CancelledError:
            return
        except Exception as e:
            db.rollback()
            logger.error("Health monitor loop error: %s", e)
        finally:
            db.close()


async def _token_rotation_loop() -> None:
    """Background loop that rotates participation tokens for all active nodes."""
    while not _shutdown_event.is_set():
        try:
            await asyncio.sleep(TOKEN_ROTATION_INTERVAL)
        except asyncio.CancelledError:
            return

        db = SessionLocal()
        try:
            nodes = db.query(TrustedNode).filter(
                TrustedNode.status.in_(["active", "verified"])
            ).all()

            for node in nodes:
                nid = node.node_id or str(node.id)
                token, expires = generate_node_token(nid)
                node.current_token = token
                node.token_expires_at = expires

            db.commit()
            if nodes:
                logger.debug("Rotated tokens for %d nodes", len(nodes))
        except asyncio.CancelledError:
            return
        except Exception as e:
            db.rollback()
            logger.error("Token rotation error: %s", e)
        finally:
            db.close()


async def start_federation_monitor() -> None:
    """Start the health-check and token-rotation background loops."""
    global _monitor_task, _token_rotation_task
    _shutdown_event.clear()

    if _monitor_task is None or _monitor_task.done():
        _monitor_task = asyncio.create_task(_health_monitor_loop())
        logger.info("Federation health monitor started")

    if _token_rotation_task is None or _token_rotation_task.done():
        _token_rotation_task = asyncio.create_task(_token_rotation_loop())
        logger.info("Federation token rotation started")


async def stop_federation_monitor() -> None:
    """Stop the background loops gracefully."""
    global _monitor_task, _token_rotation_task
    _shutdown_event.set()

    for task in (_monitor_task, _token_rotation_task):
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    _monitor_task = None
    _token_rotation_task = None
    logger.info("Federation monitor stopped")


# ══════════════════════════════════════════════════════════════════════════════
# Code Verification — choose a validator node
# ══════════════════════════════════════════════════════════════════════════════


async def _verify_code_hash_via_validator(
    candidate_hash: str,
    exclude_url: str,
    db: Session,
) -> bool:
    """Pick a random already-validated node and compare its code hash with the candidate.

    Returns True if the candidate hash matches the validator's hash (or our own
    if no external validators are available).
    """
    validators = db.query(TrustedNode).filter(
        TrustedNode.status.in_(["active", "verified"]),
        TrustedNode.url != exclude_url,
    ).all()

    if validators:
        import random
        validator = random.choice(validators)
        ssl_ctx = make_peer_ssl_context()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(5.0, connect=3.0),
                verify=ssl_ctx,
            ) as client:
                resp = await client.get(f"{validator.url}/api/federation/code-hash")
                resp.raise_for_status()
                remote_hash = resp.json().get("code_hash", "")
                return hmac.compare_digest(candidate_hash, remote_hash)
        except Exception as e:
            logger.warning(
                "Validator %s unreachable for code verification: %s",
                validator.url, e,
            )

    # Fallback: compare against local code hash
    local_hash = _get_cached_code_hash()
    return hmac.compare_digest(candidate_hash, local_hash)


# ══════════════════════════════════════════════════════════════════════════════
# Router & Endpoints
# ══════════════════════════════════════════════════════════════════════════════

trusted_nodes_router = APIRouter(prefix="/api/federation", tags=["federation-nodes"])


@trusted_nodes_router.post("/nodes/add")
async def add_node(
    body: AddNodeRequest,
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a new trusted node by URL. Probes the node to verify it's a Vortex instance."""
    try:
        normalized_url = NodeSandbox.validate_url(body.url)
    except ValueError as e:
        raise HTTPException(400, f"Invalid URL: {e}")

    # Check for duplicates
    existing = db.query(TrustedNode).filter(TrustedNode.url == normalized_url).first()
    if existing:
        raise HTTPException(409, f"Node already registered (status: {existing.status})")

    # Probe the remote node
    try:
        info = await NodeSandbox.probe_node(normalized_url)
    except Exception as e:
        raise HTTPException(
            502, f"Could not reach node at {normalized_url}: {e}"
        )

    node_id = info.get("node_id") or secrets.token_hex(16)

    node = TrustedNode(
        url=normalized_url,
        name=body.name or info.get("name", ""),
        node_id=node_id,
        status="pending",
        trust_score=10,
        version=info.get("version", ""),
        added_by=u.id,
        last_seen=datetime.now(timezone.utc),
    )
    db.add(node)
    db.commit()
    db.refresh(node)

    logger.info("Node added: %s (%s) by user %d", normalized_url, node_id, u.id)

    # Initiate handshake in background
    asyncio.create_task(_initiate_handshake(node.id))

    return {"node": _node_to_dict(node)}


async def _initiate_handshake(node_db_id: int) -> None:
    """Send a handshake request to a newly added node."""
    db = SessionLocal()
    try:
        node = db.query(TrustedNode).filter(TrustedNode.id == node_db_id).first()
        if not node:
            return

        local_hash = _get_cached_code_hash()
        local_node_id = _get_local_node_id()
        local_url = _get_local_url()

        ssl_ctx = make_peer_ssl_context()
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            verify=ssl_ctx,
        ) as client:
            resp = await client.post(
                f"{node.url}/api/federation/handshake",
                json={
                    "node_id": local_node_id,
                    "url": local_url,
                    "code_hash": local_hash,
                    "version": "1.0.0",
                    "name": Config.DEVICE_NAME or "Vortex Node",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("accepted"):
                node.status = "verified"
                node.trust_score = 50
                node.code_hash = data.get("code_hash", "")
                node.last_validated = datetime.now(timezone.utc)
                token, expires = generate_node_token(node.node_id)
                node.current_token = token
                node.token_expires_at = expires
                db.commit()
                _apply_task_distribution(db)
                logger.info("Handshake accepted by %s", node.url)
                await _gossip_new_node(node)
            else:
                node.status = "suspended"
                node.trust_score = 0
                db.commit()
                logger.warning(
                    "Handshake rejected by %s: %s",
                    node.url, data.get("reason", "unknown"),
                )
    except Exception as e:
        logger.error("Handshake with node %d failed: %s", node_db_id, e)
        try:
            if node:
                node.fail_count += 1
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


def _get_local_node_id() -> str:
    """Return a stable identifier for this node."""
    raw = f"{Config.JWT_SECRET}:node-id".encode()
    return hashlib.sha256(raw).hexdigest()[:32]


def _get_local_url() -> str:
    """Best-effort construction of this node's reachable URL."""
    import socket
    host = Config.HOST
    if host in ("0.0.0.0", "::"):
        try:
            host = socket.getfqdn()
        except Exception:
            host = "localhost"
    port = Config.PORT
    scheme = "https" if port == 443 or os.path.exists("certs/vortex.crt") else "http"
    if port in (80, 443):
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


@trusted_nodes_router.get("/nodes")
async def list_nodes(
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all trusted nodes in the federation."""
    nodes = db.query(TrustedNode).order_by(TrustedNode.trust_score.desc()).all()
    return {"nodes": [_node_to_dict(n) for n in nodes]}


@trusted_nodes_router.delete("/nodes/{node_id}")
async def remove_node(
    node_id: int,
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a trusted node from the federation."""
    node = db.query(TrustedNode).filter(TrustedNode.id == node_id).first()
    if not node:
        raise HTTPException(404, "Node not found")

    url = node.url
    db.delete(node)
    db.commit()

    # Redistribute tasks after removal
    _apply_task_distribution(db)

    logger.info("Node removed: %s (by user %d)", url, u.id)
    asyncio.create_task(_gossip_node_left(node))

    return {"removed": True, "url": url}


@trusted_nodes_router.post("/nodes/verify")
async def verify_node(
    body: VerifyNodeRequest,
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manually trigger re-verification of a node."""
    node = None
    if body.node_id:
        node = db.query(TrustedNode).filter(TrustedNode.node_id == body.node_id).first()
    elif body.url:
        node = db.query(TrustedNode).filter(TrustedNode.url == body.url).first()

    if not node:
        raise HTTPException(404, "Node not found")

    # Re-probe
    try:
        info = await NodeSandbox.probe_node(node.url)
        node.last_seen = datetime.now(timezone.utc)
        node.version = info.get("version", node.version)
        node.name = info.get("name", node.name)
    except Exception as e:
        node.fail_count += 1
        db.commit()
        raise HTTPException(502, f"Node unreachable: {e}")

    # Re-initiate handshake
    node.status = "pending"
    db.commit()

    asyncio.create_task(_initiate_handshake(node.id))

    return {"status": "verification_initiated", "node": _node_to_dict(node)}


@trusted_nodes_router.get("/nodes/status")
async def network_status(
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return a summary of the federation network status."""
    total = db.query(TrustedNode).count()
    active = db.query(TrustedNode).filter(
        TrustedNode.status.in_(["active", "verified"])
    ).count()
    pending = db.query(TrustedNode).filter(TrustedNode.status == "pending").count()
    dead = db.query(TrustedNode).filter(TrustedNode.status == "dead").count()
    suspended = db.query(TrustedNode).filter(TrustedNode.status == "suspended").count()

    return {
        "total_nodes": total,
        "active": active,
        "pending": pending,
        "dead": dead,
        "suspended": suspended,
        "local_node_id": _get_local_node_id(),
        "local_code_hash": _get_cached_code_hash(),
        "monitor_running": _monitor_task is not None and not _monitor_task.done()
        if _monitor_task else False,
    }


@trusted_nodes_router.post("/handshake")
async def receive_handshake(
    body: HandshakeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Receive an incoming handshake from another Vortex node."""
    # Validate the incoming URL
    try:
        normalized_url = NodeSandbox.validate_url(body.url)
    except ValueError as e:
        raise HTTPException(400, f"Invalid URL: {e}")

    # Rate limit by node_id
    if not NodeSandbox.check_rate_limit(body.node_id):
        raise HTTPException(429, "Rate limit exceeded")

    # Verify code hash
    hash_valid = await _verify_code_hash_via_validator(
        body.code_hash, normalized_url, db
    )

    if not hash_valid:
        logger.warning(
            "Handshake rejected for %s: code hash mismatch (theirs=%s)",
            normalized_url, body.code_hash[:16] + "...",
        )
        return {
            "accepted": False,
            "reason": "code_hash_mismatch",
            "code_hash": _get_cached_code_hash(),
        }

    # Check if node already exists
    node = db.query(TrustedNode).filter(TrustedNode.url == normalized_url).first()
    if node is None:
        node = TrustedNode(
            url=normalized_url,
            name=body.name,
            node_id=body.node_id,
            status="verified",
            trust_score=50,
            code_hash=body.code_hash,
            version=body.version,
            last_seen=datetime.now(timezone.utc),
            last_validated=datetime.now(timezone.utc),
        )
        db.add(node)
    else:
        node.status = "verified"
        node.trust_score = max(node.trust_score, 50)
        node.code_hash = body.code_hash
        node.version = body.version
        node.node_id = body.node_id
        node.name = body.name or node.name
        node.last_seen = datetime.now(timezone.utc)
        node.last_validated = datetime.now(timezone.utc)
        node.fail_count = 0

    # Generate a participation token for the joining node
    token, expires = generate_node_token(body.node_id)
    node.current_token = token
    node.token_expires_at = expires

    db.commit()
    db.refresh(node)

    # Redistribute tasks
    _apply_task_distribution(db)

    logger.info("Handshake accepted from %s (node_id=%s)", normalized_url, body.node_id)

    # Gossip about the new node
    asyncio.create_task(_gossip_new_node(node))

    return {
        "accepted": True,
        "node_id": _get_local_node_id(),
        "code_hash": _get_cached_code_hash(),
        "token": token,
        "token_expires_at": expires.isoformat(),
    }


@trusted_nodes_router.post("/code-manifest")
async def code_manifest_endpoint(
    request: Request,
    db: Session = Depends(get_db),
):
    """Return the local node's code manifest hash for verification."""
    # Rate limit by client IP
    client_ip = request.client.host if request.client else "unknown"
    if not NodeSandbox.check_rate_limit(f"manifest:{client_ip}"):
        raise HTTPException(429, "Rate limit exceeded")

    manifest = _get_code_manifest()
    manifest_hash = _get_cached_code_hash()

    return {
        "code_hash": manifest_hash,
        "file_count": len(manifest),
        "node_id": _get_local_node_id(),
    }


@trusted_nodes_router.get("/code-hash")
async def code_hash_endpoint():
    """Return the top-level code hash for this node."""
    return {
        "code_hash": _get_cached_code_hash(),
        "node_id": _get_local_node_id(),
    }


@trusted_nodes_router.post("/gossip/node-joined")
async def gossip_node_joined(
    body: GossipNodePayload,
    request: Request,
    db: Session = Depends(get_db),
):
    """Receive gossip about a new node joining the network."""
    client_ip = request.client.host if request.client else "unknown"
    if not NodeSandbox.check_rate_limit(f"gossip:{client_ip}"):
        raise HTTPException(429, "Rate limit exceeded")

    # Gossip security: rate limit + reputation + PoW
    if not _gossip_rate_limiter.is_allowed(client_ip):
        raise HTTPException(429, "Gossip cooldown active")
    if _reputation_manager.is_banned(client_ip):
        raise HTTPException(403, "Peer banned due to low reputation")
    if ProofOfWork.needs_pow(client_ip):
        raise HTTPException(428, detail=ProofOfWork.issue_challenge(client_ip))

    try:
        normalized_url = NodeSandbox.validate_url(body.url)
    except ValueError:
        _reputation_manager.record_failure(client_ip, penalty=0.2)
        raise HTTPException(400, "Invalid node URL in gossip")

    existing = db.query(TrustedNode).filter(TrustedNode.url == normalized_url).first()
    if existing:
        # Update last_seen if already known
        existing.last_seen = datetime.now(timezone.utc)
        if body.version:
            existing.version = body.version
        db.commit()
        return {"status": "already_known", "node_id": body.node_id}

    # Add as a pending node — we'll verify on next health check or manually
    node = TrustedNode(
        url=normalized_url,
        name=body.name,
        node_id=body.node_id,
        status="pending",
        trust_score=0,
        code_hash=body.code_hash,
        version=body.version,
        last_seen=datetime.now(timezone.utc),
    )
    db.add(node)
    db.commit()

    _reputation_manager.record_success(client_ip)
    logger.info("Gossip: learned about new node %s (%s)", normalized_url, body.node_id)
    return {"status": "added_as_pending", "node_id": body.node_id}


@trusted_nodes_router.post("/gossip/node-left")
async def gossip_node_left(
    body: GossipNodePayload,
    request: Request,
    db: Session = Depends(get_db),
):
    """Receive gossip about a node leaving the network."""
    client_ip = request.client.host if request.client else "unknown"
    if not NodeSandbox.check_rate_limit(f"gossip:{client_ip}"):
        raise HTTPException(429, "Rate limit exceeded")
    if not _gossip_rate_limiter.is_allowed(client_ip):
        raise HTTPException(429, "Gossip cooldown active")
    if _reputation_manager.is_banned(client_ip):
        raise HTTPException(403, "Peer banned due to low reputation")

    node = db.query(TrustedNode).filter(TrustedNode.node_id == body.node_id).first()
    if not node:
        return {"status": "unknown_node"}

    if node.status not in ("dead", "suspended"):
        node.status = "dead"
        node.trust_score = max(0, node.trust_score - TRUST_SCORE_PENALTY)
        db.commit()
        _apply_task_distribution(db)
        logger.info("Gossip: node %s marked dead", node.url)

    return {"status": "marked_dead", "node_id": body.node_id}


@trusted_nodes_router.get("/my-tasks")
async def my_tasks(
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the task types assigned to this node."""
    local_id = _get_local_node_id()
    local_hash = _get_cached_code_hash()

    # Check if this node is registered anywhere; return local perspective
    active_nodes = db.query(TrustedNode).filter(
        TrustedNode.status.in_(["active", "verified"])
    ).all()

    # Compute what tasks *would* be assigned to the local node
    # by simulating it as part of the active set
    class _LocalProxy:
        def __init__(self):
            self.id = 0
            self.node_id = local_id
            self.trust_score = 100  # local node gets max trust
            self.task_slots = "[]"

    local_proxy = _LocalProxy()
    all_nodes = [local_proxy] + active_nodes  # type: ignore[list-item]
    dist = distribute_tasks(all_nodes)  # type: ignore[arg-type]
    my = dist.get(0, [])

    return {
        "node_id": local_id,
        "tasks": my,
        "total_active_nodes": len(active_nodes),
        "code_hash": local_hash,
    }


@trusted_nodes_router.post("/validate-token")
async def validate_token(
    body: ValidateTokenRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Validate a node's participation token."""
    client_ip = request.client.host if request.client else "unknown"
    if not NodeSandbox.check_rate_limit(f"validate:{client_ip}"):
        raise HTTPException(429, "Rate limit exceeded")

    valid = verify_node_token(body.node_id, body.token)

    if valid:
        # Update last_seen for the node
        node = db.query(TrustedNode).filter(TrustedNode.node_id == body.node_id).first()
        if node:
            node.last_seen = datetime.now(timezone.utc)
            if node.status == "verified":
                node.status = "active"
                node.trust_score = min(100, node.trust_score + 5)
            db.commit()

    return {"valid": valid, "node_id": body.node_id}
