from typing import Dict, Set
from fastapi import WebSocket
import json
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for chat groups."""

    def __init__(self):
        # group_id -> set of websockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, group_id: str):
        """Accept and register a WebSocket connection for a group."""
        await websocket.accept()

        if group_id not in self.active_connections:
            self.active_connections[group_id] = set()

        self.active_connections[group_id].add(websocket)
        logger.info(f"WebSocket connected to group {group_id}. Total: {len(self.active_connections[group_id])}")

    def disconnect(self, websocket: WebSocket, group_id: str):
        """Unregister a WebSocket connection."""
        if group_id in self.active_connections:
            self.active_connections[group_id].discard(websocket)

            # Clean up empty groups
            if not self.active_connections[group_id]:
                del self.active_connections[group_id]

            logger.info(f"WebSocket disconnected from group {group_id}")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send a message to a specific WebSocket."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")

    async def broadcast_to_group(self, group_id: str, message: dict):
        """Broadcast a message to all connections in a group."""
        if group_id not in self.active_connections:
            return

        disconnected = set()

        for connection in self.active_connections[group_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to connection: {e}")
                disconnected.add(connection)

        # Remove disconnected connections
        for connection in disconnected:
            self.disconnect(connection, group_id)

    def get_group_connection_count(self, group_id: str) -> int:
        """Get the number of active connections for a group."""
        return len(self.active_connections.get(group_id, set()))


# Global connection manager instance
manager = ConnectionManager()
