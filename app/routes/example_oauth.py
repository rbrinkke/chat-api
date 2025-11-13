"""
OAuth 2.0 Example Endpoints - Chat API

WORKING examples showing all OAuth validation patterns.
These endpoints can be tested immediately after setup.

Test with:
    # Get token from Auth API
    TOKEN=$(curl -s -X POST http://localhost:8000/oauth/token \
        -d "grant_type=client_credentials" \
        -d "client_id=test-client-1" \
        -d "client_secret=test-secret-1" \
        -d "scope=chat:read chat:write" | jq -r '.access_token')

    # Test endpoints
    curl http://localhost:8001/api/oauth/examples/public
    curl http://localhost:8001/api/oauth/examples/protected -H "Authorization: Bearer $TOKEN"
    curl http://localhost:8001/api/oauth/examples/scoped -H "Authorization: Bearer $TOKEN"
"""

from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.oauth_validator import (
    validate_oauth_token,
    require_scope,
    require_any_scope,
    require_all_scopes,
    get_optional_token,
    OAuthToken
)
from app.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/oauth/examples", tags=["OAuth Examples"])


# ============================================================================
# Response Models
# ============================================================================

class PublicResponse(BaseModel):
    """Public endpoint response."""
    message: str
    timestamp: datetime
    authenticated: bool


class ProtectedResponse(BaseModel):
    """Protected endpoint response."""
    message: str
    user_id: str
    scopes: list[str]
    org_id: Optional[str]
    timestamp: datetime


class MessageRequest(BaseModel):
    """Message creation request."""
    content: str
    channel_id: Optional[str] = None


class MessageResponse(BaseModel):
    """Message creation response."""
    message_id: str
    content: str
    user_id: str
    channel_id: Optional[str]
    created_at: datetime


# ============================================================================
# Example 1: Public Endpoint (No Authentication)
# ============================================================================

@router.get("/public", response_model=PublicResponse)
async def public_endpoint():
    """
    Public endpoint - accessible without authentication.

    This endpoint does NOT require OAuth token.
    Use this pattern for public APIs like health checks, public documentation, etc.

    Test:
        curl http://localhost:8001/api/oauth/examples/public
    """
    logger.info("public_endpoint_accessed")

    return PublicResponse(
        message="This is a public endpoint - no authentication required",
        timestamp=datetime.utcnow(),
        authenticated=False
    )


# ============================================================================
# Example 2: Protected Endpoint (Requires Valid Token)
# ============================================================================

@router.get("/protected", response_model=ProtectedResponse)
async def protected_endpoint(token: OAuthToken = Depends(validate_oauth_token)):
    """
    Protected endpoint - requires valid OAuth token.

    This endpoint validates the token but does NOT check scopes.
    Use this pattern when you need to know WHO is making the request,
    but don't care about specific permissions.

    Test:
        TOKEN=$(curl -s -X POST http://localhost:8000/oauth/token \
            -d "grant_type=client_credentials" \
            -d "client_id=test-client-1" \
            -d "client_secret=test-secret-1" \
            -d "scope=chat:read" | jq -r '.access_token')

        curl http://localhost:8001/api/oauth/examples/protected \
            -H "Authorization: Bearer $TOKEN"
    """
    logger.info(
        "protected_endpoint_accessed",
        user_id=token.user_id,
        scopes=token.scopes,
        org_id=token.org_id
    )

    return ProtectedResponse(
        message="Successfully authenticated! This endpoint requires a valid token.",
        user_id=token.user_id,
        scopes=token.scopes,
        org_id=token.org_id,
        timestamp=datetime.utcnow()
    )


# ============================================================================
# Example 3: Scope-Based Endpoint (Requires Specific Scope)
# ============================================================================

@router.get("/scoped/read", response_model=ProtectedResponse)
async def scoped_read_endpoint(token: OAuthToken = Depends(require_scope("chat:read"))):
    """
    Scope-based endpoint - requires "chat:read" scope.

    This endpoint requires the token to have the "chat:read" scope.
    Use this pattern for read operations that need permission checking.

    Test with correct scope:
        TOKEN=$(curl -s -X POST http://localhost:8000/oauth/token \
            -d "grant_type=client_credentials" \
            -d "client_id=test-client-1" \
            -d "client_secret=test-secret-1" \
            -d "scope=chat:read" | jq -r '.access_token')

        curl http://localhost:8001/api/oauth/examples/scoped/read \
            -H "Authorization: Bearer $TOKEN"

    Test without scope (will fail with 403):
        TOKEN=$(curl -s -X POST http://localhost:8000/oauth/token \
            -d "grant_type=client_credentials" \
            -d "client_id=test-client-1" \
            -d "client_secret=test-secret-1" \
            -d "scope=profile:read" | jq -r '.access_token')

        curl http://localhost:8001/api/oauth/examples/scoped/read \
            -H "Authorization: Bearer $TOKEN"
        # Returns: 403 Forbidden - Insufficient scope
    """
    logger.info(
        "scoped_read_endpoint_accessed",
        user_id=token.user_id,
        scopes=token.scopes
    )

    return ProtectedResponse(
        message="Successfully accessed read-scoped endpoint! Token has 'chat:read' scope.",
        user_id=token.user_id,
        scopes=token.scopes,
        org_id=token.org_id,
        timestamp=datetime.utcnow()
    )


@router.post("/scoped/write", response_model=MessageResponse)
async def scoped_write_endpoint(
    request: MessageRequest,
    token: OAuthToken = Depends(require_scope("chat:write"))
):
    """
    Scope-based endpoint - requires "chat:write" scope.

    This endpoint requires the token to have the "chat:write" scope.
    Use this pattern for write operations that need permission checking.

    Test:
        TOKEN=$(curl -s -X POST http://localhost:8000/oauth/token \
            -d "grant_type=client_credentials" \
            -d "client_id=test-client-1" \
            -d "client_secret=test-secret-1" \
            -d "scope=chat:write" | jq -r '.access_token')

        curl -X POST http://localhost:8001/api/oauth/examples/scoped/write \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d '{"content":"Hello OAuth!","channel_id":"general"}'
    """
    logger.info(
        "scoped_write_endpoint_accessed",
        user_id=token.user_id,
        scopes=token.scopes,
        content=request.content
    )

    # Simulate message creation
    message_id = f"msg_{token.user_id[:8]}_{int(datetime.utcnow().timestamp())}"

    return MessageResponse(
        message_id=message_id,
        content=request.content,
        user_id=token.user_id,
        channel_id=request.channel_id,
        created_at=datetime.utcnow()
    )


# ============================================================================
# Example 4: Multiple Scopes (Any)
# ============================================================================

@router.get("/scoped/any", response_model=ProtectedResponse)
async def any_scope_endpoint(
    token: OAuthToken = Depends(require_any_scope(["chat:read", "chat:write", "admin"]))
):
    """
    Multiple scopes endpoint - requires ANY of: chat:read, chat:write, or admin.

    This endpoint accepts tokens with ANY of the specified scopes.
    Use this pattern when multiple permission levels can access the same resource.

    Test with chat:read:
        TOKEN=$(curl -s -X POST http://localhost:8000/oauth/token \
            -d "grant_type=client_credentials" \
            -d "client_id=test-client-1" \
            -d "client_secret=test-secret-1" \
            -d "scope=chat:read" | jq -r '.access_token')

        curl http://localhost:8001/api/oauth/examples/scoped/any \
            -H "Authorization: Bearer $TOKEN"
        # Success! Has chat:read

    Test with admin:
        TOKEN=$(curl -s -X POST http://localhost:8000/oauth/token \
            -d "grant_type=client_credentials" \
            -d "client_id=test-client-1" \
            -d "client_secret=test-secret-1" \
            -d "scope=admin" | jq -r '.access_token')

        curl http://localhost:8001/api/oauth/examples/scoped/any \
            -H "Authorization: Bearer $TOKEN"
        # Success! Has admin
    """
    logger.info(
        "any_scope_endpoint_accessed",
        user_id=token.user_id,
        scopes=token.scopes
    )

    return ProtectedResponse(
        message="Successfully accessed! Token has at least one of: chat:read, chat:write, or admin.",
        user_id=token.user_id,
        scopes=token.scopes,
        org_id=token.org_id,
        timestamp=datetime.utcnow()
    )


# ============================================================================
# Example 5: Multiple Scopes (All Required)
# ============================================================================

@router.delete("/scoped/admin", response_model=ProtectedResponse)
async def admin_endpoint(
    token: OAuthToken = Depends(require_all_scopes(["chat:write", "admin"]))
):
    """
    Admin endpoint - requires BOTH "chat:write" AND "admin" scopes.

    This endpoint requires the token to have ALL specified scopes.
    Use this pattern for privileged operations that need multiple permissions.

    Test with both scopes (success):
        TOKEN=$(curl -s -X POST http://localhost:8000/oauth/token \
            -d "grant_type=client_credentials" \
            -d "client_id=test-client-1" \
            -d "client_secret=test-secret-1" \
            -d "scope=chat:write admin" | jq -r '.access_token')

        curl -X DELETE http://localhost:8001/api/oauth/examples/scoped/admin \
            -H "Authorization: Bearer $TOKEN"
        # Success! Has both scopes

    Test with only one scope (fails):
        TOKEN=$(curl -s -X POST http://localhost:8000/oauth/token \
            -d "grant_type=client_credentials" \
            -d "client_id=test-client-1" \
            -d "client_secret=test-secret-1" \
            -d "scope=admin" | jq -r '.access_token')

        curl -X DELETE http://localhost:8001/api/oauth/examples/scoped/admin \
            -H "Authorization: Bearer $TOKEN"
        # Returns: 403 Forbidden - Missing chat:write scope
    """
    logger.info(
        "admin_endpoint_accessed",
        user_id=token.user_id,
        scopes=token.scopes
    )

    return ProtectedResponse(
        message="Successfully accessed admin endpoint! Token has both 'chat:write' and 'admin' scopes.",
        user_id=token.user_id,
        scopes=token.scopes,
        org_id=token.org_id,
        timestamp=datetime.utcnow()
    )


# ============================================================================
# Example 6: Optional Authentication
# ============================================================================

@router.get("/optional", response_model=PublicResponse)
async def optional_auth_endpoint(token: Optional[OAuthToken] = Depends(get_optional_token)):
    """
    Optional authentication endpoint.

    This endpoint works both WITH and WITHOUT authentication.
    Use this pattern for endpoints that provide enhanced features for authenticated users
    but still work for anonymous users.

    Test without token (anonymous):
        curl http://localhost:8001/api/oauth/examples/optional
        # Returns: authenticated=false

    Test with token (authenticated):
        TOKEN=$(curl -s -X POST http://localhost:8000/oauth/token \
            -d "grant_type=client_credentials" \
            -d "client_id=test-client-1" \
            -d "client_secret=test-secret-1" \
            -d "scope=chat:read" | jq -r '.access_token')

        curl http://localhost:8001/api/oauth/examples/optional \
            -H "Authorization: Bearer $TOKEN"
        # Returns: authenticated=true
    """
    if token:
        logger.info(
            "optional_endpoint_accessed_authenticated",
            user_id=token.user_id,
            scopes=token.scopes
        )
        return PublicResponse(
            message=f"Welcome, authenticated user {token.user_id}! You have enhanced access.",
            timestamp=datetime.utcnow(),
            authenticated=True
        )
    else:
        logger.info("optional_endpoint_accessed_anonymous")
        return PublicResponse(
            message="Welcome, anonymous user! Sign in for enhanced features.",
            timestamp=datetime.utcnow(),
            authenticated=False
        )


# ============================================================================
# Example 7: Organization-Scoped Endpoint
# ============================================================================

@router.get("/org/{org_id}/messages", response_model=ProtectedResponse)
async def org_scoped_endpoint(
    org_id: str,
    token: OAuthToken = Depends(require_scope("chat:read"))
):
    """
    Organization-scoped endpoint.

    This endpoint validates that the user's token org_id matches the requested org_id.
    Use this pattern for multi-tenant applications where users can only access
    resources in their own organization.

    Test (will verify org_id matches token):
        TOKEN=$(curl -s -X POST http://localhost:8000/oauth/token \
            -d "grant_type=client_credentials" \
            -d "client_id=test-client-1" \
            -d "client_secret=test-secret-1" \
            -d "scope=chat:read" | jq -r '.access_token')

        # Extract org_id from token
        ORG_ID=$(echo $TOKEN | cut -d'.' -f2 | base64 -d | jq -r '.org_id')

        curl http://localhost:8001/api/oauth/examples/org/$ORG_ID/messages \
            -H "Authorization: Bearer $TOKEN"
        # Success! org_id matches

    Test with wrong org_id (will fail):
        curl http://localhost:8001/api/oauth/examples/org/wrong-org-id/messages \
            -H "Authorization: Bearer $TOKEN"
        # Returns: 403 Forbidden - Organization access denied
    """
    # Validate organization access
    if token.org_id != org_id:
        logger.warning(
            "org_access_denied",
            user_id=token.user_id,
            requested_org=org_id,
            user_org=token.org_id
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization access denied"
        )

    logger.info(
        "org_endpoint_accessed",
        user_id=token.user_id,
        org_id=org_id,
        scopes=token.scopes
    )

    return ProtectedResponse(
        message=f"Successfully accessed organization {org_id} messages!",
        user_id=token.user_id,
        scopes=token.scopes,
        org_id=token.org_id,
        timestamp=datetime.utcnow()
    )
