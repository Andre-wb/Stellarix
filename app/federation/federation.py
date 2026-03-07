"""
app/federation/federation.py — Федеративное подключение к комнатам на других узлах.

Архитектура (всё через домашний узел — браузер не видит чужой SSL):

  Браузер → POST /api/peers/federated-join на Node A
              ↓
  Node A (server-to-server):
    1. POST /api/federation/guest-login на Node B  → remote_jwt
    2. POST /api/rooms/join/{code} на Node B       → remote_room_id
    3. Создаёт виртуальную комнату (отрицательный ID)
    4. Запускает WS-relay: Node A ↔ Node B
              ↓
  Браузер → WebSocket /ws/fed/{virtual_id} на Node A
  (обычный WS к домашнему узлу, никаких чужих сертификатов)

Виртуальные комнаты хранятся только в памяти.
ID виртуальных комнат: отрицательные числа (-1, -2, …).
Клиент определяет federated-комнату по is_federated=True или id < 0.
"""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
import time
from dataclasses import dataclass, field
from typing import Optional
import httpx
import websockets
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import Config
from app.database import get_db
from app.models import User
from app.peer.connection_manager import manager as ws_manager
from app.peer.peer_registry import registry
from app.security.auth_jwt import get_current_user

logger = logging.getLogger(__name__)

# HTTP-роутер (монтируется в main.py как /api/federation)
router = APIRouter(prefix="/api/federation", tags=["federation"])

# WS-роутер без префикса — WS не ходит через /api/
ws_router = APIRouter(tags=["federation-ws"])


# ══════════════════════════════════════════════════════════════════════════════
# Модели виртуальных комнат
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class FederatedRoomInfo:
    """In-memory запись о виртуальной комнате (alias к комнате на удалённом узле)."""
    virtual_id:      int            # отрицательный, не конфликтует с реальными room.id
    peer_ip:         str
    peer_port:       int
    remote_room_id:  int
    remote_jwt:      str            # JWT для аутентификации на удалённом узле
    room_name:       str
    invite_code:     str
    is_private:      bool
    member_count:    int
    local_user_ids:  set = field(default_factory=set)  # user.id на этом узле


def _fed_room_dict(r: FederatedRoomInfo) -> dict:
    return {
        "id":           r.virtual_id,
        "name":         r.room_name,
        "description":  f"🌐 {r.peer_ip}:{r.peer_port}",
        "is_private":   r.is_private,
        "invite_code":  r.invite_code,
        "member_count": r.member_count,
        "online_count": 0,
        "created_at":   "",
        "is_federated": True,
        "peer_ip":      r.peer_ip,
        "peer_port":    r.peer_port,
    }


# ══════════════════════════════════════════════════════════════════════════════
# FederationRelayManager
# ══════════════════════════════════════════════════════════════════════════════

class FederationRelayManager:
    """
    Управляет виртуальными комнатами и WS-relay соединениями.

    Каждая виртуальная комната:
      - FederatedRoomInfo в _rooms[virtual_id]
      - asyncio.Task (_relay_loop) — постоянное WS-соединение к удалённому узлу
      - asyncio.Queue (_outqueue) — очередь исходящих сообщений (local → remote)

    Жизненный цикл:
      join()  → создаёт запись + запускает relay
      leave() → удаляет пользователя; если комната пуста — отменяет relay
    """

    def __init__(self):
        self._rooms:    dict[int, FederatedRoomInfo] = {}
        self._tasks:    dict[int, asyncio.Task]      = {}
        self._outqueue: dict[int, asyncio.Queue]     = {}
        self._lock      = asyncio.Lock()
        self._next_id   = -1

    # ── Public API ────────────────────────────────────────────────────────────

    async def join(
            self,
            peer_ip:        str,
            peer_port:      int,
            remote_room_id: int,
            remote_jwt:     str,
            room_name:      str,
            invite_code:    str,
            is_private:     bool,
            member_count:   int,
            user_id:        int,
    ) -> FederatedRoomInfo:
        """
        Регистрирует пользователя в виртуальной комнате.
        Если комната для этого удалённого room уже существует — добавляет пользователя в неё.
        """
        async with self._lock:
            for info in self._rooms.values():
                if info.peer_ip == peer_ip and info.remote_room_id == remote_room_id:
                    info.local_user_ids.add(user_id)
                    return info

            vid = self._next_id
            self._next_id -= 1
            info = FederatedRoomInfo(
                virtual_id     = vid,
                peer_ip        = peer_ip,
                peer_port      = peer_port,
                remote_room_id = remote_room_id,
                remote_jwt     = remote_jwt,
                room_name      = room_name,
                invite_code    = invite_code,
                is_private     = is_private,
                member_count   = member_count,
                local_user_ids = {user_id},
            )
            self._rooms[vid] = info

        q = asyncio.Queue()
        self._outqueue[vid] = q
        task = asyncio.create_task(self._relay_loop(vid, q))
        self._tasks[vid] = task
        logger.info(f"🔗 Virtual room {vid} created for {peer_ip}:{peer_port}/room/{remote_room_id}")
        return info

    def is_federated_room(self, room_id: int) -> bool:
        """Возвращает True если room_id — виртуальная (федеративная) комната."""
        return room_id in self._rooms

    async def forward_to_remote(self, room_id: int, payload: dict) -> None:
        """Пробрасывает произвольный payload на удалённый узел через relay."""
        await self.send_to_remote(room_id, payload)

    async def send_to_remote(self, virtual_id: int, payload: dict) -> None:
        """Ставит сообщение в очередь для отправки на удалённый узел."""
        q = self._outqueue.get(virtual_id)
        if q:
            await q.put(payload)

    def get_user_rooms(self, user_id: int) -> list[FederatedRoomInfo]:
        return [r for r in self._rooms.values() if user_id in r.local_user_ids]

    def get_room(self, virtual_id: int) -> Optional[FederatedRoomInfo]:
        return self._rooms.get(virtual_id)

    def find_by_remote(self, peer_ip: str, remote_room_id: int) -> Optional[FederatedRoomInfo]:
        for info in self._rooms.values():
            if info.peer_ip == peer_ip and info.remote_room_id == remote_room_id:
                return info
        return None

    async def leave(self, virtual_id: int, user_id: int) -> None:
        info = self._rooms.get(virtual_id)
        if not info:
            return
        info.local_user_ids.discard(user_id)
        if not info.local_user_ids:
            task = self._tasks.pop(virtual_id, None)
            if task:
                task.cancel()
            self._outqueue.pop(virtual_id, None)
            self._rooms.pop(virtual_id, None)
            logger.info(f"🔗 Virtual room {virtual_id} closed (no users)")

    # ── Relay loop ────────────────────────────────────────────────────────────

    async def _relay_loop(self, virtual_id: int, outbound: asyncio.Queue) -> None:
        info = self._rooms.get(virtual_id)
        if not info:
            return

        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode    = ssl.CERT_NONE

        schemes    = ["wss", "ws"]
        scheme_idx = 0

        while virtual_id in self._rooms:
            scheme = schemes[scheme_idx % len(schemes)]
            uri    = f"{scheme}://{info.peer_ip}:{info.peer_port}/ws/{info.remote_room_id}?token={info.remote_jwt}"

            try:
                connect_kwargs = dict(
                    ping_interval = 20,
                    ping_timeout  = 10,
                )
                if scheme == "wss":
                    connect_kwargs["ssl"] = ssl_ctx

                async with websockets.connect(uri, **connect_kwargs) as ws:
                    logger.info(f"🔗 Relay connected {scheme}://{info.peer_ip} → room {info.remote_room_id}")
                    await asyncio.gather(
                        self._recv_loop(ws, virtual_id),
                        self._send_loop(ws, outbound),
                    )

            except asyncio.CancelledError:
                logger.info(f"🔗 Relay cancelled (virtual {virtual_id})")
                return
            except Exception as e:
                logger.warning(f"Relay {scheme}://{info.peer_ip} error: {type(e).__name__}: {e}")
                scheme_idx += 1
                if virtual_id in self._rooms:
                    await asyncio.sleep(5)

    async def _recv_loop(self, ws, virtual_id: int) -> None:
        async for raw in ws:
            try:
                data = json.loads(raw)
                data["federated"] = True
                if data.get("type") in ("room_key", "key_request", "history"):
                    data["room_id"] = virtual_id
                await ws_manager.broadcast_to_room(virtual_id, data)
            except Exception as e:
                logger.debug(f"Relay recv parse error: {e}")

    async def _send_loop(self, ws, outbound: asyncio.Queue) -> None:
        while True:
            payload = await outbound.get()
            try:
                await ws.send(json.dumps(payload))
            except Exception as e:
                logger.debug(f"Relay send error: {e}")
                await outbound.put(payload)
                raise


# Глобальный экземпляр
relay = FederationRelayManager()


# ══════════════════════════════════════════════════════════════════════════════
# Вспомогательная WS-аутентификация (cookie или query-param ?token=)
# ══════════════════════════════════════════════════════════════════════════════

async def _ws_get_user(websocket: WebSocket, db: Session) -> Optional[User]:
    """
    Получает пользователя из WebSocket-соединения.
    Поддерживает два способа передачи JWT:
      1. Cookie: access_token
      2. Query-param: ?token=... (для relay-соединений)
    """
    from app.security.auth_jwt import decode_access_token
    token = websocket.cookies.get("access_token") or websocket.query_params.get("token")
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub", 0))
        return db.query(User).filter(User.id == user_id).first()
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# WebSocket endpoint — виртуальная комната
# ══════════════════════════════════════════════════════════════════════════════

@ws_router.websocket("/ws/fed/{virtual_room_id}")
async def federated_ws(
        virtual_room_id: int,
        websocket: WebSocket,
        db: Session = Depends(get_db),
):
    user = await _ws_get_user(websocket, db)
    if not user:
        await websocket.close(code=4001)
        return

    info = relay.get_room(virtual_room_id)
    if not info or user.id not in info.local_user_ids:
        await websocket.close(code=4003)
        return

    await ws_manager.connect(
        room_id      = virtual_room_id,
        user_id      = user.id,
        username     = user.username,
        display_name = user.display_name,
        avatar_emoji = user.avatar_emoji,
        ws           = websocket,
    )

    # Пытаемся доставить ключ комнаты сразу при подключении.
    # Перебираем https/http чтобы не зависеть от конфигурации удалённого узла.
    for _scheme in ("https", "http"):
        try:
            async with httpx.AsyncClient(timeout=5.0, verify=False) as http:
                r = await http.get(
                    f"{_scheme}://{info.peer_ip}:{info.peer_port}/api/rooms/{info.remote_room_id}/key-bundle",
                    headers={"Authorization": f"Bearer {info.remote_jwt}"},
                )
                if r.status_code == 200:
                    bundle = r.json()
                    if bundle.get("has_key"):
                        await websocket.send_json({
                            "type":          "room_key",
                            "room_id":       virtual_room_id,
                            "ephemeral_pub": bundle["ephemeral_pub"],
                            "ciphertext":    bundle["ciphertext"],
                            "federated":     True,
                        })
                        logger.info(f"🔑 Key delivered to {user.username} in virtual room {virtual_room_id}")
                    break
        except Exception as e:
            logger.debug(f"Key delivery via {_scheme} failed: {e}")

    try:
        while True:
            data = await websocket.receive_json()
            await relay.send_to_remote(virtual_room_id, data)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"Fed WS error: {e}")
    finally:
        await ws_manager.disconnect(virtual_room_id, user.id)


# ══════════════════════════════════════════════════════════════════════════════
# REST API — guest-login (Node B принимает запросы от Node A)
# ══════════════════════════════════════════════════════════════════════════════

class GuestLoginRequest(BaseModel):
    username:      str
    display_name:  str
    avatar_emoji:  str = "👤"
    x25519_pubkey: str = ""
    peer_port:     int = 8000


def _is_private_ip(ip: str) -> bool:
    """Проверяет что IP из приватного диапазона (RFC 1918) или loopback."""
    return (
            ip.startswith("10.")
            or ip.startswith("192.168.")
            or ip.startswith("172.")
            or ip.startswith("127.")
            or ip == "::1"
            or ip == "localhost"
    )


@router.post("/guest-login")
async def guest_login(body: GuestLoginRequest, request: Request, db: Session = Depends(get_db)):
    """
    Принимает федеративный вход от другого узла Vortex.

    Безопасность:
      - Принимаем только запросы с приватных (LAN) IP-адресов.
      - Гостевой пользователь не может войти обычным способом (случайный пароль).
      - Для входа в комнату всё равно нужен invite-код.
    """
    src_ip = request.client.host if request.client else ""

    if not _is_private_ip(src_ip):
        logger.warning(f"guest-login rejected from public IP: {src_ip}")
        raise HTTPException(403, f"Федеративный вход разрешён только из локальной сети (получен: {src_ip})")

    from app.peer.peer_registry import registry as peer_registry
    if not peer_registry.get(src_ip):
        peer_registry.update(src_ip, src_ip, body.peer_port if hasattr(body, "peer_port") else 8000)
        logger.info(f"🔍 Auto-registered peer from guest-login: {src_ip}")

    safe_name    = body.username.replace(" ", "_")[:32]
    ip_safe      = src_ip.replace(".", "_").replace(":", "_")
    fed_username = f"fed__{safe_name}__{ip_safe}"

    user = db.query(User).filter(User.username == fed_username).first()
    if not user:
        import secrets as _secrets

        random_password = _secrets.token_hex(32)
        password_hash   = None
        hash_error      = None

        for _attempt in [
            lambda p=random_password: __import__("app.security.crypto",     fromlist=["hash_password"]).hash_password(p),
            lambda p=random_password: __import__("app.security.auth_jwt",   fromlist=["hash_password"]).hash_password(p),
            lambda p=random_password: __import__("app.authentication.auth", fromlist=["hash_password"]).hash_password(p),
            lambda p=random_password: __import__("passlib.hash", fromlist=["argon2"]).argon2.hash(p),
            lambda p=random_password: __import__("passlib.context", fromlist=["CryptContext"]).CryptContext(schemes=["bcrypt"]).hash(p),
        ]:
            try:
                password_hash = _attempt()
                break
            except Exception as _e:
                hash_error = _e

        if password_hash is None:
            logger.error(f"guest-login: не удалось хешировать пароль: {hash_error}")
            raise HTTPException(500, f"Ошибка хеширования пароля: {hash_error}")

        try:
            import secrets as _s2
            fed_phone = f"fed_{_s2.token_hex(8)}"

            user_kwargs = dict(
                username          = fed_username,
                display_name      = body.display_name[:64],
                avatar_emoji      = body.avatar_emoji or "👤",
                password_hash     = password_hash,
                x25519_public_key = body.x25519_pubkey[:64] if body.x25519_pubkey else "",
            )
            import inspect as _inspect
            _user_cols = [c.key for c in User.__table__.columns]
            if "phone" in _user_cols:
                user_kwargs["phone"] = fed_phone

            user = User(**user_kwargs)
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info(f"👤 Federated user created: {fed_username} (from {src_ip})")
        except Exception as _e:
            db.rollback()
            logger.error(f"guest-login: DB error for {fed_username}: {_e}", exc_info=True)
            raise HTTPException(500, f"Ошибка БД: {_e}")
    else:
        user.display_name = body.display_name[:64]
        user.avatar_emoji = body.avatar_emoji or "👤"
        if body.x25519_pubkey:
            user.x25519_public_key = body.x25519_pubkey[:64]
        try:
            db.commit()
        except Exception as _e:
            db.rollback()
            logger.error(f"guest-login: DB update error: {_e}", exc_info=True)
            raise HTTPException(500, f"Ошибка БД: {_e}")

    try:
        from app.security.auth_jwt import create_access_token
        token = create_access_token(user.id, getattr(user, 'phone', ''), user.username)
    except Exception as _e:
        logger.error(f"guest-login: JWT error: {_e}", exc_info=True)
        raise HTTPException(500, f"Ошибка JWT: {_e}")

    return {
        "access_token": token,
        "user_id":      user.id,
        "fed_username": fed_username,
    }


# ══════════════════════════════════════════════════════════════════════════════
# REST API — список федеративных комнат
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/my-rooms")
async def my_federated_rooms(u: User = Depends(get_current_user)):
    """Возвращает виртуальные (федеративные) комнаты текущего пользователя."""
    rooms = relay.get_user_rooms(u.id)
    return {"rooms": [_fed_room_dict(r) for r in rooms]}


# ══════════════════════════════════════════════════════════════════════════════
# REST API — выход из федеративной комнаты
# ══════════════════════════════════════════════════════════════════════════════

@router.delete("/leave/{virtual_id}")
async def leave_federated_room(virtual_id: int, u: User = Depends(get_current_user)):
    """Покидает виртуальную федеративную комнату и закрывает relay (если пусто)."""
    await relay.leave(virtual_id, u.id)
    return {"left": True}