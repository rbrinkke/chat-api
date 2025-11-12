"""
JWT Token Generation Utilities for RBAC Testing

Provides pytest fixtures and utility functions for generating valid and invalid
JWT tokens for comprehensive RBAC testing.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import jwt
import pytest


# Test JWT secret (must match app config for testing)
TEST_JWT_SECRET = "dev-secret-key-change-in-production"
TEST_JWT_ALGORITHM = "HS256"


def generate_token(
    user_id: str,
    org_id: Optional[str] = None,
    expires_in_hours: int = 1,
    extra_claims: Optional[Dict[str, Any]] = None
) -> str:
    """
    Generate a JWT token for testing

    Args:
        user_id: User ID (sub claim)
        org_id: Organization ID (optional, for backward compat testing)
        expires_in_hours: Token expiration time (can be negative for expired tokens)
        extra_claims: Additional claims to include in token

    Returns:
        Encoded JWT token string
    """
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(hours=expires_in_hours)
    }

    # Add org_id if provided (some tests need tokens without it)
    if org_id is not None:
        payload["org_id"] = org_id

    # Merge extra claims
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, TEST_JWT_SECRET, algorithm=TEST_JWT_ALGORITHM)


# =============================================================================
# Standard Test User Tokens
# =============================================================================

@pytest.fixture
def jwt_secret():
    """JWT secret for testing (matches config)"""
    return TEST_JWT_SECRET


@pytest.fixture
def valid_token():
    """
    Generate valid JWT token with standard claims

    User: test-user-123
    Org: org-test-1
    Permissions: chat:read, chat:send_message (configured in Auth API mock)
    """
    return generate_token(
        user_id="test-user-123",
        org_id="org-test-1",
        extra_claims={
            "username": "testuser",
            "email": "test@example.com"
        }
    )


@pytest.fixture
def admin_token():
    """
    Token for user with admin permissions

    User: admin-user-456
    Org: org-test-1
    Permissions: ALL (chat:*, dashboard:*)
    """
    return generate_token(
        user_id="admin-user-456",
        org_id="org-test-1",
        extra_claims={
            "username": "admin",
            "email": "admin@example.com",
            "is_admin": True
        }
    )


@pytest.fixture
def read_only_token():
    """
    Token for user with read-only permissions

    User: reader-user-789
    Org: org-test-1
    Permissions: chat:read ONLY
    """
    return generate_token(
        user_id="reader-user-789",
        org_id="org-test-1",
        extra_claims={
            "username": "reader",
            "email": "reader@example.com"
        }
    )


@pytest.fixture
def writer_token():
    """
    Token for user with write permissions

    User: writer-user-999
    Org: org-test-2 (different org!)
    Permissions: chat:read, chat:send_message, chat:delete
    """
    return generate_token(
        user_id="writer-user-999",
        org_id="org-test-2",
        extra_claims={
            "username": "writer",
            "email": "writer@example.com"
        }
    )


# =============================================================================
# Invalid/Security Test Tokens
# =============================================================================

@pytest.fixture
def expired_token():
    """Token that has already expired (1 hour ago)"""
    return generate_token(
        user_id="test-user-123",
        org_id="org-test-1",
        expires_in_hours=-1  # Expired 1 hour ago
    )


@pytest.fixture
def no_org_token():
    """
    Token without org_id (backward compatibility test)

    Should default to "default-org" with warning log
    """
    return generate_token(
        user_id="legacy-user-888",
        org_id=None,  # Explicitly no org_id
        extra_claims={
            "username": "legacy",
            "email": "legacy@example.com"
        }
    )


@pytest.fixture
def missing_sub_token(jwt_secret):
    """Token without 'sub' claim (invalid)"""
    payload = {
        "org_id": "org-test-1",
        "username": "nosubuser",
        "exp": datetime.utcnow() + timedelta(hours=1)
        # Note: no 'sub' claim!
    }
    return jwt.encode(payload, jwt_secret, algorithm=TEST_JWT_ALGORITHM)


@pytest.fixture
def tampered_token(valid_token):
    """
    Token with tampered signature

    Takes a valid token and modifies the last character to break signature
    """
    return valid_token[:-1] + ("X" if valid_token[-1] != "X" else "Y")


@pytest.fixture
def malformed_token():
    """Completely malformed JWT (not 3 parts)"""
    return "not.a.valid.jwt.token"


@pytest.fixture
def sql_injection_token(jwt_secret):
    """
    Token with SQL injection payload in claims

    Tests that claims are properly sanitized
    """
    payload = {
        "sub": "user-123",
        "org_id": "org-456' OR '1'='1",  # SQL injection attempt
        "username": "admin'--",
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    return jwt.encode(payload, jwt_secret, algorithm=TEST_JWT_ALGORITHM)


@pytest.fixture
def xss_injection_token(jwt_secret):
    """
    Token with XSS payload in claims

    Tests that claims are properly escaped in output
    """
    payload = {
        "sub": "user-123",
        "org_id": "org-456",
        "username": "<script>alert('XSS')</script>",
        "email": "user@example.com<img src=x onerror=alert('XSS')>",
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    return jwt.encode(payload, jwt_secret, algorithm=TEST_JWT_ALGORITHM)


# =============================================================================
# Multi-User Test Scenarios
# =============================================================================

@pytest.fixture
def org1_users():
    """Generate multiple tokens for org-test-1 users"""
    return {
        "admin": generate_token("admin-user-456", "org-test-1"),
        "user": generate_token("test-user-123", "org-test-1"),
        "reader": generate_token("reader-user-789", "org-test-1")
    }


@pytest.fixture
def org2_users():
    """Generate multiple tokens for org-test-2 users"""
    return {
        "writer": generate_token("writer-user-999", "org-test-2"),
        "another_user": generate_token("user-888", "org-test-2")
    }


@pytest.fixture
def cross_org_tokens(org1_users, org2_users):
    """
    Tokens from different organizations for cross-org access testing

    Tests that users cannot access other organizations' resources
    """
    return {
        "org1": org1_users,
        "org2": org2_users
    }


# =============================================================================
# Token Validation Helpers
# =============================================================================

def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode JWT token without verification (for testing)

    Args:
        token: JWT token string

    Returns:
        Decoded payload dictionary
    """
    return jwt.decode(
        token,
        TEST_JWT_SECRET,
        algorithms=[TEST_JWT_ALGORITHM],
        options={"verify_signature": False}
    )


def is_token_expired(token: str) -> bool:
    """
    Check if token is expired

    Args:
        token: JWT token string

    Returns:
        True if token is expired, False otherwise
    """
    try:
        payload = decode_token(token)
        exp = datetime.fromtimestamp(payload["exp"])
        return datetime.utcnow() > exp
    except Exception:
        return True


# =============================================================================
# Performance Test Token Generators
# =============================================================================

def generate_bulk_tokens(count: int, org_id: str = "org-load-test") -> list[str]:
    """
    Generate multiple tokens for load testing

    Args:
        count: Number of tokens to generate
        org_id: Organization ID for all tokens

    Returns:
        List of JWT token strings
    """
    return [
        generate_token(
            user_id=f"load-test-user-{i}",
            org_id=org_id,
            extra_claims={"username": f"loaduser{i}"}
        )
        for i in range(count)
    ]


@pytest.fixture
def load_test_tokens():
    """Generate 100 tokens for load testing"""
    return generate_bulk_tokens(100)


# =============================================================================
# WebSocket Test Tokens
# =============================================================================

@pytest.fixture
def websocket_valid_token():
    """
    Token specifically for WebSocket testing

    Has chat:read permission for WebSocket connection
    """
    return generate_token(
        user_id="ws-user-123",
        org_id="org-test-1",
        extra_claims={
            "username": "wsuser",
            "email": "ws@example.com"
        }
    )


@pytest.fixture
def websocket_insufficient_token():
    """
    Token without chat:read permission (WebSocket should reject)
    """
    return generate_token(
        user_id="ws-no-read-456",
        org_id="org-test-1",
        extra_claims={
            "username": "noreaduser",
            "email": "noread@example.com"
        }
    )


# =============================================================================
# Circuit Breaker Test Tokens
# =============================================================================

@pytest.fixture
def circuit_breaker_test_tokens():
    """
    Generate tokens for circuit breaker testing

    Returns dict with tokens for different test scenarios
    """
    return {
        "valid": generate_token("cb-user-1", "org-test-1"),
        "cached": generate_token("cb-user-2", "org-test-1"),  # Will be cached
        "uncached": generate_token("cb-user-3", "org-test-1"),  # Not cached
    }
