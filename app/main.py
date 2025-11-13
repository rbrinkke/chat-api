from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.core.logging_config import setup_logging, get_logger
from app.core.rate_limit import limiter
from app.core.cache import cache
# OAuth 2.0 HS256 - No legacy RBAC needed (fully migrated to OAuth2)
# JWKS not needed for HS256 (symmetric signing with shared secret)
# from app.core.jwks_manager import get_jwks_manager, close_jwks_manager  # OAuth 2.0
from app.db.mongodb import init_db
from app.middleware.access_log import AccessLogMiddleware, RequestContextMiddleware
# OAuth2Middleware uses RS256/JWKS - not needed for HS256
# from app.middleware.oauth2 import OAuth2Middleware  # OAuth 2.0 Resource Server
from app.routes import messages, websocket, dashboard, test_ui

# Setup structured logging BEFORE any other imports that might log
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info(
        "application_startup",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        log_level=settings.LOG_LEVEL,
    )

    try:
        await init_db()
        logger.info("database_initialized", database=settings.DATABASE_NAME)
    except Exception as e:
        logger.error(
            "database_initialization_failed",
            error=str(e),
            database_url=settings.MONGODB_URL,
            exc_info=True,
        )
        raise

    # Initialize cache (optional, graceful degradation if Redis unavailable)
    await cache.initialize()

    # ========== OAuth 2.0 Resource Server (HS256 - Shared Secret) ==========
    # Using HS256 symmetric signing with shared JWT_SECRET_KEY
    # NO JWKS endpoint needed - Auth API and Chat API share the same secret
    logger.info(
        "oauth2_hs256_mode",
        algorithm=settings.JWT_ALGORITHM,
        message="OAuth 2.0 using HS256 symmetric signing (shared secret with Auth API)"
    )

    # ========== Service-to-Service OAuth (Client Credentials) ==========
    # Initialize token manager for Auth-API group data access
    try:
        from app.core.service_auth import init_service_token_manager

        token_manager = init_service_token_manager(
            client_id=settings.SERVICE_CLIENT_ID,
            client_secret=settings.SERVICE_CLIENT_SECRET,
            token_url=settings.SERVICE_TOKEN_URL,
            scope=settings.SERVICE_SCOPE
        )
        logger.info(
            "service_token_manager_initialized",
            client_id=settings.SERVICE_CLIENT_ID,
            token_url=settings.SERVICE_TOKEN_URL,
            scope=settings.SERVICE_SCOPE
        )

        # ✅ CRITICAL: Start token manager in async context
        # This creates aiohttp.ClientSession in the correct event loop
        await token_manager.start()

        # ✅ CRITICAL: Start group service in async context
        # This creates aiohttp.ClientSession in the correct event loop
        from app.services.group_service import get_group_service
        group_service = get_group_service()
        await group_service.start()

    except Exception as e:
        logger.error(
            "service_token_manager_initialization_failed",
            error=str(e),
            exc_info=True
        )
        raise

    # ✅ OAuth 2.0 migration complete - No legacy RBAC needed!
    # All authorization now handled via OAuth2 Client Credentials + JWT validation

    yield

    # Shutdown
    logger.info("application_shutdown")

    # Gracefully close all WebSocket connections
    from app.services.connection_manager import manager
    await manager.shutdown_all()

    # OAuth 2.0 HS256 doesn't require cleanup (no JWKS manager)

    # Close service token manager HTTP client
    from app.core.service_auth import get_service_token_manager
    token_manager = get_service_token_manager()
    await token_manager.close()

    # Close group service HTTP client
    from app.services.group_service import get_group_service
    group_service = get_group_service()
    await group_service.close()

    # Close cache connection
    await cache.close()


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# Add rate limiter state and exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add Prometheus metrics instrumentation
try:
    from prometheus_fastapi_instrumentator import Instrumentator

    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=False,
        should_group_untemplated=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics"],  # Don't track metrics endpoint itself
        inprogress_name="http_requests_inprogress",
        inprogress_labels=True,
    )

    instrumentator.instrument(app).expose(app, endpoint="/metrics")
    logger.info("prometheus_metrics_enabled", endpoint="/metrics")
except ImportError:
    logger.warning("prometheus_metrics_disabled", reason="prometheus-fastapi-instrumentator not installed")

# ========== Middleware Stack ==========
# Middleware order matters! They execute in REVERSE order of registration.
# Last added = first to execute
#
# Execution Order:
# 1. RequestContextMiddleware (adds correlation ID)
# 2. OAuth2Middleware (validates JWT, adds auth context)
# 3. AccessLogMiddleware (logs request/response)
# 4. CORSMiddleware (handles CORS headers)
# 5. Route Handler (your business logic)

# Add CORS middleware (executes last)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# Add access logging middleware (executes third)
app.add_middleware(AccessLogMiddleware)

# OAuth2 HS256 validation happens in route handlers via oauth_validator.py
# No middleware needed - use Depends(validate_oauth_token) in routes

# Add request context middleware (executes first - enriches request)
app.add_middleware(RequestContextMiddleware)

# Include routers
# groups router removed - Auth-API is now Single Source of Truth for groups
app.include_router(messages.router, prefix=settings.API_PREFIX, tags=["messages"])
app.include_router(websocket.router, prefix=settings.API_PREFIX, tags=["websocket"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(test_ui.router, tags=["test-ui"])


# Health check endpoint
@app.get("/health")
async def health_check():
    """
    Production-grade health check endpoint.

    Verifies:
    - MongoDB connectivity
    - Redis connectivity (if configured)
    - Auth API connectivity (for RBAC)
    - Overall application health

    Returns 200 if all checks pass, 503 if any critical component fails.
    """
    from datetime import datetime
    from app.models.message import Message
    from fastapi.responses import JSONResponse

    checks = {
        "application": "healthy",
        "mongodb": "unknown",
        "redis": "unknown" if settings.REDIS_URL else "not_configured",
        "oauth_hs256": "unknown",  # JWT validation (HS256 shared secret)
        "oauth_service_auth": "unknown"  # Service-to-service OAuth2 Client Credentials
    }

    # Check MongoDB (using Message model - Group model removed)
    try:
        await Message.find().limit(1).to_list()
        checks["mongodb"] = "healthy"
    except Exception as e:
        logger.error("health_check_mongodb_failed", error=str(e))
        checks["mongodb"] = f"unhealthy: {type(e).__name__}"

    # Check Redis (if configured)
    if settings.REDIS_URL and cache.enabled:
        try:
            await cache.redis.ping()
            checks["redis"] = "healthy"
        except Exception as e:
            logger.error("health_check_redis_failed", error=str(e))
            checks["redis"] = f"unhealthy: {type(e).__name__}"

    # Check OAuth HS256 Configuration (JWT_SECRET_KEY validation)
    try:
        from app.core.oauth_validator import JWT_SECRET_KEY, JWT_ALGORITHM

        if JWT_SECRET_KEY and len(JWT_SECRET_KEY) >= 32:
            checks["oauth_hs256"] = f"healthy (algorithm: {JWT_ALGORITHM})"
        else:
            checks["oauth_hs256"] = "unhealthy: JWT_SECRET_KEY too short or missing"

    except Exception as e:
        logger.error("health_check_oauth_hs256_failed", error=str(e))
        checks["oauth_hs256"] = f"unhealthy: {type(e).__name__}"

    # OAuth 2.0 Service-to-Service Auth - Check token manager
    try:
        from app.core.service_auth import get_service_token_manager
        token_manager = get_service_token_manager()

        # Quick check: try to get a token (will use cached if valid)
        token = await token_manager.get_token()

        if token and len(token) > 0:
            checks["oauth_service_auth"] = "healthy (OAuth2 Client Credentials)"
        else:
            checks["oauth_service_auth"] = "unhealthy: no token available"

    except Exception as e:
        logger.error("health_check_service_auth_failed", error=str(e))
        checks["oauth_service_auth"] = f"unhealthy: {type(e).__name__}"

    # Determine overall status
    critical_checks = [checks["mongodb"]]  # MongoDB is critical

    # HS256 OAuth doesn't need JWKS - only shared secret required
    # Service-to-service OAuth verified via oauth_service_auth check

    all_healthy = all(
        status.startswith("healthy") or status.startswith("degraded")
        for status in critical_checks
    )

    overall_status = "healthy" if all_healthy else "degraded"
    status_code = 200 if all_healthy else 503

    response_data = {
        "status": overall_status,
        "service": "chat-api",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "checks": checks
    }

    return JSONResponse(content=response_data, status_code=status_code)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
        "dashboard": "/dashboard",
        "test_ui": "/test-chat"
    }


if __name__ == "__main__":
    import uvicorn

    # Run with proper logging configuration
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=False,  # Disable default access log - we use custom middleware
    )
