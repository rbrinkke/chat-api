"""
WebSocket endpoint for real-time chat with OAuth 2.0 validation.

Architecture:
- OAuth 2.0 HS256 token validation (shared secret with Auth-API)
- Permission validation via Auth API (chat:read required)
- Real-time message broadcasting via ConnectionManager

Security:
- JWT token validation via query parameter
- Permission check via Auth API
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from app.services.connection_manager import manager
from app.core.exceptions import NotFoundError, ForbiddenError
from app.core.logging_config import get_logger
from app.core.oauth_validator import decode_token_string, OAuthToken
from jose import JWTError
from fastapi.security import HTTPAuthorizationCredentials

router = APIRouter()
logger = get_logger(__name__)

# Import metrics collector for dashboard
try:
    from app.services.dashboard_service import metrics_collector
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False


async def verify_websocket_oauth_token(token: str) -> OAuthToken:
    """
    Verify OAuth 2.0 JWT token for WebSocket connection.
    Uses centralized decoding/validation logic from app.core.oauth_validator.

    Args:
        token: JWT token from query parameter

    Returns:
        OAuthToken with user_id, org_id, scopes

    Raises:
        JWTError: If token is invalid, expired, or wrong type
    """
    # Use the centralized function to follow DRY principle
    return decode_token_string(token)


@router.websocket("/ws/{conversation_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    conversation_id: str,
    token: str = Query(..., description="OAuth 2.0 JWT access token")
):
    """
    WebSocket endpoint for real-time chat in a group.

    Authentication: OAuth 2.0 JWT token via query parameter
    Example: ws://localhost:8001/api/chat/ws/group-uuid?token=YOUR_ACCESS_TOKEN

    Multi-Tenant Security:
    1. Validates JWT token (OAuth 2.0 HS256)
    2. Validates token has chat:read scope
    3. Validates group exists in Auth-API (via ConversationService)
    4. Validates group.org_id == token.org_id (multi-tenant isolation)
    5. Validates user is member of group

    Message Flow:
    - Client → Server: ping, typing indicators
    - Server → Client: pong, user_joined, user_left, new_message, message_updated, message_deleted

    Args:
        websocket: WebSocket connection
        conversation_id: Conversation UUID (maps to Auth-API group for RBAC)
        token: OAuth 2.0 JWT access token (from Auth-API)

    Raises:
        WebSocketDisconnect: On normal disconnection
        JWTError: On invalid/expired token
        ForbiddenError: On insufficient permissions or org_id mismatch
    """
    # Initialize for error handling
    user_id = None
    org_id = None

    try:
        # Step 1: Validate OAuth 2.0 token
        try:
            oauth_token = await verify_websocket_oauth_token(token)
            user_id = oauth_token.user_id
            org_id = oauth_token.org_id

            logger.info(
                "websocket_token_validated",
                user_id=user_id,
                org_id=org_id,
                conversation_id =conversation_id,
                scopes=oauth_token.scopes
            )
        except JWTError as e:
            logger.warning(
                "websocket_authentication_failed",
                conversation_id =conversation_id,
                error=str(e)
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Step 2: Validate OAuth scope (chat:read required)
        if not oauth_token.has_scope("chat:read"):
            logger.warning(
                "websocket_insufficient_scope",
                user_id=user_id,
                org_id=org_id,
                conversation_id =conversation_id,
                required_scope="chat:read",
                available_scopes=oauth_token.scopes
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Step 3: Verify user has permission via Auth API
        # Auth API handles:
        # - Check if user has chat:read permission for this conversation (group)
        # - Validates org_id matches
        # - Validates user is member
        try:
            from app.services.auth_api_client import get_auth_api_client
            auth_client = get_auth_api_client()

            has_permission = await auth_client.check_permission_safe(
                user_id=user_id,
                org_id=org_id,
                permission="chat:read",
                resource_id=conversation_id
            )

            if not has_permission:
                logger.warning(
                    "websocket_user_not_member",
                    conversation_id =conversation_id,
                    org_id=org_id,
                    user_id=user_id
                )
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return

        except Exception as e:
            logger.error(
                "websocket_group_validation_failed",
                conversation_id =conversation_id,
                org_id=org_id,
                user_id=user_id,
                error=str(e)
            )
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
            return

        # All validations passed - accept connection
        await manager.connect(websocket, conversation_id)
        connection_count = manager.get_group_connection_count(conversation_id)

        logger.info(
            "websocket_connected",
            conversation_id =conversation_id,
            org_id=org_id,
            user_id=user_id,
            connection_count=connection_count
        )

        # Record connection event for dashboard
        if METRICS_AVAILABLE:
            try:
                metrics_collector.record_ws_event(
                    event_type="connected",
                    conversation_id =conversation_id,
                    user_id=user_id,
                    connection_count=connection_count
                )
            except Exception as e:
                logger.warning("ws_metrics_recording_failed", error=str(e))

        # Send welcome message
        await manager.send_personal_message(
            {
                "type": "connected",
                "message": f"Connected to group {conversation_id}",
                "user_id": user_id,
                "org_id": org_id
            },
            websocket
        )

        # Broadcast user joined
        await manager.broadcast_to_group(
            conversation_id,
            {
                "type": "user_joined",
                "user_id": user_id,
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
                    conversation_id,
                    {
                        "type": "user_typing",
                        "user_id": user_id
                    }
                )
            else:
                # Echo back for now (messages are created via REST API)
                logger.debug(
                    "websocket_message_received",
                    conversation_id =conversation_id,
                    org_id=org_id,
                    user_id=user_id,
                    message_type=data.get("type", "unknown")
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket, conversation_id)
        connection_count = manager.get_group_connection_count(conversation_id)
        logger.info(
            "websocket_disconnected",
            conversation_id =conversation_id,
            org_id=org_id if org_id else "unknown",
            user_id=user_id if user_id else "unknown",
            connection_count=connection_count
        )

        # Record disconnection event for dashboard
        if METRICS_AVAILABLE:
            try:
                metrics_collector.record_ws_event(
                    event_type="disconnected",
                    conversation_id =conversation_id,
                    user_id=user_id if user_id else "unknown",
                    connection_count=connection_count
                )
            except Exception as e:
                logger.warning("ws_metrics_recording_failed", error=str(e))

        # Broadcast user left
        await manager.broadcast_to_group(
            conversation_id,
            {
                "type": "user_left",
                "user_id": user_id if user_id else "unknown",
                "connection_count": connection_count
            }
        )

    except Exception as e:
        logger.error(
            "websocket_error",
            error_type=type(e).__name__,
            error=str(e),
            conversation_id =conversation_id,
            org_id=org_id if org_id else "unknown",
            user_id=user_id if user_id else "unknown",
            exc_info=True  # Include stack trace for debugging
        )
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except:
            pass
