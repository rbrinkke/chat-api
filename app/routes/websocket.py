from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from app.services.connection_manager import manager
from app.services.chat_service import ChatService
from app.middleware.auth import get_current_user
from app.core.exceptions import UnauthorizedError, ForbiddenError
from app.core.logging_config import get_logger
from jose import JWTError, jwt
from app.config import settings

router = APIRouter()
logger = get_logger(__name__)


async def verify_websocket_token(token: str) -> str:
    """Verify JWT token for WebSocket connection."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise UnauthorizedError("Invalid token")
        return user_id
    except JWTError:
        raise UnauthorizedError("Invalid token")


@router.websocket("/ws/{group_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    group_id: str,
    token: str = Query(..., description="JWT authentication token")
):
    """
    WebSocket endpoint for real-time chat in a group.

    Args:
        websocket: WebSocket connection
        group_id: ID of the group to connect to
        token: JWT token for authentication
    """
    try:
        # Authenticate user
        user_id = await verify_websocket_token(token)
        logger.info(f"WebSocket authentication successful for user {user_id}")

        # Verify user has access to the group
        chat_service = ChatService()
        await chat_service.get_group(group_id, user_id)

        # Accept connection
        await manager.connect(websocket, group_id)

        # Send welcome message
        await manager.send_personal_message(
            {
                "type": "connected",
                "message": f"Connected to group {group_id}",
                "user_id": user_id
            },
            websocket
        )

        # Broadcast user joined
        await manager.broadcast_to_group(
            group_id,
            {
                "type": "user_joined",
                "user_id": user_id,
                "connection_count": manager.get_group_connection_count(group_id)
            }
        )

        # Listen for messages
        while True:
            # Receive message from client
            data = await websocket.receive_json()

            # Handle different message types
            if data.get("type") == "ping":
                await manager.send_personal_message(
                    {"type": "pong"},
                    websocket
                )
            elif data.get("type") == "typing":
                # Broadcast typing indicator
                await manager.broadcast_to_group(
                    group_id,
                    {
                        "type": "user_typing",
                        "user_id": user_id
                    }
                )
            else:
                # Echo back for now (messages are created via REST API)
                logger.info(f"Received WebSocket message: {data}")

    except WebSocketDisconnect:
        manager.disconnect(websocket, group_id)
        logger.info(f"WebSocket disconnected from group {group_id}")

        # Broadcast user left
        await manager.broadcast_to_group(
            group_id,
            {
                "type": "user_left",
                "user_id": user_id if 'user_id' in locals() else "unknown",
                "connection_count": manager.get_group_connection_count(group_id)
            }
        )

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        except:
            pass
