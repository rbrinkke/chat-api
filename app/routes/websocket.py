from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from app.services.connection_manager import manager
from app.services.chat_service import ChatService
from app.middleware.auth import get_current_user
from app.core.exceptions import UnauthorizedError, ForbiddenError
from app.core.logging_config import get_logger
from app.core.authorization import get_authorization_service, AuthContext
from jose import JWTError, jwt
from app.config import settings

router = APIRouter()
logger = get_logger(__name__)

# Import metrics collector for dashboard
try:
    from app.services.dashboard_service import metrics_collector
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False


async def verify_websocket_token(token: str) -> AuthContext:
    """
    Verify JWT token for WebSocket connection and extract auth context.

    Returns:
        AuthContext with user_id and org_id

    Raises:
        UnauthorizedError: If token is invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise UnauthorizedError("Invalid token: missing user_id")

        # Extract org_id (with backward compatibility)
        org_id: str = payload.get("org_id", "default-org")

        return AuthContext(
            user_id=user_id,
            org_id=org_id,
            username=payload.get("username"),
            email=payload.get("email")
        )
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

    Authentication: Pass JWT token as query parameter
    Example: ws://localhost:8001/api/chat/ws/group-123?token=YOUR_JWT_TOKEN

    Authorization: Requires chat:read permission

    Args:
        websocket: WebSocket connection
        group_id: ID of the group to connect to
        token: JWT token for authentication
    """
    # Initialize user_id for error handling
    user_id = None

    try:
        # Step 1: Authenticate user and extract context
        auth_context = await verify_websocket_token(token)
        user_id = auth_context.user_id
        logger.info(
            "websocket_authentication_successful",
            user_id=auth_context.user_id,
            org_id=auth_context.org_id,
            group_id=group_id
        )

        # Step 2: Check RBAC permission
        try:
            auth_service = await get_authorization_service()
            await auth_service.check_permission(
                org_id=auth_context.org_id,
                user_id=auth_context.user_id,
                permission="chat:read"  # WebSocket requires read permission
            )
        except ForbiddenError:
            logger.warning(
                "websocket_permission_denied",
                group_id=group_id,
                user_id=auth_context.user_id,
                org_id=auth_context.org_id
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        except Exception as e:
            logger.error(
                "websocket_permission_check_failed",
                group_id=group_id,
                user_id=auth_context.user_id,
                error=str(e)
            )
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
            return

        # Step 3: Verify user has access to the group (existing logic)
        chat_service = ChatService()
        await chat_service.get_group(group_id, auth_context.user_id)

        # Accept connection
        await manager.connect(websocket, group_id)
        connection_count = manager.get_group_connection_count(group_id)

        # Record connection event for dashboard
        if METRICS_AVAILABLE:
            try:
                metrics_collector.record_ws_event(
                    event_type="connected",
                    group_id=group_id,
                    user_id=auth_context.user_id,
                    connection_count=connection_count
                )
            except Exception as e:
                logger.warning("ws_metrics_recording_failed", error=str(e))

        # Send welcome message
        await manager.send_personal_message(
            {
                "type": "connected",
                "message": f"Connected to group {group_id}",
                "user_id": auth_context.user_id
            },
            websocket
        )

        # Broadcast user joined
        await manager.broadcast_to_group(
            group_id,
            {
                "type": "user_joined",
                "user_id": auth_context.user_id,
                "connection_count": connection_count
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
                        "user_id": auth_context.user_id
                    }
                )
            else:
                # Echo back for now (messages are created via REST API)
                logger.info(f"Received WebSocket message: {data}")

    except WebSocketDisconnect:
        manager.disconnect(websocket, group_id)
        connection_count = manager.get_group_connection_count(group_id)
        logger.info(f"WebSocket disconnected from group {group_id}")

        # Record disconnection event for dashboard
        if METRICS_AVAILABLE:
            try:
                metrics_collector.record_ws_event(
                    event_type="disconnected",
                    group_id=group_id,
                    user_id=user_id if 'user_id' in locals() else "unknown",
                    connection_count=connection_count
                )
            except Exception as e:
                logger.warning("ws_metrics_recording_failed", error=str(e))

        # Broadcast user left
        await manager.broadcast_to_group(
            group_id,
            {
                "type": "user_left",
                "user_id": user_id if 'user_id' in locals() else "unknown",
                "connection_count": connection_count
            }
        )

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        except:
            pass
