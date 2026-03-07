"""
app/transport/transport_manager.py — Unified Transport Manager.

Приоритет транспортов (от лучшего к худшему):
  1. Direct TCP (Wi-Fi/LAN)   — существующий federation/peer механизм
  2. UDP Hole Punch (NAT)     — прямой UDP через NAT
  3. Wi-Fi Direct (P2P)       — без точки доступа
  4. BLE                      — fallback для открытия канала
  5. Federation Relay         — через промежуточный узел (последний вариант)

Логика выбора транспорта:
  ┌─────────────────────────────────────────────────────┐
  │  Пытаемся Direct TCP                                │
  │    ✅ Успех → используем                            │
  │    ❌ Нет → пробуем UDP Hole Punch                  │
  │              ✅ Успех → используем                  │
  │              ❌ Нет → пробуем Wi-Fi Direct          │
  │                         ✅ Успех → используем       │
  │                         ❌ Нет → BLE discovery      │
  │                                   → Relay fallback  │
  └─────────────────────────────────────────────────────┘

Автоматическое переключение:
  - При разрыве соединения → пробуем следующий транспорт
  - Периодически пробуем восстановить лучший транспорт
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, Optional

import httpx

from app.transport.nat_traversal import (
    IceCandidate, StunClient, UdpHolePuncher,
    SignalingStore, hole_puncher, signaling,
)
from app.transport.ble_transport import BleTransportManager, ble_manager
from app.transport.wifi_direct import WifiDirectManager, wifi_direct_manager

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Приоритеты транспортов
# ─────────────────────────────────────────────────────────────────────────────

class TransportPriority(IntEnum):
    DIRECT_TCP   = 4   # Лучший: прямой HTTP/WS в локальной сети
    UDP_HOLE_PUNCH = 3  # NAT traversal через UDP
    WIFI_DIRECT  = 2   # Wi-Fi Direct P2P
    BLE          = 1   # BLE (только для малых сообщений)
    RELAY        = 0   # Худший: федеративный relay


@dataclass
class TransportStatus:
    """Статус конкретного транспорта к конкретному пиру."""
    peer_ip:    str
    transport:  TransportPriority
    active:     bool     = False
    latency_ms: float    = 9999.0
    last_ok:    float    = 0.0
    error_count: int     = 0

    def is_healthy(self, max_age: float = 30.0) -> bool:
        return self.active and (time.monotonic() - self.last_ok) < max_age


@dataclass
class PeerTransportState:
    """Состояние всех транспортов для одного пира."""
    peer_ip:   str
    peer_port: int
    transports: dict[TransportPriority, TransportStatus] = field(default_factory=dict)
    hole_punch_session: Optional[str] = None   # session_id в hole_puncher
    ble_address: Optional[str] = None
    wifi_direct_mac: Optional[str] = None

    def best_transport(self) -> Optional[TransportPriority]:
        """Возвращает лучший активный транспорт."""
        for prio in sorted(TransportPriority, reverse=True):
            ts = self.transports.get(prio)
            if ts and ts.is_healthy():
                return prio
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Transport Manager
# ─────────────────────────────────────────────────────────────────────────────

class TransportManager:
    """
    Центральный менеджер транспортов.

    Оркеструет: NAT traversal, BLE, Wi-Fi Direct и federation relay.
    Интегрируется с существующим PeerRegistry.
    """

    def __init__(self):
        self._peers:    dict[str, PeerTransportState] = {}
        self._own_ip:   str   = "127.0.0.1"
        self._own_port: int   = 8000
        self._node_name: str  = "vortex"
        self._started:  bool  = False

        # Внешний (STUN) адрес
        self._external_ip:   Optional[str] = None
        self._external_port: Optional[int] = None

        # Callback при входящем сообщении через NAT/BLE/WiFiDirect
        self._on_message: Optional[Callable] = None

    # ── Запуск ────────────────────────────────────────────────────────────────

    async def start(
            self,
            own_ip:    str,
            own_port:  int,
            node_name: str,
            on_message: Optional[Callable] = None,
    ) -> None:
        """Запускает все транспортные подсистемы."""
        self._own_ip    = own_ip
        self._own_port  = own_port
        self._node_name = node_name
        self._on_message = on_message

        logger.info("🚀 TransportManager: запуск всех транспортов...")

        # Параллельно запускаем все транспорты
        results = await asyncio.gather(
            self._init_stun(),
            self._init_ble(node_name, own_port),
            self._init_wifi_direct(node_name, own_port),
            return_exceptions=True,
        )

        for i, res in enumerate(results):
            if isinstance(res, Exception):
                logger.debug(f"Transport {i} init exception: {res}")

        self._started = True
        logger.info(
            f"🚀 TransportManager готов. "
            f"External: {self._external_ip}:{self._external_port}, "
            f"BLE: {ble_manager.available}, "
            f"WiFi Direct: {wifi_direct_manager.available}"
        )

    async def _init_stun(self) -> None:
        """Определяем внешний IP через STUN."""
        result = await StunClient.discover_external()
        if result:
            self._external_ip, self._external_port = result
        else:
            logger.warning("STUN недоступен — NAT traversal ограничен")

    async def _init_ble(self, node_name: str, port: int) -> None:
        """Запускаем BLE если доступен."""
        ok = await ble_manager.start(
            node_name           = node_name,
            http_port           = port,
            on_peer_discovered  = self._on_ble_peer,
            on_message_received = self._on_ble_message,
        )
        if ok:
            await ble_manager.start_gatt_server()

    async def _init_wifi_direct(self, node_name: str, port: int) -> None:
        """Запускаем Wi-Fi Direct если доступен."""
        from app.config import Config
        wifi_iface = getattr(Config, "WIFI_INTERFACE", "wlan0")
        await wifi_direct_manager.start(
            node_name          = node_name,
            http_port          = port,
            wifi_interface     = wifi_iface,
            on_peer_discovered = self._on_wifidirect_peer,
        )

    async def stop(self) -> None:
        await ble_manager.stop()
        await wifi_direct_manager.stop()
        self._started = False

    # ── Callbacks от транспортов ──────────────────────────────────────────────

    async def _on_ble_peer(self, peer) -> None:
        """Вызывается когда BLE обнаружил новый Vortex-узел."""
        logger.info(f"📡 BLE→Registry: {peer.node_name}")
        # Регистрируем в PeerRegistry через HTTP (пир анонсирует свой HTTP порт)
        from app.peer.peer_registry import registry
        registry.update(peer.address, peer.node_name, peer.http_port)

        # Обновляем состояние транспортов
        state = self._get_or_create(peer.address, peer.http_port)
        state.ble_address = peer.address
        state.transports[TransportPriority.BLE] = TransportStatus(
            peer_ip   = peer.address,
            transport = TransportPriority.BLE,
            active    = True,
            last_ok   = time.monotonic(),
        )

    async def _on_wifidirect_peer(self, peer) -> None:
        """Вызывается когда Wi-Fi Direct обнаружил новый узел."""
        logger.info(f"📶 WiFiDirect→Registry: {peer.name} ({peer.mac})")
        state = self._get_or_create(peer.mac, peer.port)
        state.wifi_direct_mac = peer.mac
        if peer.ip:
            state.transports[TransportPriority.WIFI_DIRECT] = TransportStatus(
                peer_ip   = peer.ip,
                transport = TransportPriority.WIFI_DIRECT,
                active    = True,
                last_ok   = time.monotonic(),
            )

    async def _on_ble_message(self, data: bytes, addr) -> None:
        """Входящее сообщение через BLE."""
        import json
        try:
            payload = json.loads(data)
            if self._on_message:
                await self._on_message(payload, addr[0] if addr else "ble")
        except Exception as e:
            logger.debug(f"BLE message parse: {e}")

    # ── NAT Hole Punch ────────────────────────────────────────────────────────

    async def initiate_hole_punch(
            self,
            peer_ip:   str,
            peer_port: int,
    ) -> bool:
        """
        Инициирует NAT hole punching к пиру.

        Протокол:
          1. Генерируем session_id, собираем ICE кандидаты
          2. Публикуем кандидаты через HTTP на пир (/api/transport/signal)
          3. Пир отвечает своими кандидатами
          4. punch()
        """
        session = hole_puncher.new_session()

        # Собираем кандидатов
        cands = await hole_puncher.gather_candidates(session, self._own_ip)
        if not cands:
            logger.warning("ICE: нет кандидатов")
            return False

        # Добавляем STUN кандидата если есть
        if self._external_ip:
            cands.append(IceCandidate(
                ip        = self._external_ip,
                port      = self._external_port or 0,
                cand_type = "srflx",
                priority  = 200,
            ))

        # Публикуем через signaling API пира
        cand_dicts = [c.to_dict() for c in cands]
        signaling.store(session.session_id, "initiator", cand_dicts)

        signal_ok = await self._send_signal(
            peer_ip    = peer_ip,
            peer_port  = peer_port,
            session_id = session.session_id,
            role       = "initiator",
            candidates = cand_dicts,
        )

        if not signal_ok:
            logger.warning(f"Signaling к {peer_ip} failed")
            hole_puncher.close_session(session.session_id)
            return False

        # Ждём кандидатов от пира
        remote_cands_raw = None
        for _ in range(20):  # ждём до 10 секунд
            await asyncio.sleep(0.5)
            remote_cands_raw = signaling.get(session.session_id, "responder")
            if remote_cands_raw:
                break

        if not remote_cands_raw:
            logger.warning(f"Нет ответных кандидатов от {peer_ip}")
            hole_puncher.close_session(session.session_id)
            return False

        remote_cands = [IceCandidate.from_dict(c) for c in remote_cands_raw]

        # Hole punch!
        success = await hole_puncher.punch(session, remote_cands)

        if success:
            state = self._get_or_create(peer_ip, peer_port)
            state.hole_punch_session = session.session_id
            state.transports[TransportPriority.UDP_HOLE_PUNCH] = TransportStatus(
                peer_ip   = peer_ip,
                transport = TransportPriority.UDP_HOLE_PUNCH,
                active    = True,
                last_ok   = time.monotonic(),
                latency_ms= await self._measure_latency(peer_ip, peer_port),
            )
            logger.info(f"✅ NAT hole punch к {peer_ip} — SUCCESS")
        else:
            hole_puncher.close_session(session.session_id)
            logger.warning(f"❌ NAT hole punch к {peer_ip} — FAILED, используем relay")

        return success

    async def _send_signal(
            self,
            peer_ip:    str,
            peer_port:  int,
            session_id: str,
            role:       str,
            candidates: list[dict],
    ) -> bool:
        """Отправляет ICE кандидатов на пир через HTTP API."""
        for scheme in ("https", "http"):
            try:
                async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
                    resp = await client.post(
                        f"{scheme}://{peer_ip}:{peer_port}/api/transport/signal",
                        json={
                            "session_id": session_id,
                            "role":       role,
                            "candidates": candidates,
                        }
                    )
                    if resp.status_code == 200:
                        return True
            except Exception as e:
                logger.debug(f"Signal send {scheme}://{peer_ip}: {e}")
        return False

    # ── Отправка сообщений через лучший транспорт ─────────────────────────────

    async def send_via_best_transport(
            self,
            peer_ip:   str,
            peer_port: int,
            payload:   dict,
    ) -> tuple[bool, str]:
        """
        Отправляет сообщение через лучший доступный транспорт.
        Возвращает (success, transport_name).
        """
        state = self._peers.get(peer_ip)

        # 1. UDP Hole Punch
        if state:
            hp_ts = state.transports.get(TransportPriority.UDP_HOLE_PUNCH)
            if hp_ts and hp_ts.is_healthy() and state.hole_punch_session:
                sess = hole_puncher.get_session(state.hole_punch_session)
                if sess:
                    import json
                    ok = await hole_puncher.send_data(sess, json.dumps(payload).encode())
                    if ok:
                        return True, "udp_hole_punch"

        # 2. Wi-Fi Direct (подключённые пиры имеют IP)
        if state and state.wifi_direct_mac:
            wd_peer = next(
                (p for p in wifi_direct_manager.get_connected_peers()
                 if p.mac == state.wifi_direct_mac),
                None,
            )
            if wd_peer and wd_peer.ip:
                ok = await self._send_http(wd_peer.ip, wd_peer.port, payload)
                if ok:
                    return True, "wifi_direct"

        # 3. BLE (только для малых сообщений)
        import json
        payload_bytes = json.dumps(payload).encode()
        if state and state.ble_address and len(payload_bytes) < 512:
            ok = await ble_manager.send_message(state.ble_address, payload)
            if ok:
                return True, "ble"

        # 4. Прямой HTTP (если в LAN)
        ok = await self._send_http(peer_ip, peer_port, payload)
        if ok:
            return True, "direct_tcp"

        return False, "failed"

    async def _send_http(self, ip: str, port: int, payload: dict) -> bool:
        """Пробует отправить payload через HTTP."""
        for scheme in ("https", "http"):
            try:
                async with httpx.AsyncClient(timeout=3.0, verify=False) as client:
                    resp = await client.post(
                        f"{scheme}://{ip}:{port}/api/peers/receive",
                        json=payload,
                    )
                    return resp.status_code == 200
            except Exception:
                pass
        return False

    async def _measure_latency(self, ip: str, port: int) -> float:
        """Измеряет round-trip latency в мс."""
        start = time.monotonic()
        for scheme in ("https", "http"):
            try:
                async with httpx.AsyncClient(timeout=3.0, verify=False) as c:
                    r = await c.get(f"{scheme}://{ip}:{port}/api/peers/status")
                    if r.status_code == 200:
                        return (time.monotonic() - start) * 1000
            except Exception:
                pass
        return 9999.0

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_or_create(self, peer_ip: str, peer_port: int) -> PeerTransportState:
        if peer_ip not in self._peers:
            self._peers[peer_ip] = PeerTransportState(
                peer_ip   = peer_ip,
                peer_port = peer_port,
            )
        return self._peers[peer_ip]

    def accept_signal(self, session_id: str, role: str, candidates: list[dict]) -> None:
        """Принимает ICE кандидаты от пира (вызывается из API)."""
        signaling.store(session_id, role, candidates)

    # ── Status API ────────────────────────────────────────────────────────────

    def full_status(self) -> dict:
        return {
            "external_ip":   self._external_ip,
            "external_port": self._external_port,
            "ble":           ble_manager.status(),
            "wifi_direct":   wifi_direct_manager.status(),
            "nat_sessions":  len(hole_puncher._sessions),
            "peers": {
                ip: {
                    "best_transport": (state.best_transport() or "none"),
                    "transports": {
                        t.name: {
                            "active":     ts.active,
                            "latency_ms": ts.latency_ms,
                            "errors":     ts.error_count,
                        }
                        for t, ts in state.transports.items()
                    },
                }
                for ip, state in self._peers.items()
            },
        }


# Глобальный экземпляр
transport_manager = TransportManager()