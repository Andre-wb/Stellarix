"""
app/transport/wifi_direct.py — Wi-Fi Direct (P2P) транспорт.

Поддерживаемые платформы:
  Linux   ✅  wpa_supplicant P2P через wpa_cli
  Windows ✅  WinRT WiFiDirect API через winrt-python (экспериментально)
  macOS   ⚠️  только через CoreWLAN (ограниченная поддержка)
  Android ❌  нужен нативный код

Архитектура на Linux:
  wpa_supplicant P2P:
    1. p2p_find           — сканируем устройства
    2. p2p_peers          — список найденных
    3. p2p_connect <mac> pbc — подключаемся (Push Button Config)
    4. Получаем IP из DHCP на интерфейсе p2p-*
    5. Запускаем обычный HTTP/WS на полученном IP

Отличие от обычного Wi-Fi:
  - Не нужна точка доступа
  - Прямое соединение устройство ↔ устройство
  - Дальность до ~200м (802.11 P2P)
  - Скорость до 250 Мбит/с
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Структуры данных
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WifiDirectPeer:
    """Пир обнаруженный через Wi-Fi Direct."""
    mac:         str
    name:        str
    ip:          Optional[str] = None
    port:        int = 8000
    connected:   bool = False
    interface:   Optional[str] = None   # p2p-wlan0-0 или аналог
    last_seen:   float = field(default_factory=time.monotonic)

    def to_dict(self) -> dict:
        return {
            "mac":       self.mac,
            "name":      self.name,
            "ip":        self.ip,
            "port":      self.port,
            "connected": self.connected,
            "transport": "wifi_direct",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Linux: wpa_supplicant P2P через wpa_cli
# ─────────────────────────────────────────────────────────────────────────────

class WpaCliInterface:
    """
    Интерфейс к wpa_supplicant через wpa_cli.

    Требования:
      - wpa_supplicant запущен с P2P поддержкой
      - wpa_cli доступен в PATH
      - Пользователь в группе netdev (или sudo)
    """

    def __init__(self, interface: str = "wlan0"):
        self.interface = interface
        self._ctrl_iface: Optional[str] = None

    async def _run(self, *args: str, timeout: float = 5.0) -> Optional[str]:
        """Выполняет wpa_cli команду, возвращает вывод или None."""
        cmd = ["wpa_cli", "-i", self.interface] + list(args)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            out = stdout.decode("utf-8", errors="ignore").strip()
            logger.debug(f"wpa_cli {' '.join(args)}: {out[:100]}")
            return out
        except asyncio.TimeoutError:
            logger.warning(f"wpa_cli timeout: {args}")
            return None
        except FileNotFoundError:
            logger.warning("wpa_cli не найден. Установите wpasupplicant.")
            return None
        except Exception as e:
            logger.debug(f"wpa_cli error: {e}")
            return None

    async def p2p_find(self) -> bool:
        """Запускает P2P discovery."""
        result = await self._run("p2p_find")
        return result == "OK"

    async def p2p_stop_find(self) -> bool:
        """Останавливает P2P discovery."""
        result = await self._run("p2p_stop_find")
        return result == "OK"

    async def p2p_peers(self) -> list[dict]:
        """Возвращает список найденных P2P пиров."""
        result = await self._run("p2p_peers")
        if not result:
            return []

        peers = []
        for mac in result.splitlines():
            mac = mac.strip()
            if not re.match(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", mac):
                continue
            info = await self._p2p_peer_info(mac)
            if info:
                peers.append(info)

        return peers

    async def _p2p_peer_info(self, mac: str) -> Optional[dict]:
        """Получает информацию о конкретном P2P пире."""
        result = await self._run("p2p_peer", mac)
        if not result:
            return None

        info = {"mac": mac}
        for line in result.splitlines():
            if "=" in line:
                key, _, val = line.partition("=")
                info[key.strip()] = val.strip()

        return {
            "mac":      mac,
            "name":     info.get("device_name", mac),
            "pri_dev":  info.get("primary_dev_type", ""),
            "config_methods": info.get("config_methods", ""),
            "dev_capab": info.get("dev_capab", ""),
        }

    async def p2p_connect_pbc(self, peer_mac: str) -> bool:
        """
        Подключается к P2P пиру методом PBC (Push Button Configuration).
        Обе стороны должны нажать кнопку в течение ~2 минут.
        """
        result = await self._run("p2p_connect", peer_mac, "pbc", timeout=15.0)
        logger.info(f"p2p_connect {peer_mac}: {result}")
        return bool(result and "FAIL" not in result)

    async def p2p_connect_pin(self, peer_mac: str, pin: str) -> bool:
        """Подключается к P2P пиру методом PIN."""
        result = await self._run("p2p_connect", peer_mac, pin, "pin", timeout=15.0)
        return bool(result and "FAIL" not in result)

    async def p2p_group_add(self) -> Optional[str]:
        """
        Создаёт P2P группу (этот узел становится GO — Group Owner).
        Возвращает имя интерфейса (p2p-wlan0-0) или None.
        """
        result = await self._run("p2p_group_add")
        if result == "OK":
            # Ждём появления нового интерфейса
            for _ in range(10):
                await asyncio.sleep(0.5)
                iface = await self._find_p2p_interface()
                if iface:
                    logger.info(f"📶 P2P Group created on {iface}")
                    return iface
        return None

    async def p2p_group_remove(self, interface: str) -> bool:
        """Удаляет P2P группу."""
        result = await self._run("p2p_group_remove", interface)
        return result == "OK"

    async def _find_p2p_interface(self) -> Optional[str]:
        """Ищет активный P2P интерфейс (p2p-*)."""
        try:
            import os
            interfaces = os.listdir("/sys/class/net")
            for iface in interfaces:
                if iface.startswith("p2p-"):
                    return iface
        except Exception:
            pass
        return None

    async def get_p2p_ip(self, interface: str) -> Optional[str]:
        """Получает IP адрес на P2P интерфейсе."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ip", "addr", "show", interface,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            text = stdout.decode()
            match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", text)
            if match:
                return match.group(1)
        except Exception as e:
            logger.debug(f"get_p2p_ip error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Windows: WinRT WiFiDirect
# ─────────────────────────────────────────────────────────────────────────────

class WinRTWifiDirect:
    """
    Wi-Fi Direct через Windows Runtime API (Windows 10+).
    Требует: pip install winrt-Windows.Devices.WiFiDirect
    """

    def __init__(self):
        self._available = False
        self._device = None

    async def check_available(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import winrt.windows.devices.wifidirect as wfd
            self._available = True
            return True
        except ImportError:
            logger.warning("winrt не установлен. "
                           "pip install winrt-Windows.Devices.WiFiDirect")
            return False

    async def scan(self) -> list[dict]:
        if not self._available:
            return []
        try:
            import winrt.windows.devices.wifidirect as wfd
            import winrt.windows.devices.enumeration as de

            # Запрашиваем список WiFi Direct устройств
            selector = wfd.WiFiDirectDevice.get_device_selector()
            devices  = await de.DeviceInformation.find_all_async(selector)

            result = []
            for dev in devices:
                result.append({
                    "id":   dev.id,
                    "name": dev.name,
                    "kind": str(dev.kind),
                })

            return result
        except Exception as e:
            logger.debug(f"WinRT WiFiDirect scan: {e}")
            return []

    async def connect(self, device_id: str) -> Optional[str]:
        """Подключается к WiFi Direct устройству, возвращает IP."""
        try:
            import winrt.windows.devices.wifidirect as wfd

            device = await wfd.WiFiDirectDevice.from_id_async(device_id)
            if device:
                # Получаем endpoint pair
                ep = device.get_connection_endpoint_pairs()
                if ep:
                    return str(ep[0].local_hostname)
        except Exception as e:
            logger.debug(f"WinRT connect {device_id}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Unified Wi-Fi Direct Manager
# ─────────────────────────────────────────────────────────────────────────────

class WifiDirectManager:
    """
    Кросс-платформенный менеджер Wi-Fi Direct.

    Автоматически выбирает бэкенд:
      Linux   → WpaCliInterface
      Windows → WinRTWifiDirect
    """

    def __init__(self):
        self._peers:     dict[str, WifiDirectPeer] = {}
        self._available: bool = False
        self._platform:  str  = sys.platform
        self._linux_iface: Optional[str] = None
        self._scan_task: Optional[asyncio.Task] = None
        self._on_peer_cb: Optional[Callable] = None
        self._wpa: Optional[WpaCliInterface] = None
        self._winrt: Optional[WinRTWifiDirect] = None

    async def start(
            self,
            node_name: str,
            http_port: int,
            wifi_interface: str = "wlan0",
            on_peer_discovered: Optional[Callable] = None,
    ) -> bool:
        """
        Инициализирует Wi-Fi Direct.
        Возвращает False если недоступен на этой платформе.
        """
        self._on_peer_cb = on_peer_discovered

        if self._platform == "linux":
            return await self._start_linux(node_name, http_port, wifi_interface)
        elif self._platform == "win32":
            return await self._start_windows()
        else:
            logger.warning(f"Wi-Fi Direct не поддерживается на {self._platform}")
            return False

    async def _start_linux(self, name: str, port: int, iface: str) -> bool:
        """Запускает P2P на Linux через wpa_supplicant."""
        self._wpa = WpaCliInterface(interface=iface)

        # Проверяем что wpa_cli доступен
        result = await self._wpa._run("status")
        if result is None:
            logger.warning("wpa_cli недоступен — Wi-Fi Direct недоступен")
            return False

        # Запускаем P2P group (становимся GO)
        p2p_iface = await self._wpa.p2p_group_add()
        if p2p_iface:
            self._linux_iface = p2p_iface
            ip = await self._wpa.get_p2p_ip(p2p_iface)
            logger.info(f"📶 Wi-Fi Direct GO на {p2p_iface}, IP: {ip}")
        else:
            # Не GO — пробуем только discovery
            logger.info("📶 Wi-Fi Direct: не удалось создать группу, только discovery")

        # Запускаем P2P discovery
        await self._wpa.p2p_find()

        # Фоновый scan
        self._available = True
        self._scan_task = asyncio.create_task(self._linux_scan_loop())
        logger.info(f"📶 Wi-Fi Direct запущен (Linux, iface={iface})")
        return True

    async def _start_windows(self) -> bool:
        """Запускает Wi-Fi Direct на Windows."""
        self._winrt = WinRTWifiDirect()
        ok = await self._winrt.check_available()
        if ok:
            self._available = True
            self._scan_task = asyncio.create_task(self._windows_scan_loop())
            logger.info("📶 Wi-Fi Direct запущен (Windows WinRT)")
        return ok

    async def stop(self) -> None:
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass

        if self._wpa and self._linux_iface:
            await self._wpa.p2p_stop_find()
            await self._wpa.p2p_group_remove(self._linux_iface)

        self._available = False
        logger.info("📶 Wi-Fi Direct остановлен")

    # ── Scan loops ────────────────────────────────────────────────────────────

    async def _linux_scan_loop(self) -> None:
        while self._available:
            try:
                if self._wpa:
                    raw_peers = await self._wpa.p2p_peers()
                    for raw in raw_peers:
                        mac  = raw["mac"]
                        name = raw.get("name", mac)
                        is_new = mac not in self._peers
                        self._peers[mac] = WifiDirectPeer(
                            mac  = mac,
                            name = name,
                        )
                        if is_new:
                            logger.info(f"📶 Wi-Fi Direct peer: {name} ({mac})")
                            if self._on_peer_cb:
                                asyncio.create_task(
                                    self._on_peer_cb(self._peers[mac])
                                )
            except Exception as e:
                logger.debug(f"P2P scan error: {e}")

            await asyncio.sleep(10.0)

    async def _windows_scan_loop(self) -> None:
        while self._available:
            try:
                if self._winrt:
                    devices = await self._winrt.scan()
                    for dev in devices:
                        mac  = dev.get("id", "")
                        name = dev.get("name", mac)
                        is_new = mac not in self._peers
                        self._peers[mac] = WifiDirectPeer(mac=mac, name=name)
                        if is_new and self._on_peer_cb:
                            asyncio.create_task(self._on_peer_cb(self._peers[mac]))
            except Exception as e:
                logger.debug(f"WinRT scan error: {e}")
            await asyncio.sleep(15.0)

    # ── Connect ───────────────────────────────────────────────────────────────

    async def connect_pbc(self, peer_mac: str) -> Optional[str]:
        """
        Подключается к P2P пиру методом PBC.
        Возвращает IP адрес пира или None.
        """
        if self._wpa:
            ok = await self._wpa.p2p_connect_pbc(peer_mac)
            if ok:
                # Ждём получения IP через DHCP
                for attempt in range(20):
                    await asyncio.sleep(1.0)
                    if self._linux_iface:
                        ip = await self._wpa.get_p2p_ip(self._linux_iface)
                        if ip:
                            peer = self._peers.get(peer_mac)
                            if peer:
                                peer.ip = ip
                                peer.connected = True
                            logger.info(f"📶 P2P connected to {peer_mac}, peer IP: {ip}")
                            return ip
        return None

    async def connect_winrt(self, device_id: str) -> Optional[str]:
        """Windows: подключается к WiFi Direct устройству."""
        if self._winrt:
            return await self._winrt.connect(device_id)
        return None

    # ── Status ────────────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self._available

    def get_peers(self) -> list[WifiDirectPeer]:
        return list(self._peers.values())

    def get_connected_peers(self) -> list[WifiDirectPeer]:
        return [p for p in self._peers.values() if p.connected and p.ip]

    def get_p2p_interface_ip(self) -> Optional[str]:
        """Возвращает IP нашего P2P интерфейса (если мы GO)."""
        if self._linux_iface and self._wpa:
            # Синхронный вариант для quick check
            try:
                import subprocess as sp
                result = sp.run(
                    ["ip", "addr", "show", self._linux_iface],
                    capture_output=True, text=True, timeout=2
                )
                m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", result.stdout)
                if m:
                    return m.group(1)
            except Exception:
                pass
        return None

    def status(self) -> dict:
        return {
            "available":     self._available,
            "platform":      self._platform,
            "p2p_interface": self._linux_iface,
            "p2p_ip":        self.get_p2p_interface_ip(),
            "peers":         len(self.get_peers()),
            "connected":     len(self.get_connected_peers()),
            "peers_list":    [p.to_dict() for p in self.get_peers()],
        }


# Глобальный экземпляр
wifi_direct_manager = WifiDirectManager()