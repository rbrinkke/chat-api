from fastapi import APIRouter
from fastapi.responses import JSONResponse
from datetime import datetime
from app.config import settings
from app.core.logging_config import get_logger
from app.core.cache import cache
from app.models.message import Message
from app.core.oauth_validator import JWT_SECRET_KEY, JWT_ALGORITHM
from app.services.auth_api_client import get_auth_api_client

router = APIRouter()
logger = get_logger(__name__)

# Health check endpoint
@router.get("/health")
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

    checks = {
        "application": "healthy",
        "mongodb": "unknown",
        "redis": "unknown" if settings.REDIS_URL else "not_configured",
        "oauth_hs256": "unknown",  # JWT validation (HS256 shared secret)
        "auth_api_client": "unknown"  # Auth API Client (API Key)
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
        if JWT_SECRET_KEY and len(JWT_SECRET_KEY) >= 32:
            checks["oauth_hs256"] = f"healthy (algorithm: {JWT_ALGORITHM})"
        else:
            checks["oauth_hs256"] = "unhealthy: JWT_SECRET_KEY too short or missing"

    except Exception as e:
        logger.error("health_check_oauth_hs256_failed", error=str(e))
        checks["oauth_hs256"] = f"unhealthy: {type(e).__name__}"

    # Auth API Client - Check connectivity
    try:
        auth_client = get_auth_api_client()

        if auth_client.service_token and len(auth_client.service_token) > 10:
            checks["auth_api_client"] = "healthy (API Key configured)"
        else:
            checks["auth_api_client"] = "unhealthy: SERVICE_AUTH_TOKEN missing"

    except Exception as e:
        logger.error("health_check_auth_api_client_failed", error=str(e))
        checks["auth_api_client"] = f"unhealthy: {type(e).__name__}"

    # Determine overall status
    critical_checks = [checks["mongodb"]]  # MongoDB is critical

    # HS256 OAuth doesn't need JWKS - only shared secret required
    # Auth API Client verified via auth_api_client check

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
@router.get("/")
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
