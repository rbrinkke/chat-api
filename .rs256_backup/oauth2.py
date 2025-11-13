"""
OAuth 2.0 Resource Server Middleware

Validates JWT access tokens locally using public keys from the Authorization Server.
No remote calls to Auth API during request handling = maximum performance.

Architecture Flow:
1. Extract Bearer token from Authorization header
2. Parse JWT header to get Key ID (kid)
3. Fetch public key from JWKS manager (cached, sub-ms)
4. Validate JWT signature, issuer, audience, expiration
5. Extract claims (user_id, org_id, permissions) from validated payload
6. Attach AuthContext to request.state for downstream use

Performance:
- <1ms overhead per request (all local operations)
- Zero network calls during request handling
- Scales to millions of requests/second

Security:
- Validates signature cryptographically (RS256)
- Validates issuer (prevents token from other systems)
- Validates audience (prevents token reuse across services)
- Validates expiration (prevents replay attacks)
- Fail-closed by default (invalid token = 401)

Usage:
    # In main.py
    from app.middleware.oauth2 import OAuth2Middleware
    app.add_middleware(OAuth2Middleware)

    # In routes
    def my_route(request: Request):
        auth = request.state.auth  # AuthContext with user_id, org_id, permissions
        user_id = auth.user_id
        if "groups:read" in auth.permissions:
            ...
"""

from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.datastructures import Headers
from jose import jwt, JWTError, ExpiredSignatureError
from jose.exceptions import JWKError

from app.config import settings
from app.core.jwks_manager import get_jwks_manager
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class AuthContext:
    """
    Authentication context extracted from validated JWT.

    This is the ONLY source of auth data for the application.
    All authorization decisions are made based on these claims.

    Attributes:
        user_id: UUID of authenticated user (from 'sub' claim)
        org_id: UUID of user's current organization
        username: Optional username
        email: Optional email address
        permissions: List of granted permissions (e.g., ['groups:read', 'chat:send'])
        roles: Optional list of roles (e.g., ['admin', 'member'])
        token_exp: Token expiration timestamp
        token_iat: Token issued-at timestamp
        raw_payload: Full JWT payload (for advanced use cases)
    """

    def __init__(self, payload: dict):
        # Required claims
        self.user_id: str = payload["sub"]
        self.org_id: str = payload["org_id"]

        # Optional claims
        self.username: Optional[str] = payload.get("username")
        self.email: Optional[str] = payload.get("email")
        self.permissions: list[str] = payload.get("permissions", [])
        self.roles: list[str] = payload.get("roles", [])

        # Token metadata
        self.token_exp: Optional[int] = payload.get("exp")
        self.token_iat: Optional[int] = payload.get("iat")

        # Raw payload for debugging/advanced use
        self.raw_payload: dict = payload

    def has_permission(self, permission: str) -> bool:
        """Check if user has specific permission"""
        return permission in self.permissions

    def has_any_permission(self, *permissions: str) -> bool:
        """Check if user has any of the specified permissions"""
        return any(p in self.permissions for p in permissions)

    def has_all_permissions(self, *permissions: str) -> bool:
        """Check if user has all specified permissions"""
        return all(p in self.permissions for p in permissions)

    def has_role(self, role: str) -> bool:
        """Check if user has specific role"""
        return role in self.roles

    def __repr__(self) -> str:
        return (
            f"AuthContext(user_id={self.user_id}, org_id={self.org_id}, "
            f"permissions_count={len(self.permissions)})"
        )


class OAuth2Middleware(BaseHTTPMiddleware):
    """
    OAuth 2.0 Bearer Token validation middleware.

    Validates JWT access tokens against Authorization Server's public keys.
    Implements RFC 6750 (Bearer Token) and RFC 7519 (JWT).

    Public Endpoints (No Auth Required):
    - /health
    - /metrics
    - /docs, /redoc, /openapi.json
    - /test-chat (test UI)

    All other endpoints require valid Bearer token.
    """

    # Endpoints that don't require authentication
    PUBLIC_PATHS = {
        "/health",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/test-chat"
    }

    async def dispatch(self, request: Request, call_next):
        """Process request and validate JWT if present"""

        # Skip auth for public endpoints
        if self._is_public_path(request.url.path):
            logger.debug("oauth2_public_path", path=request.url.path)
            return await call_next(request)

        # Extract token
        token = self._extract_token(request.headers)

        if not token:
            logger.warning(
                "oauth2_missing_token",
                path=request.url.path,
                method=request.method
            )
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Missing authentication token",
                    "error": "unauthorized",
                    "message": "Authorization header with Bearer token required"
                },
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Validate token and extract auth context
        try:
            auth_context = await self._validate_token(token, request)

            # Attach to request state
            request.state.auth = auth_context
            request.state.user_id = auth_context.user_id  # Backward compatibility
            request.state.org_id = auth_context.org_id

            logger.debug(
                "oauth2_token_valid",
                user_id=auth_context.user_id,
                org_id=auth_context.org_id,
                permission_count=len(auth_context.permissions),
                path=request.url.path
            )

            # Continue to route handler
            response = await call_next(request)
            return response

        except ExpiredSignatureError:
            logger.warning(
                "oauth2_token_expired",
                path=request.url.path,
                method=request.method
            )
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Token has expired",
                    "error": "token_expired",
                    "message": "Please obtain a new access token"
                },
                headers={"WWW-Authenticate": "Bearer"}
            )

        except JWTError as e:
            logger.warning(
                "oauth2_invalid_token",
                error=str(e),
                error_type=type(e).__name__,
                path=request.url.path,
                method=request.method
            )
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Invalid token",
                    "error": "invalid_token",
                    "message": str(e)
                },
                headers={"WWW-Authenticate": "Bearer"}
            )

        except JWKError as e:
            logger.error(
                "oauth2_jwk_error",
                error=str(e),
                path=request.url.path,
                message="Public key not found - possible key rotation"
            )
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Token validation failed",
                    "error": "invalid_token",
                    "message": "Unable to validate token signature"
                },
                headers={"WWW-Authenticate": "Bearer"}
            )

        except KeyError as e:
            logger.error(
                "oauth2_missing_claim",
                missing_claim=str(e),
                path=request.url.path,
                message="Token missing required claim"
            )
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Invalid token claims",
                    "error": "invalid_token",
                    "message": f"Token missing required claim: {e}"
                },
                headers={"WWW-Authenticate": "Bearer"}
            )

        except Exception as e:
            logger.error(
                "oauth2_unexpected_error",
                error=str(e),
                error_type=type(e).__name__,
                path=request.url.path,
                exc_info=True
            )
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal authentication error",
                    "error": "internal_error"
                }
            )

    def _is_public_path(self, path: str) -> bool:
        """Check if path is public (no auth required)"""
        # Exact match
        if path in self.PUBLIC_PATHS:
            return True

        # Prefix match for /docs variants
        if path.startswith("/docs") or path.startswith("/redoc"):
            return True

        return False

    def _extract_token(self, headers: Headers) -> Optional[str]:
        """
        Extract Bearer token from Authorization header.

        Expected format: "Authorization: Bearer <token>"

        Returns:
            Token string or None if not present/invalid format
        """
        auth_header = headers.get("Authorization")

        if not auth_header:
            return None

        parts = auth_header.split()

        if len(parts) != 2:
            logger.debug("oauth2_malformed_header", header_parts=len(parts))
            return None

        scheme, token = parts

        if scheme.lower() != "bearer":
            logger.debug("oauth2_wrong_scheme", scheme=scheme)
            return None

        return token

    async def _validate_token(self, token: str, request: Request) -> AuthContext:
        """
        Validate JWT token and extract claims.

        Validation Steps:
        1. Parse JWT header (unverified) to get Key ID
        2. Fetch public key from JWKS manager
        3. Decode and validate signature
        4. Validate standard claims (iss, aud, exp)
        5. Extract custom claims (org_id, permissions)
        6. Return AuthContext

        Args:
            token: JWT access token
            request: Request object (for correlation ID logging)

        Returns:
            AuthContext with validated claims

        Raises:
            JWTError: Invalid token
            JWKError: Key not found
            KeyError: Missing required claim
        """
        # Step 1: Get Key ID from token header (unverified)
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")

        if not kid:
            raise JWTError("Token header missing 'kid' (Key ID)")

        # Step 2: Get public key from JWKS manager (cached, fast!)
        jwks_manager = await get_jwks_manager()
        public_key = await jwks_manager.get_key(kid)

        # Step 3: Decode and validate JWT
        # This validates:
        # - Signature (cryptographic)
        # - Issuer (iss claim)
        # - Audience (aud claim)
        # - Expiration (exp claim)
        # - Not before (nbf claim, if present)
        payload = jwt.decode(
            token,
            public_key,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.AUTH_API_ISSUER,
            audience=settings.JWT_AUDIENCE,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": True,
                "verify_iss": True,
                "require_exp": True,
                "require_sub": True,  # Require user ID
            }
        )

        # Step 4: Validate required custom claims
        if "org_id" not in payload:
            raise KeyError("org_id")

        # Step 5: Create AuthContext
        auth_context = AuthContext(payload)

        # Log successful validation
        correlation_id = getattr(request.state, "correlation_id", None)
        logger.info(
            "oauth2_token_validated",
            user_id=auth_context.user_id,
            org_id=auth_context.org_id,
            kid=kid,
            permissions_count=len(auth_context.permissions),
            roles_count=len(auth_context.roles),
            correlation_id=correlation_id
        )

        return auth_context


# Backward compatibility: Export under old name
# TODO: Remove after migration complete
JWTMiddleware = OAuth2Middleware
