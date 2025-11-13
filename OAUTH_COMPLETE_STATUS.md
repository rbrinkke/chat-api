# 🎯 Chat-API OAuth Integration - COMPLETE STATUS OVERVIEW

**Date**: 2025-11-12
**Focus**: 100% clarity on what works, what's broken, and what needs to be fixed

## 📊 Current Situation Summary

### What We're Testing
Sending a message from Alice (user) to Chat-API → Chat-API validates with Auth-API using OAuth → Message created in MongoDB.

### Test Flow
```
1. ✅ Alice logs in to Auth-API
   → Email: alice.admin@example.com
   → Got JWT access token

2. ✅ Alice sends message to Chat-API
   → POST /api/chat/groups/{group_id}/messages
   → Authorization: Bearer {alice_token}
   → Body: {content: "Hello", sender_id: "alice_uuid"}

3. ❌ Chat-API validates group with Auth-API (FAILS HERE)
   → Chat-API needs group details and members from Auth-API
   → Chat-API uses OAuth Client Credentials token (chat-api-service)
   → Auth-API rejects the request
```

## 🔴 THE CORE PROBLEM

**Auth-API has TWO types of authentication:**

### Type 1: USER Tokens (Alice's token)
- **Subject (sub)**: User UUID (e.g., `4c52f4f6-6afe-4203-8761-9d30f0382695`)
- **Purpose**: User accesses their own resources
- **Example**: Alice logs in, gets token, sends messages
- **Works on**: `/api/chat/groups/{id}/messages` (Chat-API endpoints)

### Type 2: SERVICE Tokens (Chat-API's token)
- **Subject (sub)**: Client ID (e.g., `chat-api-service`)
- **Purpose**: Service-to-service communication
- **Example**: Chat-API validates groups with Auth-API
- **Should work on**: `/api/auth/groups/{id}` and `/api/auth/groups/{id}/members`

## 🚨 THE EXACT ERROR

When Chat-API tries to validate a group, it calls Auth-API:

```bash
# Chat-API makes this call with SERVICE token:
GET /api/auth/groups/{id}        → ✅ WORKS (recently fixed)
GET /api/auth/groups/{id}/members → ❌ FAILS with "Invalid subject in token"
```

**Error Details**:
```
aiohttp.client_exceptions.ClientResponseError:
401, message='Unauthorized',
url='http://auth-api:8000/api/auth/groups/{id}/members'

Response: {"detail":"Invalid subject in token"}
```

## 🔍 ROOT CAUSE ANALYSIS

### Auth-API Group Endpoints Use `get_current_user_id` Dependency

Looking at `/api/auth/groups/{id}/members` endpoint:
```python
async def list_group_members(
    group_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),  # ← THIS IS THE PROBLEM
    db: asyncpg.Connection = Depends(get_db_connection)
):
```

### What `get_current_user_id` Expects
- **Expects**: Token with `sub` claim containing a **user UUID**
- **Gets**: Service token with `sub` = `"chat-api-service"` (string, not UUID)
- **Result**: Error "Invalid subject in token"

### Why This Happens
1. Chat-API acquires OAuth token: `client_id=chat-api-service`
2. OAuth spec: `sub` claim MUST be the client_id for Client Credentials flow
3. Token has: `sub: "chat-api-service"` (correct per OAuth2 spec)
4. Auth-API tries: `UUID(current_user_id)` where `current_user_id = "chat-api-service"`
5. Fails: Cannot convert "chat-api-service" string to UUID

## ✅ WHAT'S ALREADY FIXED

### 1. Chat-API Side (100% Complete)
- ✅ Migrated httpx → aiohttp (DNS issues resolved)
- ✅ OAuth Client Credentials flow implemented
- ✅ ServiceTokenManager with auto-refresh
- ✅ GroupService integration with Auth-API
- ✅ Proper error handling and logging
- ✅ Docker networking (auth-api service name)
- ✅ All legacy code removed

### 2. Auth-API Side (Partially Fixed)
- ✅ `/api/auth/groups/{id}` accepts OAuth Bearer tokens (working!)
- ❌ `/api/auth/groups/{id}/members` does NOT accept OAuth Bearer tokens (broken!)

## 🎯 WHAT NEEDS TO BE FIXED IN AUTH-API

### The Solution: Create `get_current_principal` Dependency

Auth-API needs a NEW dependency that supports BOTH user and service tokens:

```python
# app/dependencies.py (or wherever dependencies live)

async def get_current_principal(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    session_user_id: Optional[UUID] = Depends(get_session_user_id_optional)
) -> dict:
    """
    Get current principal (user OR service) from session or OAuth token.

    Returns:
        {
            "type": "user" | "service",
            "user_id": UUID or None,
            "client_id": str or None,
            "scopes": List[str]
        }
    """
    # If session exists, use it (user authentication)
    if session_user_id:
        return {
            "type": "user",
            "user_id": session_user_id,
            "client_id": None,
            "scopes": []
        }

    # If Bearer token exists, validate it (OAuth2)
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ")
        payload = decode_jwt(token)  # Validate JWT

        sub = payload.get("sub")
        scopes = payload.get("scope", "").split()

        # Try to parse sub as UUID (user token)
        try:
            user_id = UUID(sub)
            return {
                "type": "user",
                "user_id": user_id,
                "client_id": None,
                "scopes": scopes
            }
        except ValueError:
            # sub is not a UUID, it's a client_id (service token)
            return {
                "type": "service",
                "user_id": None,
                "client_id": sub,
                "scopes": scopes
            }

    raise HTTPException(status_code=401, detail="Authentication required")
```

### Update Members Endpoint

```python
# app/routes/groups.py

@router.get(
    "/groups/{group_id}/members",
    response_model=List[GroupMemberResponse],
    summary="List Members"
)
async def list_group_members(
    group_id: UUID,
    principal: dict = Depends(get_current_principal),  # ← CHANGED
    db: asyncpg.Connection = Depends(get_db_connection)
):
    """
    List all members of a group.

    **Security**:
    - User tokens: Requires membership in group's organization
    - Service tokens: Requires groups:read scope
    """
    service = GroupService(db)

    # If service token, skip user-based authorization
    if principal["type"] == "service":
        if "groups:read" not in principal["scopes"]:
            raise HTTPException(status_code=403, detail="Insufficient scope")
        # Return members without checking user membership
        return await service.get_group_members_admin(group_id)

    # User token: check organization membership
    return await service.get_group_members(group_id, principal["user_id"])
```

## 📋 IMPLEMENTATION CHECKLIST FOR AUTH-API TEAM

### Step 1: Create `get_current_principal` Dependency
- [ ] Create new dependency function supporting both user and service tokens
- [ ] Handle session authentication (existing flow)
- [ ] Handle OAuth Bearer tokens (new flow)
- [ ] Distinguish user UUIDs from service client_ids
- [ ] Return structured principal with type, user_id/client_id, scopes

### Step 2: Update GroupService Methods
- [ ] Add `get_group_members_admin(group_id)` method (no user_id required)
- [ ] Add `get_group_details_admin(group_id)` method (no user_id required)
- [ ] Keep existing methods for user-based access

### Step 3: Update Group Endpoints
- [ ] Update `GET /api/auth/groups/{id}` to use `get_current_principal`
- [ ] Update `GET /api/auth/groups/{id}/members` to use `get_current_principal`
- [ ] Add scope checks for service tokens (`groups:read`)
- [ ] Keep user authorization checks for user tokens

### Step 4: Testing
- [ ] Test with user session (existing flow must still work)
- [ ] Test with user Bearer token (JWT from login)
- [ ] Test with service Bearer token (OAuth Client Credentials)
- [ ] Verify scope enforcement for service tokens
- [ ] Verify organization membership for user tokens

## 🧪 TEST COMMANDS (After Fix)

### Test 1: Service Token Gets Members
```bash
# Get service token
TOKEN=$(curl -s -X POST "http://localhost:8000/oauth/token" \
  -d "grant_type=client_credentials" \
  -d "client_id=chat-api-service" \
  -d "client_secret=your-service-secret-change-in-production" \
  -d "scope=groups:read" | jq -r '.access_token')

# Get members with service token
curl -X GET "http://localhost:8000/api/auth/groups/{group_id}/members" \
  -H "Authorization: Bearer $TOKEN"

# Expected: 200 OK with members list
```

### Test 2: End-to-End Message Flow
```bash
# Login as Alice
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"alice.admin@example.com","password":"SecurePass123!Admin"}' \
  | jq -r '.access_token' > /tmp/alice_token.txt

# Send message to Chat-API
curl -X POST "http://localhost:8001/api/chat/groups/{group_id}/messages" \
  -H "Authorization: Bearer $(cat /tmp/alice_token.txt)" \
  -H "Content-Type: application/json" \
  -d '{"content":"Hello via OAuth!","sender_id":"alice_uuid"}'

# Expected: 201 Created with message object
```

## 🎯 SUCCESS CRITERIA (100%)

### ✅ Complete Success Means:
1. **Alice can send messages** - User token works on Chat-API endpoints
2. **Chat-API can validate groups** - Service token works on Auth-API group endpoint
3. **Chat-API can get members** - Service token works on Auth-API members endpoint
4. **No 401 errors** - All authentication flows work perfectly
5. **Proper authorization** - Scope-based for services, role-based for users
6. **Full end-to-end flow** - User login → send message → Chat-API validates → message created

### 🚀 When This Is Fixed:
- Chat-API will work 100% with OAuth2
- No more httpx/DNS issues
- No more 401 errors
- Real-time chat with proper multi-tenant isolation
- Production-ready service-to-service authentication

## 📝 CURRENT BLOCKING STATUS

**STATUS**: 🔴 **BLOCKED ON AUTH-API**

**Blocking Issue**: `/api/auth/groups/{id}/members` endpoint does not accept OAuth Bearer tokens with service client_id as subject.

**What's Working**: Everything on Chat-API side is 100% complete and ready.

**What's Needed**: Auth-API must implement `get_current_principal` dependency to support both user and service authentication.

**ETA**: Once Auth-API implements the fix above, the ENTIRE OAuth integration will be 100% working.

---

**For Auth-API Team**: See `/mnt/d/activity/auth-api/ISSUE_GROUP_ENDPOINTS_OAUTH.md` for the original issue documentation (covers the `/groups/{id}` endpoint which was already fixed, but members endpoint needs the same fix).

**For Chat-API Team**: Chat-API side is 100% DONE. Waiting on Auth-API dependency changes only.
