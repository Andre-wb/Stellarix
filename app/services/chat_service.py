"""
app/chats/chat_service.py — Простая реализация WebSocket чата с шифрованием.

Этот модуль предоставляет класс ChatService, который управляет WebSocket-соединениями,
обрабатывает входящие сообщения, шифрует их с помощью внешней библиотеки vortex_chat
и рассылает всем подключённым клиентам (кроме отправителя). Также ведёт статистику
сообщений и отправляет системные уведомления о подключении/отключении.

Используется глобальный экземпляр chat_service, который можно импортировать в других
частях приложения (например, в WebSocket эндпоинте FastAPI).
"""

from fastapi import WebSocket
import json
import vortex_chat


class ChatService:
    """
    Сервис управления чатом: хранит активные соединения, обрабатывает сообщения,
    шифрует их и рассылает участникам.
    """

    def __init__(self):
        # Словарь активных WebSocket-соединений: client_id -> WebSocket
        self.active_connections: dict[str, WebSocket] = {}

        # Объект статистики из vortex_chat (предположительно считает количество сообщений, байт и т.д.)
        self.chat_stats = vortex_chat.ChatStats()

        # Генерируем ключ шифрования для всех сообщений (в реальном проекте может быть свой ключ на комнату)
        self.encryption_key = vortex_chat.generate_key()

    async def handle_connection(self, websocket: WebSocket, client_id: str):
        """
        Основной метод для обработки нового WebSocket-подключения.

        - Принимает соединение.
        - Регистрирует клиента в active_connections.
        - Отправляет приветственное системное сообщение.
        - Уведомляет остальных о подключении нового участника.
        - Входит в цикл приёма сообщений.
        - При ошибке или отключении вызывает disconnect_client.
        """
        # Принимаем WebSocket-соединение (подтверждаем handshake)
        await websocket.accept()

        # Сохраняем сокет в словаре под идентификатором клиента
        self.active_connections[client_id] = websocket
        print(f"✅ {client_id} joined")  # Логируем подключение

        # Отправляем личное приветствие новому клиенту
        await self.send_system_message(websocket, f"👋 Hi, {client_id}!")

        # Оповещаем всех остальных клиентов, что новый пользователь присоединился
        await self.broadcast_system(f"📢 {client_id} joined", exclude=client_id)

        try:
            # Бесконечный цикл чтения сообщений от клиента
            while True:
                # Получаем текстовое сообщение (ожидается JSON)
                data = await websocket.receive_text()
                # Обрабатываем полученное сообщение
                await self.process_message(client_id, websocket, data)
        except Exception as e:
            # Любое исключение (например, закрытие соединения) приводит к выходу из цикла
            print(f"❌ {client_id} disconnected: {e}")
        finally:
            # Гарантированно удаляем клиента из активных соединений при выходе
            await self.disconnect_client(client_id)

    async def process_message(self, client_id: str, websocket: WebSocket, data: str):
        """
        Обрабатывает входящее JSON-сообщение от клиента.

        Ожидается сообщение вида {"type": "message", "text": "..."}
        - Шифрует текст с помощью ключа комнаты.
        - Вычисляет хэш зашифрованного сообщения.
        - Обновляет статистику (vortex_chat.ChatStats).
        - Рассылает зашифрованное сообщение всем остальным клиентам.
        - Отправляет отправителю подтверждение доставки (delivery).
        """
        # Парсим JSON
        message_data = json.loads(data)

        # Проверяем тип сообщения (может быть расширено для других типов)
        if message_data["type"] == "message":
            text = message_data["text"]

            # Шифруем текст с использованием ключа (vortex_chat.encrypt_message возвращает bytes)
            encrypted = vortex_chat.encrypt_message(text.encode(), self.encryption_key)

            # Вычисляем хэш зашифрованного сообщения (вероятно, для проверки целостности)
            msg_hash = vortex_chat.hash_message(encrypted)
            # Берём первые 8 символов hex-представления для краткости (можно использовать полный)
            msg_hash_hex = msg_hash.hex()

            # Обновляем статистику: добавляем сообщение с длиной исходного текста
            self.chat_stats.add_message(len(text))

            # Рассылаем зашифрованное сообщение всем остальным клиентам
            await self.broadcast_encrypted(client_id, encrypted, msg_hash_hex)

            # Отправляем отправителю подтверждение о том, что сообщение обработано
            await websocket.send_json({
                "type": "delivery",
                "status": "sent",
                "hash": msg_hash_hex[:8]  # Короткий хэш для идентификации
            })

    async def broadcast_encrypted(self, sender_id: str, encrypted: bytes, msg_hash: str):
        """
        Рассылает зашифрованное сообщение всем клиентам, кроме отправителя.

        Каждому получателю отправляется JSON с полями:
        - type: "message"
        - from: идентификатор отправителя
        - encrypted: зашифрованные данные в hex-представлении
        - hash: короткий хэш (первые 8 символов)
        - encrypted_size: размер зашифрованных данных в байтах
        """
        for conn_id, conn in self.active_connections.items():
            if conn_id != sender_id:
                try:
                    await conn.send_json({
                        "type": "message",
                        "from": sender_id,
                        "encrypted": encrypted.hex(),       # Передаём как hex-строку
                        "hash": msg_hash[:8],                # Короткий идентификатор
                        "encrypted_size": len(encrypted)     # Размер для информации
                    })
                except Exception as e:
                    # Если не удалось отправить (например, сокет закрыт), логируем ошибку
                    print(f"❌ Failed to relay to {conn_id}: {e}")

    async def broadcast_system(self, message: str, exclude: str = None):
        """
        Рассылает системное сообщение всем клиентам, кроме указанного (опционально).

        Сообщение имеет тип "system" и содержит текст в поле "message".
        """
        for conn_id, conn in self.active_connections.items():
            if conn_id != exclude:
                await self.send_system_message(conn, message)

    async def send_system_message(self, websocket: WebSocket, message: str):
        """
        Отправляет одному клиенту системное сообщение.
        """
        await websocket.send_json({
            "type": "system",
            "message": message
        })

    async def disconnect_client(self, client_id: str):
        """
        Удаляет клиента из активных соединений и оповещает остальных о его уходе.
        """
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            # Оповещаем всех оставшихся, что пользователь покинул чат
            await self.broadcast_system(f"👋 {client_id} left")


# Глобальный экземпляр сервиса, который можно импортировать и использовать в WebSocket эндпоинтах
chat_service = ChatService()