"""
Production-grade structured logging configuration with structlog.

This module implements the architectural best practices for container-based
logging as outlined in the FastAPI/Uvicorn/Docker logging doctrine:

- All logs to STDOUT/STDERR for Docker log collection
- Structured JSON logging for production environments
- Human-readable console logs for development
- Granular log level control per module
- Third-party library noise filtering
- Zero log duplication through propagation control
- Request correlation IDs for distributed tracing
- Performance metrics and timing information
"""

import logging
import logging.config
import sys
from typing import Any
import structlog
from structlog.types import EventDict, Processor
from app.config import settings


def add_app_context(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """
    Add application context to every log entry.

    This processor enriches logs with:
    - Service name (for observability stack filtering)
    - Application name
    - Environment (dev/staging/prod)
    - Service version
    """
    event_dict["service"] = "chat-api"  # Fixed service name for observability stack
    event_dict["app"] = settings.APP_NAME
    event_dict["version"] = settings.APP_VERSION
    event_dict["environment"] = settings.ENVIRONMENT
    return event_dict


def add_severity_level(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """
    Add explicit severity level for better log aggregation filtering.

    Maps Python logging levels to standard severity labels.
    """
    if "level" in event_dict:
        event_dict["severity"] = event_dict["level"].upper()
    return event_dict


def add_trace_id_alias(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """
    Add trace_id as an alias for correlation_id for observability stack compatibility.

    The observability stack expects 'trace_id' field, while our internal
    middleware uses 'correlation_id'. This processor ensures both are present.
    """
    if "correlation_id" in event_dict:
        event_dict["trace_id"] = event_dict["correlation_id"]
    elif "request_id" in event_dict:
        event_dict["trace_id"] = event_dict["request_id"]

    return event_dict


def censor_sensitive_data(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """
    Censor sensitive data from logs to prevent security leaks.

    Automatically redacts common sensitive fields:
    - Passwords
    - API keys
    - JWT tokens
    - Authorization headers
    """
    sensitive_keys = ["password", "token", "api_key", "secret", "authorization"]

    for key in list(event_dict.keys()):
        if any(sensitive in key.lower() for sensitive in sensitive_keys):
            event_dict[key] = "***REDACTED***"

    return event_dict


def setup_logging() -> None:
    """
    Configure the complete logging stack for the application.

    This function:
    1. Configures Python's standard logging module for third-party libraries
    2. Sets up structlog with production-grade processors
    3. Establishes the logging format based on environment (JSON vs Console)
    4. Implements granular log level control
    5. Prevents log duplication through proper propagation settings

    Architecture:
    - Development: Colored console output with readable format
    - Production: Structured JSON to STDOUT for log aggregators
    - All environments: STDERR for ERROR and CRITICAL levels
    """

    # Determine log level from environment (with fallback)
    log_level_name = settings.LOG_LEVEL.upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    # Shared processors for all environments
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,  # Merge context variables (correlation_id, etc)
        structlog.stdlib.add_log_level,           # Add log level
        structlog.stdlib.add_logger_name,         # Add logger name
        structlog.processors.TimeStamper(fmt="iso", utc=True),  # ISO timestamp
        add_app_context,                          # Add app metadata (includes service field)
        add_severity_level,                       # Add severity field
        add_trace_id_alias,                       # Add trace_id alias for observability stack
        censor_sensitive_data,                    # Security: redact sensitive data
        structlog.processors.StackInfoRenderer(), # Add stack traces when available
        structlog.processors.format_exc_info,     # Format exceptions
    ]

    # Configure output format based on environment
    if settings.ENVIRONMENT == "production":
        # Production: Pure JSON for machine parsing
        processors = shared_processors + [
            structlog.processors.JSONRenderer()   # Output as JSON
        ]
    else:
        # Development: Human-readable colored console output
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True)  # Colored output
        ]

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging (for third-party libraries)
    # This ensures libraries like SQLAlchemy, httpx, etc. also log through structlog
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.processors.JSONRenderer() if settings.ENVIRONMENT == "production"
                            else structlog.dev.ConsoleRenderer(colors=True),
                "foreign_pre_chain": shared_processors,
            },
        },
        "handlers": {
            "default": {
                "level": log_level_name,
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "json",
            },
            "error": {
                "level": "ERROR",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
                "formatter": "json",
            },
        },
        "loggers": {
            # Root logger - catches everything not explicitly configured
            "": {
                "handlers": ["default", "error"],
                "level": log_level_name,
                "propagate": False,
            },
            # Application loggers - always at configured level for detailed debugging
            "app": {
                "handlers": ["default", "error"],
                "level": log_level_name,
                "propagate": False,
            },
            # Uvicorn loggers - controlled separately, no duplication
            "uvicorn": {
                "handlers": ["default"],
                "level": log_level_name,
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["default", "error"],
                "level": log_level_name,
                "propagate": False,  # Critical: prevents duplication
            },
            "uvicorn.access": {
                "handlers": [],  # Disabled - we use custom access log middleware
                "level": "CRITICAL",
                "propagate": False,
            },
            # Third-party library noise filtering
            # These are set to WARNING to reduce log volume in debug mode
            "sqlalchemy.engine": {
                "handlers": ["default"],
                "level": "WARNING",  # Prevents SQL query spam in debug mode
                "propagate": False,
            },
            "databases": {
                "handlers": ["default"],
                "level": "WARNING",
                "propagate": False,
            },
            "httpx": {
                "handlers": ["default"],
                "level": "WARNING",
                "propagate": False,
            },
            "httpcore": {
                "handlers": ["default"],
                "level": "WARNING",
                "propagate": False,
            },
            "asyncio": {
                "handlers": ["default"],
                "level": "WARNING",
                "propagate": False,
            },
        },
    })

    # Log the logging configuration itself for debugging
    logger = get_logger(__name__)
    logger.info(
        "logging_configured",
        log_level=log_level_name,
        environment=settings.ENVIRONMENT,
        format="json" if settings.ENVIRONMENT == "production" else "console",
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.

    Usage:
        logger = get_logger(__name__)
        logger.info("user_login", user_id="123", ip_address="1.2.3.4")
        logger.error("database_error", error=str(e), query=query)

    All structured data passed as kwargs will be included in the log output.
    In production, this becomes searchable JSON fields.

    Args:
        name: Logger name (typically __name__ for the current module)

    Returns:
        Structured logger instance
    """
    return structlog.get_logger(name)


class PerformanceLogger:
    """
    Context manager for performance timing and logging.

    Usage:
        with PerformanceLogger("database_query", logger, query_type="select"):
            result = await db.execute(query)

    This will automatically log the operation duration.
    """

    def __init__(self, operation: str, logger: structlog.stdlib.BoundLogger, **context):
        self.operation = operation
        self.logger = logger
        self.context = context
        self.start_time = None

    def __enter__(self):
        import time
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        duration_ms = (time.perf_counter() - self.start_time) * 1000

        if exc_type is None:
            # Success
            self.logger.debug(
                "operation_completed",
                operation=self.operation,
                duration_ms=round(duration_ms, 2),
                **self.context
            )
        else:
            # Error occurred
            self.logger.error(
                "operation_failed",
                operation=self.operation,
                duration_ms=round(duration_ms, 2),
                error_type=exc_type.__name__,
                error=str(exc_val),
                **self.context
            )

        # Don't suppress exceptions
        return False
