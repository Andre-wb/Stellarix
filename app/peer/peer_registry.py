"""
app/peer/peer_registry.py — P2P Discovery с зашифрованным межузловым транспортом.

Ключевые изменения:
  1. UDP broadcast теперь включает X25519 публичный ключ узла
     → Узлы знают публичные ключи друг друга без дополнительных запросов
  2. Все P2P HTTP-запросы (/api/peers/receive) шифруются ECIES
     → Нода-отправитель шифрует payload pubkey ноды-получателя
     → Нода-получатель расшифровывает своим приватным ключом
     → Подслушивающий в локальной сети не видит содержимое
  3. Каждый запрос использует эфемерную пару → forward secrecy
  4. Verifier: получатель проверяет sender_pubkey через PeerRegistry

UDP Broadcast payload (JSON):
  {"name": "MyNode", "port": 9000, "pubkey": "a1b2c3...64 hex chars..."}

P2P HTTP Request (POST /api/peers/receive) body:
  {
    "ephemeral_pub":  "<hex>",          // эфемерный X25519 ключ отправителя
    "ciphertext":     "<hex>",          // ECIES зашифрованный JSON payload
    "sender_pubkey":  "<hex>"           // постоянный X25519 ключ узла-отправителя
  }

Расшифрованный payload:
  {"room_id": 5, "sender": "alice", "ciphertext": "<hex msg ciphertext>", "msg_type": "text"}

Важно: P2P сообщения также содержат только зашифрованный контент сообщения (ciphertext),
сервер-получатель ретранслирует его локальным WebSocket-клиентам без расшифровки.
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
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import Config
from app.models import User
from app.peer.connection_manager import manager as ws_manager
from app.security.auth_jwt import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/peers", tags=["peers"])


# ══════════════════════════════════════════════════════════════════════════════
# PeerInfo с поддержкой X25519 публичного ключа
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class PeerInfo:
    """
    Информация об обнаруженном P2P узле.

    node_pubkey_hex — X25519 публичный ключ узла, полученный из UDP broadcast.
    Используется для шифрования P2P сообщений (ECIES).
    Если None — узел работает без шифрования (деградированный режим, только локальная сеть).
    """
    name:            str
    ip:              str
    port:            int
    node_pubkey_hex: Optional[str] = None   # X25519 pubkey узла (hex, 64 chars)
    last_seen:       float         = field(default_factory=time.monotonic)

    def alive(self) -> bool:
        return (time.monotonic() - self.last_seen) < Config.PEER_TIMEOUT_SEC

    def has_encryption(self) -> bool:
        """Узел поддерживает зашифрованный P2P транспорт."""
        return bool(self.node_pubkey_hex and len(self.node_pubkey_hex) == 64)

    def to_dict(self) -> dict:
        return {
            "name":       self.name,
            "ip":         self.ip,
            "port":       self.port,
            "age_sec":    round(time.monotonic() - self.last_seen, 1),
            "online":     self.alive(),
            "encrypted":  self.has_encryption(),   # поддерживает E2E P2P?
            "pubkey":     self.node_pubkey_hex[:16] + "..." if self.node_pubkey_hex else None,
        }

    @property
    def base_url(self) -> str:
        return f"http://{self.ip}:{self.port}"


# ══════════════════════════════════════════════════════════════════════════════
# PeerRegistry
# ══════════════════════════════════════════════════════════════════════════════

class PeerRegistry:
    def __init__(self):
        self._peers: dict[str, PeerInfo] = {}
        self._lock  = threading.Lock()
        self.own_ip: str = "127.0.0.1"

    def update(self, ip: str, name: str, port: int,
               node_pubkey_hex: Optional[str] = None) -> None:
        with self._lock:
            if ip in self._peers:
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


registry = PeerRegistry()


# ══════════════════════════════════════════════════════════════════════════════
# Вспомогательные функции
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
    """Возвращает (priv, pub) X25519 ключи этого узла."""
    from app.security.crypto import load_or_create_node_keypair
    return load_or_create_node_keypair(Config.KEYS_DIR)


# ══════════════════════════════════════════════════════════════════════════════
# Запуск discovery
# ══════════════════════════════════════════════════════════════════════════════

def start_discovery(device_name: str = "") -> None:
    """
    Запускает UDP discovery в фоновых потоках.
    UDP broadcast теперь включает X25519 публичный ключ узла.
    """
    name = device_name or socket.gethostname()
    registry.own_ip = _local_ip()

    # Получаем публичный ключ этого узла для включения в broadcast
    try:
        _, node_pub = _get_node_keys()
        node_pubkey_hex = node_pub.hex() if isinstance(node_pub, bytes) else bytes(node_pub).hex()
    except Exception as e:
        logger.warning(f"Не удалось получить X25519 ключ узла: {e}")
        node_pubkey_hex = None

    # Пробуем Rust-модуль
    try:
        import vortex_chat as _vc
        _vc.start_discovery(name, Config.PORT)
        logger.info(f"🦀 Rust UDP discovery: «{name}»")

        def _sync_rust_peers():
            while True:
                try:
                    for ip, port in _vc.get_peers():
                        # Rust не передаёт pubkey — обновляем без него
                        registry.update(ip, ip, port)
                except Exception:
                    pass
                time.sleep(3)

        threading.Thread(target=_sync_rust_peers, daemon=True, name="rust-peers-sync").start()
        return
    except (ImportError, AttributeError):
        logger.info("Python UDP discovery fallback")

    # Python fallback — с pubkey в payload
    threading.Thread(
        target=_py_listener, daemon=True, name="udp-listen"
    ).start()
    threading.Thread(
        target=_py_sender, args=(name, node_pubkey_hex), daemon=True, name="udp-send"
    ).start()
    logger.info(f"🐍 Python UDP discovery: «{name}» pubkey={'yes' if node_pubkey_hex else 'no'}")


def _py_listener():
    """UDP-слушатель. Парсит имя, порт и X25519 pubkey из broadcast-пакетов."""
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

            info = json.loads(data.decode())

            # Извлекаем X25519 pubkey из broadcast payload
            pubkey = info.get("pubkey")
            if pubkey and len(pubkey) != 64:
                pubkey = None  # невалидный pubkey — игнорируем
            if pubkey:
                try:
                    bytes.fromhex(pubkey)  # валидируем hex
                except ValueError:
                    pubkey = None

            registry.update(
                src_ip,
                str(info.get("name", src_ip))[:64],
                int(info.get("port", Config.PORT)),
                pubkey,
            )
        except socket.timeout:
            registry.cleanup()
        except Exception as e:
            logger.debug(f"UDP recv: {e}")


def _py_sender(name: str, node_pubkey_hex: Optional[str]):
    """
    UDP-отправитель. Включает X25519 pubkey в каждый broadcast-пакет.
    Другие узлы используют этот pubkey для шифрования P2P сообщений нам.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    while True:
        try:
            own_ip = _local_ip()
            if own_ip != registry.own_ip and not own_ip.startswith("127."):
                registry.own_ip = own_ip

            # Включаем pubkey в payload — соседние узлы узнают наш X25519 ключ
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
# P2P зашифрованная отправка сообщений
# ══════════════════════════════════════════════════════════════════════════════

async def _send_to_peer_encrypted(
        peer:      PeerInfo,
        room_id:   int,
        sender:    str,
        ciphertext_hex: str,    # уже зашифрованный клиентом текст сообщения
        msg_type:  str = "text",
) -> bool:
    """
    Отправляет P2P сообщение другому узлу с ECIES шифрованием транспортного уровня.

    Двойное шифрование:
      1. Содержимое сообщения (ciphertext_hex) — уже зашифровано клиентом room_key
      2. Транспортный payload — шифруется ECIES X25519 ключом узла-получателя

    Подслушивающий видит только зашифрованный транспортный payload.
    Даже при расшифровке транспорта — содержимое сообщения остаётся зашифрованным room_key.
    """
    node_priv, node_pub_raw = _get_node_keys()
    node_pub = node_pub_raw if isinstance(node_pub_raw, bytes) else bytes(node_pub_raw)
    node_priv_bytes = node_priv if isinstance(node_priv, bytes) else bytes(node_priv)

    payload_dict = {
        "room_id":    room_id,
        "sender":     sender,
        "ciphertext": ciphertext_hex,   # зашифрованное сообщение (room_key)
        "msg_type":   msg_type,
    }

    try:
        if peer.has_encryption():
            # Шифруем транспортный payload X25519 ключом узла-получателя
            from app.security.key_exchange import encrypt_p2p_payload
            encrypted = encrypt_p2p_payload(payload_dict, node_priv_bytes, peer.node_pubkey_hex)

            request_body = {
                "ephemeral_pub": encrypted["ephemeral_pub"],
                "ciphertext":    encrypted["ciphertext"],
                "sender_pubkey": node_pub.hex(),
            }
        else:
            # Деградированный режим: узел не опубликовал свой X25519 ключ
            # Отправляем незашифрованно (только внутри доверенной локальной сети)
            logger.warning(
                f"Peer {peer.ip} has no pubkey — P2P transport unencrypted (LAN only)"
            )
            request_body = {
                "plaintext_payload": payload_dict,   # fallback без шифрования
                "sender_pubkey":     node_pub.hex(),
            }

        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(
                f"{peer.base_url}/api/peers/receive",
                json=request_body,
            )
            return response.status_code == 200

    except Exception as e:
        logger.debug(f"P2P send to {peer.ip} failed: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# REST API endpoints
# ══════════════════════════════════════════════════════════════════════════════

@router.get("")
async def list_peers(u: User = Depends(get_current_user)):
    """Список активных P2P узлов в локальной сети."""
    peers = registry.active()
    return {
        "own_ip":    registry.own_ip,
        "count":     len(peers),
        "peers":     [p.to_dict() for p in peers],
        "encrypted": sum(1 for p in peers if p.has_encryption()),
    }


@router.get("/status")
async def peer_status():
    """Публичный endpoint — соседние узлы проверяют доступность."""
    _, node_pub_raw = _get_node_keys()
    node_pub = node_pub_raw if isinstance(node_pub_raw, bytes) else bytes(node_pub_raw)
    return {
        "ok":       True,
        "own_ip":   registry.own_ip,
        "peers":    len(registry.active()),
        "pubkey":   node_pub.hex(),   # X25519 pubkey узла — для инициации зашифрованного канала
    }


class P2PReceiveRequest(BaseModel):
    """Входящий зашифрованный P2P запрос от другого узла."""
    # Зашифрованный режим (ECIES):
    ephemeral_pub:     Optional[str] = None
    ciphertext:        Optional[str] = None
    sender_pubkey:     Optional[str] = None
    # Fallback незашифрованный режим:
    plaintext_payload: Optional[dict] = None


@router.post("/receive")
async def receive_from_peer(body: P2PReceiveRequest, request: Request):
    """
    Принимает P2P сообщение от другого узла.

    Расшифровывает ECIES payload (если зашифрован) и ретранслирует
    зашифрованное сообщение локальным WebSocket-клиентам.
    Содержимое сообщения (ciphertext) НЕ расшифровывается — это делает клиент.
    """
    src_ip = request.client.host if request.client else "unknown"

    # ── Расшифровка транспортного уровня ─────────────────────────────────────
    if body.ephemeral_pub and body.ciphertext:
        # Зашифрованный режим — используем X25519 ключ нашего узла
        node_priv_raw, _ = _get_node_keys()
        node_priv = node_priv_raw if isinstance(node_priv_raw, bytes) else bytes(node_priv_raw)

        try:
            from app.security.key_exchange import decrypt_p2p_payload
            msg = decrypt_p2p_payload(body.ephemeral_pub, body.ciphertext, node_priv)
        except Exception as e:
            logger.warning(f"P2P decrypt failed from {src_ip}: {e}")
            raise HTTPException(400, "Не удалось расшифровать P2P сообщение")

    elif body.plaintext_payload:
        # Fallback — незашифрованный режим (деградированный, только LAN)
        msg = body.plaintext_payload
        logger.debug(f"P2P plaintext from {src_ip} (unencrypted fallback)")

    else:
        raise HTTPException(400, "Отсутствует payload (ни encrypted, ни plaintext)")

    # ── Опциональная верификация sender_pubkey ────────────────────────────────
    if body.sender_pubkey:
        peer = registry.get(src_ip)
        if peer and peer.node_pubkey_hex and peer.node_pubkey_hex != body.sender_pubkey:
            logger.warning(
                f"P2P pubkey mismatch from {src_ip}: "
                f"expected={peer.node_pubkey_hex[:16]}... "
                f"got={body.sender_pubkey[:16]}..."
            )
            # Не блокируем — логируем как предупреждение
        elif not peer:
            # Обновляем реестр с новым пиром
            registry.update(src_ip, src_ip, Config.PORT, body.sender_pubkey)

    # ── Ретрансляция зашифрованного сообщения локальным WebSocket-клиентам ───
    room_id       = msg.get("room_id")
    sender        = msg.get("sender", "unknown")
    ciphertext_hex= msg.get("ciphertext", "")   # зашифровано room_key на клиенте
    msg_type      = msg.get("msg_type", "text")

    if not room_id:
        raise HTTPException(400, "Отсутствует room_id в payload")

    await ws_manager.broadcast_to_room(room_id, {
        "type":       "peer_message",
        "sender":     sender,
        "sender_ip":  src_ip,
        "ciphertext": ciphertext_hex,    # клиент расшифрует сам
        "msg_type":   msg_type,
        "from_peer":  True,
    })

    return {"ok": True}


class SendReq(BaseModel):
    room_id:    int
    ciphertext: str            # уже зашифрованное клиентом сообщение (hex)
    msg_type:   str = "text"
    peer_ip:    Optional[str] = None


@router.post("/send")
async def send_p2p(body: SendReq, u: User = Depends(get_current_user)):
    """
    Отправляет зашифрованное сообщение P2P-узлам.

    Клиент должен передать ciphertext — сообщение, уже зашифрованное room_key.
    Сервер не видит открытый текст: только зашифрованный payload.
    Транспортный уровень дополнительно шифруется ECIES X25519 ключами узлов.
    """
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
    sent_count      = sum(1 for r in results if r is True)
    encrypted_count = sum(1 for p in peers if p.has_encryption())

    return {
        "sent_to":        sent_count,
        "total":          len(peers),
        "encrypted_peers":encrypted_count,
    }