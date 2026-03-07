"""
app/peer/connection_manager.py — WebSocket менеджер с разделением по комнатам.

Добавлено:
- Глобальный кэш seen_ids для дедупликации сообщений (критерий 5.1)
- TokenBucket rate limiter для защиты ретранслятора от перегрузки (критерий 5.2)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Token Bucket — ограничение нагрузки на ретранслятор
# ══════════════════════════════════════════════════════════════════════════════

class TokenBucket:
    """
    Алгоритм Token Bucket для ограничения скорости сообщений.

    Параметры:
        capacity   — максимальное число токенов (всплески).
        rate       — скорость пополнения (токенов/сек).

    Пример: capacity=20, rate=5 разрешает всплески до 20 сообщений,
    но в среднем не более 5 в секунду.
    """

    __slots__ = ("capacity", "rate", "_tokens", "_last_ts")

    def __init__(self, capacity: float = 20.0, rate: float = 5.0):
        self.capacity  = capacity
        self.rate      = rate
        self._tokens   = capacity
        self._last_ts  = time.monotonic()

    def consume(self, tokens: float = 1.0) -> bool:
        """
        Пытается потребить `tokens` токенов.
        Возвращает True если токенов достаточно, False — если лимит исчерпан.
        """
        now   = time.monotonic()
        delta = now - self._last_ts
        self._last_ts = now
        self._tokens  = min(self.capacity, self._tokens + delta * self.rate)
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False


# ══════════════════════════════════════════════════════════════════════════════
# Глобальный кэш дедупликации сообщений
# ══════════════════════════════════════════════════════════════════════════════

class MessageDeduplicator:
    """
    LRU-подобный кэш уже обработанных msg_id.

    Хранит последние `max_size` идентификаторов.
    При превышении лимита удаляет самые старые записи (FIFO).
    TTL — дополнительная защита от устаревших повторов.
    """

    def __init__(self, max_size: int = 10_000, ttl_sec: float = 300.0):
        self._max_size = max_size
        self._ttl      = ttl_sec
        self._seen:    dict[str, float] = {}   # msg_id → timestamp
        self._order:   deque[str]       = deque()
        self._lock     = asyncio.Lock()

    async def is_duplicate(self, msg_id: str) -> bool:
        """
        Возвращает True если msg_id уже обрабатывался, иначе регистрирует его и возвращает False.
        """
        async with self._lock:
            now = time.monotonic()

            # Проверяем TTL: чистим записи старше TTL
            while self._order and (now - self._seen.get(self._order[0], now)) > self._ttl:
                old = self._order.popleft()
                self._seen.pop(old, None)

            if msg_id in self._seen:
                return True

            # Добавляем
            self._seen[msg_id] = now
            self._order.append(msg_id)

            # Обрезаем по размеру
            while len(self._seen) > self._max_size:
                old = self._order.popleft()
                self._seen.pop(old, None)

            return False

    def seen_count(self) -> int:
        return len(self._seen)


# Глобальный экземпляр дедупликатора для всего приложения
deduplicator = MessageDeduplicator(max_size=10_000, ttl_sec=300.0)


# ══════════════════════════════════════════════════════════════════════════════
# ConnectedUser
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ConnectedUser:
    """
    Хранит информацию о подключённом пользователе в комнате.

    Дополнения:
        rate_limiter — индивидуальный Token Bucket для защиты от флуда.
        msg_ack_queue — очередь сообщений, ожидающих ACK (для повторной отправки).
    """
    user_id:      int
    username:     str
    display_name: str
    avatar_emoji: str
    websocket:    WebSocket
    room_id:      int
    connected_at: datetime    = field(default_factory=lambda: datetime.now(timezone.utc))
    is_typing:    bool        = False
    rate_limiter: TokenBucket = field(default_factory=lambda: TokenBucket(capacity=30, rate=10))


# ══════════════════════════════════════════════════════════════════════════════
# ConnectionManager
# ══════════════════════════════════════════════════════════════════════════════

class ConnectionManager:
    """
    Менеджер WebSocket-соединений с поддержкой комнат.

    Расширения по сравнению с исходной версией:
    1. Проверка дедупликации сообщений через глобальный MessageDeduplicator.
    2. Token Bucket rate limiting на пользователя для broadcast.
    3. Метод check_rate_limit() для проверки перед обработкой входящего сообщения.
    """

    def __init__(self):
        self._rooms: dict[int, dict[int, ConnectedUser]] = defaultdict(dict)
        self._lock  = asyncio.Lock()

    async def connect(
            self,
            room_id:      int,
            user_id:      int,
            username:     str,
            display_name: str,
            avatar_emoji: str,
            ws:           WebSocket,
    ) -> None:
        await ws.accept()
        async with self._lock:
            self._rooms[room_id][user_id] = ConnectedUser(
                user_id      = user_id,
                username     = username,
                display_name = display_name,
                avatar_emoji = avatar_emoji,
                websocket    = ws,
                room_id      = room_id,
            )
        logger.info(f"WS+ {username}({user_id}) → room {room_id}")

        await self.broadcast_to_room(
            room_id,
            {
                "type":         "user_joined",
                "user_id":      user_id,
                "username":     username,
                "display_name": display_name,
                "avatar_emoji": avatar_emoji,
                "online_users": self.get_online_users(room_id),
            },
            exclude=user_id,
        )

    async def disconnect(self, room_id: int, user_id: int) -> None:
        async with self._lock:
            user = self._rooms[room_id].pop(user_id, None)
            if not self._rooms[room_id]:
                del self._rooms[room_id]

        if user:
            logger.info(f"WS- {user.username}({user_id}) ← room {room_id}")
            await self.broadcast_to_room(
                room_id,
                {
                    "type":         "user_left",
                    "user_id":      user_id,
                    "username":     user.username,
                    "online_users": self.get_online_users(room_id),
                },
            )

    async def broadcast_to_room(
            self,
            room_id: int,
            payload: dict[str, Any],
            exclude: int | None = None,
    ) -> None:
        dead = []
        for uid, conn in dict(self._rooms.get(room_id, {})).items():
            if uid == exclude:
                continue
            try:
                await conn.websocket.send_json(payload)
            except Exception:
                dead.append(uid)

        for uid in dead:
            await self.disconnect(room_id, uid)

    async def send_to_user(self, room_id: int, user_id: int, payload: dict) -> bool:
        conn = self._rooms.get(room_id, {}).get(user_id)
        if not conn:
            return False
        try:
            await conn.websocket.send_json(payload)
            return True
        except Exception:
            await self.disconnect(room_id, user_id)
            return False

    async def set_typing(self, room_id: int, user_id: int, is_typing: bool) -> None:
        conn = self._rooms.get(room_id, {}).get(user_id)
        if not conn:
            return
        conn.is_typing = is_typing
        await self.broadcast_to_room(
            room_id,
            {
                "type":      "typing",
                "user_id":   user_id,
                "username":  conn.username,
                "is_typing": is_typing,
            },
            exclude=user_id,
        )

    def check_rate_limit(self, room_id: int, user_id: int) -> bool:
        """
        Проверяет Token Bucket для пользователя.
        Возвращает True если сообщение разрешено, False — если превышен лимит.
        """
        conn = self._rooms.get(room_id, {}).get(user_id)
        if not conn:
            return False
        return conn.rate_limiter.consume()

    async def is_duplicate_message(self, msg_id: str) -> bool:
        """
        Проверяет дедупликацию через глобальный кэш.
        Возвращает True если сообщение уже обрабатывалось.
        """
        if not msg_id:
            return False
        return await deduplicator.is_duplicate(msg_id)

    def get_online_users(self, room_id: int) -> list[dict]:
        return [
            {
                "user_id":      c.user_id,
                "username":     c.username,
                "display_name": c.display_name,
                "avatar_emoji": c.avatar_emoji,
                "is_typing":    c.is_typing,
            }
            for c in self._rooms.get(room_id, {}).values()
        ]

    def is_online(self, room_id: int, user_id: int) -> bool:
        return user_id in self._rooms.get(room_id, {})

    def total_connections(self) -> int:
        return sum(len(v) for v in self._rooms.values())

    def dedup_stats(self) -> dict:
        """Возвращает статистику дедупликатора для мониторинга."""
        return {
            "seen_msg_ids": deduplicator.seen_count(),
            "rooms":        len(self._rooms),
            "connections":  self.total_connections(),
        }


# Глобальный экземпляр менеджера
manager = ConnectionManager()