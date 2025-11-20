"""
Dependency injection for FastAPI routes.

Provides reusable dependencies that can be easily mocked in tests.
"""

from typing import Callable
from fastapi import Depends
from app.services.chat_service import ChatService
from app.middleware.auth import get_auth_context
from app.core.authorization import (
    get_authorization_service,
    AuthorizationService,
    AuthContext
)
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def get_chat_service() -> ChatService:
    """
    Provide ChatService instance for dependency injection.

    This allows routes to receive the service via FastAPI's Depends(),
    making it easy to mock in tests:

    Example test setup:
        app.dependency_overrides[get_chat_service] = lambda: MockChatService()
    """
    return ChatService()


# ==================== RBAC AUTHORIZATION DEPENDENCIES ====================


def require_permission(permission: str, custom_cache_ttl: int = None):
    """
    FastAPI dependency factory for permission checks.

    Usage in routes:
        @router.post("/conversations/{conversation_id}/messages")
        async def create_message(
            conversation_id: str,
            auth_context: AuthContext = Depends(require_permission("chat:send_message"))
        ):
            # If this code runs, user has permission
            # auth_context contains user_id and org_id
            ...

        # With custom cache TTL:
        @router.post("/critical-operation")
        async def critical_op(
            auth_context: AuthContext = Depends(
                require_permission("admin:critical", custom_cache_ttl=10)
            )
        ):
            # Cache for only 10 seconds due to sensitivity
            ...

    Args:
        permission: Permission string (e.g., "chat:send_message")
        custom_cache_ttl: Optional custom cache TTL in seconds (overrides default TTL logic)

    Returns:
        Dependency function that checks permission

    Raises:
        HTTPException(401): If authentication fails
        HTTPException(403): If permission denied
        HTTPException(503): If Auth API unavailable (Fail-Closed mode)
    """
    async def _check_permission(
        auth_context: AuthContext = Depends(get_auth_context),
        auth_service: AuthorizationService = Depends(get_authorization_service)
    ) -> AuthContext:
        """Inner function that performs the actual permission check"""

        try:
            # Check permission with Auth API (or cache)
            result = await auth_service.check_permission(
                org_id=auth_context.org_id,
                user_id=auth_context.user_id,
                permission=permission,
                custom_cache_ttl=custom_cache_ttl
            )

            logger.info(
                "permission_check_passed",
                user_id=auth_context.user_id,
                org_id=auth_context.org_id,
                permission=permission,
                cached=result.cached,
                source=result.source
            )

            # Return auth_context so route handlers can access user info
            return auth_context

        except Exception as e:
            # Log permission denial for audit trail
            logger.warning(
                "permission_check_failed",
                user_id=auth_context.user_id,
                org_id=auth_context.org_id,
                permission=permission,
                error=str(e),
                error_type=type(e).__name__
            )
            raise

    return _check_permission


def require_any_permission(*permissions: str):
    """
    Require ANY of the specified permissions (OR logic).

    Usage:
        @router.get("/admin")
        async def admin_endpoint(
            auth_context: AuthContext = Depends(
                require_any_permission("chat:admin", "dashboard:read_metrics")
            )
        ):
            ...

    Args:
        *permissions: Variable number of permission strings

    Returns:
        Dependency function that checks if user has ANY permission
    """
    async def _check_any_permission(
        auth_context: AuthContext = Depends(get_auth_context),
        auth_service: AuthorizationService = Depends(get_authorization_service)
    ) -> AuthContext:
        """Check if user has any of the required permissions"""

        for permission in permissions:
            try:
                await auth_service.check_permission(
                    org_id=auth_context.org_id,
                    user_id=auth_context.user_id,
                    permission=permission
                )
                # If we get here, permission was granted
                logger.info(
                    "permission_check_passed_any",
                    user_id=auth_context.user_id,
                    org_id=auth_context.org_id,
                    granted_permission=permission,
                    required_permissions=list(permissions)
                )
                return auth_context

            except Exception:
                # Try next permission
                continue

        # None of the permissions were granted
        logger.warning(
            "permission_check_failed_all",
            user_id=auth_context.user_id,
            org_id=auth_context.org_id,
            required_permissions=list(permissions)
        )

        from app.core.exceptions import ForbiddenError
        raise ForbiddenError(
            f"Requires one of: {', '.join(permissions)}"
        )

    return _check_any_permission


def require_all_permissions(*permissions: str):
    """
    Require ALL of the specified permissions (AND logic).

    Usage:
        @router.delete("/conversations/{conversation_id}")
        async def delete_group(
            conversation_id: str,
            auth_context: AuthContext = Depends(
                require_all_permissions("chat:delete", "chat:manage_members")
            )
        ):
            ...

    Args:
        *permissions: Variable number of permission strings

    Returns:
        Dependency function that checks if user has ALL permissions
    """
    async def _check_all_permissions(
        auth_context: AuthContext = Depends(get_auth_context),
        auth_service: AuthorizationService = Depends(get_authorization_service)
    ) -> AuthContext:
        """Check if user has all required permissions"""

        for permission in permissions:
            try:
                await auth_service.check_permission(
                    org_id=auth_context.org_id,
                    user_id=auth_context.user_id,
                    permission=permission
                )
            except Exception as e:
                logger.warning(
                    "permission_check_failed_required",
                    user_id=auth_context.user_id,
                    org_id=auth_context.org_id,
                    failed_permission=permission,
                    required_permissions=list(permissions)
                )
                raise

        logger.info(
            "permission_check_passed_all",
            user_id=auth_context.user_id,
            org_id=auth_context.org_id,
            required_permissions=list(permissions)
        )

        return auth_context

    return _check_all_permissions
