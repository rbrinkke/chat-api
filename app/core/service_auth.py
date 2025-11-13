"""
Service-to-Service OAuth 2.0 Client Credentials Flow

Manages machine-to-machine authentication between Chat-API and Auth-API.

Uses aiohttp (native asyncio) for reliable HTTP communication in FastAPI context.
"""

import aiohttp
from datetime import datetime, timedelta, timezone
from typing import Optional
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class ServiceTokenManager:
    """
    Manages OAuth 2.0 Client Credentials flow for service-to-service authentication.

    Automatically handles token acquisition and refresh.
    Tokens are refreshed 5 minutes before expiry to avoid race conditions.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_url: str,
        scope: str = "groups:read"
    ):
        """
        Initialize service token manager.

        Args:
            client_id: OAuth client ID for chat-api service
            client_secret: OAuth client secret
            token_url: Auth-API token endpoint (e.g., http://auth-api:8000/oauth/token)
            scope: Requested scope (default: groups:read)
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        self.scope = scope

        self._token: Optional[str] = None
        self._expires_at: Optional[datetime] = None
        self._session: Optional[aiohttp.ClientSession] = None  # Persistent HTTP session
        self._started: bool = False

    async def start(self) -> None:
        """
        Start the token manager by creating aiohttp session in async context.

        MUST be called during app startup (lifespan) to ensure ClientSession
        is created in the correct event loop context.

        Uses aiohttp (native asyncio) for reliable HTTP communication.
        """
        import asyncio

        if self._started:
            logger.warning("service_token_manager_already_started")
            return

        startup_loop_id = id(asyncio.get_event_loop())

        logger.info(
            "starting_service_token_manager",
            token_url=self.token_url,
            client_id=self.client_id,
            event_loop_id_startup=startup_loop_id
        )

        # ✅ Production-grade aiohttp connector (native asyncio - no anyio!)
        connector = aiohttp.TCPConnector(
            limit=1000,              # Total connections (default: 100)
            limit_per_host=200,      # Per-host connection pool (default: 30)
            ttl_dns_cache=300,       # DNS cache TTL seconds (default: 10)
            force_close=False,       # Keep-alive enabled
            enable_cleanup_closed=True  # Auto-cleanup closed connections
        )

        # Create timeout with explicit connect timeout
        timeout = aiohttp.ClientTimeout(
            total=10.0,      # Total request timeout
            connect=5.0,     # Connection establishment timeout
            sock_read=10.0   # Socket read timeout
        )

        # Create aiohttp session in async context (correct event loop)
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            trust_env=False,  # Disable environment proxy settings
            auto_decompress=True,  # Handle gzip/deflate automatically
            raise_for_status=False  # We'll handle status codes manually
        )

        logger.info(
            "http_session_configured",
            library="aiohttp",
            max_connections=1000,
            limit_per_host=200,
            dns_cache_ttl=300,
            connect_timeout=5.0
        )

        self._started = True

        logger.info(
            "service_token_manager_started",
            session_id=id(self._session),
            is_closed=self._session.closed,
            event_loop_id_startup=startup_loop_id
        )

    async def get_token(self) -> str:
        """
        Get valid service access token.

        Automatically refreshes if token is expired or about to expire.
        Thread-safe for concurrent access.

        Returns:
            Valid access token

        Raises:
            httpx.HTTPError: If token acquisition fails
        """
        # Check if we have a valid token (with 5 min buffer)
        if self._token and self._expires_at:
            now = datetime.now(timezone.utc)
            buffer = timedelta(minutes=5)

            if self._expires_at > now + buffer:
                logger.debug(
                    "service_token_reused",
                    expires_in_seconds=(self._expires_at - now).total_seconds()
                )
                return self._token

        # Token expired or doesn't exist - acquire new one
        logger.info("service_token_refresh_needed")
        await self._acquire_token()

        return self._token

    def _get_session(self) -> aiohttp.ClientSession:
        """
        Get the persistent aiohttp session.

        Raises:
            RuntimeError: If start() has not been called
        """
        if not self._started or self._session is None:
            raise RuntimeError(
                "ServiceTokenManager not started. "
                "Call await token_manager.start() during app startup (lifespan)."
            )

        if self._session.closed:
            raise RuntimeError(
                "HTTP session is closed. ServiceTokenManager cannot be used after shutdown."
            )

        return self._session

    async def _acquire_token(self) -> None:
        """
        Acquire new access token via Client Credentials flow.

        Raises:
            aiohttp.ClientError: If token request fails
        """
        import asyncio

        try:
            session = self._get_session()
            request_loop_id = id(asyncio.get_event_loop())

            logger.info(
                "attempting_oauth_token_request",
                token_url=self.token_url,
                client_id=self.client_id,
                scope=self.scope,
                session_id=id(session),
                session_closed=session.closed,
                event_loop_id_request=request_loop_id
            )

            # aiohttp uses context manager for requests (beautiful pattern!)
            async with session.post(
                self.token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": self.scope
                }
            ) as response:
                logger.info(
                    "oauth_token_response_received",
                    status=response.status,
                    headers=dict(response.headers)
                )

                # Raise for 4xx/5xx status codes
                response.raise_for_status()

                # Parse JSON response
                data = await response.json()

            self._token = data["access_token"]
            expires_in = data.get("expires_in", 3600)  # Default 1 hour
            self._expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            logger.info(
                "service_token_acquired",
                expires_in_seconds=expires_in,
                scope=self.scope
            )

        except aiohttp.ClientConnectionError as e:
            # Connection errors (DNS, TCP, network issues)
            logger.error(
                "service_token_connection_failed",
                error=str(e),
                error_type=type(e).__name__,
                token_url=self.token_url,
                session_closed=self._session.closed if self._session else "no_session",
                exc_info=True  # Full traceback
            )
            raise
        except aiohttp.ClientResponseError as e:
            # HTTP errors (4xx, 5xx)
            logger.error(
                "service_token_http_error",
                error=str(e),
                status=e.status,
                message=e.message,
                token_url=self.token_url,
                exc_info=True
            )
            raise
        except aiohttp.ClientError as e:
            # Other client errors
            logger.error(
                "service_token_acquisition_failed",
                error=str(e),
                error_type=type(e).__name__,
                token_url=self.token_url,
                exc_info=True
            )
            raise

    async def close(self) -> None:
        """Close aiohttp session on shutdown."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("http_session_closed")

    def invalidate(self) -> None:
        """Force token refresh on next get_token() call."""
        self._token = None
        self._expires_at = None
        logger.info("service_token_invalidated")


# Singleton instance (initialized in main.py lifespan)
_token_manager: Optional[ServiceTokenManager] = None


def init_service_token_manager(
    client_id: str,
    client_secret: str,
    token_url: str,
    scope: str = "groups:read"
) -> ServiceTokenManager:
    """
    Initialize global service token manager.

    Call this once during app startup (in lifespan).
    """
    global _token_manager
    _token_manager = ServiceTokenManager(
        client_id=client_id,
        client_secret=client_secret,
        token_url=token_url,
        scope=scope
    )
    logger.info(
        "service_token_manager_initialized",
        client_id=client_id,
        token_url=token_url,
        scope=scope
    )
    return _token_manager


def get_service_token_manager() -> ServiceTokenManager:
    """
    Get global service token manager instance.

    Raises:
        RuntimeError: If not initialized
    """
    if _token_manager is None:
        raise RuntimeError(
            "ServiceTokenManager not initialized. "
            "Call init_service_token_manager() during app startup."
        )
    return _token_manager
