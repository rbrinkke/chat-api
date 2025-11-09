"""
Redis caching layer for performance optimization.

Provides graceful degradation: if Redis is unavailable, falls back to no caching
without crashing the application.

Usage:
    from app.core.cache import cache

    # Try to get from cache
    value = await cache.get("key")
    if value is None:
        value = await expensive_db_query()
        await cache.set("key", value, ttl=300)
"""

from typing import Optional, Any
import json
from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Try to import Redis dependencies
try:
    from redis import asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available - caching will be disabled")


class CacheBackend:
    """Abstract cache interface with graceful Redis fallback."""

    def __init__(self):
        self.redis: Optional[Any] = None
        self.enabled = False

    async def initialize(self):
        """Initialize Redis connection if available."""
        if not REDIS_AVAILABLE:
            logger.info("cache_disabled", reason="redis_not_installed")
            return

        if not settings.REDIS_URL:
            logger.info("cache_disabled", reason="no_redis_url_configured")
            return

        try:
            self.redis = await aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=2,  # Fast timeout to avoid blocking requests
                socket_connect_timeout=2
            )
            # Test connection
            await self.redis.ping()
            self.enabled = True
            logger.info("cache_enabled", redis_url=settings.REDIS_URL)
        except Exception as e:
            logger.warning("cache_initialization_failed", error=str(e))
            self.enabled = False

    async def close(self):
        """Close Redis connection."""
        if self.redis:
            try:
                await self.redis.close()
            except Exception as e:
                logger.error("cache_close_error", error=str(e))

    async def get(self, key: str) -> Optional[str]:
        """
        Get value from cache.

        Returns None if:
        - Cache is disabled
        - Key doesn't exist
        - Redis error occurs (graceful degradation)
        """
        if not self.enabled or not self.redis:
            return None

        try:
            value = await self.redis.get(key)
            if value:
                logger.debug("cache_hit", key=key)
            else:
                logger.debug("cache_miss", key=key)
            return value
        except Exception as e:
            logger.error("cache_get_error", key=key, error=str(e))
            return None  # Graceful degradation

    async def set(self, key: str, value: str, ttl: int = 300) -> bool:
        """
        Set value in cache with TTL (in seconds).

        Returns True if successful, False if cache is disabled or error occurs.
        """
        if not self.enabled or not self.redis:
            return False

        try:
            await self.redis.setex(key, ttl, value)
            logger.debug("cache_set", key=key, ttl=ttl)
            return True
        except Exception as e:
            logger.error("cache_set_error", key=key, error=str(e))
            return False  # Graceful degradation

    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        if not self.enabled or not self.redis:
            return False

        try:
            await self.redis.delete(key)
            logger.debug("cache_delete", key=key)
            return True
        except Exception as e:
            logger.error("cache_delete_error", key=key, error=str(e))
            return False

    async def invalidate_pattern(self, pattern: str) -> bool:
        """
        Delete all keys matching a pattern.

        Example: invalidate_pattern("group:*")
        """
        if not self.enabled or not self.redis:
            return False

        try:
            keys = await self.redis.keys(pattern)
            if keys:
                await self.redis.delete(*keys)
                logger.info("cache_invalidate_pattern", pattern=pattern, count=len(keys))
            return True
        except Exception as e:
            logger.error("cache_invalidate_error", pattern=pattern, error=str(e))
            return False


# Utility functions for JSON serialization
def serialize_for_cache(data: Any) -> str:
    """Serialize data to JSON string for caching."""
    return json.dumps(data, default=str)  # default=str handles datetime, ObjectId, etc.


def deserialize_from_cache(data: str) -> Any:
    """Deserialize JSON string from cache."""
    return json.loads(data)


# Global cache instance
cache = CacheBackend()
