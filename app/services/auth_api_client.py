"""
Auth API Client for Chat API

Service-to-service authentication with Auth API for permission checks.
Supports API Key authentication (simple and fast for internal services).
"""

import httpx
import logging
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)


class AuthAPIClient:
    """
    Client for Auth API service-to-service communication.

    Uses API Key authentication (X-Service-Token header) for permission checks.
    Simple and fast - suitable for internal microservices.

    Example:
        auth_client = AuthAPIClient()
        has_permission = await auth_client.check_permission(
            user_id="550e8400-e29b-41d4-a716-446655440000",
            org_id="660e8400-e29b-41d4-a716-446655440000",
            permission="chat:write"
        )
    """

    def __init__(self):
        self.auth_api_url = settings.AUTH_API_URL
        self.service_token = settings.SERVICE_AUTH_TOKEN
        self.timeout = settings.AUTH_API_TIMEOUT

        logger.info(
            "auth_api_client_initialized",
            extra={
                "auth_api_url": self.auth_api_url,
                "timeout": self.timeout
            }
        )

    async def check_permission(
        self,
        user_id: str,
        org_id: str,
        permission: str
    ) -> dict:
        """
        Check if user has permission in organization.

        Args:
            user_id: User UUID string
            org_id: Organization UUID string
            permission: Permission string (e.g., "chat:write", "chat:read")

        Returns:
            dict: {
                "allowed": bool,
                "groups": list[str] | None,  # Groups that granted permission
                "reason": str | None
            }

        Raises:
            httpx.HTTPError: On network/API errors

        Example:
            result = await client.check_permission(
                user_id="550e8400-e29b-41d4-a716-446655440000",
                org_id="660e8400-e29b-41d4-a716-446655440000",
                permission="chat:write"
            )

            if result["allowed"]:
                print(f"Permission granted via groups: {result['groups']}")
            else:
                print(f"Permission denied: {result['reason']}")
        """
        endpoint = f"{self.auth_api_url}/api/v1/authorization/check"

        payload = {
            "user_id": user_id,
            "org_id": org_id,
            "permission": permission
        }

        headers = {
            "X-Service-Token": self.service_token,
            "Content-Type": "application/json"
        }

        logger.debug(
            "auth_api_permission_check",
            extra={
                "user_id": user_id,
                "org_id": org_id,
                "permission": permission,
                "endpoint": endpoint
            }
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint,
                    json=payload,
                    headers=headers
                )

                # Auth API always returns 200 OK with {"allowed": true/false}
                # Even on authorization denial (not 403!)
                response.raise_for_status()

                result = response.json()

                logger.info(
                    "auth_api_permission_result",
                    extra={
                        "user_id": user_id,
                        "permission": permission,
                        "allowed": result.get("allowed"),
                        "groups": result.get("groups"),
                        "reason": result.get("reason")
                    }
                )

                return result

        except httpx.HTTPStatusError as e:
            logger.error(
                "auth_api_http_error",
                extra={
                    "status_code": e.response.status_code,
                    "response": e.response.text,
                    "user_id": user_id,
                    "permission": permission
                }
            )
            raise

        except httpx.TimeoutException as e:
            logger.error(
                "auth_api_timeout",
                extra={
                    "timeout": self.timeout,
                    "user_id": user_id,
                    "permission": permission,
                    "error": str(e)
                }
            )
            raise

        except Exception as e:
            logger.error(
                "auth_api_unexpected_error",
                extra={
                    "user_id": user_id,
                    "permission": permission,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            raise

    async def check_permission_safe(
        self,
        user_id: str,
        org_id: str,
        permission: str
    ) -> bool:
        """
        Check permission with error handling (returns False on errors).

        Wraps check_permission() but returns False on any errors instead of raising.
        Useful for fail-closed security (deny on errors).

        Args:
            user_id: User UUID string
            org_id: Organization UUID string
            permission: Permission string

        Returns:
            bool: True if allowed, False on denial OR errors

        Example:
            # Fail-closed: deny access on errors
            if await client.check_permission_safe(user_id, org_id, "chat:write"):
                # Allow action
                pass
            else:
                # Deny (either permission denied OR error occurred)
                raise HTTPException(403, "Forbidden")
        """
        try:
            result = await self.check_permission(user_id, org_id, permission)
            return result.get("allowed", False)
        except Exception as e:
            logger.warning(
                "auth_api_check_failed_deny_access",
                extra={
                    "user_id": user_id,
                    "permission": permission,
                    "error": str(e),
                    "fail_mode": "closed"  # Deny on errors (secure)
                }
            )
            return False

    async def check_permission_in_group(
        self,
        user_id: str,
        org_id: str,
        group_id: str,
        permission: str
    ) -> bool:
        """
        Ultrathin group-specific permission check (FAST & SIMPLE).

        Checks if user has permission in SPECIFIC group only.
        Returns simple boolean - perfect for chat access control.

        Args:
            user_id: User UUID string
            org_id: Organization UUID string
            group_id: Group UUID string (specific group to check)
            permission: Permission string (e.g., "chat:read", "chat:write")

        Returns:
            bool: True if user has permission in that specific group, False otherwise
                  (including on errors - fail-closed!)

        Example:
            # Check if user can read chat in "vrienden" group
            can_read = await client.check_permission_in_group(
                user_id="550e8400-e29b-41d4-a716-446655440000",
                org_id="660e8400-e29b-41d4-a716-446655440000",
                group_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                permission="chat:read"
            )

            if can_read:
                # Allow reading messages in vrienden group
                return messages
            else:
                # Deny access to this group's messages
                raise HTTPException(403, "No access to this group")
        """
        endpoint = f"{self.auth_api_url}/api/v1/authorization/check-group"

        payload = {
            "user_id": user_id,
            "org_id": org_id,
            "group_id": group_id,
            "permission": permission
        }

        headers = {
            "X-Service-Token": self.service_token,
            "Content-Type": "application/json"
        }

        logger.debug(
            "auth_api_group_permission_check",
            extra={
                "user_id": user_id,
                "org_id": org_id,
                "group_id": group_id,
                "permission": permission,
                "endpoint": endpoint
            }
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint,
                    json=payload,
                    headers=headers
                )

                response.raise_for_status()
                result = response.json()

                allowed = result.get("allowed", False)

                logger.info(
                    "auth_api_group_permission_result",
                    extra={
                        "user_id": user_id,
                        "org_id": org_id,
                        "group_id": group_id,
                        "permission": permission,
                        "allowed": allowed
                    }
                )

                return allowed

        except Exception as e:
            logger.error(
                "auth_api_group_check_failed",
                extra={
                    "user_id": user_id,
                    "org_id": org_id,
                    "group_id": group_id,
                    "permission": permission,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "fail_mode": "closed"  # Deny on errors (secure)
                }
            )
            return False  # Fail closed!


# Singleton instance for dependency injection
_auth_api_client: Optional[AuthAPIClient] = None


def get_auth_api_client() -> AuthAPIClient:
    """
    Get singleton AuthAPIClient instance.

    Usage in FastAPI endpoints:
        from fastapi import Depends
        from app.services.auth_api_client import get_auth_api_client, AuthAPIClient

        @router.post("/messages")
        async def send_message(
            auth_client: AuthAPIClient = Depends(get_auth_api_client)
        ):
            has_permission = await auth_client.check_permission_safe(...)
    """
    global _auth_api_client

    if _auth_api_client is None:
        _auth_api_client = AuthAPIClient()

    return _auth_api_client
