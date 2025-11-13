"""
WebSocket endpoint for real-time chat with OAuth 2.0 and multi-tenant org_id validation.

Architecture:
- OAuth 2.0 HS256 token validation (shared secret with Auth-API)
- GroupService validates group access and org_id
- Multi-tenant isolation via org_id validation
- Real-time message broadcasting via ConnectionManager

Security:
- JWT token validation via query parameter
- Validates user is member of group (GroupService)
- Validates group.org_id == token.org_id (multi-tenant security)
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from app.services.connection_manager import manager
from app.services.group_service import get_group_service
from app.core.exceptions import NotFoundError, ForbiddenError
from app.core.logging_config import get_logger
from app.core.oauth_validator import validate_oauth_token, OAuthToken, JWT_SECRET_KEY, JWT_ALGORITHM
from jose import JWTError, jwt
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

    Validates:
    - JWT signature (HS256 shared secret)
    - Token expiration
    - Token type (must be "access")
    - Extracts user_id, org_id, scopes

    Args:
        token: JWT token from query parameter

    Returns:
        OAuthToken with user_id, org_id, scopes

    Raises:
        JWTError: If token is invalid, expired, or wrong type
    """
    try:
        # Decode and validate JWT token (same as oauth_validator.py)
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={
                "verify_exp": True,  # Verify expiration
                "verify_iat": True,  # Verify issued_at
                "verify_signature": True,  # Verify signature
                "verify_aud": False  # Skip audience validation
            }
        )

        # Validate token type (must be "access" not "refresh")
        if payload.get("type") != "access":
            logger.warning(
                "websocket_invalid_token_type",
                token_type=payload.get("type"),
                expected="access"
            )
            raise JWTError("Invalid token type")

        # Create OAuthToken object
        oauth_token = OAuthToken.from_jwt_payload(payload)

        logger.debug(
            "websocket_token_validated",
            user_id=oauth_token.user_id,
            org_id=oauth_token.org_id,
            scopes=oauth_token.scopes
        )

        return oauth_token

    except jwt.ExpiredSignatureError:
        logger.warning("websocket_token_expired")
        raise
    except JWTError as e:
        logger.warning("websocket_token_invalid", error=str(e))
        raise


@router.websocket("/ws/{group_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    group_id: str,
    token: str = Query(..., description="OAuth 2.0 JWT access token")
):
    """
    WebSocket endpoint for real-time chat in a group.

    Authentication: OAuth 2.0 JWT token via query parameter
    Example: ws://localhost:8001/api/chat/ws/group-uuid?token=YOUR_ACCESS_TOKEN

    Multi-Tenant Security:
    1. Validates JWT token (OAuth 2.0 HS256)
    2. Validates token has chat:read scope
    3. Validates group exists in Auth-API (via GroupService)
    4. Validates group.org_id == token.org_id (multi-tenant isolation)
    5. Validates user is member of group

    Message Flow:
    - Client → Server: ping, typing indicators
    - Server → Client: pong, user_joined, user_left, new_message, message_updated, message_deleted

    Args:
        websocket: WebSocket connection
        group_id: Group UUID from Auth-API
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
                group_id=group_id,
                scopes=oauth_token.scopes
            )
        except JWTError as e:
            logger.warning(
                "websocket_authentication_failed",
                group_id=group_id,
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
                group_id=group_id,
                required_scope="chat:read",
                available_scopes=oauth_token.scopes
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Step 3: Verify user has access to group AND org_id matches
        # GroupService handles:
        # - Fetch group from Auth-API (with caching)
        # - Validate group.org_id == org_id
        # - Validate user in group.member_ids
        try:
            group_service = get_group_service()
            group = await group_service.get_group_details(
                group_id=group_id,
                expected_org_id=org_id
            )

            if not group:
                logger.warning(
                    "websocket_group_not_found_or_org_mismatch",
                    group_id=group_id,
                    org_id=org_id,
                    user_id=user_id
                )
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return

            # Verify user is member of the group
            if user_id not in group.member_ids:
                logger.warning(
                    "websocket_user_not_member",
                    group_id=group_id,
                    org_id=org_id,
                    user_id=user_id
                )
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return

        except Exception as e:
            logger.error(
                "websocket_group_validation_failed",
                group_id=group_id,
                org_id=org_id,
                user_id=user_id,
                error=str(e)
            )
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
            return

        # All validations passed - accept connection
        await manager.connect(websocket, group_id)
        connection_count = manager.get_group_connection_count(group_id)

        logger.info(
            "websocket_connected",
            group_id=group_id,
            org_id=org_id,
            user_id=user_id,
            connection_count=connection_count
        )

        # Record connection event for dashboard
        if METRICS_AVAILABLE:
            try:
                metrics_collector.record_ws_event(
                    event_type="connected",
                    group_id=group_id,
                    user_id=user_id,
                    connection_count=connection_count
                )
            except Exception as e:
                logger.warning("ws_metrics_recording_failed", error=str(e))

        # Send welcome message
        await manager.send_personal_message(
            {
                "type": "connected",
                "message": f"Connected to group {group_id}",
                "group_name": group.name,
                "user_id": user_id,
                "org_id": org_id
            },
            websocket
        )

        # Broadcast user joined
        await manager.broadcast_to_group(
            group_id,
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
                    group_id,
                    {
                        "type": "user_typing",
                        "user_id": user_id
                    }
                )
            else:
                # Echo back for now (messages are created via REST API)
                logger.debug(
                    "websocket_message_received",
                    group_id=group_id,
                    org_id=org_id,
                    user_id=user_id,
                    message_type=data.get("type", "unknown")
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket, group_id)
        connection_count = manager.get_group_connection_count(group_id)
        logger.info(
            "websocket_disconnected",
            group_id=group_id,
            org_id=org_id if org_id else "unknown",
            user_id=user_id if user_id else "unknown",
            connection_count=connection_count
        )

        # Record disconnection event for dashboard
        if METRICS_AVAILABLE:
            try:
                metrics_collector.record_ws_event(
                    event_type="disconnected",
                    group_id=group_id,
                    user_id=user_id if user_id else "unknown",
                    connection_count=connection_count
                )
            except Exception as e:
                logger.warning("ws_metrics_recording_failed", error=str(e))

        # Broadcast user left
        await manager.broadcast_to_group(
            group_id,
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
            group_id=group_id,
            org_id=org_id if org_id else "unknown",
            user_id=user_id if user_id else "unknown",
            exc_info=True  # Include stack trace for debugging
        )
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except:
            pass
