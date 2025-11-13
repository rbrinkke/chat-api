from fastapi import Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from app.core.exceptions import UnauthorizedError
from app.core.authorization import AuthContext
from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """
    Extract and validate JWT token, return user_id.

    Args:
        credentials: HTTP Bearer token from Authorization header

    Returns:
        str: User ID from JWT token

    Raises:
        UnauthorizedError: If token is invalid or missing
    """
    token = credentials.credentials

    try:
        # Decode JWT token
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )

        # Extract user_id from payload
        user_id: str = payload.get("sub")
        if user_id is None:
            logger.warning("token_missing_sub_claim", message="Token missing 'sub' claim")
            raise UnauthorizedError("Invalid authentication credentials")

        # Log expiration info for debugging
        exp_timestamp = payload.get("exp")
        if exp_timestamp:
            from datetime import datetime
            exp_datetime = datetime.fromtimestamp(exp_timestamp)
            time_until_expiry = (exp_datetime - datetime.utcnow()).total_seconds()

            logger.debug(
                "user_authenticated",
                user_id=user_id,
                token_expires_in_seconds=round(time_until_expiry, 0)
            )
        else:
            logger.debug("user_authenticated", user_id=user_id)

        return user_id

    except JWTError as e:
        logger.warning(
            "jwt_validation_failed",
            error_type=type(e).__name__,
            error=str(e),
            message="JWT token validation failed"
        )
        raise UnauthorizedError("Invalid authentication credentials")


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> AuthContext:
    """
    Extract full authentication context from JWT token.

    NEW: Returns AuthContext with user_id AND org_id for RBAC.

    JWT Payload Structure:
        {
            "sub": "user-123",           # user_id (REQUIRED)
            "org_id": "org-456",         # organization_id (REQUIRED for RBAC)
            "username": "john",          # optional
            "email": "john@example.com", # optional
            "exp": 1234567890            # expiration
        }

    Args:
        credentials: HTTP Bearer token from Authorization header

    Returns:
        AuthContext: Full authentication context

    Raises:
        UnauthorizedError: If token is invalid or missing required claims
    """
    token = credentials.credentials

    try:
        # Decode JWT token
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )

        # Extract required claims
        user_id: str = payload.get("sub")
        if user_id is None:
            logger.warning("Token missing 'sub' claim")
            raise UnauthorizedError("Invalid authentication credentials: missing user_id")

        org_id: str = payload.get("org_id")

        # Backward compatibility: If org_id missing, use default
        if org_id is None:
            logger.warning(
                "token_missing_org_id",
                user_id=user_id,
                message="Token missing 'org_id' claim - using default. Update Auth API to include org_id in tokens."
            )
            # Use a default org_id for legacy tokens
            org_id = "default-org"

            # FUTURE: Uncomment to enforce org_id requirement (after Auth API migration)
            # raise UnauthorizedError("Invalid authentication credentials: missing org_id")

        # Extract optional claims
        username = payload.get("username")
        email = payload.get("email")

        context = AuthContext(
            user_id=user_id,
            org_id=org_id,
            username=username,
            email=email
        )

        # Extract token expiration for debugging
        exp_timestamp = payload.get("exp")
        if exp_timestamp:
            from datetime import datetime
            exp_datetime = datetime.fromtimestamp(exp_timestamp)
            time_until_expiry = (exp_datetime - datetime.utcnow()).total_seconds()

            logger.debug(
                "auth_context_extracted",
                user_id=context.user_id,
                org_id=context.org_id,
                username=context.username,
                token_expires_in_seconds=round(time_until_expiry, 0),
                token_expiry_time=exp_datetime.isoformat()
            )
        else:
            logger.debug(
                "auth_context_extracted",
                user_id=context.user_id,
                org_id=context.org_id,
                username=context.username
            )

        return context

    except JWTError as e:
        logger.warning(
            "jwt_validation_failed_auth_context",
            error_type=type(e).__name__,
            error=str(e),
            message="JWT token validation failed during auth context extraction"
        )
        raise UnauthorizedError("Invalid authentication credentials")


async def get_optional_user(
    authorization: str = Header(None)
) -> str | None:
    """
    Extract user_id from JWT token if present, otherwise return None.
    Used for endpoints that work both authenticated and unauthenticated.

    LEGACY: For backward compatibility. New code should use get_auth_context().

    Args:
        authorization: Optional Authorization header

    Returns:
        str | None: User ID if authenticated, None otherwise
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None

    token = authorization.replace("Bearer ", "")

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )
        user_id: str = payload.get("sub")
        return user_id
    except JWTError:
        return None
