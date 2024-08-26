from typing import List, Dict

from fastapi import WebSocket


class WebSocketManager:
    def __init__(self):
        """
        Example of active_connections structure

        {
            chat_room_id_1: [user_id_1_websocket_1, user_id_1_websocket_2],
            chat_room_id_2: [user_id_2_websocket_1, user_id_2_websocket_1]
        }
        """
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, chat_room_id: int):
        await websocket.accept()

        if chat_room_id not in self.active_connections:
            self.active_connections[chat_room_id] = []
        self.active_connections[chat_room_id].append(websocket)

    def disconnect(self, chat_room_id: int):
        self.active_connections.pop(chat_room_id)

    async def send_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast(self, message: dict, chat_room_id: id):
        for connection in self.active_connections[chat_room_id]:
            await connection.send_json(message)
