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
from app.routes import messages, websocket, dashboard, test_ui, example_auth_check, ops

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

    # ========== Auth API Client (API Key Authentication) ==========
    # Initialize Auth API Client for permission checks
    # Uses simple API Key authentication (X-Service-Token header)
    from app.services.auth_api_client import get_auth_api_client
    auth_api_client = get_auth_api_client()
    logger.info(
        "auth_api_client_initialized",
        auth_api_url=settings.AUTH_API_URL,
        auth_method="api_key"
    )

    yield

    # Shutdown
    logger.info("application_shutdown")

    # Gracefully close all WebSocket connections
    from app.services.connection_manager import manager
    await manager.shutdown_all()

    # Close cache connection
    await cache.close()


# Create FastAPI app with environment-conditional Swagger UI (best practice for production security)
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.API_VERSION,
    description="""
**Real-time chat API built with FastAPI, MongoDB, and WebSocket support.**

Features JWT authentication (shared secret with auth-api), group-based authorization, and production-grade structured logging with correlation IDs.

## Key Features
- **WebSocket Real-time Communication**: Live message broadcasting to all group members
- **Group-based Authorization**: Fine-grained access control per chat group
- **Soft Deletes**: Messages never permanently deleted (audit trail preserved)
- **OAuth 2.0 Integration**: HS256 JWT validation with shared secret from auth-api
- **Structured Logging**: JSON logging with correlation IDs for request tracing
- **Circuit Breaker**: Resilient authorization service communication

## Architecture
- **Database**: MongoDB with Beanie ODM for document modeling
- **Cache**: Optional Redis for authorization caching (5min TTL)
- **WebSocket**: In-memory connection pooling with automatic cleanup
- **Authentication**: JWT tokens issued by auth-api (shared JWT_SECRET_KEY)
- **Observability**: Prometheus metrics, structured logging, real-time dashboard

## Security
- JWT Bearer authentication required for all endpoints
- Group authorization checks on every message operation
- Circuit breaker with fail-closed security (denies access on auth service failure)
- Correlation ID tracking for security auditing
    """,
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_DOCS else None,
    contact={
        "name": "Activity Platform Team",
        "email": "dev@activityapp.com"
    },
    license_info={
        "name": "Proprietary"
    },
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
app.include_router(ops.router, tags=["operations"])
app.include_router(messages.router, prefix=settings.API_PREFIX, tags=["messages"])
app.include_router(websocket.router, prefix=settings.API_PREFIX, tags=["websocket"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])

if settings.ENVIRONMENT == "development":
    app.include_router(test_ui.router, tags=["test-ui"])
    app.include_router(example_auth_check.router, prefix=settings.API_PREFIX, tags=["auth-examples"])


# Configure OpenAPI security scheme for JWT Bearer authentication
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    from fastapi.openapi.utils import get_openapi

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    if settings.ENABLE_DOCS:
        # Add JWT Bearer security scheme
        openapi_schema["components"] = openapi_schema.get("components", {})
        openapi_schema["components"]["securitySchemes"] = {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "JWT access token from auth-api. Format: `Bearer <token>`. Token must be obtained from auth-api /auth/login endpoint."
            }
        }

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


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
