"""
OAuth 2.0 FastAPI Dependencies

Clean, elegant dependencies for OAuth 2.0 Resource Server pattern.
All authorization based on JWT claims - ZERO remote calls.

Performance: <1ms per request (reads from request.state)
Security: Claims validated by OAuth2Middleware
Simplicity: Declarative permission checks in route signatures

Usage Examples:

    # Basic auth - just need user_id
    @router.get("/profile")
    async def get_profile(user_id: str = Depends(get_current_user)):
        return {"user_id": user_id}

    # Full context - user_id, org_id, permissions
    @router.get("/groups")
    async def list_groups(auth: AuthContext = Depends(get_auth_context)):
        groups = await service.get_groups(auth.org_id, auth.user_id)
        return groups

    # Permission required - declarative and elegant
    @router.post("/groups")
    async def create_group(
        data: CreateGroupRequest,
        auth: AuthContext = Depends(require_permission("groups:create"))
    ):
        # If this code runs, user has permission
        group = await service.create_group(auth.org_id, auth.user_id, data)
        return group

    # Multiple permissions - OR logic
    @router.get("/admin")
    async def admin_panel(
        auth: AuthContext = Depends(
            require_any_permission("admin:read", "admin:manage")
        )
    ):
        return {"admin": True}

    # Multiple permissions - AND logic
    @router.delete("/groups/{id}")
    async def delete_group(
        id: str,
        auth: AuthContext = Depends(
            require_all_permissions("groups:delete", "groups:admin")
        )
    ):
        await service.delete_group(id, auth.org_id)
        return {"deleted": True}

    # Role-based auth
    @router.get("/admin/users")
    async def manage_users(
        auth: AuthContext = Depends(require_role("admin"))
    ):
        return {"users": [...]}

    # Optional auth - works both ways
    @router.get("/public")
    async def public_endpoint(
        auth: Optional[AuthContext] = Depends(get_optional_auth)
    ):
        if auth:
            return {"personalized": True, "user_id": auth.user_id}
        else:
            return {"public": True}
"""

from typing import Optional
from fastapi import Request, HTTPException, status, Depends
from app.middleware.oauth2 import AuthContext
from app.core.logging_config import get_logger

logger = get_logger(__name__)


# ========================================
# Core Dependencies
# ========================================


def get_auth_context(request: Request) -> AuthContext:
    """
    Get full authentication context from validated JWT.

    This is the primary dependency for most routes.
    Provides complete user information:
    - user_id: User UUID
    - org_id: Organization UUID
    - permissions: List of granted permissions
    - roles: List of assigned roles
    - username, email: Optional metadata

    All data comes from validated JWT claims (set by OAuth2Middleware).
    Zero database lookups, zero remote calls.

    Args:
        request: FastAPI request object

    Returns:
        AuthContext with validated user claims

    Raises:
        HTTPException(401): If not authenticated

    Example:
        @router.get("/my-groups")
        async def list_my_groups(auth: AuthContext = Depends(get_auth_context)):
            groups = await service.get_user_groups(
                org_id=auth.org_id,
                user_id=auth.user_id
            )
            return groups
    """
    if not hasattr(request.state, "auth"):
        logger.error(
            "auth_context_missing",
            path=request.url.path,
            method=request.method,
            message="OAuth2Middleware did not set request.state.auth"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return request.state.auth


def get_current_user(request: Request) -> str:
    """
    Get current user ID (simplified version).

    Use when you only need user_id and don't need org_id or permissions.

    Args:
        request: FastAPI request object

    Returns:
        User ID (UUID string)

    Raises:
        HTTPException(401): If not authenticated

    Example:
        @router.get("/my-profile")
        async def get_my_profile(user_id: str = Depends(get_current_user)):
            profile = await service.get_user_profile(user_id)
            return profile
    """
    auth = get_auth_context(request)
    return auth.user_id


def get_optional_auth(request: Request) -> Optional[AuthContext]:
    """
    Get authentication context if present, otherwise None.

    Use for public endpoints that can be personalized when authenticated.

    Args:
        request: FastAPI request object

    Returns:
        AuthContext if authenticated, None otherwise

    Example:
        @router.get("/discover")
        async def discover_groups(
            auth: Optional[AuthContext] = Depends(get_optional_auth)
        ):
            if auth:
                # Personalized recommendations
                groups = await service.get_recommended_groups(auth.user_id)
            else:
                # Public discover page
                groups = await service.get_popular_groups()

            return {"groups": groups}
    """
    if hasattr(request.state, "auth"):
        return request.state.auth
    return None


# ========================================
# Permission-Based Authorization
# ========================================


def require_permission(permission: str):
    """
    Dependency factory that requires specific permission.

    Creates a dependency that validates the user has the required permission.
    Permission check is local (reads from JWT claims) - zero remote calls.

    Args:
        permission: Permission string (e.g., "groups:create")

    Returns:
        Dependency function that returns AuthContext

    Raises:
        HTTPException(403): If user lacks the permission

    Example:
        @router.post("/groups")
        async def create_group(
            data: CreateGroupRequest,
            auth: AuthContext = Depends(require_permission("groups:create"))
        ):
            # User definitely has groups:create permission
            group = await service.create_group(auth.org_id, auth.user_id, data)
            return group
    """
    def _check_permission(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        """Inner function that performs the permission check"""

        if not auth.has_permission(permission):
            logger.warning(
                "permission_denied_oauth2",
                user_id=auth.user_id,
                org_id=auth.org_id,
                required_permission=permission,
                user_permissions=auth.permissions,
                source="jwt_claims"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required",
                headers={"X-Required-Permission": permission}
            )

        logger.debug(
            "permission_granted_oauth2",
            user_id=auth.user_id,
            org_id=auth.org_id,
            permission=permission,
            source="jwt_claims"
        )

        return auth

    # Set function name for better error messages
    _check_permission.__name__ = f"require_permission({permission})"
    return _check_permission


def require_any_permission(*permissions: str):
    """
    Dependency factory that requires ANY of the specified permissions (OR logic).

    User needs at least one of the permissions to proceed.

    Args:
        *permissions: Variable number of permission strings

    Returns:
        Dependency function that returns AuthContext

    Raises:
        HTTPException(403): If user has none of the permissions

    Example:
        @router.get("/admin")
        async def admin_dashboard(
            auth: AuthContext = Depends(
                require_any_permission("admin:read", "admin:manage", "superadmin")
            )
        ):
            # User has at least one admin permission
            return {"admin": True}
    """
    def _check_permissions(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        """Check if user has any of the required permissions"""

        if auth.has_any_permission(*permissions):
            granted = [p for p in permissions if auth.has_permission(p)]
            logger.debug(
                "permission_granted_any_oauth2",
                user_id=auth.user_id,
                org_id=auth.org_id,
                granted_permissions=granted,
                required_permissions=list(permissions),
                source="jwt_claims"
            )
            return auth

        logger.warning(
            "permission_denied_any_oauth2",
            user_id=auth.user_id,
            org_id=auth.org_id,
            required_permissions=list(permissions),
            user_permissions=auth.permissions,
            source="jwt_claims"
        )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"One of these permissions required: {', '.join(permissions)}",
            headers={"X-Required-Permissions": ", ".join(permissions)}
        )

    _check_permissions.__name__ = f"require_any_permission({', '.join(permissions)})"
    return _check_permissions


def require_all_permissions(*permissions: str):
    """
    Dependency factory that requires ALL specified permissions (AND logic).

    User must have every single permission to proceed.

    Args:
        *permissions: Variable number of permission strings

    Returns:
        Dependency function that returns AuthContext

    Raises:
        HTTPException(403): If user missing any permission

    Example:
        @router.delete("/groups/{id}")
        async def delete_group(
            id: str,
            auth: AuthContext = Depends(
                require_all_permissions("groups:delete", "groups:admin")
            )
        ):
            # User has both required permissions
            await service.delete_group(id, auth.org_id)
            return {"deleted": True}
    """
    def _check_permissions(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        """Check if user has all required permissions"""

        if auth.has_all_permissions(*permissions):
            logger.debug(
                "permission_granted_all_oauth2",
                user_id=auth.user_id,
                org_id=auth.org_id,
                required_permissions=list(permissions),
                source="jwt_claims"
            )
            return auth

        missing = [p for p in permissions if not auth.has_permission(p)]
        logger.warning(
            "permission_denied_all_oauth2",
            user_id=auth.user_id,
            org_id=auth.org_id,
            required_permissions=list(permissions),
            missing_permissions=missing,
            user_permissions=auth.permissions,
            source="jwt_claims"
        )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"All of these permissions required: {', '.join(permissions)}",
            headers={
                "X-Required-Permissions": ", ".join(permissions),
                "X-Missing-Permissions": ", ".join(missing)
            }
        )

    _check_permissions.__name__ = f"require_all_permissions({', '.join(permissions)})"
    return _check_permissions


# ========================================
# Role-Based Authorization
# ========================================


def require_role(role: str):
    """
    Dependency factory that requires specific role.

    Role-based authorization (RBAC).
    Use sparingly - prefer permission-based auth for better granularity.

    Args:
        role: Role name (e.g., "admin", "member", "owner")

    Returns:
        Dependency function that returns AuthContext

    Raises:
        HTTPException(403): If user lacks the role

    Example:
        @router.get("/admin/system")
        async def system_settings(
            auth: AuthContext = Depends(require_role("admin"))
        ):
            # User has admin role
            return await service.get_system_settings()
    """
    def _check_role(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        """Check if user has the required role"""

        if auth.has_role(role):
            logger.debug(
                "role_granted_oauth2",
                user_id=auth.user_id,
                org_id=auth.org_id,
                role=role,
                user_roles=auth.roles,
                source="jwt_claims"
            )
            return auth

        logger.warning(
            "role_denied_oauth2",
            user_id=auth.user_id,
            org_id=auth.org_id,
            required_role=role,
            user_roles=auth.roles,
            source="jwt_claims"
        )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{role}' required",
            headers={"X-Required-Role": role}
        )

    _check_role.__name__ = f"require_role({role})"
    return _check_role


def require_any_role(*roles: str):
    """
    Dependency factory that requires ANY of the specified roles (OR logic).

    Args:
        *roles: Variable number of role strings

    Returns:
        Dependency function that returns AuthContext

    Example:
        @router.get("/moderation")
        async def moderation_panel(
            auth: AuthContext = Depends(
                require_any_role("admin", "moderator", "superadmin")
            )
        ):
            return {"moderation": True}
    """
    def _check_roles(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        has_role = any(auth.has_role(role) for role in roles)

        if has_role:
            return auth

        logger.warning(
            "role_denied_any_oauth2",
            user_id=auth.user_id,
            org_id=auth.org_id,
            required_roles=list(roles),
            user_roles=auth.roles
        )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"One of these roles required: {', '.join(roles)}"
        )

    return _check_roles


# ========================================
# Service Dependencies
# ========================================


def get_chat_service():
    """
    Provide ChatService instance for dependency injection.

    Allows easy mocking in tests:
        app.dependency_overrides[get_chat_service] = lambda: MockChatService()

    Example:
        @router.get("/groups")
        async def list_groups(
            auth: AuthContext = Depends(get_auth_context),
            service: ChatService = Depends(get_chat_service)
        ):
            groups = await service.get_groups(auth.org_id, auth.user_id)
            return groups
    """
    from app.services.chat_service import ChatService
    return ChatService()


# ========================================
# Backward Compatibility Adapters
# ========================================


def get_legacy_auth_context(request: Request):
    """
    DEPRECATED: Adapter for legacy code using old AuthContext structure.

    This maintains backward compatibility during migration.
    New code should use get_auth_context() directly.

    Will be removed in future version.
    """
    from app.core.authorization import AuthContext as LegacyAuthContext

    oauth2_auth = get_auth_context(request)

    # Convert OAuth2 AuthContext to legacy AuthContext
    return LegacyAuthContext(
        user_id=oauth2_auth.user_id,
        org_id=oauth2_auth.org_id,
        username=oauth2_auth.username,
        email=oauth2_auth.email
    )


# ========================================
# Exports
# ========================================

__all__ = [
    # Core
    "AuthContext",
    "get_auth_context",
    "get_current_user",
    "get_optional_auth",

    # Permission-based
    "require_permission",
    "require_any_permission",
    "require_all_permissions",

    # Role-based
    "require_role",
    "require_any_role",

    # Services
    "get_chat_service",

    # Legacy (deprecated)
    "get_legacy_auth_context",
]
