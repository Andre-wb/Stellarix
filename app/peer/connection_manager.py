"""
app/peer/connection_manager.py — WebSocket менеджер с разделением по комнатам.

Этот модуль предоставляет класс ConnectionManager, который управляет всеми активными
WebSocket-соединениями пользователей в комнатах чата. Он хранит информацию о каждом
подключённом пользователе, позволяет отправлять сообщения конкретному пользователю,
всем в комнате (broadcast), а также отслеживает статус "печатает" и список онлайн.

Менеджер потокобезопасен: использует asyncio.Lock для защиты внутренних структур данных
от конкурентного доступа (например, при одновременном подключении/отключении).

Также менеджер автоматически удаляет "мертвые" соединения при попытке отправки,
чтобы избежать накопления нерабочих сокетов.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class ConnectedUser:
    """
    Хранит информацию о подключённом пользователе в комнате.

    Атрибуты:
        user_id: int — уникальный идентификатор пользователя.
        username: str — логин пользователя.
        display_name: str — отображаемое имя (может совпадать с username).
        avatar_emoji: str — эмодзи аватара.
        websocket: WebSocket — объект соединения FastAPI.
        room_id: int — идентификатор комнаты.
        connected_at: datetime — время подключения (UTC).
        is_typing: bool — флаг, указывающий, печатает ли пользователь в данный момент.
    """
    user_id: int
    username: str
    display_name: str
    avatar_emoji: str
    websocket: WebSocket
    room_id: int
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_typing: bool = False


class ConnectionManager:
    """
    Менеджер WebSocket-соединений с поддержкой комнат.

    Внутренняя структура: _rooms[room_id][user_id] = ConnectedUser.
    Все операции, изменяющие _rooms, защищены блокировкой _lock.
    """

    def __init__(self):
        # Используем defaultdict(dict) для автоматического создания вложенного словаря
        self._rooms: dict[int, dict[int, ConnectedUser]] = defaultdict(dict)
        self._lock = asyncio.Lock()  # блокировка для потокобезопасности (asyncio)

    async def connect(
            self,
            room_id: int,
            user_id: int,
            username: str,
            display_name: str,
            avatar_emoji: str,
            ws: WebSocket,
    ) -> None:
        """
        Принимает WebSocket-соединение, регистрирует пользователя в комнате.

        - Вызывает ws.accept() для подтверждения соединения.
        - Создаёт объект ConnectedUser и сохраняет его в _rooms.
        - Логирует подключение.
        - Рассылает всем остальным участникам комнаты сообщение "user_joined",
          включая актуальный список онлайн (чтобы у них обновился счётчик).
        """
        await ws.accept()
        async with self._lock:
            self._rooms[room_id][user_id] = ConnectedUser(
                user_id=user_id,
                username=username,
                display_name=display_name,
                avatar_emoji=avatar_emoji,
                websocket=ws,
                room_id=room_id,
            )
        logger.info(f"WS+ {username}({user_id}) → room {room_id}")

        # Уведомляем остальных о новом пользователе, передаём им полный список онлайн
        await self.broadcast_to_room(
            room_id,
            {
                "type": "user_joined",
                "user_id": user_id,
                "username": username,
                "display_name": display_name,
                "avatar_emoji": avatar_emoji,
                "online_users": self.get_online_users(room_id),  # для обновления счётчика
            },
            exclude=user_id,  # не отправляем самому новому пользователю
        )

    async def disconnect(self, room_id: int, user_id: int) -> None:
        """
        Удаляет пользователя из комнаты (отключение).

        - Удаляет запись из _rooms.
        - Если комната стала пустой, удаляет и ключ комнаты.
        - Логирует отключение.
        - Рассылает остальным сообщение "user_left" с обновлённым списком онлайн.
        """
        async with self._lock:
            user = self._rooms[room_id].pop(user_id, None)
            if not self._rooms[room_id]:          # если в комнате больше никого нет
                del self._rooms[room_id]

        if user:
            logger.info(f"WS- {user.username}({user_id}) ← room {room_id}")
            await self.broadcast_to_room(
                room_id,
                {
                    "type": "user_left",
                    "user_id": user_id,
                    "username": user.username,
                    "online_users": self.get_online_users(room_id),
                },
            )

    async def broadcast_to_room(
            self,
            room_id: int,
            payload: dict[str, Any],
            exclude: int | None = None,
    ) -> None:
        """
        Отправляет сообщение всем пользователям в комнате, кроме указанного (exclude).

        - Итерируется по копии словаря, чтобы избежать ошибок при изменении во время итерации.
        - При ошибке отправки (соединение разорвано) помечает пользователя как "мёртвого"
          и затем вызывает disconnect для него.
        """
        dead = []  # список user_id, у которых не удалось отправить
        # Используем dict() для создания поверхностной копии, чтобы не блокировать долго
        for uid, conn in dict(self._rooms.get(room_id, {})).items():
            if uid == exclude:
                continue
            try:
                await conn.websocket.send_json(payload)
            except Exception:
                # Соединение, скорее всего, закрыто — запоминаем для удаления
                dead.append(uid)

        # Удаляем мёртвые соединения
        for uid in dead:
            await self.disconnect(room_id, uid)

    async def send_to_user(self, room_id: int, user_id: int, payload: dict) -> bool:
        """
        Отправляет сообщение конкретному пользователю в комнате.

        Возвращает True, если отправка успешна, иначе False (пользователь не найден или ошибка).
        При ошибке отправки вызывает disconnect для этого пользователя.
        """
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
        """
        Устанавливает флаг "печатает" для пользователя и уведомляет остальных.

        - Обновляет поле is_typing в объекте ConnectedUser.
        - Рассылает в комнату сообщение "typing" (кроме самого пользователя).
        """
        conn = self._rooms.get(room_id, {}).get(user_id)
        if not conn:
            return
        conn.is_typing = is_typing
        await self.broadcast_to_room(
            room_id,
            {
                "type": "typing",
                "user_id": user_id,
                "username": conn.username,
                "is_typing": is_typing,
            },
            exclude=user_id,
        )

    def get_online_users(self, room_id: int) -> list[dict]:
        """
        Возвращает список всех онлайн-пользователей в комнате с их данными.
        Используется для отправки при подключении нового пользователя или при обновлении статуса.
        """
        return [
            {
                "user_id": c.user_id,
                "username": c.username,
                "display_name": c.display_name,
                "avatar_emoji": c.avatar_emoji,
                "is_typing": c.is_typing,
            }
            for c in self._rooms.get(room_id, {}).values()
        ]

    def is_online(self, room_id: int, user_id: int) -> bool:
        """Проверяет, находится ли пользователь онлайн в данной комнате."""
        return user_id in self._rooms.get(room_id, {})

    def total_connections(self) -> int:
        """Возвращает общее количество активных WebSocket-соединений во всех комнатах."""
        return sum(len(v) for v in self._rooms.values())


# Глобальный экземпляр менеджера, используемый во всём приложении
manager = ConnectionManager()