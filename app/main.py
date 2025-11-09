from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.core.logging_config import setup_logging, get_logger
from app.core.rate_limit import limiter
from app.core.cache import cache
from app.db.mongodb import init_db
from app.middleware.access_log import AccessLogMiddleware, RequestContextMiddleware
from app.routes import groups, messages, websocket

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

    yield

    # Shutdown
    logger.info("application_shutdown")

    # Gracefully close all WebSocket connections
    from app.services.connection_manager import manager
    await manager.shutdown_all()

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

# Middleware order matters! They execute in reverse order of registration.
# Last added = first to execute

# Add CORS middleware (executes first)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# Add access logging middleware (executes second - logs every request)
app.add_middleware(AccessLogMiddleware)

# Add request context middleware (executes last - enriches request with user info)
app.add_middleware(RequestContextMiddleware)

# Include routers
app.include_router(groups.router, prefix=settings.API_PREFIX, tags=["groups"])
app.include_router(messages.router, prefix=settings.API_PREFIX, tags=["messages"])
app.include_router(websocket.router, prefix=settings.API_PREFIX, tags=["websocket"])


# Health check endpoint
@app.get("/health")
async def health_check():
    """
    Production-grade health check endpoint.

    Verifies:
    - MongoDB connectivity
    - Redis connectivity (if configured)
    - Overall application health

    Returns 200 if all checks pass, 503 if any critical component fails.
    """
    from app.models.group import Group
    from fastapi.responses import JSONResponse

    checks = {
        "application": "healthy",
        "mongodb": "unknown",
        "redis": "unknown" if settings.REDIS_URL else "not_configured"
    }

    # Check MongoDB
    try:
        await Group.find().limit(1).to_list()
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

    # Determine overall status
    critical_checks = [checks["mongodb"]]  # MongoDB is critical
    all_healthy = all(status == "healthy" for status in critical_checks)

    overall_status = "healthy" if all_healthy else "degraded"
    status_code = 200 if all_healthy else 503

    response_data = {
        "status": overall_status,
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
        "health": "/health"
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
