from typing import Dict, Optional, Set

from fastapi import WebSocket


class WebSocketConnectionManager:
    def __init__(self):
        self.group_connections: Dict[str, Set[WebSocket]] = {}
        self.connection_info: Dict[WebSocket, Dict] = {}

    async def connect(self, websocket: WebSocket, group_id: str, metadata: Optional[Dict] = None):
        await websocket.accept()

        if group_id not in self.group_connections:
            self.group_connections[group_id] = set()

        self.group_connections[group_id].add(websocket)
        self.connection_info[websocket] = {'group_id': group_id, 'metadata': metadata or {}}

    async def disconnect(self, websocket: WebSocket):
        if websocket in self.connection_info:
            group_id = self.connection_info[websocket]['group_id']
            self.group_connections[group_id].discard(websocket)

            # Clean up empty groups
            if not self.group_connections[group_id]:
                del self.group_connections[group_id]

            del self.connection_info[websocket]

    async def broadcast_to_group(self, group_id: str, data: bytes):
        if group_id not in self.group_connections:
            return

        disconnected = []
        for websocket in self.group_connections[group_id]:
            try:
                await websocket.send_bytes(data)
            except Exception:
                disconnected.append(websocket)

        # Clean up disconnected sockets
        for ws in disconnected:
            await self.disconnect(ws)

    async def broadcast_to_filtered(self, group_id: str, data: bytes, filter_func=None):
        if group_id not in self.group_connections:
            return

        disconnected = []
        for websocket in self.group_connections[group_id]:
            try:
                if filter_func is None or filter_func(self.connection_info[websocket]):
                    await websocket.send_bytes(data)
            except Exception:
                disconnected.append(websocket)

        for ws in disconnected:
            await self.disconnect(ws)

    def get_group_size(self, group_id: str) -> int:
        return len(self.group_connections.get(group_id, set()))

    def get_connection_metadata(self, websocket: WebSocket) -> Optional[Dict]:
        return self.connection_info.get(websocket, {}).get('metadata')

    def update_connection_metadata(self, websocket: WebSocket, metadata: Dict):
        if websocket in self.connection_info:
            self.connection_info[websocket]['metadata'].update(metadata)
