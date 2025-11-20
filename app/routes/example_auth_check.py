"""
Example: How to use AuthAPIClient for permission checks

This demonstrates how to call Auth API from Chat API to verify permissions.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from app.core.oauth_validator import validate_oauth_token, OAuthToken
from app.services.auth_api_client import get_auth_api_client, AuthAPIClient
from app.core.logging_config import get_logger
from pydantic import BaseModel

router = APIRouter(prefix="/example", tags=["Examples"])
logger = get_logger(__name__)


class PermissionCheckRequest(BaseModel):
    """Request to check a specific permission."""
    permission: str  # e.g., "chat:write", "chat:read"


class PermissionCheckResponse(BaseModel):
    """Response from permission check."""
    allowed: bool
    permission: str
    groups: list[str] | None = None
    reason: str | None = None


@router.post(
    "/check-permission",
    response_model=PermissionCheckResponse,
    summary="Example: Check Permission via Auth API",
    description="""
    Example endpoint showing how to verify permissions via Auth API.

    Flow:
    1. User sends request with JWT token (Authorization: Bearer <token>)
    2. Chat API validates JWT token (local validation)
    3. Chat API calls Auth API to check if user has permission
    4. Auth API checks RBAC (groups, permissions) in database
    5. Chat API receives result and allows/denies action

    This is useful when you need to verify permissions that are managed
    in Auth API's RBAC system (groups, permissions).
    """
)
async def check_permission_example(
    request_data: PermissionCheckRequest,
    token: OAuthToken = Depends(validate_oauth_token),
    auth_client: AuthAPIClient = Depends(get_auth_api_client)
):
    """
    Example: Check if current user has a specific permission.

    This demonstrates the Auth API Client usage pattern.
    """

    logger.info(
        "example_permission_check_start",
        extra={
            "user_id": token.user_id,
            "org_id": token.org_id,
            "permission": request_data.permission
        }
    )

    # Verify user has org_id (required for permission checks)
    if not token.org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token must include org_id for permission checks"
        )

    # Call Auth API to check permission
    try:
        result = await auth_client.check_permission(
            user_id=token.user_id,
            org_id=token.org_id,
            permission=request_data.permission
        )

        logger.info(
            "example_permission_check_result",
            extra={
                "user_id": token.user_id,
                "permission": request_data.permission,
                "allowed": result["allowed"],
                "groups": result.get("groups")
            }
        )

        return PermissionCheckResponse(
            allowed=result["allowed"],
            permission=request_data.permission,
            groups=result.get("groups"),
            reason=result.get("reason")
        )

    except Exception as e:
        logger.error(
            "example_permission_check_failed",
            extra={
                "user_id": token.user_id,
                "permission": request_data.permission,
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth API unavailable"
        )


@router.post(
    "/send-message-with-auth-check",
    summary="Example: Send Message with Permission Check",
    description="""
    Example showing how to protect an endpoint with Auth API permission check.

    Before allowing the action (send message), we verify the user has 'chat:write' permission.
    """
)
async def send_message_with_auth_check(
    token: OAuthToken = Depends(validate_oauth_token),
    auth_client: AuthAPIClient = Depends(get_auth_api_client)
):
    """
    Example: Protected endpoint that checks chat:write permission.

    Pattern for protecting actions:
    1. Validate JWT token (automatic via Depends)
    2. Check permission via Auth API
    3. Allow or deny action
    """

    # Verify org_id present
    if not token.org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization context required"
        )

    # Check permission via Auth API (fail-closed: deny on errors)
    has_permission = await auth_client.check_permission_safe(
        user_id=token.user_id,
        org_id=token.org_id,
        permission="chat:write"
    )

    if not has_permission:
        logger.warning(
            "send_message_denied_no_permission",
            extra={
                "user_id": token.user_id,
                "org_id": token.org_id,
                "permission": "chat:write"
            }
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have chat:write permission"
        )

    # Permission granted - proceed with action
    logger.info(
        "send_message_allowed",
        extra={
            "user_id": token.user_id,
            "org_id": token.org_id
        }
    )

    return {
        "success": True,
        "message": "Message sent successfully!",
        "user_id": token.user_id,
        "permission_checked": "chat:write"
    }


@router.get(
    "/my-permissions",
    summary="Example: List My Permissions",
    description="""
    Example showing how to check multiple permissions for the current user.
    Useful for UI to show/hide features based on permissions.
    """
)
async def get_my_permissions(
    token: OAuthToken = Depends(validate_oauth_token),
    auth_client: AuthAPIClient = Depends(get_auth_api_client)
):
    """
    Example: Check what permissions the current user has.
    """

    if not token.org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization context required"
        )

    # Check multiple permissions
    permissions_to_check = ["chat:read", "chat:write", "groups:read", "groups:write"]

    results = {}
    for permission in permissions_to_check:
        has_permission = await auth_client.check_permission_safe(
            user_id=token.user_id,
            org_id=token.org_id,
            permission=permission
        )
        results[permission] = has_permission

    logger.info(
        "user_permissions_checked",
        extra={
            "user_id": token.user_id,
            "org_id": token.org_id,
            "permissions": results
        }
    )

    return {
        "user_id": token.user_id,
        "org_id": token.org_id,
        "permissions": results
    }
