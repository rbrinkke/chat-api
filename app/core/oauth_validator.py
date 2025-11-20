"""
OAuth 2.0 Token Validator for Chat API

Validates JWT tokens issued by Auth API OAuth 2.0 Authorization Server.
Uses HS256 (shared secret) - NO JWKS endpoint needed.

Auth API must share the same JWT_SECRET_KEY with Chat API.
"""

import os
from typing import List, Optional
from datetime import datetime, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.core.logging_config import get_logger
from app.config import settings

logger = get_logger(__name__)

# ============================================================================
# Configuration (from environment variables)
# ============================================================================

JWT_SECRET_KEY = settings.JWT_SECRET_KEY
JWT_ALGORITHM = settings.JWT_ALGORITHM
AUTH_API_URL = settings.AUTH_API_URL



security = HTTPBearer()


# ============================================================================
# OAuth Token Model
# ============================================================================

class OAuthToken(BaseModel):
    """
    OAuth 2.0 access token payload.

    Attributes:
        user_id (str): User UUID from 'sub' claim
        client_id (str): OAuth client ID
        scopes (List[str]): List of granted scopes
        org_id (Optional[str]): Organization UUID
        token_id (str): Unique token ID from 'jti' claim
        issued_at (datetime): Token issuance time
        expires_at (datetime): Token expiration time
    """
    user_id: str
    client_id: str
    scopes: List[str]
    org_id: Optional[str] = None
    token_id: Optional[str] = None  # Only refresh tokens have jti
    issued_at: datetime
    expires_at: datetime

    @classmethod
    def from_jwt_payload(cls, payload: dict) -> "OAuthToken":
        """Create OAuthToken from JWT payload."""
        return cls(
            user_id=payload["sub"],
            client_id=payload.get("client_id", "unknown"),
            scopes=payload.get("scope", "").split(),
            org_id=payload.get("org_id"),
            token_id=payload.get("jti"),  # Optional - only refresh tokens have jti
            issued_at=datetime.fromtimestamp(payload["iat"], tz=timezone.utc) if "iat" in payload else datetime.now(tz=timezone.utc),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        )

    def has_scope(self, required_scope: str) -> bool:
        """Check if token has a specific scope."""
        return required_scope in self.scopes

    def has_any_scope(self, required_scopes: List[str]) -> bool:
        """Check if token has ANY of the required scopes."""
        return any(scope in self.scopes for scope in required_scopes)

    def has_all_scopes(self, required_scopes: List[str]) -> bool:
        """Check if token has ALL of the required scopes."""
        return all(scope in self.scopes for scope in required_scopes)


# ============================================================================
# Token Validation
# ============================================================================

def decode_token_string(token: str) -> OAuthToken:
    """
    Decodes and validates a raw JWT token string.
    This is used for non-HTTP-header authentication (e.g., WebSocket query param).

    Args:
        token: Raw JWT string.

    Returns:
        OAuthToken: Parsed and validated token object.

    Raises:
        jwt.InvalidTokenError: If token is invalid, expired, or wrong type.
        jwt.ExpiredSignatureError: If token is expired.
    """
    try:
        # Decode and validate JWT token
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={
                "verify_exp": True,  # Verify expiration
                "verify_iat": True,  # Verify issued_at
                "verify_signature": True,  # Verify signature
                "verify_aud": False  # Skip audience validation (accept any audience)
            }
        )
    except jwt.ExpiredSignatureError:
        logger.warning("oauth_token_expired")
        raise
    except jwt.InvalidTokenError:
        logger.warning("oauth_token_invalid")
        raise

    # Validate token type (must be "access" not "refresh")
    if payload.get("type") != "access":
        logger.warning(
            "oauth_invalid_token_type",
            token_type=payload.get("type"),
            expected="access"
        )
        raise jwt.InvalidTokenError("Invalid token type")

    # Create OAuthToken object
    oauth_token = OAuthToken.from_jwt_payload(payload)

    logger.debug(
        "oauth_token_decoded_raw",
        user_id=oauth_token.user_id,
        client_id=oauth_token.client_id,
        scopes=oauth_token.scopes,
        source="raw_string_decode"
    )

    return oauth_token


def validate_oauth_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> OAuthToken:
    """
    Validate OAuth 2.0 access token from Authorization header.

    Usage:
        @app.get("/api/v1/messages")
        async def get_messages(token: OAuthToken = Depends(validate_oauth_token)):
            user_id = token.user_id
            return {"messages": [...]}

    Raises:
        HTTPException: 401 if token is invalid, expired, or wrong type
    """
    token = credentials.credentials

    try:
        # Decode and validate JWT token
        # Note: We skip audience validation as Chat API accepts tokens for any audience
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={
                "verify_exp": True,  # Verify expiration
                "verify_iat": True,  # Verify issued_at
                "verify_signature": True,  # Verify signature
                "verify_aud": False  # Skip audience validation (accept any audience)
            }
        )

        # Validate token type (must be "access" not "refresh")
        if payload.get("type") != "access":
            logger.warning(
                "oauth_invalid_token_type",
                token_type=payload.get("type"),
                expected="access"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )

        # Create OAuthToken object
        oauth_token = OAuthToken.from_jwt_payload(payload)

        logger.info(
            "oauth_token_validated",
            user_id=oauth_token.user_id,
            client_id=oauth_token.client_id,
            scopes=oauth_token.scopes,
            org_id=oauth_token.org_id
        )

        return oauth_token

    except jwt.ExpiredSignatureError:
        logger.warning("oauth_token_expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError as e:
        logger.warning("oauth_token_invalid", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )


# ============================================================================
# Scope-Based Authorization
# ============================================================================

def require_scope(required_scope: str):
    """
    Require a specific OAuth scope.

    Usage:
        @app.post("/api/v1/messages")
        async def create_message(token: OAuthToken = Depends(require_scope("chat:write"))):
            return {"status": "created"}

    Raises:
        HTTPException: 403 if token lacks required scope
    """
    def scope_checker(token: OAuthToken = Depends(validate_oauth_token)) -> OAuthToken:
        # User tokens (no scopes) are automatically authorized for all operations
        # Only service tokens (with scopes) need scope validation
        if token.scopes and not token.has_scope(required_scope):
            logger.warning(
                "oauth_insufficient_scope",
                user_id=token.user_id,
                required_scope=required_scope,
                available_scopes=token.scopes
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient scope: '{required_scope}' required"
            )
        return token

    return scope_checker


def require_any_scope(required_scopes: List[str]):
    """
    Require ANY of the specified OAuth scopes.

    Usage:
        @app.get("/api/v1/messages")
        async def get_messages(
            token: OAuthToken = Depends(require_any_scope(["chat:read", "admin"]))
        ):
            return {"messages": [...]}

    Raises:
        HTTPException: 403 if token lacks all required scopes
    """
    def scope_checker(token: OAuthToken = Depends(validate_oauth_token)) -> OAuthToken:
        if not token.has_any_scope(required_scopes):
            logger.warning(
                "oauth_insufficient_scope_any",
                user_id=token.user_id,
                required_scopes=required_scopes,
                available_scopes=token.scopes
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient scope: one of {required_scopes} required"
            )
        return token

    return scope_checker


def require_all_scopes(required_scopes: List[str]):
    """
    Require ALL of the specified OAuth scopes.

    Usage:
        @app.post("/api/v1/admin/messages")
        async def admin_action(
            token: OAuthToken = Depends(require_all_scopes(["chat:write", "admin"]))
        ):
            return {"status": "executed"}

    Raises:
        HTTPException: 403 if token lacks any required scope
    """
    def scope_checker(token: OAuthToken = Depends(validate_oauth_token)) -> OAuthToken:
        if not token.has_all_scopes(required_scopes):
            logger.warning(
                "oauth_insufficient_scope_all",
                user_id=token.user_id,
                required_scopes=required_scopes,
                available_scopes=token.scopes
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient scope: all of {required_scopes} required"
            )
        return token

    return scope_checker


# ============================================================================
# Optional Token (for public endpoints with optional authentication)
# ============================================================================

def get_optional_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Optional[OAuthToken]:
    """
    Get OAuth token if provided, None otherwise.

    Usage:
        @app.get("/api/v1/public/messages")
        async def get_public_messages(token: Optional[OAuthToken] = Depends(get_optional_token)):
            if token:
                # Authenticated request - return user-specific data
                return {"messages": [...], "user_id": token.user_id}
            else:
                # Anonymous request - return public data only
                return {"messages": [...]}
    """
    if not credentials:
        return None

    try:
        return validate_oauth_token(credentials)
    except HTTPException:
        # Invalid token - treat as anonymous
        return None
