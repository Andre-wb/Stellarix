"""
app/peer/peer_registry.py — P2P Discovery и обмен сообщениями между узлами.

Этот модуль реализует обнаружение соседних узлов (peers) в локальной сети через UDP broadcast.
Он также предоставляет HTTP API для взаимодействия с другими узлами:
- отправка сообщений в комнаты другого узла,
- получение списка активных пиров,
- приём входящих P2P сообщений и их ретрансляция локальным WebSocket-клиентам.

Модуль поддерживает два режима работы:
1. Если установлен Rust-модуль `vortex_chat` (скомпилирован), используется его
   высокопроизводительная реализация UDP discovery.
2. Иначе работает чистый Python fallback с потоками-слушателем и отправителем.

Реестр пиров (PeerRegistry) хранит информацию об обнаруженных узлах и периодически
очищает устаревшие записи (по таймауту Config.PEER_TIMEOUT_SEC).
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

# Создаём роутер для эндпоинтов, связанных с пирами
router = APIRouter(prefix="/api/peers", tags=["peers"])


@dataclass
class PeerInfo:
    """
    Информация об одном обнаруженном пире (узле).

    Атрибуты:
        name: str — имя узла (обычно hostname или переданное имя).
        ip: str — IP-адрес узла.
        port: int — порт, на котором работает HTTP-сервер узла.
        last_seen: float — временная метка последнего получения UDP-пакета (time.monotonic).
    """
    name: str
    ip: str
    port: int
    last_seen: float = field(default_factory=time.monotonic)

    def alive(self) -> bool:
        """Проверяет, не истёк ли таймаут для этого пира."""
        return (time.monotonic() - self.last_seen) < Config.PEER_TIMEOUT_SEC

    def to_dict(self) -> dict:
        """Возвращает словарь с данными пира для JSON-ответа."""
        return {
            "name": self.name,
            "ip": self.ip,
            "port": self.port,
            "age_sec": round(time.monotonic() - self.last_seen, 1),
            "online": self.alive(),
        }

    @property
    def base_url(self) -> str:
        """Базовый URL для HTTP-запросов к этому пиру."""
        return f"http://{self.ip}:{self.port}"


class PeerRegistry:
    """
    Реестр пиров (локальная копия сети).

    Хранит словарь IP -> PeerInfo. Потокобезопасен благодаря использованию threading.Lock.
    Методы update, active, get, cleanup должны вызываться с блокировкой (или внутри с ней).
    """

    def __init__(self):
        self._peers: dict[str, PeerInfo] = {}
        self._lock = threading.Lock()
        self.own_ip: str = "127.0.0.1"  # будет обновлено при старте discovery

    def update(self, ip: str, name: str, port: int) -> None:
        """
        Обновляет или добавляет информацию о пире.
        Вызывается при получении UDP-пакета.
        """
        with self._lock:
            if ip in self._peers:
                p = self._peers[ip]
                p.name = name
                p.port = port
                p.last_seen = time.monotonic()
            else:
                self._peers[ip] = PeerInfo(name=name, ip=ip, port=port)
                logger.info(f"🔍 New peer: {name} @ {ip}:{port}")

    def active(self) -> list[PeerInfo]:
        """Возвращает список пиров, которые считаются живыми (alive())."""
        with self._lock:
            return [p for p in self._peers.values() if p.alive()]

    def get(self, ip: str) -> Optional[PeerInfo]:
        """Возвращает информацию о пире по IP, если он есть и жив (но не проверяет alive)."""
        with self._lock:
            return self._peers.get(ip)

    def cleanup(self) -> None:
        """Удаляет все пиры, у которых истёк таймаут."""
        with self._lock:
            dead = [ip for ip, p in self._peers.items() if not p.alive()]
            for ip in dead:
                del self._peers[ip]


# Глобальный экземпляр реестра
registry = PeerRegistry()


# ══════════════════════════════════════════════════════════════════════════════
# Вспомогательные функции для UDP discovery
# ══════════════════════════════════════════════════════════════════════════════

def _local_ip() -> str:
    """
    Определяет локальный IP-адрес машины в сети.

    Использует UDP-соединение с фиктивными адресами (не отправляет реальные пакеты),
    чтобы определить, через какой интерфейс пойдёт трафик. Пробует несколько адресов
    из разных подсетей, затем fallback через gethostbyname.
    Возвращает "127.0.0.1", если ничего не удалось.
    """
    # Пробуем несколько LAN-адресов — UDP connect не шлёт пакетов, просто выбирает маршрут
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
    # Fallback через hostname
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return "127.0.0.1"


def _subnet_broadcast(ip: str) -> str:
    """
    Вычисляет широковещательный адрес для подсети /24 на основе локального IP.
    Предполагается маска 255.255.255.0. Если не удаётся разобрать, возвращает
    глобальный broadcast 255.255.255.255.
    """
    try:
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}.255"
    except Exception:
        pass
    return "255.255.255.255"


# ══════════════════════════════════════════════════════════════════════════════
# Запуск discovery (Rust или Python)
# ══════════════════════════════════════════════════════════════════════════════

def start_discovery(device_name: str = "") -> None:
    """
    Запускает процесс обнаружения пиров (UDP broadcast) в фоновых потоках.

    Если доступен скомпилированный Rust-модуль vortex_chat, использует его.
    Иначе запускает Python-реализацию: два потока (слушатель и отправитель).

    Параметр device_name — имя, под которым узел будет виден другим. Если не указан,
    используется socket.gethostname().
    """
    name = device_name or socket.gethostname()
    registry.own_ip = _local_ip()

    # Попытка импортировать и использовать Rust-модуль
    try:
        import vortex_chat as _vc
        _vc.start_discovery(name, Config.PORT)
        logger.info(f"🦀 Rust UDP discovery запущен как «{name}»")

        # Запускаем фоновый поток для периодической синхронизации обнаруженных Rust-пиров
        # в наш Python-реестр. Rust-модуль хранит свой список пиров отдельно.
        def _sync_rust_peers():
            while True:
                try:
                    for ip, port in _vc.get_peers():
                        # В Rust-версии имена пиров пока не передаются, используем IP как имя
                        registry.update(ip, ip, port)
                except Exception:
                    pass
                time.sleep(3)

        threading.Thread(target=_sync_rust_peers, daemon=True, name="rust-peers-sync").start()
        return

    except (ImportError, AttributeError):
        # Rust-модуль не найден или не содержит нужных функций — используем Python fallback
        logger.info("Python UDP discovery fallback")

    # Python fallback
    threading.Thread(target=_py_listener, daemon=True, name="udp-listen").start()
    threading.Thread(target=_py_sender, args=(name,), daemon=True, name="udp-send").start()
    logger.info(f"🐍 Python UDP discovery запущен как «{name}»")


def _py_listener():
    """
    Фоновый поток для прослушивания UDP-пакетов (Python fallback).
    При получении пакета парсит JSON, извлекает имя и порт, обновляет реестр.
    Также периодически (по таймауту сокета) вызывает cleanup для удаления устаревших пиров.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", Config.UDP_PORT))  # слушаем на всех интерфейсах
        sock.settimeout(2.0)
    except OSError as e:
        logger.error(f"UDP bind failed: {e}")
        return

    while True:
        try:
            data, addr = sock.recvfrom(1024)
            src_ip = addr[0]
            # Игнорируем пакеты от самого себя (own_ip может измениться, но проверяем оба варианта)
            if src_ip == registry.own_ip or src_ip.startswith("127."):
                continue
            info = json.loads(data.decode())
            # Обрезаем имя до 64 символов для безопасности
            registry.update(src_ip, str(info.get("name", src_ip))[:64],
                            int(info.get("port", Config.PORT)))
        except socket.timeout:
            # Таймаут — регулярно чистим устаревших пиров
            registry.cleanup()
        except Exception as e:
            logger.debug(f"UDP recv: {e}")


def _py_sender(name: str):
    """
    Фоновый поток для периодической рассылки UDP-пакетов (Python fallback).
    Каждые Config.UDP_INTERVAL_SEC отправляет broadcast-пакет со своим именем и портом.
    Отправляет на широковещательный адрес подсети и на глобальный broadcast 255.255.255.255.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    while True:
        try:
            # Пересчитываем IP и broadcast каждую итерацию — IP может измениться (например, смена сети)
            own_ip = _local_ip()
            if own_ip != registry.own_ip and not own_ip.startswith("127."):
                registry.own_ip = own_ip
            payload = json.dumps({"name": name, "port": Config.PORT}).encode()
            bcast = _subnet_broadcast(own_ip)
            sock.sendto(payload, (bcast, Config.UDP_PORT))
            # Также шлём на 255.255.255.255 для максимальной совместимости
            try:
                sock.sendto(payload, ("255.255.255.255", Config.UDP_PORT))
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"UDP send: {e}")
        time.sleep(Config.UDP_INTERVAL_SEC)


# ══════════════════════════════════════════════════════════════════════════════
# Вспомогательная функция для отправки сообщения пиру по HTTP
# ══════════════════════════════════════════════════════════════════════════════

async def _send_to_peer(peer: PeerInfo, room_id: int, sender: str, text: str) -> bool:
    """
    Отправляет P2P-сообщение одному пиру через его HTTP-эндпоинт /api/peers/receive.
    Возвращает True при успехе (статус 200).
    """
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(
                f"{peer.base_url}/api/peers/receive",
                json={"room_id": room_id, "sender": sender, "text": text},
            )
            return response.status_code == 200
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# REST API endpoints
# ══════════════════════════════════════════════════════════════════════════════

@router.get("")
async def list_peers(u: User = Depends(get_current_user)):
    """
    Возвращает список активных пиров (соседних узлов), обнаруженных в локальной сети.
    Требует аутентификации.
    """
    peers = registry.active()
    return {
        "own_ip": registry.own_ip,
        "count": len(peers),
        "peers": [p.to_dict() for p in peers],
    }


@router.get("/status")
async def peer_status():
    """
    Публичный эндпоинт для проверки доступности узла и получения информации о нём.
    Используется другими пирами при P2P-взаимодействии.
    """
    return {
        "ok": True,
        "own_ip": registry.own_ip,
        "peers": len(registry.active()),  # количество известных этому узлу пиров
    }


class MsgIn(BaseModel):
    """Модель входящего P2P-сообщения от другого узла."""
    room_id: int
    sender: str
    text: str


@router.post("/receive")
async def receive_from_peer(msg: MsgIn, request: Request):
    """
    Эндпоинт, через который другие узлы отправляют сообщения.
    Полученное сообщение транслируется всем локальным WebSocket-клиентам,
    находящимся в указанной комнате.

    Примечание: не требует аутентификации, так как доверие основано на IP (локальная сеть).
    """
    src_ip = request.client.host if request.client else "unknown"
    peer = registry.get(src_ip)
    if not peer:
        # Питер не зарегистрирован — возможно, он только что появился.
        # Всё равно принимаем сообщение, но логируем предупреждение.
        logger.warning(f"P2P msg from unregistered peer {src_ip}")

    # Рассылаем всем локальным WebSocket-клиентам в комнате
    await ws_manager.broadcast_to_room(
        msg.room_id,
        {
            "type": "peer_message",
            "sender": msg.sender,
            "sender_ip": src_ip,
            "text": msg.text,
            "from_peer": True,  # флаг для отличия от обычных сообщений чата
        },
    )
    return {"ok": True}


class SendReq(BaseModel):
    """Модель запроса на отправку P2P-сообщения от локального пользователя."""
    room_id: int
    text: str
    peer_ip: Optional[str] = None  # если указан, отправить только конкретному пиру


@router.post("/send")
async def send_p2p(body: SendReq, u: User = Depends(get_current_user)):
    """
    Отправляет сообщение одному или всем активным пирам от имени текущего пользователя.

    - Если указан peer_ip, отправляет только этому пиру (если он есть в реестре).
    - Иначе отправляет всем активным пирам параллельно.

    Возвращает статистику: сколько пиров получили сообщение.
    """
    if body.peer_ip:
        peer = registry.get(body.peer_ip)
        if not peer:
            raise HTTPException(404, "Пир не найден")
        ok = await _send_to_peer(peer, body.room_id, u.username, body.text)
        return {"sent": ok}

    # Отправка всем активным пирам
    peers = registry.active()
    # Запускаем все запросы параллельно (asyncio.gather)
    results = await asyncio.gather(
        *[_send_to_peer(p, body.room_id, u.username, body.text) for p in peers],
        return_exceptions=True,  # не прерываем при ошибках
    )
    sent_count = sum(1 for r in results if r is True)
    return {"sent_to": sent_count, "total": len(peers)}