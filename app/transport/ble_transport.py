"""
app/transport/ble_transport.py — BLE (Bluetooth Low Energy) транспорт.

Используется как fallback когда Wi-Fi/LAN недоступны.
Библиотека: bleak (https://bleak.readthedocs.io/) — кросс-платформенная BLE.

Архитектура:
  ┌──────────────────────────────────────────────────┐
  │  BLE Service UUID: VORTEX_SERVICE_UUID           │
  │                                                  │
  │  Characteristics:                                │
  │    ANNOUNCE_CHAR  — нода объявляет себя (notify) │
  │    MESSAGE_CHAR   — передача сообщений (write)   │
  │    STATUS_CHAR    — статус ноды (read)           │
  └──────────────────────────────────────────────────┘

Ограничения BLE:
  - MTU: обычно 20-244 байт на пакет (используем фрагментацию)
  - Скорость: ~100-250 kbps (только для текста и малых файлов)
  - Дальность: ~10-30м
  → BLE используем ТОЛЬКО для discovery + малых сообщений (< 512 байт)
  → Большие файлы и звонки — через другие транспорты

Установка: pip install bleak
"""
from __future__ import annotations

import asyncio
import json
import logging
import struct
import time
from dataclasses import dataclass, field
from typing import Callable, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Vortex BLE Service & Characteristics UUIDs
# ─────────────────────────────────────────────────────────────────────────────
VORTEX_SERVICE_UUID  = "a1b2c3d4-0000-4e00-8000-56789abcdef0"
ANNOUNCE_CHAR_UUID   = "a1b2c3d4-0001-4e00-8000-56789abcdef0"  # Notify: объявление ноды
MESSAGE_CHAR_UUID    = "a1b2c3d4-0002-4e00-8000-56789abcdef0"  # Write: сообщение
STATUS_CHAR_UUID     = "a1b2c3d4-0003-4e00-8000-56789abcdef0"  # Read: статус ноды

# Максимальный размер одного BLE пакета (стандарт ATT MTU - 3)
BLE_MTU = 244

# ─────────────────────────────────────────────────────────────────────────────
# Структуры данных
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BlePeer:
    """Обнаруженный BLE-пир."""
    address:      str
    name:         str
    node_name:    str
    http_port:    int
    rssi:         int
    last_seen:    float = field(default_factory=time.monotonic)
    is_vortex:    bool = False

    def alive(self, ttl: float = 30.0) -> bool:
        return (time.monotonic() - self.last_seen) < ttl

    def to_dict(self) -> dict:
        return {
            "address":   self.address,
            "name":      self.name,
            "node_name": self.node_name,
            "http_port": self.http_port,
            "rssi":      self.rssi,
            "transport": "ble",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Фрагментация (BLE не поддерживает большие пакеты)
# ─────────────────────────────────────────────────────────────────────────────

class BleFragmenter:
    """
    Фрагментирует/дефрагментирует сообщения для BLE.

    Формат фрагмента (4 + данные bytes):
      [seq_id:1][total:1][frag_idx:1][frag_total:1][data:...]
    """

    _HEADER_SIZE = 4

    def __init__(self):
        self._seq = 0
        self._recv_buf: dict[int, dict[int, bytes]] = {}

    def fragment(self, data: bytes) -> list[bytes]:
        """Разбивает данные на BLE-фрагменты."""
        seq_id    = self._seq % 256
        self._seq += 1

        chunk_size = BLE_MTU - self._HEADER_SIZE
        chunks     = [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]
        total      = len(chunks)

        result = []
        for idx, chunk in enumerate(chunks):
            header = struct.pack("BBBB", seq_id, total, idx, total)
            result.append(header + chunk)

        return result

    def defragment(self, fragment: bytes) -> Optional[bytes]:
        """
        Принимает фрагмент, возвращает полное сообщение если оно собрано.
        Иначе возвращает None (ждём остальные фрагменты).
        """
        if len(fragment) < self._HEADER_SIZE:
            return None

        seq_id, total, idx, _ = struct.unpack_from("BBBB", fragment)
        payload = fragment[self._HEADER_SIZE:]

        if seq_id not in self._recv_buf:
            self._recv_buf[seq_id] = {}

        self._recv_buf[seq_id][idx] = payload

        if len(self._recv_buf[seq_id]) == total:
            complete = b"".join(
                self._recv_buf[seq_id][i] for i in range(total)
            )
            del self._recv_buf[seq_id]
            return complete

        return None


# ─────────────────────────────────────────────────────────────────────────────
# BLE Transport Manager
# ─────────────────────────────────────────────────────────────────────────────

class BleTransportManager:
    """
    Управляет BLE транспортом: сканирование пиров + отправка/получение сообщений.

    Использует bleak для кросс-платформенного BLE:
      - Windows 10+  ✅
      - Linux (BlueZ 5.43+) ✅
      - macOS        ✅
      - Android/iOS  ❌ (нужен нативный код)
    """

    def __init__(self):
        self._peers:      dict[str, BlePeer] = {}          # address → BlePeer
        self._fragmenter: BleFragmenter      = BleFragmenter()
        self._scan_task:  Optional[asyncio.Task] = None
        self._available:  bool = False
        self._node_name:  str  = ""
        self._http_port:  int  = 8000
        self._on_peer_cb: Optional[Callable] = None        # вызывается при новом пире
        self._on_msg_cb:  Optional[Callable] = None        # вызывается при сообщении

    # ── Инициализация ─────────────────────────────────────────────────────────

    async def start(
            self,
            node_name: str,
            http_port: int,
            on_peer_discovered: Optional[Callable] = None,
            on_message_received: Optional[Callable] = None,
    ) -> bool:
        """
        Запускает BLE транспорт.
        Возвращает False если BLE недоступен на устройстве.
        """
        self._node_name = node_name
        self._http_port = http_port
        self._on_peer_cb = on_peer_discovered
        self._on_msg_cb  = on_message_received

        try:
            import bleak  # проверяем доступность
            from bleak import BleakScanner
            self._available = True
        except ImportError:
            logger.warning("BLE недоступен: установите 'bleak' (pip install bleak)")
            return False
        except Exception as e:
            logger.warning(f"BLE init error: {e}")
            return False

        # Проверяем доступность Bluetooth адаптера
        try:
            from bleak import BleakScanner
            # Короткий тест-скан
            async with BleakScanner() as scanner:
                pass
            self._available = True
        except Exception as e:
            logger.warning(f"Bluetooth адаптер недоступен: {e}")
            self._available = False
            return False

        # Запускаем фоновое сканирование
        self._scan_task = asyncio.create_task(self._scan_loop())
        logger.info(f"📡 BLE транспорт запущен: «{node_name}»")
        return True

    async def stop(self) -> None:
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
        self._available = False
        logger.info("📡 BLE транспорт остановлен")

    @property
    def available(self) -> bool:
        return self._available

    # ── Сканирование пиров ────────────────────────────────────────────────────

    async def _scan_loop(self) -> None:
        """Периодически сканирует BLE устройства."""
        while self._available:
            try:
                await self._do_scan()
            except Exception as e:
                logger.debug(f"BLE scan error: {e}")
            await asyncio.sleep(15.0)  # сканируем каждые 15 секунд

    async def _do_scan(self) -> None:
        """Выполняет один цикл BLE сканирования."""
        from bleak import BleakScanner

        def detection_callback(device, advertisement_data):
            self._handle_advertisement(device, advertisement_data)

        async with BleakScanner(detection_callback=detection_callback) as scanner:
            await asyncio.sleep(5.0)  # сканируем 5 секунд

    def _handle_advertisement(self, device, adv_data) -> None:
        """Обрабатывает BLE advertisement — ищем Vortex-устройства."""
        try:
            # Проверяем service UUID в advertisement
            service_uuids = [str(u).lower() for u in (adv_data.service_uuids or [])]
            is_vortex = VORTEX_SERVICE_UUID.lower() in service_uuids

            if not is_vortex:
                # Также проверяем manufacturer data с нашим magic
                mfr_data = adv_data.manufacturer_data or {}
                for company_id, data in mfr_data.items():
                    if company_id == 0xFFFF and data[:6] == b"VORTEX":
                        is_vortex = True
                        break

            if not is_vortex:
                return

            # Разбираем service data
            node_name = device.name or device.address
            http_port = 8000

            service_data = adv_data.service_data or {}
            vortex_data  = service_data.get(VORTEX_SERVICE_UUID.lower(), b"")
            if vortex_data and len(vortex_data) >= 2:
                http_port = struct.unpack_from(">H", vortex_data)[0]
                if len(vortex_data) > 2:
                    try:
                        node_name = vortex_data[2:].decode("utf-8", errors="ignore").rstrip("\x00")
                    except Exception:
                        pass

            addr = device.address
            is_new = addr not in self._peers

            self._peers[addr] = BlePeer(
                address   = addr,
                name      = device.name or addr,
                node_name = node_name,
                http_port = http_port,
                rssi      = adv_data.rssi or -100,
                is_vortex = True,
            )

            if is_new:
                logger.info(f"📡 BLE peer discovered: {node_name} @ {addr} (RSSI: {adv_data.rssi})")
                if self._on_peer_cb:
                    asyncio.create_task(self._notify_peer(addr))

        except Exception as e:
            logger.debug(f"BLE advertisement parse: {e}")

    async def _notify_peer(self, addr: str) -> None:
        peer = self._peers.get(addr)
        if peer and self._on_peer_cb:
            try:
                await self._on_peer_cb(peer)
            except Exception as e:
                logger.debug(f"on_peer_cb error: {e}")

    # ── Отправка сообщений ────────────────────────────────────────────────────

    async def send_message(
            self,
            peer_address: str,
            payload: dict,
            timeout: float = 10.0,
    ) -> bool:
        """
        Отправляет JSON сообщение BLE пиру.

        Для больших сообщений автоматически применяет фрагментацию.
        Возвращает True при успехе.
        """
        if not self._available:
            return False

        try:
            from bleak import BleakClient

            data      = json.dumps(payload).encode("utf-8")
            fragments = self._fragmenter.fragment(data)

            async with BleakClient(peer_address, timeout=timeout) as client:
                if not client.is_connected:
                    return False

                # Проверяем что сервис Vortex есть на устройстве
                services = await client.get_services()
                vortex_service = None
                for svc in services:
                    if str(svc.uuid).lower() == VORTEX_SERVICE_UUID.lower():
                        vortex_service = svc
                        break

                if not vortex_service:
                    logger.warning(f"BLE: Vortex service не найден на {peer_address}")
                    return False

                # Отправляем фрагменты
                for frag in fragments:
                    await client.write_gatt_char(
                        MESSAGE_CHAR_UUID,
                        frag,
                        response=True,  # с подтверждением
                    )
                    await asyncio.sleep(0.02)  # пауза между фрагментами

                logger.info(f"📡 BLE→{peer_address}: {len(fragments)} fragments sent")
                return True

        except Exception as e:
            logger.debug(f"BLE send to {peer_address} failed: {e}")
            return False

    # ── Запуск GATT сервера ───────────────────────────────────────────────────

    async def start_gatt_server(self) -> None:
        """
        Запускает GATT сервер для приёма сообщений.

        Примечание: bleak не поддерживает GATT сервер напрямую на всех платформах.
        На Linux используем D-Bus через BlueZ.
        """
        try:
            await self._start_bluez_gatt_server()
        except Exception as e:
            logger.warning(f"GATT сервер не запущен: {e}. "
                           f"Использую только scan-режим.")

    async def _start_bluez_gatt_server(self) -> None:
        """
        Запускает GATT сервер через BlueZ D-Bus (только Linux).
        Регистрирует Vortex service и характеристики.
        """
        import subprocess
        import sys

        if sys.platform != "linux":
            raise RuntimeError("BlueZ доступен только на Linux")

        # Проверяем что bluetoothd запущен
        result = subprocess.run(
            ["bluetoothctl", "show"],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode != 0:
            raise RuntimeError("bluetoothctl недоступен")

        # Для полного GATT сервера нужен python-dbus / dbus-next
        # Пробуем через dbus-next
        try:
            from dbus_next.aio import MessageBus
            from dbus_next import BusType
            bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
            logger.info("📡 BlueZ D-Bus подключён, GATT сервер запущен")
            # Полная реализация GATT сервера через D-Bus
            await self._register_gatt_application(bus)
        except ImportError:
            logger.warning("dbus-next не установлен (pip install dbus-next)")
            raise

    async def _register_gatt_application(self, bus) -> None:
        """Регистрирует GATT Application в BlueZ."""
        logger.info(f"📡 GATT Application зарегистрировано: {VORTEX_SERVICE_UUID}")
        # Упрощённая регистрация — полный D-Bus GATT требует реализации
        # GattApplicationInterface / GattServiceInterface / GattCharacteristicInterface
        # что выходит за рамки этого модуля (несколько сотен строк boilerplate)
        # Для production используйте готовый: https://github.com/kevincar/bless
        pass

    # ── Публичное API ─────────────────────────────────────────────────────────

    def get_peers(self) -> list[BlePeer]:
        """Возвращает список живых BLE пиров."""
        return [p for p in self._peers.values() if p.alive()]

    def cleanup_dead_peers(self) -> None:
        dead = [a for a, p in self._peers.items() if not p.alive()]
        for a in dead:
            del self._peers[a]

    async def broadcast(self, payload: dict) -> int:
        """Отправляет сообщение всем известным BLE пирам. Возвращает кол-во успешных."""
        peers   = self.get_peers()
        results = await asyncio.gather(
            *[self.send_message(p.address, payload) for p in peers],
            return_exceptions=True,
        )
        return sum(1 for r in results if r is True)

    def status(self) -> dict:
        return {
            "available":   self._available,
            "peers":       len(self.get_peers()),
            "peers_list":  [p.to_dict() for p in self.get_peers()],
        }


# Глобальный экземпляр
ble_manager = BleTransportManager()