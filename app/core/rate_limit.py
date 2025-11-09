"""
Rate limiting configuration for API endpoints.

Uses slowapi (FastAPI-compatible rate limiter) to prevent abuse and ensure fair usage.

Rate limiting strategy:
- Default: 100 requests/minute for most endpoints
- Message creation: 20 requests/minute (prevent spam)
- WebSocket connections: 10 connections/minute per user
- Health check: No limit (monitoring needs unrestricted access)

Rate limits are based on:
1. User ID (from JWT) for authenticated requests
2. Client IP for unauthenticated requests
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request
from typing import Optional


def get_user_identifier(request: Request) -> str:
    """
    Get unique identifier for rate limiting.

    Priority:
    1. User ID from JWT (most accurate)
    2. Client IP (fallback for unauthenticated requests)

    This ensures:
    - Authenticated users are rate-limited per account (prevents multi-IP abuse)
    - Unauthenticated endpoints use IP-based limiting
    """
    # Check if user is authenticated (set by RequestContextMiddleware)
    user_id: Optional[str] = getattr(request.state, "user_id", None)

    if user_id:
        return f"user:{user_id}"

    # Fallback to IP address
    return f"ip:{get_remote_address(request)}"


# Initialize rate limiter
limiter = Limiter(
    key_func=get_user_identifier,
    default_limits=["100/minute"],  # Default limit for all endpoints
    storage_uri="memory://",  # Use in-memory storage (for production: use Redis)
    strategy="fixed-window",  # Fixed time window strategy
)
