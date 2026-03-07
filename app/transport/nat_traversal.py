"""
app/transport/nat_traversal.py — NAT Traversal: STUN + UDP Hole Punching.

Архитектура:
  1. STUN (RFC 5389) — определяем внешний IP:port через публичный STUN-сервер
  2. Signaling — обмениваемся кандидатами через существующий HTTP API (/api/transport/signal)
  3. UDP Hole Punching — одновременно шлём UDP пакеты → NAT открывает путь
  4. Fallback на federation relay если hole punch не прошёл

Схема NAT traversal:
  Node A (NAT-A) ←──── STUN ────→ 1.2.3.4:5678 (external candidate A)
  Node B (NAT-B) ←──── STUN ────→ 5.6.7.8:9012 (external candidate B)

  A → сигнализирует B свой кандидат через /api/transport/signal
  B → сигнализирует A свой кандидат

  A ──────── UDP ────────→ 5.6.7.8:9012  (пробиваем дыру)
  B ──────── UDP ────────→ 1.2.3.4:5678  (пробиваем дыру)

  Если успешно — прямой UDP канал, иначе → relay через федерацию.

Поддержка типов NAT:
  - Full-cone NAT        ✅ легко
  - Restricted-cone NAT  ✅ через hole punch
  - Symmetric NAT        ⚠️  сложно, fallback на relay
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import socket
import struct
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# STUN Constants (RFC 5389)
# ─────────────────────────────────────────────────────────────────────────────
_STUN_MAGIC       = 0x2112A442
_BINDING_REQUEST  = 0x0001
_BINDING_RESPONSE = 0x0101
_ATTR_XOR_MAPPED  = 0x0020
_ATTR_MAPPED      = 0x0001

# Публичные STUN серверы (пробуем по порядку)
STUN_SERVERS = [
    ("stun.l.google.com",     19302),
    ("stun1.l.google.com",    19302),
    ("stun.cloudflare.com",   3478),
    ("stun.stunprotocol.org", 3478),
]

# ─────────────────────────────────────────────────────────────────────────────
# Структуры данных
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class IceCandidate:
    """ICE-like кандидат для соединения."""
    ip:        str
    port:      int
    cand_type: str      # "host" | "srflx" (server reflexive) | "relay"
    priority:  int = 0
    foundation: str = ""

    def to_dict(self) -> dict:
        return {
            "ip":        self.ip,
            "port":      self.port,
            "type":      self.cand_type,
            "priority":  self.priority,
            "foundation": self.foundation,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "IceCandidate":
        return cls(
            ip        = d["ip"],
            port      = int(d["port"]),
            cand_type = d.get("type", "host"),
            priority  = int(d.get("priority", 0)),
            foundation= d.get("foundation", ""),
        )


@dataclass
class HolePunchSession:
    """Состояние сессии UDP hole punching."""
    session_id:    str
    local_cands:   list[IceCandidate] = field(default_factory=list)
    remote_cands:  list[IceCandidate] = field(default_factory=list)
    punch_sock:    Optional[socket.socket] = None
    connected:     bool  = False
    remote_addr:   Optional[tuple[str, int]] = None
    created_at:    float = field(default_factory=time.monotonic)
    callback:      Optional[Callable] = None  # вызывается при получении сообщения


# ─────────────────────────────────────────────────────────────────────────────
# STUN Client (RFC 5389 — только Binding Request/Response)
# ─────────────────────────────────────────────────────────────────────────────

class StunClient:
    """
    Минимальный STUN-клиент для определения внешнего IP:порта.
    Реализует только Binding Request без TURN/ICE.
    """

    @staticmethod
    def _build_binding_request() -> tuple[bytes, bytes]:
        """Строит STUN Binding Request. Возвращает (пакет, transaction_id)."""
        tid     = secrets.token_bytes(12)
        # Header: msg_type(2) + length(2) + magic(4) + tid(12) = 20 bytes
        msg     = struct.pack(">HHI12s", _BINDING_REQUEST, 0, _STUN_MAGIC, tid)
        return msg, tid

    @staticmethod
    def _parse_xor_mapped(data: bytes, tid: bytes) -> Optional[tuple[str, int]]:
        """Разбирает XOR-MAPPED-ADDRESS из STUN ответа."""
        if len(data) < 20:
            return None

        msg_type, length, magic = struct.unpack_from(">HHI", data, 0)
        if msg_type != _BINDING_RESPONSE or magic != _STUN_MAGIC:
            return None

        offset = 20
        end    = 20 + length

        while offset + 4 <= end:
            attr_type, attr_len = struct.unpack_from(">HH", data, offset)
            offset += 4

            if attr_type == _ATTR_XOR_MAPPED and attr_len >= 8:
                # family(1) + pad(1) + xport(2) + xaddr(4)
                _, family, xport = struct.unpack_from(">BBH", data, offset)
                if family == 0x01:  # IPv4
                    xaddr, = struct.unpack_from(">I", data, offset + 4)
                    port = xport ^ (_STUN_MAGIC >> 16)
                    ip_int = xaddr ^ _STUN_MAGIC
                    ip = socket.inet_ntoa(struct.pack(">I", ip_int))
                    return ip, port

            elif attr_type == _ATTR_MAPPED and attr_len >= 8:
                _, family, port = struct.unpack_from(">BBH", data, offset)
                if family == 0x01:
                    ip_bytes = data[offset + 4: offset + 8]
                    ip = socket.inet_ntoa(ip_bytes)
                    return ip, port

            # Выравнивание до 4 байт
            offset += attr_len + (4 - attr_len % 4) % 4

        return None

    @staticmethod
    async def query(
            stun_host: str,
            stun_port: int,
            local_sock: Optional[socket.socket] = None,
            timeout: float = 3.0,
    ) -> Optional[tuple[str, int]]:
        """
        Отправляет STUN Binding Request и получает внешний IP:port.

        Если local_sock передан — используем его (важно для hole punch,
        чтобы STUN знал именно тот порт, который будет использоваться).
        """
        loop   = asyncio.get_event_loop()
        own_sock = local_sock

        try:
            if own_sock is None:
                own_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                own_sock.settimeout(timeout)
                own_sock.bind(("", 0))

            msg, tid = StunClient._build_binding_request()

            # Резолвим хост (может быть DNS имя)
            try:
                stun_ip = await asyncio.wait_for(
                    loop.run_in_executor(None, socket.gethostbyname, stun_host),
                    timeout=2.0,
                )
            except Exception:
                return None

            await loop.run_in_executor(None, own_sock.sendto, msg, (stun_ip, stun_port))

            data = await asyncio.wait_for(
                loop.run_in_executor(None, own_sock.recv, 1024),
                timeout=timeout,
            )
            result = StunClient._parse_xor_mapped(data, tid)
            return result

        except Exception as e:
            logger.debug(f"STUN {stun_host}:{stun_port} failed: {e}")
            return None
        finally:
            if local_sock is None and own_sock is not None:
                try:
                    own_sock.close()
                except Exception:
                    pass

    @classmethod
    async def discover_external(cls) -> Optional[tuple[str, int]]:
        """Пробуем несколько STUN серверов, возвращаем первый успешный результат."""
        for host, port in STUN_SERVERS:
            result = await cls.query(host, port)
            if result:
                logger.info(f"🌐 STUN: external address = {result[0]}:{result[1]} (via {host})")
                return result
            await asyncio.sleep(0.2)
        logger.warning("STUN: все серверы недоступны")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# UDP Hole Punching
# ─────────────────────────────────────────────────────────────────────────────

class UdpHolePuncher:
    """
    Реализует UDP Hole Punching для двух пиров за NAT.

    Протокол:
      1. Оба узла вызывают gather_candidates() → получают host + srflx кандидатов
      2. Обмениваются через signaling (HTTP API /api/transport/signal)
      3. punch(remote_candidates) → пробуем соединиться
      4. При успехе — возвращает сокет для прямого UDP обмена
    """

    # Magic bytes для идентификации наших punch пакетов
    PUNCH_MAGIC   = b"VORTEX_PUNCH_V1\x00"
    ACK_MAGIC     = b"VORTEX_PUNCH_ACK\x00"
    DATA_MAGIC    = b"VORTEX_DATA_V1\x00\x00"

    def __init__(self):
        self._sessions: dict[str, HolePunchSession] = {}

    def new_session(self, session_id: Optional[str] = None) -> HolePunchSession:
        sid = session_id or secrets.token_hex(16)
        sess = HolePunchSession(session_id=sid)
        self._sessions[sid] = sess
        return sess

    def get_session(self, sid: str) -> Optional[HolePunchSession]:
        return self._sessions.get(sid)

    def close_session(self, sid: str) -> None:
        sess = self._sessions.pop(sid, None)
        if sess and sess.punch_sock:
            try:
                sess.punch_sock.close()
            except Exception:
                pass

    async def gather_candidates(
            self,
            session: HolePunchSession,
            local_ip: str,
    ) -> list[IceCandidate]:
        """
        Собирает ICE-кандидатов:
          - host: локальный IP:port
          - srflx: внешний IP:port через STUN
        """
        candidates: list[IceCandidate] = []

        # Создаём UDP сокет с фиксированным портом
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", 0))
        local_port = sock.getsockname()[1]
        session.punch_sock = sock

        # Host кандидат
        if local_ip and not local_ip.startswith("127."):
            host_cand = IceCandidate(
                ip        = local_ip,
                port      = local_port,
                cand_type = "host",
                priority  = 100,
                foundation= hashlib.md5(f"host_{local_ip}".encode()).hexdigest()[:8],
            )
            candidates.append(host_cand)

        # Server-reflexive кандидат (через STUN)
        srflx = await StunClient.query(
            STUN_SERVERS[0][0],
            STUN_SERVERS[0][1],
            local_sock = sock,
        )
        if srflx:
            srflx_cand = IceCandidate(
                ip        = srflx[0],
                port      = srflx[1],
                cand_type = "srflx",
                priority  = 200,
                foundation= hashlib.md5(f"srflx_{srflx[0]}".encode()).hexdigest()[:8],
            )
            candidates.append(srflx_cand)

        session.local_cands = candidates
        logger.info(f"🧊 ICE candidates for session {session.session_id}: "
                    f"{[f'{c.cand_type}:{c.ip}:{c.port}' for c in candidates]}")
        return candidates

    async def punch(
            self,
            session: HolePunchSession,
            remote_candidates: list[IceCandidate],
            timeout: float = 10.0,
    ) -> bool:
        """
        Выполняет hole punching к удалённым кандидатам.
        Возвращает True если соединение установлено.

        Алгоритм:
          1. Сортируем кандидатов по приоритету
          2. Для каждого: шлём пачку PUNCH пакетов
          3. Слушаем ACK
          4. При получении ACK — соединение установлено
        """
        if not session.punch_sock:
            logger.error("punch_sock не инициализирован — вызови gather_candidates() сначала")
            return False

        session.remote_cands = remote_candidates
        sock = session.punch_sock
        sock.setblocking(False)

        # Сортируем по приоритету (srflx > host)
        sorted_cands = sorted(remote_candidates, key=lambda c: c.priority, reverse=True)

        loop    = asyncio.get_event_loop()
        ping_id = secrets.token_bytes(8)

        async def send_punches():
            """Посылаем пачку punch-пакетов ко всем кандидатам."""
            for _ in range(10):  # 10 попыток с паузами
                for cand in sorted_cands:
                    pkt = self.PUNCH_MAGIC + ping_id
                    try:
                        sock.sendto(pkt, (cand.ip, cand.port))
                    except Exception:
                        pass
                await asyncio.sleep(0.3)

        async def listen_for_ack() -> Optional[tuple[str, int]]:
            """Ждём ACK от удалённого пира."""
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    data, addr = await asyncio.wait_for(
                        loop.run_in_executor(None, sock.recvfrom, 512),
                        timeout=0.5,
                    )
                    if data.startswith(self.PUNCH_MAGIC):
                        # Получили punch — отвечаем ACK
                        remote_ping_id = data[len(self.PUNCH_MAGIC):]
                        ack = self.ACK_MAGIC + remote_ping_id
                        sock.sendto(ack, addr)
                        logger.info(f"🥊 Punch received from {addr}, sent ACK")
                        return addr

                    elif data.startswith(self.ACK_MAGIC):
                        logger.info(f"🥊 ACK received from {addr} — hole punch SUCCESS")
                        return addr

                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.debug(f"Punch listen error: {e}")
                    await asyncio.sleep(0.1)
            return None

        # Запускаем одновременно отправку и прослушивание
        punch_task  = asyncio.create_task(send_punches())
        listen_task = asyncio.create_task(listen_for_ack())

        try:
            done, pending = await asyncio.wait(
                [punch_task, listen_task],
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()

            if listen_task in done:
                addr = listen_task.result()
                if addr:
                    session.connected   = True
                    session.remote_addr = addr
                    logger.info(f"✅ Hole punch complete: {addr}")
                    return True
        except Exception as e:
            logger.debug(f"Hole punch exception: {e}")

        logger.warning(f"❌ Hole punch failed for session {session.session_id}")
        return False

    async def send_data(
            self,
            session: HolePunchSession,
            data: bytes,
    ) -> bool:
        """Отправляет данные через пробитый UDP туннель."""
        if not session.connected or not session.remote_addr or not session.punch_sock:
            return False
        pkt = self.DATA_MAGIC + data
        try:
            session.punch_sock.sendto(pkt, session.remote_addr)
            return True
        except Exception as e:
            logger.debug(f"UDP send error: {e}")
            return False

    async def receive_loop(
            self,
            session: HolePunchSession,
            on_data: Callable[[bytes, tuple], None],
    ) -> None:
        """
        Цикл получения данных из UDP туннеля.
        Вызывает on_data(payload, addr) для каждого пакета.
        """
        if not session.punch_sock:
            return

        sock = session.punch_sock
        loop = asyncio.get_event_loop()

        while session.connected:
            try:
                raw, addr = await asyncio.wait_for(
                    loop.run_in_executor(None, sock.recvfrom, 65535),
                    timeout=30.0,
                )
                if raw.startswith(self.DATA_MAGIC):
                    payload = raw[len(self.DATA_MAGIC):]
                    try:
                        await on_data(payload, addr)
                    except Exception as e:
                        logger.debug(f"on_data error: {e}")
            except asyncio.TimeoutError:
                # keepalive
                if session.remote_addr:
                    try:
                        sock.sendto(b"VORTEX_KEEPALIVE", session.remote_addr)
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"UDP receive loop error: {e}")
                break


# ─────────────────────────────────────────────────────────────────────────────
# SignalingStore — временное хранилище кандидатов для обмена
# ─────────────────────────────────────────────────────────────────────────────

class SignalingStore:
    """
    In-memory хранилище ICE кандидатов для signaling.

    Структура: session_id → {role → candidates}
    TTL: 60 секунд
    """

    def __init__(self):
        self._data: dict[str, dict] = {}
        self._ttl:  dict[str, float] = {}

    def store(self, session_id: str, role: str, candidates: list[dict]) -> None:
        self._data.setdefault(session_id, {})[role] = candidates
        self._ttl[session_id] = time.monotonic() + 60.0
        logger.debug(f"Signal stored: session={session_id} role={role} cands={len(candidates)}")

    def get(self, session_id: str, role: str) -> Optional[list[dict]]:
        self._cleanup()
        return self._data.get(session_id, {}).get(role)

    def _cleanup(self) -> None:
        now  = time.monotonic()
        dead = [sid for sid, exp in self._ttl.items() if now > exp]
        for sid in dead:
            self._data.pop(sid, None)
            self._ttl.pop(sid, None)


# Глобальные экземпляры
stun_client  = StunClient()
hole_puncher = UdpHolePuncher()
signaling    = SignalingStore()