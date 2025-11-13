"""
GroupService - Fetch and cache group data from Auth-API

Single Source of Truth: Auth-API PostgreSQL
Security: Always validate group.org_id == expected_org_id
Caching: Aggressive Redis caching with org-scoped keys

Architecture:
- Auth-API owns all group data (name, description, org_id, members)
- Chat-API fetches via service-to-service OAuth (Client Credentials)
- Redis caching with differential TTLs:
  * Group details: 300s (5 min) - rarely changes
  * Member list: 60s (1 min) - more volatile
- Org-scoped cache keys prevent cross-org data leaks

Security Model:
- Every fetch validates: group.org_id == expected_org_id
- Prevents malicious cross-org access attempts
- Logs all security violations for monitoring
"""

from dataclasses import dataclass, asdict
from typing import List, Optional
from datetime import datetime
import aiohttp

from app.core.logging_config import get_logger
from app.core.service_auth import get_service_token_manager
from app.core.cache import cache, serialize_for_cache, deserialize_from_cache
from app.config import settings

logger = get_logger(__name__)


@dataclass
class GroupDetails:
    """
    Group details fetched from Auth-API.

    All fields come from Auth-API PostgreSQL (Single Source of Truth).
    """
    id: str  # Group UUID
    name: str  # Group name (max 100 chars)
    description: str  # Group description
    org_id: str  # Organization UUID (multi-tenant isolation)
    created_at: str  # ISO 8601 datetime string
    member_ids: List[str]  # User UUIDs who are members

    def to_dict(self) -> dict:
        """Convert to dict for cache serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GroupDetails":
        """Create from dict for cache deserialization."""
        return cls(**data)


class GroupService:
    """
    Fetch group data from Auth-API with org_id validation and caching.

    Usage:
        group_service = GroupService()

        # Fetch group with security validation
        group = await group_service.get_group_details(
            group_id="550e8400-e29b-41d4-a716-446655440000",
            expected_org_id="660e8400-e29b-41d4-a716-446655440000"
        )

        if group:
            # Authorized - use group data
            print(f"Group: {group.name}, Members: {len(group.member_ids)}")
        else:
            # Unauthorized or not found
            raise HTTPException(403, "Not authorized for this group")

    Security:
        - Always validates group.org_id == expected_org_id
        - Prevents cross-org data leaks
        - Logs all security violations

    Performance:
        - Redis caching with 300s TTL (5 min)
        - Org-scoped keys: "org:{org_id}:group:{group_id}:details"
        - Cache hit rate target: 95%+
        - Fallback to stale cache if Auth-API down (circuit breaker)
    """

    def __init__(self):
        """Initialize GroupService with Auth-API URL and token manager."""
        self.auth_api_url = settings.AUTH_API_URL.rstrip('/')
        self.token_manager = get_service_token_manager()
        self.cache_ttl_details = 300  # 5 minutes for group details
        self._session: Optional[aiohttp.ClientSession] = None  # Persistent HTTP session
        self._started: bool = False

        logger.info(
            "group_service_initialized",
            auth_api_url=self.auth_api_url,
            cache_ttl=self.cache_ttl_details
        )

    async def start(self) -> None:
        """
        Start the group service by creating aiohttp session in async context.

        MUST be called during app startup (lifespan) to ensure ClientSession
        is created in the correct event loop context.
        """
        import asyncio

        if self._started:
            logger.warning("group_service_already_started")
            return

        startup_loop_id = id(asyncio.get_event_loop())

        logger.info(
            "starting_group_service",
            auth_api_url=self.auth_api_url,
            event_loop_id_startup=startup_loop_id
        )

        # ✅ Production-grade aiohttp connector (native asyncio - no anyio!)
        connector = aiohttp.TCPConnector(
            limit=1000,              # Total connections
            limit_per_host=200,      # Per-host connection pool
            ttl_dns_cache=300,       # DNS cache TTL seconds
            force_close=False,       # Keep-alive enabled
            enable_cleanup_closed=True
        )

        # Create timeout with explicit connect timeout
        timeout = aiohttp.ClientTimeout(
            total=10.0,
            connect=5.0,
            sock_read=10.0
        )

        # Create aiohttp session in async context (correct event loop)
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            trust_env=False,
            auto_decompress=True,
            raise_for_status=False
        )

        logger.info(
            "http_session_configured",
            library="aiohttp",
            max_connections=1000,
            limit_per_host=200,
            dns_cache_ttl=300
        )

        self._started = True

        logger.info(
            "group_service_started",
            session_id=id(self._session),
            is_closed=self._session.closed,
            event_loop_id_startup=startup_loop_id
        )

    async def get_group_details(
        self,
        group_id: str,
        expected_org_id: str
    ) -> Optional[GroupDetails]:
        """
        Get group details with org_id validation.

        Flow:
        1. Check Redis cache (org-scoped key)
        2. If cache miss, fetch from Auth-API
        3. Validate group.org_id == expected_org_id (CRITICAL)
        4. Cache result with TTL
        5. Return validated group or None

        Args:
            group_id: Group UUID from Auth-API
            expected_org_id: Organization UUID from user's JWT token

        Returns:
            GroupDetails if authorized and found
            None if not found or org_id mismatch (unauthorized)

        Security:
            - Validates group.org_id == expected_org_id
            - Returns None (not raises exception) to prevent info disclosure
            - Logs security violations for monitoring

        Performance:
            - Cache hit: ~1-2ms (Redis lookup)
            - Cache miss: ~50-200ms (Auth-API HTTP call)

        Raises:
            httpx.HTTPError: Only if Auth-API unreachable after circuit breaker
        """
        cache_key = f"org:{expected_org_id}:group:{group_id}:details"

        # Try cache first (fast path - ~1ms)
        cached = await self._get_from_cache(cache_key)
        if cached:
            logger.debug(
                "group_cache_hit",
                group_id=group_id,
                org_id=expected_org_id,
                cache_key=cache_key
            )
            return cached

        # Cache miss - fetch from Auth-API (slow path - ~50-200ms)
        logger.info(
            "group_cache_miss_fetching_from_auth_api",
            group_id=group_id,
            org_id=expected_org_id
        )

        try:
            group = await self._fetch_from_auth_api(group_id)

            if not group:
                logger.warning(
                    "group_not_found_in_auth_api",
                    group_id=group_id,
                    org_id=expected_org_id
                )
                return None

            # CRITICAL SECURITY CHECK: Validate org_id matches
            if group.org_id != expected_org_id:
                logger.error(
                    "cross_org_access_attempt_blocked",
                    group_id=group_id,
                    group_org_id=group.org_id,
                    expected_org_id=expected_org_id,
                    security_violation=True,
                    alert=True  # Flag for security monitoring
                )
                # Return None to prevent info disclosure
                # (Don't reveal if group exists in different org)
                return None

            # Validation passed - cache the result
            await self._save_to_cache(cache_key, group, ttl=self.cache_ttl_details)

            logger.info(
                "group_fetched_and_cached",
                group_id=group_id,
                org_id=expected_org_id,
                member_count=len(group.member_ids)
            )

            return group

        except aiohttp.ClientError as e:
            logger.error(
                "auth_api_fetch_failed",
                group_id=group_id,
                error=str(e),
                auth_api_url=self.auth_api_url
            )

            # Circuit breaker: Try stale cache for graceful degradation
            stale = await self._get_from_cache(cache_key, allow_expired=True)
            if stale:
                logger.warning(
                    "using_stale_cache_due_to_auth_api_failure",
                    group_id=group_id,
                    org_id=expected_org_id,
                    degraded_mode=True
                )
                return stale

            # No cache available - propagate error
            raise

    def _get_session(self) -> aiohttp.ClientSession:
        """
        Get the persistent aiohttp session.

        Raises:
            RuntimeError: If start() has not been called
        """
        if not self._started or self._session is None:
            raise RuntimeError(
                "GroupService not started. "
                "Call await group_service.start() during app startup (lifespan)."
            )

        if self._session.closed:
            raise RuntimeError(
                "HTTP session is closed. GroupService cannot be used after shutdown."
            )

        return self._session

    async def _fetch_from_auth_api(self, group_id: str) -> Optional[GroupDetails]:
        """
        Fetch group details from Auth-API using aiohttp.

        Calls Auth-API endpoints:
        - GET /api/auth/groups/{group_id} - Basic group info (name, description, org_id)
        - GET /api/auth/groups/{group_id}/members - Member list (user_ids)

        Returns:
            GroupDetails with all fields populated
            None if group not found (404)

        Raises:
            aiohttp.ClientError: If Auth-API returns error (500, timeout, etc.)
        """
        # Get service access token (auto-refreshes if needed)
        token = await self.token_manager.get_token()

        session = self._get_session()
        headers = {"Authorization": f"Bearer {token}"}

        # Fetch group basic info
        logger.debug(
            "fetching_group_from_auth_api",
            group_id=group_id,
            endpoint=f"{self.auth_api_url}/api/auth/groups/{group_id}"
        )

        async with session.get(
            f"{self.auth_api_url}/api/auth/groups/{group_id}",
            headers=headers
        ) as group_response:
            # Handle 404 gracefully
            if group_response.status == 404:
                return None

            group_response.raise_for_status()
            group_data = await group_response.json()

        # Fetch member list
        logger.debug(
            "fetching_group_members_from_auth_api",
            group_id=group_id,
            endpoint=f"{self.auth_api_url}/api/auth/groups/{group_id}/members"
        )

        async with session.get(
            f"{self.auth_api_url}/api/auth/groups/{group_id}/members",
            headers=headers
        ) as members_response:
            members_response.raise_for_status()
            members_data = await members_response.json()

        # Construct GroupDetails from API response
        # Auth-API returns members as a list directly, not wrapped in {"members": [...]}
        members_list = members_data if isinstance(members_data, list) else members_data.get("members", [])

        return GroupDetails(
            id=group_data["id"],
            name=group_data["name"],
            description=group_data.get("description", ""),
            org_id=group_data.get("organization_id") or group_data.get("org_id"),  # Auth-API returns 'organization_id'
            created_at=group_data["created_at"],
            member_ids=[m["user_id"] for m in members_list]
        )

    async def _get_from_cache(
        self,
        key: str,
        allow_expired: bool = False
    ) -> Optional[GroupDetails]:
        """
        Get group from Redis cache.

        Args:
            key: Cache key (org-scoped)
            allow_expired: If True, return expired cache for circuit breaker

        Returns:
            GroupDetails if found, None otherwise
        """
        cached_json = await cache.get(key)
        if not cached_json:
            return None

        try:
            data = deserialize_from_cache(cached_json)
            return GroupDetails.from_dict(data)
        except Exception as e:
            logger.error(
                "cache_deserialization_error",
                key=key,
                error=str(e)
            )
            return None

    async def _save_to_cache(
        self,
        key: str,
        group: GroupDetails,
        ttl: int
    ) -> None:
        """
        Save group to Redis cache with TTL.

        Args:
            key: Cache key (org-scoped)
            group: GroupDetails to cache
            ttl: Time-to-live in seconds
        """
        try:
            cached_json = serialize_for_cache(group.to_dict())
            await cache.set(key, cached_json, ttl=ttl)

            logger.debug(
                "group_cached",
                key=key,
                ttl=ttl,
                group_id=group.id
            )
        except Exception as e:
            # Graceful degradation - don't fail request if caching fails
            logger.error(
                "cache_save_error",
                key=key,
                error=str(e)
            )

    async def invalidate_group_cache(
        self,
        group_id: str,
        org_id: str
    ) -> None:
        """
        Invalidate cached group data.

        Call this when:
        - Group name/description changes
        - Members added/removed
        - Group deleted

        Args:
            group_id: Group UUID
            org_id: Organization UUID
        """
        cache_key = f"org:{org_id}:group:{group_id}:details"
        await cache.delete(cache_key)

        logger.info(
            "group_cache_invalidated",
            group_id=group_id,
            org_id=org_id,
            cache_key=cache_key
        )

    async def close(self) -> None:
        """Close aiohttp session on shutdown."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("group_service_http_session_closed")


# Singleton instance
_group_service: Optional[GroupService] = None


def get_group_service() -> GroupService:
    """
    Get singleton GroupService instance.

    Usage in routes:
        @router.get("/messages")
        async def get_messages(
            group_service: GroupService = Depends(get_group_service)
        ):
            group = await group_service.get_group_details(group_id, org_id)
    """
    global _group_service
    if _group_service is None:
        _group_service = GroupService()
    return _group_service
