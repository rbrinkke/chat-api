"""
Shared utilities for mock servers.

Provides common functionality for JWT generation, mock data creation,
error simulation, and network delay simulation.
"""

import uuid
import asyncio
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import jwt
from passlib.context import CryptContext
from fastapi import HTTPException

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Hashed password
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password to compare against

    Returns:
        True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)


def generate_jwt_token(
    user_id: str,
    secret: str,
    algorithm: str = "HS256",
    expiry_hours: int = 24,
    additional_claims: Optional[Dict[str, Any]] = None
) -> str:
    """
    Generate a JWT token for a user.

    Args:
        user_id: User identifier to encode in token
        secret: Secret key for signing the token
        algorithm: JWT algorithm (default: HS256)
        expiry_hours: Token expiration time in hours (default: 24)
        additional_claims: Optional additional claims to include in token

    Returns:
        Encoded JWT token string
    """
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(hours=expiry_hours),
        "iat": datetime.utcnow(),
        "type": "access"
    }

    # Add any additional claims
    if additional_claims:
        payload.update(additional_claims)

    return jwt.encode(payload, secret, algorithm=algorithm)


def generate_refresh_token(
    user_id: str,
    secret: str,
    algorithm: str = "HS256",
    expiry_days: int = 30
) -> str:
    """
    Generate a refresh token for a user.

    Args:
        user_id: User identifier to encode in token
        secret: Secret key for signing the token
        algorithm: JWT algorithm (default: HS256)
        expiry_days: Token expiration time in days (default: 30)

    Returns:
        Encoded JWT refresh token string
    """
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(days=expiry_days),
        "iat": datetime.utcnow(),
        "type": "refresh"
    }

    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_token(token: str, secret: str, algorithm: str = "HS256") -> Dict[str, Any]:
    """
    Decode and validate a JWT token.

    Args:
        token: JWT token to decode
        secret: Secret key for verification
        algorithm: JWT algorithm (default: HS256)

    Returns:
        Decoded token payload

    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


def generate_user_id() -> str:
    """
    Generate a unique user ID (UUID format).

    Returns:
        UUID string
    """
    return str(uuid.uuid4())


class MockUser:
    """Data class for mock user."""

    def __init__(
        self,
        id: str,
        email: str,
        name: str,
        hashed_password: str,
        created_at: Optional[datetime] = None
    ):
        self.id = id
        self.email = email
        self.name = name
        self.hashed_password = hashed_password
        self.created_at = created_at or datetime.utcnow()

    def dict(self, exclude_password: bool = True) -> Dict[str, Any]:
        """Convert user to dictionary."""
        data = {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "created_at": self.created_at.isoformat()
        }
        if not exclude_password:
            data["hashed_password"] = self.hashed_password
        return data


class SeededDataGenerator:
    """
    Generate consistent, realistic mock data for testing.

    Provides seed users and helper methods for creating test data.
    """

    # Default password for all seed users
    DEFAULT_PASSWORD = "password123"

    # Seed users for testing
    SEED_USERS = [
        {
            "id": "test-user-123",
            "email": "alice@example.com",
            "name": "Alice Johnson"
        },
        {
            "id": "test-user-456",
            "email": "bob@example.com",
            "name": "Bob Smith"
        },
        {
            "id": "test-user-789",
            "email": "charlie@example.com",
            "name": "Charlie Brown"
        },
        {
            "id": "test-user-abc",
            "email": "diana@example.com",
            "name": "Diana Prince"
        },
        {
            "id": "test-user-def",
            "email": "ethan@example.com",
            "name": "Ethan Hunt"
        }
    ]

    @classmethod
    def get_seed_users(cls, password: Optional[str] = None) -> Dict[str, MockUser]:
        """
        Get dictionary of seed users with hashed passwords.

        Args:
            password: Password to use for all users (default: password123)

        Returns:
            Dictionary mapping user_id to MockUser
        """
        pwd = password or cls.DEFAULT_PASSWORD
        hashed = hash_password(pwd)

        users = {}
        for user_data in cls.SEED_USERS:
            user = MockUser(
                id=user_data["id"],
                email=user_data["email"],
                name=user_data["name"],
                hashed_password=hashed
            )
            users[user.id] = user

        return users

    @classmethod
    def get_user_by_email(cls, users: Dict[str, MockUser], email: str) -> Optional[MockUser]:
        """
        Find user by email address.

        Args:
            users: Dictionary of users
            email: Email to search for

        Returns:
            MockUser if found, None otherwise
        """
        for user in users.values():
            if user.email.lower() == email.lower():
                return user
        return None


async def simulate_network_delay(min_ms: int = 50, max_ms: int = 200):
    """
    Simulate realistic network delay.

    Args:
        min_ms: Minimum delay in milliseconds
        max_ms: Maximum delay in milliseconds
    """
    delay_seconds = random.randint(min_ms, max_ms) / 1000.0
    await asyncio.sleep(delay_seconds)


def error_simulator(error_code: Optional[int] = None):
    """
    Simulate errors for testing error handling.

    Usage:
        @app.get("/endpoint")
        async def endpoint(simulate_error: Optional[int] = None):
            error_simulator(simulate_error)
            # ... normal logic

    Args:
        error_code: HTTP error code to simulate (400, 401, 404, 500, etc.)

    Raises:
        HTTPException: If error_code is provided
    """
    if error_code:
        error_messages = {
            400: "Bad Request - Simulated error",
            401: "Unauthorized - Simulated error",
            403: "Forbidden - Simulated error",
            404: "Not Found - Simulated error",
            409: "Conflict - Simulated error",
            500: "Internal Server Error - Simulated error",
            503: "Service Unavailable - Simulated error"
        }
        message = error_messages.get(error_code, f"Error {error_code} - Simulated error")
        raise HTTPException(status_code=error_code, detail=message)


def random_error_simulator(error_rate: float = 0.1, error_code: int = 500):
    """
    Randomly simulate errors based on error rate.

    Args:
        error_rate: Probability of error (0.0 to 1.0)
        error_code: HTTP error code to raise

    Raises:
        HTTPException: Randomly based on error_rate
    """
    if random.random() < error_rate:
        error_simulator(error_code)


class MockMetrics:
    """Simple in-memory metrics collection for mock servers."""

    def __init__(self):
        self.request_count = 0
        self.error_count = 0
        self.endpoint_counts: Dict[str, int] = {}

    def record_request(self, endpoint: str):
        """Record a request to an endpoint."""
        self.request_count += 1
        self.endpoint_counts[endpoint] = self.endpoint_counts.get(endpoint, 0) + 1

    def record_error(self):
        """Record an error."""
        self.error_count += 1

    def get_stats(self) -> Dict[str, Any]:
        """Get current metrics."""
        return {
            "total_requests": self.request_count,
            "total_errors": self.error_count,
            "error_rate": self.error_count / self.request_count if self.request_count > 0 else 0,
            "endpoints": self.endpoint_counts
        }


# Singleton metrics instance
metrics = MockMetrics()
