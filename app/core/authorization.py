"""
RBAC Authorization System for Chat API

Architecture:
- Auth API Client: Calls central Auth API for permission checks
- Redis Cache: Caches authorization decisions with configurable TTL
- Circuit Breaker: Protects against Auth API failures
- Fail-Closed: Denies access by default if Auth API is unavailable (configurable)

Usage:
    from app.core.authorization import get_authorization_service

    auth_service = await get_authorization_service()
    await auth_service.check_permission(
        org_id="org-123",
        user_id="user-456",
        permission="chat:send_message"
    )
"""

from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import httpx
from app.config import settings
from app.core.logging_config import get_logger
from app.core.cache import cache
from app.core.exceptions import ForbiddenError

logger = get_logger(__name__)


class CircuitBreakerState(str, Enum):
    """Circuit Breaker states"""
    CLOSED = "closed"        # Normal operation, requests allowed
    OPEN = "open"            # Auth API failing, all requests blocked
    HALF_OPEN = "half_open"  # Testing if Auth API recovered


@dataclass
class AuthContext:
    """Authentication context extracted from JWT token"""
    user_id: str
    org_id: str
    username: Optional[str] = None
    email: Optional[str] = None


@dataclass
class PermissionCheckResult:
    """Result of a permission check"""
    allowed: bool
    cached: bool = False
    source: str = "auth_api"  # "auth_api", "cache", "circuit_breaker"
    cache_ttl: Optional[int] = None


class AuthorizationCache:
    """
    Redis-based cache for authorization decisions.

    Cache Key Pattern: auth:permission:{org_id}:{user_id}:{permission}

    TTL Strategy:
    - Read operations: 5 minutes (frequent, safe)
    - Write operations: 1 minute (might change data)
    - Admin operations: 30 seconds (sensitive)
    - Denied permissions: 2 minutes (prevent hammering)
    """

    def __init__(self):
        self.enabled = settings.AUTH_CACHE_ENABLED

    def _build_key(self, org_id: str, user_id: str, permission: str) -> str:
        """Build Redis cache key for permission check"""
        return f"auth:permission:{org_id}:{user_id}:{permission}"

    def _determine_ttl(self, permission: str, allowed: bool) -> int:
        """
        Determine TTL based on permission type and result.

        Strategy:
        - Denied permissions: Cache longer to prevent Auth API hammering
        - Read permissions: Cache longer (safe, frequent)
        - Write permissions: Cache shorter (data might change)
        - Admin permissions: Cache shortest (most sensitive)
        """
        if not allowed:
            return settings.AUTH_CACHE_TTL_DENIED

        # Parse permission format: "resource:action"
        if ":" in permission:
            resource, action = permission.split(":", 1)

            # Admin operations
            if action in ["delete", "manage_members", "admin"]:
                return settings.AUTH_CACHE_TTL_ADMIN

            # Write operations
            elif action in ["create", "update", "send_message"]:
                return settings.AUTH_CACHE_TTL_WRITE

            # Read operations
            elif action == "read":
                return settings.AUTH_CACHE_TTL_READ

        # Default to write TTL for unknown permissions
        return settings.AUTH_CACHE_TTL_WRITE

    async def get(
        self,
        org_id: str,
        user_id: str,
        permission: str
    ) -> Optional[bool]:
        """
        Get cached permission result.

        Returns:
            True if allowed (cached)
            False if denied (cached)
            None if not in cache
        """
        if not self.enabled:
            return None

        key = self._build_key(org_id, user_id, permission)
        value = await cache.get(key)

        if value is None:
            return None

        # Value is stored as "1" (allowed) or "0" (denied)
        result = value == "1"
        logger.debug(
            "auth_cache_hit",
            org_id=org_id,
            user_id=user_id,
            permission=permission,
            allowed=result
        )
        return result

    async def set(
        self,
        org_id: str,
        user_id: str,
        permission: str,
        allowed: bool
    ) -> bool:
        """
        Cache permission result with appropriate TTL.

        Returns:
            True if cached successfully
            False if caching failed
        """
        if not self.enabled:
            return False

        key = self._build_key(org_id, user_id, permission)
        value = "1" if allowed else "0"
        ttl = self._determine_ttl(permission, allowed)

        success = await cache.set(key, value, ttl=ttl)

        if success:
            logger.debug(
                "auth_cache_set",
                org_id=org_id,
                user_id=user_id,
                permission=permission,
                allowed=allowed,
                ttl=ttl
            )

        return success

    async def invalidate_user_cache(
        self,
        org_id: str,
        user_id: str
    ) -> bool:
        """
        Invalidate all cached permissions for a user.

        Useful when:
        - User's role changes
        - User is removed from groups
        - User's permissions are modified
        """
        pattern = f"auth:permission:{org_id}:{user_id}:*"
        success = await cache.invalidate_pattern(pattern)

        if success:
            logger.info(
                "auth_cache_invalidated",
                org_id=org_id,
                user_id=user_id
            )

        return success


class CircuitBreaker:
    """
    Circuit Breaker pattern for Auth API calls.

    States:
    - CLOSED: Normal operation, all requests go to Auth API
    - OPEN: Auth API is failing, block all requests
    - HALF_OPEN: Testing if Auth API recovered

    State Transitions:
    - CLOSED -> OPEN: After N consecutive failures
    - OPEN -> HALF_OPEN: After timeout period
    - HALF_OPEN -> CLOSED: After successful test call
    - HALF_OPEN -> OPEN: If test call fails
    """

    REDIS_KEY = "auth:circuit_breaker"

    async def _get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state from Redis"""
        data = await cache.get(self.REDIS_KEY)

        if data is None:
            return {
                "state": CircuitBreakerState.CLOSED,
                "failure_count": 0,
                "last_failure_time": None,
                "half_open_attempts": 0
            }

        return json.loads(data)

    async def _set_state(self, state_data: Dict[str, Any]) -> None:
        """Save circuit breaker state to Redis"""
        await cache.set(
            self.REDIS_KEY,
            json.dumps(state_data, default=str),
            ttl=settings.CIRCUIT_BREAKER_TIMEOUT * 2  # Keep state longer than timeout
        )

    async def should_attempt(self) -> tuple[bool, CircuitBreakerState]:
        """
        Check if we should attempt to call Auth API.

        Returns:
            (should_attempt, current_state)
        """
        state_data = await self._get_state()
        current_state = CircuitBreakerState(state_data["state"])

        if current_state == CircuitBreakerState.CLOSED:
            return True, current_state

        if current_state == CircuitBreakerState.OPEN:
            # Check if timeout has passed
            last_failure = state_data.get("last_failure_time")
            if last_failure:
                last_failure_dt = datetime.fromisoformat(last_failure)
                timeout_passed = (datetime.utcnow() - last_failure_dt).total_seconds() > settings.CIRCUIT_BREAKER_TIMEOUT

                if timeout_passed:
                    # Transition to HALF_OPEN
                    state_data["state"] = CircuitBreakerState.HALF_OPEN
                    state_data["half_open_attempts"] = 0
                    await self._set_state(state_data)
                    logger.info("circuit_breaker_half_open", reason="timeout_passed")
                    return True, CircuitBreakerState.HALF_OPEN

            return False, current_state

        if current_state == CircuitBreakerState.HALF_OPEN:
            # Allow limited attempts in HALF_OPEN state
            attempts = state_data.get("half_open_attempts", 0)
            if attempts < settings.CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS:
                state_data["half_open_attempts"] = attempts + 1
                await self._set_state(state_data)
                return True, current_state

            return False, current_state

        return False, current_state

    async def record_success(self) -> None:
        """Record successful Auth API call"""
        state_data = await self._get_state()
        current_state = CircuitBreakerState(state_data["state"])

        if current_state == CircuitBreakerState.HALF_OPEN:
            # Successful call in HALF_OPEN -> return to CLOSED
            state_data["state"] = CircuitBreakerState.CLOSED
            state_data["failure_count"] = 0
            state_data["half_open_attempts"] = 0
            await self._set_state(state_data)
            logger.info("circuit_breaker_closed", reason="half_open_success")

        elif current_state == CircuitBreakerState.CLOSED:
            # Reset failure count on success
            if state_data.get("failure_count", 0) > 0:
                state_data["failure_count"] = 0
                await self._set_state(state_data)

    async def record_failure(self) -> None:
        """Record failed Auth API call"""
        state_data = await self._get_state()
        current_state = CircuitBreakerState(state_data["state"])

        state_data["failure_count"] = state_data.get("failure_count", 0) + 1
        state_data["last_failure_time"] = datetime.utcnow().isoformat()

        if current_state == CircuitBreakerState.CLOSED:
            if state_data["failure_count"] >= settings.CIRCUIT_BREAKER_THRESHOLD:
                # Transition to OPEN
                state_data["state"] = CircuitBreakerState.OPEN
                await self._set_state(state_data)
                logger.error(
                    "circuit_breaker_opened",
                    failure_count=state_data["failure_count"],
                    threshold=settings.CIRCUIT_BREAKER_THRESHOLD
                )
                return

        elif current_state == CircuitBreakerState.HALF_OPEN:
            # Failure in HALF_OPEN -> back to OPEN
            state_data["state"] = CircuitBreakerState.OPEN
            state_data["half_open_attempts"] = 0
            await self._set_state(state_data)
            logger.warning("circuit_breaker_reopened", reason="half_open_failure")
            return

        await self._set_state(state_data)


class AuthAPIClient:
    """
    HTTP client for Auth API permission checks.

    Endpoints:
    - POST /api/v1/authorization/check

    Request:
        {
            "organization_id": "org-123",
            "user_id": "user-456",
            "permission": "chat:send_message"
        }

    Response (200 OK):
        {"allowed": true}

    Response (403 Forbidden):
        {"allowed": false, "reason": "..."}
    """

    def __init__(self):
        self.base_url = settings.AUTH_API_URL.rstrip("/")
        self.timeout = settings.AUTH_API_TIMEOUT
        self.endpoint = settings.AUTH_API_PERMISSION_CHECK_ENDPOINT
        self.circuit_breaker = CircuitBreaker()

        # Create persistent HTTP client
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={"Content-Type": "application/json"}
        )

    async def close(self):
        """Close HTTP client connection"""
        await self.client.aclose()

    async def check_permission(
        self,
        org_id: str,
        user_id: str,
        permission: str
    ) -> Optional[bool]:
        """
        Check permission with Auth API.

        Returns:
            True if allowed
            False if denied
            None if Auth API is unavailable (circuit breaker open or error)
        """
        # Check circuit breaker
        should_attempt, breaker_state = await self.circuit_breaker.should_attempt()

        if not should_attempt:
            logger.warning(
                "auth_api_blocked_by_circuit_breaker",
                state=breaker_state,
                org_id=org_id,
                user_id=user_id,
                permission=permission
            )
            return None

        # Make request with timing
        import time
        start_time = time.perf_counter()

        try:
            response = await self.client.post(
                self.endpoint,
                json={
                    "organization_id": org_id,
                    "user_id": user_id,
                    "permission": permission
                }
            )

            # Calculate latency
            latency_ms = (time.perf_counter() - start_time) * 1000

            # Success responses
            if response.status_code == 200:
                result = response.json()
                allowed = result.get("allowed", False)

                # Record success with circuit breaker
                await self.circuit_breaker.record_success()

                logger.info(
                    "auth_api_check_success",
                    org_id=org_id,
                    user_id=user_id,
                    permission=permission,
                    allowed=allowed,
                    latency_ms=round(latency_ms, 2),
                    slow_response=latency_ms > 500  # Flag slow Auth API responses
                )

                return allowed

            # Explicit denial (403)
            elif response.status_code == 403:
                result = response.json()
                reason = result.get("reason", "Permission denied")

                # This is NOT a failure - Auth API responded correctly
                await self.circuit_breaker.record_success()

                logger.info(
                    "auth_api_permission_denied",
                    org_id=org_id,
                    user_id=user_id,
                    permission=permission,
                    reason=reason,
                    latency_ms=round(latency_ms, 2)
                )

                return False

            # Unexpected status code
            else:
                logger.error(
                    "auth_api_unexpected_status",
                    status_code=response.status_code,
                    org_id=org_id,
                    user_id=user_id,
                    permission=permission,
                    latency_ms=round(latency_ms, 2)
                )
                await self.circuit_breaker.record_failure()
                return None

        except httpx.TimeoutException:
            logger.error(
                "auth_api_timeout",
                timeout=self.timeout,
                org_id=org_id,
                user_id=user_id,
                permission=permission
            )
            await self.circuit_breaker.record_failure()
            return None

        except httpx.ConnectError:
            logger.error(
                "auth_api_connection_error",
                base_url=self.base_url,
                org_id=org_id,
                user_id=user_id,
                permission=permission
            )
            await self.circuit_breaker.record_failure()
            return None

        except Exception as e:
            logger.error(
                "auth_api_unexpected_error",
                error=str(e),
                error_type=type(e).__name__,
                org_id=org_id,
                user_id=user_id,
                permission=permission,
                exc_info=True
            )
            await self.circuit_breaker.record_failure()
            return None


class AuthorizationService:
    """
    Main authorization service that orchestrates cache, Auth API, and circuit breaker.

    Flow:
    1. Check cache
    2. If cache miss, call Auth API
    3. Cache result
    4. Apply fail-open/fail-closed policy if Auth API unavailable
    """

    def __init__(self):
        self.cache = AuthorizationCache()
        self.auth_api_client = AuthAPIClient()

    async def close(self):
        """Cleanup resources"""
        await self.auth_api_client.close()

    async def check_permission(
        self,
        org_id: str,
        user_id: str,
        permission: str,
        custom_cache_ttl: Optional[int] = None
    ) -> PermissionCheckResult:
        """
        Check if user has permission.

        Args:
            org_id: Organization ID
            user_id: User ID
            permission: Permission string (e.g., "chat:send_message")
            custom_cache_ttl: Optional custom TTL override

        Returns:
            PermissionCheckResult with allowed=True/False

        Raises:
            ForbiddenError: If permission denied
            HTTPException(503): If Auth API unavailable and Fail-Closed policy
        """
        # Step 1: Check cache
        cached_result = await self.cache.get(org_id, user_id, permission)

        if cached_result is not None:
            if not cached_result:
                logger.info(
                    "permission_denied_cached",
                    org_id=org_id,
                    user_id=user_id,
                    permission=permission,
                    source="cache"
                )
                raise ForbiddenError(f"Permission denied: {permission}")

            # Log successful permission grant from cache
            logger.info(
                "permission_granted_cached",
                org_id=org_id,
                user_id=user_id,
                permission=permission,
                source="cache"
            )

            return PermissionCheckResult(
                allowed=True,
                cached=True,
                source="cache"
            )

        # Step 2: Cache miss - call Auth API
        logger.debug(
            "auth_cache_miss",
            org_id=org_id,
            user_id=user_id,
            permission=permission,
            message="Permission not in cache, calling Auth API"
        )

        auth_api_result = await self.auth_api_client.check_permission(
            org_id, user_id, permission
        )

        # Step 3: Handle Auth API response
        if auth_api_result is not None:
            # Auth API responded successfully
            allowed = auth_api_result

            # Cache the result
            await self.cache.set(org_id, user_id, permission, allowed)

            if not allowed:
                logger.info(
                    "permission_denied",
                    org_id=org_id,
                    user_id=user_id,
                    permission=permission,
                    source="auth_api"
                )
                raise ForbiddenError(f"Permission denied: {permission}")

            # Log successful permission grant from Auth API
            logger.info(
                "permission_granted",
                org_id=org_id,
                user_id=user_id,
                permission=permission,
                source="auth_api"
            )

            return PermissionCheckResult(
                allowed=True,
                cached=False,
                source="auth_api"
            )

        # Step 4: Auth API unavailable - apply fail-open/fail-closed policy
        if settings.AUTH_FAIL_OPEN:
            # Fail-Open: Allow access (DANGEROUS!)
            logger.warning(
                "auth_unavailable_fail_open",
                org_id=org_id,
                user_id=user_id,
                permission=permission,
                policy="fail_open"
            )

            return PermissionCheckResult(
                allowed=True,
                cached=False,
                source="fail_open_policy"
            )
        else:
            # Fail-Closed: Deny access (SAFE)
            logger.error(
                "auth_unavailable_fail_closed",
                org_id=org_id,
                user_id=user_id,
                permission=permission,
                policy="fail_closed"
            )

            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authorization service temporarily unavailable"
            )

    async def invalidate_user_permissions(
        self,
        org_id: str,
        user_id: str
    ) -> bool:
        """
        Invalidate all cached permissions for a user.

        Use cases:
        - User's role changed
        - User removed from group
        - Permissions updated
        """
        return await self.cache.invalidate_user_cache(org_id, user_id)


# Global singleton instance
_authorization_service: Optional[AuthorizationService] = None


async def get_authorization_service() -> AuthorizationService:
    """Get or create singleton AuthorizationService instance"""
    global _authorization_service

    if _authorization_service is None:
        _authorization_service = AuthorizationService()
        logger.info("authorization_service_initialized")

    return _authorization_service


async def close_authorization_service():
    """Close and cleanup authorization service"""
    global _authorization_service

    if _authorization_service is not None:
        await _authorization_service.close()
        _authorization_service = None
        logger.info("authorization_service_closed")
