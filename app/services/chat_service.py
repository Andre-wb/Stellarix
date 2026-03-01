from fastapi import WebSocket
import json
import vortex_chat


class ChatService:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}
        self.chat_stats = vortex_chat.ChatStats()
        self.encryption_key = vortex_chat.generate_key()

    async def handle_connection(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        print(f"✅ {client_id} joined")

        await self.send_system_message(websocket, f"👋 Hi, {client_id}!")
        await self.broadcast_system(f"📢 {client_id} joined", exclude=client_id)

        try:
            while True:
                data = await websocket.receive_text()
                await self.process_message(client_id, websocket, data)
        except Exception as e:
            print(f"❌ {client_id} disconnected: {e}")
        finally:
            await self.disconnect_client(client_id)

    async def process_message(self, client_id: str, websocket: WebSocket, data: str):
        message_data = json.loads(data)

        if message_data["type"] == "message":
            text = message_data["text"]

            encrypted = vortex_chat.encrypt_message(text.encode(), self.encryption_key)
            msg_hash = vortex_chat.hash_message(encrypted)
            msg_hash_hex = msg_hash.hex()
            self.chat_stats.add_message(len(text))
            await self.broadcast_encrypted(client_id, encrypted, msg_hash_hex)

            await websocket.send_json({
                "type": "delivery",
                "status": "sent",
                "hash": msg_hash_hex[:8]
            })

    async def broadcast_encrypted(self, sender_id: str, encrypted: bytes, msg_hash: str):
        for conn_id, conn in self.active_connections.items():
            if conn_id != sender_id:
                try:
                    await conn.send_json({
                        "type": "message",
                        "from": sender_id,
                        "encrypted": encrypted.hex(),
                        "hash": msg_hash[:8],
                        "encrypted_size": len(encrypted)
                    })
                except Exception as e:
                    print(f"❌ Failed to relay to {conn_id}: {e}")

    async def broadcast_system(self, message: str, exclude: str = None):
        for conn_id, conn in self.active_connections.items():
            if conn_id != exclude:
                await self.send_system_message(conn, message)

    async def send_system_message(self, websocket: WebSocket, message: str):
        await websocket.send_json({
            "type": "system",
            "message": message
        })

    async def disconnect_client(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            await self.broadcast_system(f"👋 {client_id} left")


chat_service = ChatService()