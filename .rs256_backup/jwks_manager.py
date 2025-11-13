"""
Production-Grade JWKS (JSON Web Key Set) Manager

Handles fetching, caching, and rotation of public keys from the Authorization Server.
Implements best practices for OAuth 2.0 Resource Servers.

Architecture:
- Async key fetching with connection pooling
- Automatic background refresh (proactive key rotation support)
- Exponential backoff retry logic
- Thread-safe key storage
- Comprehensive error handling and logging
- Graceful degradation strategies

Key Benefits:
- Zero network calls during request handling (keys cached)
- Supports key rotation without downtime
- Resilient to temporary Auth API outages
- Performance: <1ms key lookup from memory
"""

import asyncio
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
import httpx
from jose import jwk
from jose.exceptions import JWKError

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class JWKSFetchError(Exception):
    """Raised when JWKS fetching fails after all retries"""
    pass


class JWKSManager:
    """
    Manages JSON Web Key Sets for JWT signature validation.

    Thread-safe, async-first design optimized for high-throughput environments.

    Lifecycle:
    1. On startup: Fetch initial keys (critical - fail fast if unavailable)
    2. Runtime: Serve keys from memory cache (sub-millisecond)
    3. Background: Refresh keys periodically (every 30 min)
    4. On KID miss: Fetch fresh keys immediately (supports key rotation)

    Example:
        manager = JWKSManager()
        await manager.initialize()  # Startup

        # During request handling (fast!)
        public_key = await manager.get_key(kid="key-123")
    """

    def __init__(self):
        self.jwks_url = settings.AUTH_API_JWKS_URL
        self.cache_ttl = settings.JWKS_CACHE_TTL
        self.refresh_interval = settings.JWKS_REFRESH_INTERVAL
        self.retry_attempts = settings.JWKS_RETRY_ATTEMPTS
        self.retry_delay = settings.JWKS_RETRY_DELAY

        # Key storage: {kid: RSAKey object}
        self._keys: Dict[str, Any] = {}
        self._keys_lock = asyncio.Lock()

        # Metadata
        self._last_fetch_time: Optional[datetime] = None
        self._last_fetch_success: bool = False
        self._refresh_task: Optional[asyncio.Task] = None

        # HTTP client (persistent connection pool)
        self._client: Optional[httpx.AsyncClient] = None

        logger.info(
            "jwks_manager_created",
            jwks_url=self.jwks_url,
            cache_ttl=self.cache_ttl,
            refresh_interval=self.refresh_interval
        )

    async def initialize(self) -> None:
        """
        Initialize JWKS manager and perform initial key fetch.

        CRITICAL: This MUST succeed on startup. If Auth API is unreachable,
        the application cannot validate tokens and should fail fast.

        Raises:
            JWKSFetchError: If initial fetch fails after all retries
        """
        logger.info("jwks_manager_initializing")

        # Create persistent HTTP client
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.AUTH_API_TIMEOUT),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )

        # Perform initial fetch (critical!)
        try:
            await self._fetch_keys_with_retry()
            logger.info(
                "jwks_manager_initialized",
                key_count=len(self._keys),
                key_ids=list(self._keys.keys())
            )
        except JWKSFetchError as e:
            logger.critical(
                "jwks_manager_initialization_failed",
                error=str(e),
                message="Cannot start without valid JWKS keys. Check AUTH_API_JWKS_URL."
            )
            await self.close()
            raise

        # Start background refresh task
        self._refresh_task = asyncio.create_task(self._background_refresh())
        logger.info("jwks_background_refresh_started", interval_seconds=self.refresh_interval)

    async def close(self) -> None:
        """Cleanup resources"""
        logger.info("jwks_manager_closing")

        # Cancel background refresh
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass

        # Close HTTP client
        if self._client:
            await self._client.aclose()
            self._client = None

        logger.info("jwks_manager_closed")

    async def get_key(self, kid: str) -> Any:
        """
        Get public key for signature validation.

        Fast path: Return key from memory cache (sub-millisecond)
        Slow path: If KID not found, fetch fresh keys and retry

        Args:
            kid: Key ID from JWT header

        Returns:
            RSA public key object (jose.jwk.Key)

        Raises:
            JWKError: If key not found after refresh
        """
        # Fast path: Key exists in cache
        if kid in self._keys:
            logger.debug("jwks_key_cache_hit", kid=kid)
            return self._keys[kid]

        logger.warning(
            "jwks_key_cache_miss",
            kid=kid,
            available_kids=list(self._keys.keys()),
            message="Key not in cache - this may indicate key rotation"
        )

        # Slow path: Refresh keys (might be key rotation)
        try:
            await self._fetch_keys_with_retry()
        except JWKSFetchError as e:
            logger.error(
                "jwks_refresh_failed_on_cache_miss",
                kid=kid,
                error=str(e)
            )
            raise JWKError(f"Key ID '{kid}' not found and refresh failed: {e}")

        # Retry lookup after refresh
        if kid in self._keys:
            logger.info("jwks_key_found_after_refresh", kid=kid)
            return self._keys[kid]

        # Still not found - invalid KID
        logger.error(
            "jwks_key_not_found",
            kid=kid,
            available_kids=list(self._keys.keys()),
            message="Key ID not found even after refresh"
        )
        raise JWKError(f"Key ID '{kid}' not found in JWKS")

    async def _fetch_keys_with_retry(self) -> None:
        """
        Fetch JWKS with exponential backoff retry logic.

        Retry Strategy:
        - Attempt 1: immediate
        - Attempt 2: wait 2s
        - Attempt 3: wait 4s
        - Attempt N: wait min(2^N, 60)s

        Raises:
            JWKSFetchError: If all retries exhausted
        """
        last_error = None

        for attempt in range(1, self.retry_attempts + 1):
            try:
                await self._fetch_keys()
                logger.info(
                    "jwks_fetch_success",
                    attempt=attempt,
                    key_count=len(self._keys)
                )
                return

            except Exception as e:
                last_error = e
                logger.warning(
                    "jwks_fetch_attempt_failed",
                    attempt=attempt,
                    max_attempts=self.retry_attempts,
                    error=str(e),
                    error_type=type(e).__name__
                )

                # Don't sleep after last attempt
                if attempt < self.retry_attempts:
                    # Exponential backoff: 2s, 4s, 8s, ...
                    delay = min(self.retry_delay * (2 ** (attempt - 1)), 60)
                    logger.debug("jwks_retry_delay", delay_seconds=delay)
                    await asyncio.sleep(delay)

        # All retries exhausted
        raise JWKSFetchError(
            f"Failed to fetch JWKS after {self.retry_attempts} attempts: {last_error}"
        )

    async def _fetch_keys(self) -> None:
        """
        Fetch and parse JWKS from Authorization Server.

        Updates internal key cache atomically.

        Raises:
            httpx.HTTPError: Network/HTTP errors
            JWKError: Invalid JWKS format
        """
        if not self._client:
            raise RuntimeError("HTTP client not initialized")

        logger.debug("jwks_fetching", url=self.jwks_url)

        # Fetch JWKS document
        response = await self._client.get(self.jwks_url)
        response.raise_for_status()

        jwks_data = response.json()

        # Validate structure
        if "keys" not in jwks_data:
            raise JWKError("Invalid JWKS: missing 'keys' field")

        if not isinstance(jwks_data["keys"], list):
            raise JWKError("Invalid JWKS: 'keys' must be an array")

        # Parse keys
        new_keys = {}
        for key_data in jwks_data["keys"]:
            try:
                kid = key_data.get("kid")
                if not kid:
                    logger.warning("jwks_key_missing_kid", key_data=key_data)
                    continue

                # Construct JWK object (validates key format)
                key_obj = jwk.construct(key_data)
                new_keys[kid] = key_obj

            except Exception as e:
                logger.error(
                    "jwks_key_parse_failed",
                    kid=key_data.get("kid"),
                    error=str(e),
                    exc_info=True
                )
                # Continue with other keys
                continue

        if not new_keys:
            raise JWKError("No valid keys found in JWKS")

        # Atomic update
        async with self._keys_lock:
            old_kids = set(self._keys.keys())
            new_kids = set(new_keys.keys())

            added_kids = new_kids - old_kids
            removed_kids = old_kids - new_kids

            self._keys = new_keys
            self._last_fetch_time = datetime.utcnow()
            self._last_fetch_success = True

        # Log key changes (important for key rotation debugging)
        if added_kids or removed_kids:
            logger.info(
                "jwks_keys_updated",
                added=list(added_kids),
                removed=list(removed_kids),
                current_keys=list(new_kids)
            )

    async def _background_refresh(self) -> None:
        """
        Background task that refreshes keys periodically.

        Implements proactive key refresh to support seamless key rotation.
        Runs until cancelled.
        """
        logger.info("jwks_background_refresh_loop_started")

        try:
            while True:
                await asyncio.sleep(self.refresh_interval)

                logger.debug("jwks_background_refresh_triggered")

                try:
                    await self._fetch_keys_with_retry()
                    logger.info(
                        "jwks_background_refresh_success",
                        key_count=len(self._keys)
                    )

                except JWKSFetchError as e:
                    # Log but don't crash - keep using cached keys
                    logger.error(
                        "jwks_background_refresh_failed",
                        error=str(e),
                        message="Continuing with cached keys"
                    )
                    self._last_fetch_success = False

        except asyncio.CancelledError:
            logger.info("jwks_background_refresh_cancelled")
            raise
        except Exception as e:
            logger.critical(
                "jwks_background_refresh_crashed",
                error=str(e),
                exc_info=True
            )
            raise

    @property
    def is_healthy(self) -> bool:
        """
        Check if JWKS manager is healthy.

        Returns:
            True if keys are cached and recently refreshed
        """
        if not self._keys:
            return False

        if not self._last_fetch_time:
            return False

        # Consider unhealthy if keys haven't refreshed in 2x the TTL
        age = (datetime.utcnow() - self._last_fetch_time).total_seconds()
        max_age = self.cache_ttl * 2

        return age < max_age

    @property
    def status(self) -> Dict[str, Any]:
        """Get manager status for health checks and monitoring"""
        return {
            "healthy": self.is_healthy,
            "key_count": len(self._keys),
            "key_ids": list(self._keys.keys()),
            "last_fetch": self._last_fetch_time.isoformat() if self._last_fetch_time else None,
            "last_fetch_success": self._last_fetch_success,
            "cache_ttl": self.cache_ttl,
            "refresh_interval": self.refresh_interval
        }


# Global singleton instance
_jwks_manager: Optional[JWKSManager] = None


async def get_jwks_manager() -> JWKSManager:
    """Get or create singleton JWKS manager"""
    global _jwks_manager

    if _jwks_manager is None:
        _jwks_manager = JWKSManager()
        await _jwks_manager.initialize()

    return _jwks_manager


async def close_jwks_manager() -> None:
    """Close and cleanup JWKS manager"""
    global _jwks_manager

    if _jwks_manager is not None:
        await _jwks_manager.close()
        _jwks_manager = None
