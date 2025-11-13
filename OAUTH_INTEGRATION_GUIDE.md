# OAuth 2.0 Integration Guide for Chat API

**Date:** 2025-11-12
**Auth API:** https://github.com/rbrinkke/auth-api
**Status:** ✅ Auth API OAuth 2.0 Ready (23/23 tests passing)

---

## 🎯 Overview

This guide explains how Chat API can authenticate users and validate tokens from Auth API's OAuth 2.0 Authorization Server.

**Architecture:**
```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   Frontend   │─────▶│   Auth API   │      │   Chat API   │
│  (User/App)  │      │  OAuth Server│◀─────│  (Resource)  │
└──────────────┘      └──────────────┘      └──────────────┘
   1. Login            2. Issues Token       3. Validates Token
```

---

## 🔑 Token Validation Strategy

Auth API uses **HS256 (symmetric)** JWT tokens with a **shared secret**. This is the **recommended approach** for internal microservices.

### Why HS256 is Perfect Here

✅ **Faster** - No asymmetric crypto overhead
✅ **Simpler** - No JWKS endpoint needed
✅ **Secure** - When JWT_SECRET_KEY is properly protected
✅ **RFC Compliant** - OAuth 2.0 doesn't mandate RS256

**Auth API and Chat API share the same JWT_SECRET_KEY for validation.**

---

## 📋 Prerequisites

### 1. Environment Variables

Add to Chat API's `.env` file:

```bash
# OAuth 2.0 Configuration
AUTH_API_URL=http://auth-api:8000
JWT_SECRET_KEY=<SAME_SECRET_AS_AUTH_API>
JWT_ALGORITHM=HS256

# Optional: OAuth Client Registration (if Chat API acts as OAuth client)
OAUTH_CLIENT_ID=chat-api-service
OAUTH_CLIENT_SECRET=<your-client-secret>
```

⚠️ **CRITICAL**: `JWT_SECRET_KEY` must be **EXACTLY** the same as Auth API's secret.

### 2. Test Users Available

Auth API has 10 pre-configured test users ready to use:

```bash
# View credentials
cd /mnt/d/activity/auth-api
./test_oauth.sh --show-users
```

**Example test user:**
- Email: `grace.oauth@yahoo.com`
- Password: `OAuth!Testing321`
- Role: `oauth_client` (dedicated for OAuth testing)

See `auth-api/TEST_USERS_CREDENTIALS.md` for full list.

---

## 🔐 Implementation Guide

### Step 1: Install Dependencies

```bash
# For Python/FastAPI Chat API
pip install pyjwt[crypto] httpx

# Add to requirements.txt
pyjwt[crypto]==2.8.0
httpx==0.26.0
```

### Step 2: Create Token Validation Utility

Create `app/core/oauth_validator.py`:

```python
"""
OAuth 2.0 Token Validation for Chat API
Validates access tokens issued by Auth API's OAuth Authorization Server
"""

import jwt
from typing import Optional, Dict
from datetime import datetime, timezone
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Environment configuration
JWT_SECRET_KEY = "your-shared-secret"  # Must match Auth API
JWT_ALGORITHM = "HS256"
AUTH_API_URL = "http://auth-api:8000"

security = HTTPBearer()


class OAuthToken:
    """Parsed OAuth 2.0 access token"""

    def __init__(self, payload: Dict):
        self.user_id: str = payload.get("sub")
        self.client_id: str = payload.get("client_id")
        self.scopes: list = payload.get("scope", "").split()
        self.org_id: Optional[str] = payload.get("org_id")
        self.audience: list = payload.get("aud", [])
        self.issued_at: int = payload.get("iat")
        self.expires_at: int = payload.get("exp")
        self.jti: str = payload.get("jti")  # JWT ID (for revocation)

    def has_scope(self, required_scope: str) -> bool:
        """Check if token has required scope"""
        return required_scope in self.scopes

    def has_any_scope(self, *required_scopes: str) -> bool:
        """Check if token has any of the required scopes"""
        return any(scope in self.scopes for scope in required_scopes)

    def has_all_scopes(self, *required_scopes: str) -> bool:
        """Check if token has all required scopes"""
        return all(scope in self.scopes for scope in required_scopes)


def validate_oauth_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> OAuthToken:
    """
    Validate OAuth 2.0 access token from Authorization header.

    Usage in FastAPI route:
        @app.get("/protected")
        async def protected_route(token: OAuthToken = Depends(validate_oauth_token)):
            return {"user_id": token.user_id, "scopes": token.scopes}

    Raises:
        HTTPException: 401 if token invalid/expired, 403 if insufficient scope
    """
    token = credentials.credentials

    try:
        # Decode and validate JWT
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={"verify_exp": True}  # Verify expiration
        )

        # Validate token type
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type (expected 'access' token)"
            )

        # Validate audience (optional - check if chat-api is in audience)
        audience = payload.get("aud", [])
        if audience and "https://api.activity.com" not in audience:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token not intended for this service"
            )

        return OAuthToken(payload)

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"}
        )


def require_scope(*required_scopes: str):
    """
    Dependency factory for scope-based authorization.

    Usage:
        @app.get("/messages", dependencies=[Depends(require_scope("chat:read"))])
        async def get_messages():
            return {"messages": [...]}
    """
    def scope_checker(token: OAuthToken = Depends(validate_oauth_token)) -> OAuthToken:
        if not token.has_all_scopes(*required_scopes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient scope. Required: {', '.join(required_scopes)}"
            )
        return token
    return scope_checker
```

### Step 3: Protect Chat API Endpoints

```python
from fastapi import FastAPI, Depends
from app.core.oauth_validator import validate_oauth_token, require_scope, OAuthToken

app = FastAPI()


# Example 1: Basic token validation
@app.get("/api/v1/chat/messages")
async def get_messages(token: OAuthToken = Depends(validate_oauth_token)):
    """
    Get chat messages for authenticated user.
    Requires valid OAuth 2.0 access token.
    """
    return {
        "user_id": token.user_id,
        "messages": [
            {"id": 1, "text": "Hello!", "user_id": token.user_id}
        ]
    }


# Example 2: Require specific scope
@app.post("/api/v1/chat/messages")
async def send_message(
    message: dict,
    token: OAuthToken = Depends(require_scope("chat:write"))
):
    """
    Send a chat message.
    Requires 'chat:write' scope.
    """
    return {
        "message_id": 123,
        "user_id": token.user_id,
        "text": message["text"]
    }


# Example 3: Multiple scopes (any)
@app.get("/api/v1/chat/rooms")
async def list_rooms(token: OAuthToken = Depends(validate_oauth_token)):
    """List chat rooms - requires chat:read OR chat:admin scope"""
    if not token.has_any_scope("chat:read", "chat:admin"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    return {"rooms": [...]}


# Example 4: Organization-scoped data
@app.get("/api/v1/chat/org/{org_id}/messages")
async def get_org_messages(
    org_id: str,
    token: OAuthToken = Depends(require_scope("chat:read"))
):
    """Get organization chat messages"""
    # Validate user has access to this organization
    if token.org_id != org_id:
        raise HTTPException(status_code=403, detail="Not authorized for this organization")

    return {"messages": [...]}
```

---

## 🧪 Testing with Auth API

### 1. Get Access Token from Auth API

**Option A: Direct Login (Testing)**

```bash
# Login with test user
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "grace.oauth@yahoo.com",
    "password": "OAuth!Testing321"
  }'

# Response includes login code (email-based auth)
# For testing, you can extract user_id and generate token directly
```

**Option B: OAuth 2.0 Flow (Production)**

```bash
# Step 1: Generate PKCE challenge
CODE_VERIFIER=$(openssl rand -hex 32)
CODE_CHALLENGE=$(echo -n "$CODE_VERIFIER" | openssl dgst -binary -sha256 | base64 | tr '+/' '-_' | tr -d '=')

# Step 2: Get authorization code (user consent)
# Browser: http://localhost:8000/oauth/authorize?client_id=test-client-1&response_type=code&redirect_uri=http://localhost:3000/callback&scope=chat:read+chat:write&code_challenge=$CODE_CHALLENGE&code_challenge_method=S256&state=random123

# Step 3: Exchange code for tokens
curl -X POST http://localhost:8000/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code" \
  -d "client_id=test-client-1" \
  -d "code=<authorization_code>" \
  -d "redirect_uri=http://localhost:3000/callback" \
  -d "code_verifier=$CODE_VERIFIER"

# Response:
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 900,
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "scope": "chat:read chat:write"
}
```

### 2. Test Chat API with Token

```bash
# Use access token from Auth API
ACCESS_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# Call Chat API protected endpoint
curl http://localhost:8080/api/v1/chat/messages \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# Expected: 200 OK with messages
# If token invalid: 401 Unauthorized
# If scope missing: 403 Forbidden
```

---

## 📊 Available OAuth Scopes

Auth API supports these scopes (can be used by Chat API):

### Activity Management
- `activity:create` - Create activities
- `activity:read` - Read activities
- `activity:update` - Update activities
- `activity:delete` - Delete activities

### Image Management
- `image:upload` - Upload images
- `image:read` - View images
- `image:delete` - Delete images

### User Profile
- `user:read` - Read user profile
- `user:update` - Update user profile
- `profile:read` - Read profile (alias)

### Organization
- `organization:read` - Read org data
- `organization:update` - Update org
- `organization:manage_members` - Manage members

### Custom Chat Scopes (Add to Auth API)

If Chat API needs specific scopes, register them in Auth API:

```python
# In Auth API: app/services/scope_service.py
SCOPE_DEFINITIONS = {
    # ... existing scopes ...

    # Chat API scopes
    "chat:read": ScopeDefinition(
        scope="chat:read",
        description="Read chat messages and rooms",
        category="chat",
        requires_permission="can_read_chat"
    ),
    "chat:write": ScopeDefinition(
        scope="chat:write",
        description="Send chat messages",
        category="chat",
        requires_permission="can_write_chat"
    ),
    "chat:admin": ScopeDefinition(
        scope="chat:admin",
        description="Administer chat rooms and moderate",
        category="chat",
        requires_permission="can_admin_chat"
    ),
}
```

---

## 🔄 Token Refresh Flow

Access tokens expire after 15 minutes. Use refresh tokens to get new access tokens:

```python
import httpx

async def refresh_access_token(refresh_token: str, client_id: str) -> dict:
    """
    Refresh access token using refresh token.

    Returns:
        dict with new access_token, refresh_token, expires_in
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{AUTH_API_URL}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id
            }
        )
        response.raise_for_status()
        return response.json()
```

---

## 🛡️ Security Considerations

### 1. JWT Secret Protection

⚠️ **CRITICAL**: `JWT_SECRET_KEY` must be:
- ✅ At least 32 characters (preferably 64+)
- ✅ Stored in environment variables (never in code)
- ✅ Same across Auth API and Chat API
- ✅ Changed regularly in production
- ❌ Never committed to Git

### 2. Token Validation Best Practices

```python
# ✅ ALWAYS validate expiration
jwt.decode(token, secret, algorithms=["HS256"], options={"verify_exp": True})

# ✅ Check token type
if payload.get("type") != "access":
    raise InvalidTokenError("Not an access token")

# ✅ Validate audience
if "https://api.activity.com" not in payload.get("aud", []):
    raise InvalidTokenError("Token not for this service")

# ✅ Check required scopes
if "chat:read" not in payload.get("scope", "").split():
    raise InsufficientScopeError()
```

### 3. Token Revocation Check (Optional)

For high-security endpoints, check if token JTI is blacklisted:

```python
async def is_token_revoked(jti: str, redis_client) -> bool:
    """Check if token JTI is in blacklist"""
    return await redis_client.exists(f"blacklist_jti:{jti}") == 1
```

---

## 📖 Example: Complete Chat Endpoint

```python
from fastapi import FastAPI, Depends, HTTPException, status
from typing import List
from pydantic import BaseModel
from app.core.oauth_validator import validate_oauth_token, require_scope, OAuthToken

app = FastAPI()


class Message(BaseModel):
    id: int
    text: str
    user_id: str
    room_id: str
    created_at: str


class SendMessageRequest(BaseModel):
    room_id: str
    text: str


@app.get("/api/v1/chat/rooms/{room_id}/messages", response_model=List[Message])
async def get_room_messages(
    room_id: str,
    token: OAuthToken = Depends(require_scope("chat:read"))
):
    """
    Get all messages in a chat room.

    Requires:
        - Valid OAuth 2.0 access token
        - Scope: chat:read

    Security:
        - Token validated via HS256 JWT
        - User must have chat:read scope
        - Organization isolation enforced
    """
    # Get messages from database (example)
    messages = await get_messages_from_db(room_id, token.org_id)

    # Filter by user's organization
    if token.org_id:
        messages = [m for m in messages if m.org_id == token.org_id]

    return messages


@app.post("/api/v1/chat/rooms/{room_id}/messages", status_code=status.HTTP_201_CREATED)
async def send_message(
    room_id: str,
    request: SendMessageRequest,
    token: OAuthToken = Depends(require_scope("chat:write"))
):
    """
    Send a message to a chat room.

    Requires:
        - Valid OAuth 2.0 access token
        - Scope: chat:write
    """
    # Validate user has access to this room
    if not await user_can_access_room(token.user_id, room_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this chat room"
        )

    # Create message
    message = await create_message(
        room_id=room_id,
        user_id=token.user_id,
        org_id=token.org_id,
        text=request.text
    )

    return {"message_id": message.id}
```

---

## 🧪 Testing Checklist

Before integrating OAuth 2.0:

- [ ] `JWT_SECRET_KEY` matches Auth API
- [ ] `JWT_ALGORITHM` set to `HS256`
- [ ] `AUTH_API_URL` points to Auth API
- [ ] Token validation utility implemented
- [ ] Protected endpoints use `Depends(validate_oauth_token)`
- [ ] Scope checks implemented where needed
- [ ] Test with Auth API test users (grace.oauth@yahoo.com)
- [ ] Test token expiration (wait 15 minutes)
- [ ] Test invalid token (modified JWT)
- [ ] Test missing/wrong scope (403 response)
- [ ] Test refresh token flow

---

## 📚 Additional Resources

### Auth API Documentation

- **OAuth Implementation**: `/mnt/d/activity/auth-api/OAUTH_IMPLEMENTATION.md`
- **Test Users**: `/mnt/d/activity/auth-api/TEST_USERS_CREDENTIALS.md`
- **Test Suite**: `/mnt/d/activity/auth-api/test_oauth.sh --help`

### Testing OAuth Flows

```bash
cd /mnt/d/activity/auth-api

# Show test users
./test_oauth.sh --show-users

# Run OAuth test suite
./test_oauth.sh

# Setup test users
./test_oauth.sh --setup-users
```

### OAuth 2.0 RFCs

- **RFC 6749**: OAuth 2.0 Framework
- **RFC 7636**: PKCE (Proof Key for Code Exchange)
- **RFC 8414**: Authorization Server Metadata
- **RFC 7009**: Token Revocation
- **RFC 9068**: JWT Profile for OAuth 2.0 Access Tokens

---

## 🆘 Troubleshooting

### Issue: "Invalid token signature"

**Cause**: `JWT_SECRET_KEY` doesn't match between Auth API and Chat API

**Solution**:
```bash
# Check Auth API secret
docker exec auth-api env | grep JWT_SECRET_KEY

# Update Chat API .env to match
JWT_SECRET_KEY=<same-as-auth-api>
```

### Issue: "Token has expired"

**Cause**: Access token expired (15 min lifetime)

**Solution**: Use refresh token to get new access token

### Issue: "Insufficient scope"

**Cause**: Token doesn't have required scope

**Solution**: Request correct scopes during OAuth authorization flow

### Issue: "Token not intended for this service"

**Cause**: Audience (`aud`) claim doesn't include Chat API

**Solution**: Either remove audience check or ensure Auth API includes correct audience

---

## ✅ Quick Start Checklist

1. [ ] Copy `JWT_SECRET_KEY` from Auth API to Chat API `.env`
2. [ ] Set `JWT_ALGORITHM=HS256` in Chat API `.env`
3. [ ] Install dependencies: `pip install pyjwt[crypto] httpx`
4. [ ] Copy `oauth_validator.py` to `app/core/`
5. [ ] Update protected endpoints to use `Depends(validate_oauth_token)`
6. [ ] Test with Auth API test user (grace.oauth@yahoo.com)
7. [ ] Verify 401 for invalid tokens
8. [ ] Verify 403 for insufficient scopes

---

**Ready to integrate! 🚀**

Questions? Check Auth API's comprehensive test suite and documentation.

**Created by:** Claude Code
**Auth API Status:** ✅ Production Ready (23/23 tests passing)
**Last Updated:** 2025-11-12
