"""
app/routes/websocket.py — WebSocket эндпоинт с E2E шифрованием.

Архитектура E2E (End-to-End Encryption):
─────────────────────────────────────────
  Клиент A ──(зашифровано ключом A↔B)──► Сервер ──(зашифровано, не трогаем)──► Клиент B
                                            │
                              Сервер ТОЛЬКО ретранслирует.
                              Сервер НЕ ЗНАЕТ session_key.
                              Сервер НЕ МОЖЕТ прочитать сообщение.

Handshake (обмен ключами, протокол X25519 DH):
──────────────────────────────────────────────
  1. Клиент A подключается → сервер сохраняет запись, ждёт handshake
  2. Клиент A отправляет {"type":"hello","public_key":"<base64>"}
     (публичный ключ X25519 клиента A, сгенерированный на клиенте)
  3. Когда Клиент B подключается и тоже шлёт hello,
     сервер рассылает всем в паре публичный ключ друг друга
  4. Каждый клиент самостоятельно вычисляет session_key = DH(priv_self, pub_peer)
     Сервер этот ключ никогда не видит.
  5. Дальше клиенты шлют {"type":"message","ciphertext":"<base64>","room_id":N}
     Сервер ретранслирует ciphertext как есть — НЕ дешифруя.
"""
from __future__ import annotations
import base64
import json
import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

class PeerClient:
    """
    Представляет одного подключённого клиента.

    Атрибуты:
        client_id   — уникальный ID клиента (передаётся в URL: /ws/{client_id})
        websocket   — объект соединения FastAPI
        public_key  — X25519 публичный ключ клиента (bytes), получен в hello-фазе
        room_id     — комната, в которой находится клиент (None до входа)
        handshake_done — True после получения hello от этого клиента
    """
    def __init__(self, client_id: str, websocket: WebSocket):
        self.client_id:      str             = client_id
        self.websocket:      WebSocket       = websocket
        self.public_key:     Optional[bytes] = None
        self.room_id:        Optional[int]   = None
        self.handshake_done: bool            = False

    async def send(self, payload: dict) -> bool:
        """
        Отправляет JSON клиенту. Возвращает False если соединение закрыто.
        Отдельный метод чтобы не повторять try/except везде.
        """
        try:
            await self.websocket.send_json(payload)
            return True
        except Exception as e:
            logger.debug(f"Не удалось отправить {self.client_id}: {e}")
            return False
_clients: dict[str, PeerClient] = {}


def _clients_in_room(room_id: int) -> list[PeerClient]:
    """Возвращает список всех клиентов в заданной комнате."""
    return [c for c in _clients.values() if c.room_id == room_id]


async def _broadcast_public_keys(room_id: int):
    """
    После того как в комнате появился новый клиент с публичным ключом,
    рассылаем всем участникам комнаты список публичных ключей друг друга.

    Именно так клиенты узнают ключи своих собеседников для DH-вычисления.
    Сервер при этом НЕ вычисляет ни один session_key.
    """
    members = _clients_in_room(room_id)

    peers_info = [
        {
            "client_id":  c.client_id,
            "public_key": base64.b64encode(c.public_key).decode(),
        }
        for c in members
        if c.public_key is not None
    ]

    # Рассылаем каждому участнику
    for client in members:
        await client.send({
            "type":  "peers_keys",
            "room_id": room_id,
            "peers": peers_info,
        })


@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """
    Точка входа для WebSocket соединений.

    URL: ws://host/ws/{client_id}
    client_id — произвольная строка (можно использовать username или UUID).

    Жизненный цикл:
      1. accept()                   — принять TCP соединение
      2. hello (← клиент)          — получить публичный ключ клиента
      3. join  (← клиент)          — войти в комнату
      4. peers_keys (→ клиент)     — разослать ключи участников
      5. message (← клиент)        — получить зашифрованное сообщение
      6. message (→ все в комнате) — ретранслировать без дешифровки
      7. disconnect                 — убрать из реестра
    """
    await websocket.accept()  # подтверждаем WebSocket handshake (HTTP → WS upgrade)
    logger.info(f"WS подключился: {client_id}")

    client = PeerClient(client_id, websocket)
    _clients[client_id] = client

    await client.send({"type": "connected", "client_id": client_id})

    try:
        while True:
            raw  = await websocket.receive_text()

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await client.send({"type": "error", "message": "Неверный JSON"})
                continue

            msg_type = msg.get("type", "")

            if msg_type == "hello":
                raw_key = msg.get("public_key")
                if not raw_key:
                    await client.send({"type": "error", "message": "Нет public_key в hello"})
                    continue

                try:
                    client.public_key = base64.b64decode(raw_key)
                except Exception:
                    await client.send({"type": "error", "message": "Неверный base64 в public_key"})
                    continue

                client.handshake_done = True
                logger.info(f"Получен X25519 ключ от {client_id}")

                await client.send({"type": "hello_ack"})

                if client.room_id is not None:
                    await _broadcast_public_keys(client.room_id)

            elif msg_type == "join":
                room_id = msg.get("room_id")
                if not isinstance(room_id, int):
                    await client.send({"type": "error", "message": "room_id должен быть int"})
                    continue

                client.room_id = room_id
                logger.info(f"{client_id} вошёл в комнату {room_id}")

                for peer in _clients_in_room(room_id):
                    if peer.client_id != client_id:
                        await peer.send({
                            "type":      "user_joined",
                            "client_id": client_id,
                        })

                if client.handshake_done:
                    await _broadcast_public_keys(room_id)

                await client.send({
                    "type":    "joined",
                    "room_id": room_id,
                    "peers":   [p.client_id for p in _clients_in_room(room_id)
                                if p.client_id != client_id],  # список других участников
                })

            elif msg_type == "message":
                if not client.handshake_done:
                    await client.send({"type": "error", "message": "Сначала выполни hello"})
                    continue

                if client.room_id is None:
                    await client.send({"type": "error", "message": "Сначала выполни join"})
                    continue

                ciphertext_b64 = msg.get("ciphertext")
                if not ciphertext_b64:
                    await client.send({"type": "error", "message": "Нет ciphertext в message"})
                    continue

                target_id: Optional[str] = msg.get("to")

                relay_payload = {
                    "type":       "message",
                    "from":       client_id,
                    "ciphertext": ciphertext_b64,
                    "room_id":    client.room_id,
                }

                if target_id:
                    target = _clients.get(target_id)
                    if target and target.room_id == client.room_id:
                        await target.send(relay_payload)
                    else:
                        await client.send({"type": "error", "message": f"Клиент {target_id} не найден"})
                else:
                    for peer in _clients_in_room(client.room_id):
                        if peer.client_id != client_id:
                            await peer.send(relay_payload)

                await client.send({
                    "type":   "delivered",
                    "to":     target_id or "room",
                })

            elif msg_type == "typing":
                if client.room_id is None:
                    continue  # игнорируем без комнаты

                # Ретранслируем индикатор печати всем в комнате
                for peer in _clients_in_room(client.room_id):
                    if peer.client_id != client_id:
                        await peer.send({
                            "type":      "typing",
                            "client_id": client_id,
                            "is_typing": bool(msg.get("is_typing", False)),
                        })

            else:
                await client.send({"type": "error", "message": f"Неизвестный тип: {msg_type}"})

    except WebSocketDisconnect:
        logger.info(f"WS отключился: {client_id}")

    except Exception as e:
        logger.warning(f"WS ошибка {client_id}: {e}")

    finally:
        _clients.pop(client_id, None)

        # Уведомляем оставшихся в комнате что клиент ушёл
        if client.room_id is not None:
            for peer in _clients_in_room(client.room_id):
                await peer.send({
                    "type":      "user_left",
                    "client_id": client_id,
                })

        logger.info(f"WS очищен: {client_id}")