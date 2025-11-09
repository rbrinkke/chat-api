from fastapi import Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from app.core.exceptions import UnauthorizedError
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
            logger.warning("Token missing 'sub' claim")
            raise UnauthorizedError("Invalid authentication credentials")

        logger.debug(f"Authenticated user: {user_id}")
        return user_id

    except JWTError as e:
        logger.warning(f"JWT validation failed: {e}")
        raise UnauthorizedError("Invalid authentication credentials")


async def get_optional_user(
    authorization: str = Header(None)
) -> str | None:
    """
    Extract user_id from JWT token if present, otherwise return None.
    Used for endpoints that work both authenticated and unauthenticated.

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
