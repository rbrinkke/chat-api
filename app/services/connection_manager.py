from typing import Dict, Set
from fastapi import WebSocket
import json
import asyncio
from app.core.logging_config import get_logger
from app.core import metrics

logger = get_logger(__name__)


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

        # Update Prometheus metrics
        metrics.websocket_connections_total.labels(group_id=group_id).inc()
        metrics.websocket_connections_active.labels(group_id=group_id).set(
            len(self.active_connections[group_id])
        )

        logger.info(f"WebSocket connected to group {group_id}. Total: {len(self.active_connections[group_id])}")

    def disconnect(self, websocket: WebSocket, group_id: str, reason: str = "normal"):
        """Unregister a WebSocket connection."""
        if group_id in self.active_connections:
            self.active_connections[group_id].discard(websocket)

            # Update Prometheus metrics
            metrics.websocket_disconnections_total.labels(
                group_id=group_id,
                reason=reason
            ).inc()

            # Update active connections gauge
            if self.active_connections[group_id]:
                metrics.websocket_connections_active.labels(group_id=group_id).set(
                    len(self.active_connections[group_id])
                )
            else:
                # No more connections, set to 0
                metrics.websocket_connections_active.labels(group_id=group_id).set(0)

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
        """
        Broadcast a message to all connections in a group.

        Performance optimization: Uses asyncio.gather to send to all
        connections in parallel instead of sequentially. This dramatically
        improves broadcast performance with many concurrent connections.
        """
        if group_id not in self.active_connections:
            return

        connections = list(self.active_connections[group_id])

        # Create tasks for parallel execution
        async def send_to_connection(websocket: WebSocket) -> tuple[WebSocket, Exception | None]:
            """Send message to a single connection, return any error."""
            try:
                await websocket.send_json(message)
                return websocket, None
            except Exception as e:
                logger.error(f"Error broadcasting to connection: {e}")
                return websocket, e

        # Execute all sends in parallel
        results = await asyncio.gather(
            *[send_to_connection(conn) for conn in connections],
            return_exceptions=False  # We handle exceptions inside send_to_connection
        )

        # Track successful broadcast
        metrics.websocket_messages_broadcast_total.labels(group_id=group_id).inc()

        # Clean up any failed connections
        error_count = 0
        for websocket, error in results:
            if error is not None:
                error_count += 1
                self.disconnect(websocket, group_id, reason="broadcast_error")

        # Track broadcast errors
        if error_count > 0:
            metrics.websocket_broadcast_errors_total.labels(group_id=group_id).inc(error_count)

    def get_group_connection_count(self, group_id: str) -> int:
        """Get the number of active connections for a group."""
        return len(self.active_connections.get(group_id, set()))

    async def shutdown_all(self):
        """
        Gracefully shut down all WebSocket connections.

        Sends a shutdown notification to all connected clients before closing,
        allowing them to handle the disconnection gracefully.
        """
        total_connections = sum(len(conns) for conns in self.active_connections.values())

        if total_connections == 0:
            logger.info("websocket_shutdown", message="No active connections to close")
            return

        logger.info("websocket_shutdown_started", connection_count=total_connections)

        # Collect all connections from all groups
        all_connections = []
        for group_id, connections in self.active_connections.items():
            all_connections.extend(connections)

        # Send shutdown notification and close all connections in parallel
        async def close_connection(websocket: WebSocket):
            """Send shutdown message and close a connection."""
            try:
                # Send shutdown notification
                await websocket.send_json({
                    "type": "server_shutdown",
                    "message": "Server is restarting. Please reconnect in a few seconds."
                })
                # Close with "Going Away" status code
                await websocket.close(code=1001)
            except Exception as e:
                logger.debug(f"Error during websocket shutdown: {e}")

        # Execute all closures in parallel
        await asyncio.gather(
            *[close_connection(conn) for conn in all_connections],
            return_exceptions=True  # Continue even if some connections fail
        )

        # Clear all connection tracking
        self.active_connections.clear()
        logger.info("websocket_shutdown_completed", connections_closed=total_connections)


# Global connection manager instance
manager = ConnectionManager()
