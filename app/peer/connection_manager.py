"""WebSocket менеджер с разделением по комнатам."""
from __future__ import annotations
import asyncio, logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class ConnectedUser:
    user_id: int
    username: str
    display_name: str
    avatar_emoji: str
    websocket: WebSocket
    room_id: int
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_typing: bool = False


class ConnectionManager:
    def __init__(self):
        self._rooms: dict[int, dict[int, ConnectedUser]] = defaultdict(dict)
        self._lock = asyncio.Lock()

    async def connect(self, room_id: int, user_id: int, username: str,
                      display_name: str, avatar_emoji: str, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._rooms[room_id][user_id] = ConnectedUser(
                user_id=user_id, username=username,
                display_name=display_name, avatar_emoji=avatar_emoji,
                websocket=ws, room_id=room_id,
            )
        logger.info(f"WS+ {username}({user_id}) → room {room_id}")
        await self.broadcast_to_room(room_id, {
            "type": "user_joined", "user_id": user_id,
            "username": username, "display_name": display_name,
            "avatar_emoji": avatar_emoji,
        }, exclude=user_id)

    async def disconnect(self, room_id: int, user_id: int):
        async with self._lock:
            user = self._rooms[room_id].pop(user_id, None)
            if not self._rooms[room_id]:
                del self._rooms[room_id]
        if user:
            logger.info(f"WS- {user.username}({user_id}) ← room {room_id}")
            await self.broadcast_to_room(room_id, {
                "type": "user_left", "user_id": user_id, "username": user.username,
            })

    async def broadcast_to_room(self, room_id: int, payload: dict[str, Any],
                                exclude: int | None = None):
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

    async def set_typing(self, room_id: int, user_id: int, is_typing: bool):
        conn = self._rooms.get(room_id, {}).get(user_id)
        if not conn:
            return
        conn.is_typing = is_typing
        await self.broadcast_to_room(room_id, {
            "type": "typing", "user_id": user_id,
            "username": conn.username, "is_typing": is_typing,
        }, exclude=user_id)

    def get_online_users(self, room_id: int) -> list[dict]:
        return [{
            "user_id": c.user_id, "username": c.username,
            "display_name": c.display_name, "avatar_emoji": c.avatar_emoji,
            "is_typing": c.is_typing,
        } for c in self._rooms.get(room_id, {}).values()]

    def is_online(self, room_id: int, user_id: int) -> bool:
        return user_id in self._rooms.get(room_id, {})

    def total_connections(self) -> int:
        return sum(len(v) for v in self._rooms.values())


manager = ConnectionManager()