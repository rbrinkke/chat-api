"""
Custom structured access log middleware.

This middleware replaces Uvicorn's default access logs with structured JSON logs
that include performance metrics, correlation IDs, and request context.

Architecture advantages:
- Homogeneous JSON format across all logs
- Performance timing for every request
- Automatic correlation ID propagation
- Request/response body size tracking
- Error context enrichment
- Zero duplication (Uvicorn access logs are disabled)
"""

import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars


logger = structlog.get_logger(__name__)

# Import metrics collector for dashboard
try:
    from app.services.dashboard_service import metrics_collector
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    logger.warning("metrics_collector_unavailable", message="Dashboard metrics will not be collected")


class AccessLogMiddleware(BaseHTTPMiddleware):
    """
    Production-grade access logging middleware with performance metrics.

    Features:
    - Structured JSON access logs
    - Request correlation IDs for distributed tracing
    - Performance timing (request duration)
    - Request/response metadata (method, path, status, size)
    - Error tracking with stack traces
    - User identification from JWT
    - Client IP tracking
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate or extract correlation ID
        correlation_id = request.headers.get("X-Correlation-ID") or request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Bind correlation ID to structlog context for the entire request lifecycle
        # This makes it available to all logs generated during this request
        bind_contextvars(
            correlation_id=correlation_id,
            request_id=correlation_id,  # Alias for compatibility
        )

        # Add to request state for access in route handlers
        request.state.correlation_id = correlation_id

        # Start performance timer
        start_time = time.perf_counter()

        # Extract request metadata
        method = request.method
        url = str(request.url)
        path = request.url.path
        query_params = str(request.url.query) if request.url.query else None
        client_host = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

        # Extract user ID from request state (set by auth middleware)
        user_id = getattr(request.state, "user_id", None)

        # Log request started (useful for debugging stuck requests)
        logger.debug(
            "request_started",
            method=method,
            path=path,
            client_ip=client_host,
            user_id=user_id,
        )

        # Process request
        response = None
        error = None
        status_code = 500  # Default to error if something goes wrong

        try:
            response = await call_next(request)
            status_code = response.status_code

        except Exception as e:
            # Catch any unhandled exceptions
            error = e
            status_code = 500

            # Log the error with full context
            logger.error(
                "request_error_unhandled",
                method=method,
                path=path,
                error_type=type(e).__name__,
                error=str(e),
                client_ip=client_host,
                user_id=user_id,
                exc_info=True,  # Include stack trace
            )

            # Re-raise to let FastAPI's exception handler deal with it
            raise

        finally:
            # Calculate request duration
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Determine log level based on status code
            if status_code >= 500:
                log_level = "error"
            elif status_code >= 400:
                log_level = "warning"
            else:
                log_level = "info"

            # Get the appropriate logger method
            log_method = getattr(logger, log_level)

            # Log access with full metadata
            log_method(
                "http_request",
                method=method,
                path=path,
                full_url=url,
                query_params=query_params,
                status_code=status_code,
                duration_ms=round(duration_ms, 2),
                client_ip=client_host,
                user_agent=user_agent,
                user_id=user_id,
                error_type=type(error).__name__ if error else None,
                # Performance categorization
                slow_request=duration_ms > 1000,  # Flag slow requests (>1s)
                very_slow_request=duration_ms > 5000,  # Flag very slow requests (>5s)
            )

            # Alert on very slow requests
            if duration_ms > 5000:
                logger.warning(
                    "performance_degradation",
                    message="Request took longer than 5 seconds",
                    method=method,
                    path=path,
                    duration_ms=round(duration_ms, 2),
                    user_id=user_id,
                )

            # Record metrics for dashboard
            if METRICS_AVAILABLE:
                try:
                    metrics_collector.record_request(
                        endpoint=path,
                        method=method,
                        duration_ms=duration_ms,
                        status_code=status_code,
                        correlation_id=correlation_id
                    )
                except Exception as e:
                    logger.warning("metrics_recording_failed", error=str(e))

            # Clear structlog context variables for next request
            clear_contextvars()

        # Add correlation ID to response headers for client-side tracing
        if response:
            response.headers["X-Correlation-ID"] = correlation_id
            response.headers["X-Request-ID"] = correlation_id

        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Lightweight middleware to enrich request context.

    This runs before AccessLogMiddleware and extracts user info from JWT
    if available, making it accessible to access logs.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Extract user_id from JWT if present
        user_id = None

        # Check if Authorization header exists
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                from jose import jwt
                from app.config import settings

                token = auth_header.replace("Bearer ", "")
                payload = jwt.decode(
                    token,
                    settings.JWT_SECRET,
                    algorithms=[settings.JWT_ALGORITHM]
                )
                user_id = payload.get("sub")

                # Store in request state for access logs
                request.state.user_id = user_id

            except Exception:
                # Invalid token - ignore for logging purposes
                # The auth middleware will handle the actual rejection
                pass

        # Continue to next middleware
        response = await call_next(request)
        return response
