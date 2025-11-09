from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.core.logging_config import setup_logging, get_logger
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

    yield

    # Shutdown
    logger.info("application_shutdown")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

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
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION
    }


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
