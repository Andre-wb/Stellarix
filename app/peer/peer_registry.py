"""
app/peer/peer_registry.py — P2P Discovery + Federation + Multihop
"""
from __future__ import annotations

import asyncio
import json
import logging
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.config import Config
from app.models import User
from app.peer.connection_manager import manager as ws_manager
from app.security.auth_jwt import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/peers", tags=["peers"])


# ══════════════════════════════════════════════════════════════════════════════
# PeerInfo
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class PeerInfo:
    name:            str
    ip:              str
    port:            int
    node_pubkey_hex: Optional[str] = None
    last_seen:       float         = field(default_factory=time.monotonic)

    def alive(self) -> bool:
        return (time.monotonic() - self.last_seen) < Config.PEER_TIMEOUT_SEC

    def has_encryption(self) -> bool:
        return bool(self.node_pubkey_hex and len(self.node_pubkey_hex) == 64)

    def to_dict(self) -> dict:
        return {
            "name":      self.name,
            "ip":        self.ip,
            "port":      self.port,
            "age_sec":   round(time.monotonic() - self.last_seen, 1),
            "online":    self.alive(),
            "encrypted": self.has_encryption(),
            "pubkey":    self.node_pubkey_hex[:16] + "..." if self.node_pubkey_hex else None,
        }

    @property
    def base_url(self) -> str:
        scheme = "https" if getattr(Config, "SSL_ENABLED", False) else "http"
        return f"{scheme}://{self.ip}:{self.port}"


# ══════════════════════════════════════════════════════════════════════════════
# PeerRegistry
# ══════════════════════════════════════════════════════════════════════════════

class PeerRegistry:
    def __init__(self):
        self._peers:      dict[str, PeerInfo] = {}
        self._lock        = threading.Lock()
        self.own_ip:  str = "127.0.0.1"
        self._peer_rooms: dict[str, list] = {}
        self._rooms_lock  = threading.Lock()

    def update(self, ip: str, name: str, port: int,
               node_pubkey_hex: Optional[str] = None) -> bool:
        with self._lock:
            is_new = ip not in self._peers
            if not is_new:
                p = self._peers[ip]
                p.name      = name
                p.port      = port
                p.last_seen = time.monotonic()
                if node_pubkey_hex and len(node_pubkey_hex) == 64:
                    p.node_pubkey_hex = node_pubkey_hex
            else:
                self._peers[ip] = PeerInfo(
                    name            = name,
                    ip              = ip,
                    port            = port,
                    node_pubkey_hex = node_pubkey_hex,
                )
                logger.info(f"🔍 New peer: {name}@{ip}:{port} encrypted={bool(node_pubkey_hex)}")
            return is_new

    def active(self) -> list[PeerInfo]:
        with self._lock:
            return [p for p in self._peers.values() if p.alive()]

    def get(self, ip: str) -> Optional[PeerInfo]:
        with self._lock:
            return self._peers.get(ip)

    def cleanup(self) -> None:
        with self._lock:
            dead = [ip for ip, p in self._peers.items() if not p.alive()]
            for ip in dead:
                del self._peers[ip]
        with self._rooms_lock:
            for ip in dead:
                self._peer_rooms.pop(ip, None)

    def set_peer_rooms(self, ip: str, rooms: list) -> None:
        with self._rooms_lock:
            self._peer_rooms[ip] = rooms

    def get_all_peer_rooms(self) -> list[dict]:
        result     = []
        active_ips = {p.ip for p in self.active()}
        with self._rooms_lock:
            for ip, rooms in self._peer_rooms.items():
                if ip not in active_ips:
                    continue
                peer      = self.get(ip)
                peer_name = peer.name if peer else ip
                peer_port = peer.port if peer else getattr(Config, "PORT", 8000)
                for room in rooms:
                    result.append({
                        **room,
                        "peer_ip":   ip,
                        "peer_name": peer_name,
                        "peer_port": peer_port,
                    })
        return result


registry = PeerRegistry()

_main_loop: Optional[asyncio.AbstractEventLoop] = None


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _local_ip() -> str:
    for target in ("192.168.1.1", "10.0.0.1", "172.16.0.1", "8.8.8.8"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.05)
            s.connect((target, 80))
            ip = s.getsockname()[0]
            s.close()
            if not ip.startswith("127."):
                return ip
        except Exception:
            pass
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return "127.0.0.1"


def _subnet_broadcast(ip: str) -> str:
    try:
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}.255"
    except Exception:
        pass
    return "255.255.255.255"


def _get_node_keys():
    from app.security.crypto import load_or_create_node_keypair
    return load_or_create_node_keypair(Config.KEYS_DIR)


# ══════════════════════════════════════════════════════════════════════════════
# Room fetching
# ══════════════════════════════════════════════════════════════════════════════

async def _fetch_peer_rooms(peer: PeerInfo) -> None:
    for scheme in ("https", "http"):
        url = f"{scheme}://{peer.ip}:{peer.port}/api/rooms/public"
        try:
            async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    rooms = resp.json().get("rooms", [])
                    registry.set_peer_rooms(peer.ip, rooms)
                    logger.info(
                        f"📦 {len(rooms)} public rooms from {peer.name}@{peer.ip} via {scheme}"
                    )
                    return
        except Exception as e:
            logger.debug(f"Failed {scheme}://{peer.ip}: {e}")


def _schedule_fetch_peer_rooms(peer: PeerInfo) -> None:
    if _main_loop is not None and _main_loop.is_running():
        asyncio.run_coroutine_threadsafe(_fetch_peer_rooms(peer), _main_loop)
    else:
        logger.debug(f"_main_loop not ready, skip room fetch for {peer.ip}")


# ══════════════════════════════════════════════════════════════════════════════
# Discovery
# ══════════════════════════════════════════════════════════════════════════════

def start_discovery(device_name: str = "") -> None:
    global _main_loop
    try:
        _main_loop = asyncio.get_running_loop()
    except RuntimeError:
        _main_loop = asyncio.get_event_loop()

    name = device_name or socket.gethostname()
    registry.own_ip = _local_ip()

    try:
        _, node_pub = _get_node_keys()
        node_pubkey_hex = node_pub.hex() if isinstance(node_pub, bytes) else bytes(node_pub).hex()
    except Exception as e:
        logger.warning(f"Не удалось получить X25519 ключ: {e}")
        node_pubkey_hex = None

    try:
        import vortex_chat as _vc
        _vc.start_discovery(name, Config.PORT)
        logger.info(f"🦀 Rust UDP discovery: «{name}»")

        def _sync_rust_peers():
            while True:
                try:
                    for ip, port in _vc.get_peers():
                        is_new = registry.update(ip, ip, port)
                        if is_new:
                            peer = registry.get(ip)
                            if peer:
                                _schedule_fetch_peer_rooms(peer)
                        else:
                            # Пир уже известен — всё равно обновляем его комнаты,
                            # чтобы подхватывать новые комнаты созданные после discovery.
                            peer = registry.get(ip)
                            if peer:
                                _schedule_fetch_peer_rooms(peer)
                except Exception:
                    pass
                time.sleep(3)

        threading.Thread(target=_sync_rust_peers, daemon=True, name="rust-peers-sync").start()
        return
    except (ImportError, AttributeError):
        logger.info("Python UDP discovery fallback")

    threading.Thread(target=_py_listener, daemon=True, name="udp-listen").start()
    threading.Thread(
        target=_py_sender, args=(name, node_pubkey_hex), daemon=True, name="udp-send"
    ).start()
    logger.info(f"🐍 Python UDP discovery: «{name}» pubkey={'yes' if node_pubkey_hex else 'no'}")


def _py_listener():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", Config.UDP_PORT))
        sock.settimeout(2.0)
    except OSError as e:
        logger.error(f"UDP bind failed: {e}")
        return

    while True:
        try:
            data, addr = sock.recvfrom(1024)
            src_ip = addr[0]
            if src_ip == registry.own_ip or src_ip.startswith("127."):
                continue

            info   = json.loads(data.decode())
            pubkey = info.get("pubkey")
            if pubkey and len(pubkey) != 64:
                pubkey = None
            if pubkey:
                try:
                    bytes.fromhex(pubkey)
                except ValueError:
                    pubkey = None

            is_new = registry.update(
                src_ip,
                str(info.get("name", src_ip))[:64],
                int(info.get("port", Config.PORT)),
                pubkey,
            )

            peer = registry.get(src_ip)
            if peer:
                if is_new:
                    # Новый пир — сразу забираем его комнаты.
                    _schedule_fetch_peer_rooms(peer)
                else:
                    # Известный пир прислал heartbeat — обновляем список его комнат,
                    # чтобы новые комнаты появлялись у соседей без перезапуска.
                    _schedule_fetch_peer_rooms(peer)

        except socket.timeout:
            registry.cleanup()
        except Exception as e:
            logger.debug(f"UDP recv: {e}")


def _py_sender(name: str, node_pubkey_hex: Optional[str]):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    while True:
        try:
            own_ip = _local_ip()
            if own_ip != registry.own_ip and not own_ip.startswith("127."):
                registry.own_ip = own_ip

            payload_dict = {"name": name, "port": Config.PORT}
            if node_pubkey_hex:
                payload_dict["pubkey"] = node_pubkey_hex

            payload = json.dumps(payload_dict).encode()
            bcast   = _subnet_broadcast(own_ip)
            sock.sendto(payload, (bcast, Config.UDP_PORT))
            try:
                sock.sendto(payload, ("255.255.255.255", Config.UDP_PORT))
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"UDP send: {e}")
        time.sleep(Config.UDP_INTERVAL_SEC)


# ══════════════════════════════════════════════════════════════════════════════
# P2P encrypted send
# ══════════════════════════════════════════════════════════════════════════════

async def _send_to_peer_encrypted(
        peer:           PeerInfo,
        room_id:        int,
        sender:         str,
        ciphertext_hex: str,
        msg_type:       str = "text",
) -> bool:
    node_priv, node_pub_raw = _get_node_keys()
    node_pub        = node_pub_raw if isinstance(node_pub_raw, bytes) else bytes(node_pub_raw)
    node_priv_bytes = node_priv    if isinstance(node_priv,    bytes) else bytes(node_priv)

    payload_dict = {
        "room_id":    room_id,
        "sender":     sender,
        "ciphertext": ciphertext_hex,
        "msg_type":   msg_type,
    }

    try:
        if peer.has_encryption():
            from app.security.key_exchange import encrypt_p2p_payload
            encrypted    = encrypt_p2p_payload(payload_dict, node_priv_bytes, peer.node_pubkey_hex)
            request_body = {
                "ephemeral_pub": encrypted["ephemeral_pub"],
                "ciphertext":    encrypted["ciphertext"],
                "sender_pubkey": node_pub.hex(),
            }
        else:
            logger.warning(f"Peer {peer.ip} no pubkey — P2P unencrypted")
            request_body = {
                "plaintext_payload": payload_dict,
                "sender_pubkey":     node_pub.hex(),
            }

        async with httpx.AsyncClient(timeout=3.0, verify=False) as client:
            response = await client.post(
                f"{peer.base_url}/api/peers/receive",
                json=request_body,
            )
            return response.status_code == 200

    except Exception as e:
        logger.debug(f"P2P send to {peer.ip} failed: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# REST API
# ══════════════════════════════════════════════════════════════════════════════

@router.get("")
async def list_peers(u: User = Depends(get_current_user)):
    peers = registry.active()
    return {
        "own_ip":    registry.own_ip,
        "count":     len(peers),
        "peers":     [p.to_dict() for p in peers],
        "encrypted": sum(1 for p in peers if p.has_encryption()),
    }


@router.get("/status")
async def peer_status():
    _, node_pub_raw = _get_node_keys()
    node_pub = node_pub_raw if isinstance(node_pub_raw, bytes) else bytes(node_pub_raw)
    return {"ok": True, "own_ip": registry.own_ip,
            "peers": len(registry.active()), "pubkey": node_pub.hex()}


@router.get("/public-rooms")
async def get_peer_public_rooms(u: User = Depends(get_current_user)):
    return {"rooms": registry.get_all_peer_rooms(), "peers": len(registry.active())}


# Принудительно опрашивает всех известных активных пиров и обновляет кэш комнат.
# Вызывается клиентом перед чтением /public-rooms чтобы получить актуальный список.
@router.post("/refresh-rooms")
async def refresh_peer_rooms(u: User = Depends(get_current_user)):
    peers = registry.active()
    await asyncio.gather(*[_fetch_peer_rooms(p) for p in peers], return_exceptions=True)
    return {"refreshed": len(peers), "rooms": len(registry.get_all_peer_rooms())}


# ══════════════════════════════════════════════════════════════════════════════
# Federated join
# ══════════════════════════════════════════════════════════════════════════════

class FederatedJoinRequest(BaseModel):
    invite_code: str
    peer_ip:     str
    peer_port:   int


@router.post("/federated-join")
async def federated_join(body: FederatedJoinRequest, u: User = Depends(get_current_user)):
    remote_base = None
    for scheme in ("https", "http"):
        try:
            async with httpx.AsyncClient(timeout=4.0, verify=False) as client:
                r = await client.get(
                    f"{scheme}://{body.peer_ip}:{body.peer_port}/api/peers/status"
                )
                if r.status_code == 200:
                    remote_base = f"{scheme}://{body.peer_ip}:{body.peer_port}"
                    break
        except Exception:
            continue

    if not remote_base:
        raise HTTPException(503, f"Узел {body.peer_ip}:{body.peer_port} недоступен")

    try:
        async with httpx.AsyncClient(timeout=8.0, verify=False) as client:
            resp = await client.post(
                f"{remote_base}/api/federation/guest-login",
                json={
                    "username":      u.username,
                    "display_name":  u.display_name,
                    "avatar_emoji":  u.avatar_emoji,
                    "x25519_pubkey": u.x25519_public_key or "",
                    "peer_port":     Config.PORT,
                },
            )
    except Exception as e:
        raise HTTPException(502, f"Ошибка подключения к узлу: {e}")

    if resp.status_code == 403:
        raise HTTPException(
            403,
            "Удалённый узел не распознал этот узел. "
            "Подождите ~10 секунд (UDP discovery) и попробуйте снова."
        )
    if resp.status_code != 200:
        raise HTTPException(502, f"guest-login: {resp.status_code} {resp.text[:200]}")

    remote_jwt = resp.json()["access_token"]

    try:
        async with httpx.AsyncClient(timeout=8.0, verify=False) as client:
            join_resp = await client.post(
                f"{remote_base}/api/rooms/join/{body.invite_code.upper()}",
                headers={"Authorization": f"Bearer {remote_jwt}"},
                json={},
            )
    except Exception as e:
        raise HTTPException(502, f"Ошибка при вступлении: {e}")

    if join_resp.status_code not in (200, 201):
        raise HTTPException(join_resp.status_code, join_resp.text[:200])

    room_info      = join_resp.json().get("room", {})
    remote_room_id = room_info.get("id")
    if not remote_room_id:
        raise HTTPException(502, "Удалённый узел не вернул room_id")

    from app.federation.federation import relay

    virtual_room = await relay.join(
        peer_ip        = body.peer_ip,
        peer_port      = body.peer_port,
        remote_room_id = remote_room_id,
        remote_jwt     = remote_jwt,
        room_name      = room_info.get("name", "Remote Room"),
        invite_code    = body.invite_code.upper(),
        is_private     = room_info.get("is_private", False),
        member_count   = room_info.get("member_count", 0),
        user_id        = u.id,
    )

    logger.info(
        f"🌐 {u.username} → {body.peer_ip}:{body.peer_port}/room/{remote_room_id} "
        f"(virtual_id={virtual_room.virtual_id})"
    )

    return {
        "joined":       True,
        "is_federated": True,
        "ws_path":      f"/ws/fed/{virtual_room.virtual_id}",
        "room": {
            "id":           virtual_room.virtual_id,
            "name":         virtual_room.room_name,
            "description":  f"🌐 {body.peer_ip}:{body.peer_port}",
            "is_private":   virtual_room.is_private,
            "invite_code":  virtual_room.invite_code,
            "member_count": virtual_room.member_count,
            "online_count": 0,
            "created_at":   "",
            "is_federated": True,
            "peer_ip":      body.peer_ip,
            "peer_port":    body.peer_port,
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# Multihop join (A → B → C)
# ══════════════════════════════════════════════════════════════════════════════

class MultihopJoinRequest(BaseModel):
    invite_code: str
    target_ip:   str
    target_port: int
    via_ip:      str
    via_port:    int


@router.post("/multihop-join")
async def multihop_join(
        body:    MultihopJoinRequest,
        u:       User    = Depends(get_current_user),
):
    """
    Мультихоп A → B → C.
    A не может достучаться до C напрямую.
    A авторизуется на B и просит его сделать federated-join к C.
    Итог: два relay-соединения A↔B↔C.
    """
    via_base = None
    for scheme in ("https", "http"):
        try:
            async with httpx.AsyncClient(timeout=4.0, verify=False) as client:
                r = await client.get(f"{scheme}://{body.via_ip}:{body.via_port}/api/peers/status")
                if r.status_code == 200:
                    via_base = f"{scheme}://{body.via_ip}:{body.via_port}"
                    break
        except Exception:
            continue

    if not via_base:
        raise HTTPException(503, f"Промежуточный узел {body.via_ip} недоступен")

    try:
        async with httpx.AsyncClient(timeout=8.0, verify=False) as client:
            gr = await client.post(
                f"{via_base}/api/federation/guest-login",
                json={
                    "username":      u.username,
                    "display_name":  u.display_name,
                    "avatar_emoji":  u.avatar_emoji,
                    "x25519_pubkey": u.x25519_public_key or "",
                    "peer_port":     Config.PORT,
                },
            )
    except Exception as e:
        raise HTTPException(502, f"guest-login на B ({body.via_ip}) failed: {e}")

    if gr.status_code != 200:
        raise HTTPException(502, f"guest-login на B: {gr.status_code}")

    via_jwt = gr.json()["access_token"]

    try:
        async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
            hr = await client.post(
                f"{via_base}/api/peers/federated-join",
                headers={"Authorization": f"Bearer {via_jwt}"},
                json={
                    "invite_code": body.invite_code,
                    "peer_ip":     body.target_ip,
                    "peer_port":   body.target_port,
                },
            )
    except Exception as e:
        raise HTTPException(502, f"federated-join B→C failed: {e}")

    if hr.status_code != 200:
        raise HTTPException(502, f"B→C join: {hr.status_code} {hr.text[:200]}")

    hop_data    = hr.json()
    via_room_id = hop_data["room"]["id"]

    from app.federation.federation import relay

    virtual_room = await relay.join(
        peer_ip        = body.via_ip,
        peer_port      = body.via_port,
        remote_room_id = via_room_id,
        remote_jwt     = via_jwt,
        room_name      = hop_data["room"].get("name", f"Room@{body.target_ip}"),
        invite_code    = body.invite_code.upper(),
        is_private     = hop_data["room"].get("is_private", True),
        member_count   = hop_data["room"].get("member_count", 1),
        user_id        = u.id,
    )

    logger.info(
        f"🔀 Multihop: {u.username} → {body.via_ip} → {body.target_ip}/room/{body.invite_code} "
        f"(virtual_id={virtual_room.virtual_id}, hops=2)"
    )

    return {
        "joined":       True,
        "is_federated": True,
        "hops":         2,
        "ws_path":      f"/ws/fed/{virtual_room.virtual_id}",
        "room": {
            "id":           virtual_room.virtual_id,
            "name":         virtual_room.room_name,
            "description":  f"🌐 {body.target_ip} via {body.via_ip}",
            "is_private":   virtual_room.is_private,
            "invite_code":  virtual_room.invite_code,
            "member_count": virtual_room.member_count,
            "online_count": 0,
            "created_at":   "",
            "is_federated": True,
            "peer_ip":      body.target_ip,
            "peer_port":    body.target_port,
            "hop_via":      body.via_ip,
            "hop_count":    2,
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# P2P receive / send
# ══════════════════════════════════════════════════════════════════════════════

class P2PReceiveRequest(BaseModel):
    ephemeral_pub:     Optional[str]  = None
    ciphertext:        Optional[str]  = None
    sender_pubkey:     Optional[str]  = None
    plaintext_payload: Optional[dict] = None


@router.post("/receive")
async def receive_from_peer(body: P2PReceiveRequest, request: Request):
    src_ip = request.client.host if request.client else "unknown"

    if body.ephemeral_pub and body.ciphertext:
        node_priv_raw, _ = _get_node_keys()
        node_priv = node_priv_raw if isinstance(node_priv_raw, bytes) else bytes(node_priv_raw)
        try:
            from app.security.key_exchange import decrypt_p2p_payload
            msg = decrypt_p2p_payload(body.ephemeral_pub, body.ciphertext, node_priv)
        except Exception as e:
            logger.warning(f"P2P decrypt failed from {src_ip}: {e}")
            raise HTTPException(400, "Не удалось расшифровать P2P сообщение")
    elif body.plaintext_payload:
        msg = body.plaintext_payload
    else:
        raise HTTPException(400, "Отсутствует payload")

    if body.sender_pubkey:
        peer = registry.get(src_ip)
        if peer and peer.node_pubkey_hex and peer.node_pubkey_hex != body.sender_pubkey:
            logger.warning(f"P2P pubkey mismatch from {src_ip}")
        elif not peer:
            registry.update(src_ip, src_ip, Config.PORT, body.sender_pubkey)

    room_id        = msg.get("room_id")
    sender         = msg.get("sender", "unknown")
    ciphertext_hex = msg.get("ciphertext", "")
    msg_type       = msg.get("msg_type", "text")

    if not room_id:
        raise HTTPException(400, "Отсутствует room_id в payload")

    await ws_manager.broadcast_to_room(room_id, {
        "type":       "peer_message",
        "sender":     sender,
        "sender_ip":  src_ip,
        "ciphertext": ciphertext_hex,
        "msg_type":   msg_type,
        "from_peer":  True,
    })
    return {"ok": True}


class SendReq(BaseModel):
    room_id:    int
    ciphertext: str
    msg_type:   str           = "text"
    peer_ip:    Optional[str] = None


@router.post("/send")
async def send_p2p(body: SendReq, u: User = Depends(get_current_user)):
    if body.peer_ip:
        peer = registry.get(body.peer_ip)
        if not peer:
            raise HTTPException(404, "Пир не найден")
        ok = await _send_to_peer_encrypted(
            peer, body.room_id, u.username, body.ciphertext, body.msg_type
        )
        return {"sent": ok, "encrypted": peer.has_encryption()}

    peers   = registry.active()
    results = await asyncio.gather(
        *[_send_to_peer_encrypted(p, body.room_id, u.username, body.ciphertext, body.msg_type)
          for p in peers],
        return_exceptions=True,
    )
    return {
        "sent_to":         sum(1 for r in results if r is True),
        "total":           len(peers),
        "encrypted_peers": sum(1 for p in peers if p.has_encryption()),
    }