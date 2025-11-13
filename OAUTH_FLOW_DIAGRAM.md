# 🎯 OAuth Flow Diagram - Complete Visual Overview

## Current Flow (What Happens Now)

```
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 1: Alice Logs In (USER AUTHENTICATION)                        │
└─────────────────────────────────────────────────────────────────────┘

Alice Browser                    Auth-API
     │                              │
     │  POST /auth/login            │
     │  {email, password}           │
     ├─────────────────────────────>│
     │                              │ Validate credentials
     │                              │ Generate JWT token
     │  200 OK                      │ sub: "alice_uuid"
     │  {access_token: ...}         │ type: "user"
     │<─────────────────────────────┤
     │                              │
     ✅ Alice has USER token


┌─────────────────────────────────────────────────────────────────────┐
│ STEP 2: Alice Sends Message (USER → CHAT-API)                      │
└─────────────────────────────────────────────────────────────────────┘

Alice Browser                    Chat-API                    MongoDB
     │                              │                            │
     │  POST /api/chat/groups/      │                            │
     │       {group_id}/messages    │                            │
     │  Authorization: Bearer       │                            │
     │    {alice_token}             │                            │
     │  {content, sender_id}        │                            │
     ├─────────────────────────────>│                            │
     │                              │ Decode token               │
     │                              │ Extract alice_uuid         │
     │                              │ Validate sender_id match   │
     │                              │                            │
     ✅ Alice authenticated           │                            │


┌─────────────────────────────────────────────────────────────────────┐
│ STEP 3: Chat-API Validates Group (SERVICE → AUTH-API)              │
└─────────────────────────────────────────────────────────────────────┘

Chat-API                         Auth-API OAuth               Auth-API Groups
    │                                    │                            │
    │ Need to validate group             │                            │
    │ Get OAuth service token            │                            │
    │                                    │                            │
    │  POST /oauth/token                 │                            │
    │  grant_type=client_credentials     │                            │
    │  client_id=chat-api-service        │                            │
    │  client_secret=...                 │                            │
    │  scope=groups:read                 │                            │
    ├───────────────────────────────────>│                            │
    │                                    │ Validate client            │
    │                                    │ Generate OAuth token       │
    │  200 OK                            │ sub: "chat-api-service"    │
    │  {access_token: ...}               │ scope: ["groups:read"]     │
    │<───────────────────────────────────┤                            │
    │                                    │                            │
    ✅ Chat-API has SERVICE token         │                            │
    │                                    │                            │
    │  GET /api/auth/groups/{id}         │                            │
    │  Authorization: Bearer             │                            │
    │    {service_token}                 │                            │
    ├────────────────────────────────────┼───────────────────────────>│
    │                                    │                            │ Validate token
    │                                    │                            │ ✅ WORKS NOW!
    │  200 OK                            │                            │ Returns group
    │  {id, name, org_id, ...}           │                            │
    │<────────────────────────────────────┼────────────────────────────┤
    │                                    │                            │
    ✅ Got group details                  │                            │
    │                                    │                            │
    │  GET /api/auth/groups/{id}/members │                            │
    │  Authorization: Bearer             │                            │
    │    {service_token}                 │                            │
    ├────────────────────────────────────┼───────────────────────────>│
    │                                    │                            │ Validate token
    │                                    │                            │ Decode JWT
    │                                    │                            │ Extract sub: "chat-api-service"
    │                                    │                            │ Try: UUID("chat-api-service")
    │                                    │                            │ ❌ FAILS!
    │  401 Unauthorized                  │                            │
    │  "Invalid subject in token"        │                            │
    │<────────────────────────────────────┼────────────────────────────┤
    │                                    │                            │
    ❌ BLOCKED HERE                       │                            │


┌─────────────────────────────────────────────────────────────────────┐
│ RESULT: Message Send FAILS                                          │
└─────────────────────────────────────────────────────────────────────┘

Chat-API                         MongoDB
    │                               │
    │ Cannot verify group members   │
    │ Throw 500 Internal Error      │
    │                               │
    ❌ Message NOT created            │


════════════════════════════════════════════════════════════════════════

## Fixed Flow (What SHOULD Happen)

```
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 3 (FIXED): Chat-API Validates Group                           │
└─────────────────────────────────────────────────────────────────────┘

Chat-API                         Auth-API OAuth               Auth-API Groups
    │                                    │                            │
    │ Already has SERVICE token          │                            │
    │                                    │                            │
    │  GET /api/auth/groups/{id}/members │                            │
    │  Authorization: Bearer             │                            │
    │    {service_token}                 │                            │
    ├────────────────────────────────────┼───────────────────────────>│
    │                                    │                            │ Validate token
    │                                    │                            │ Decode JWT
    │                                    │                            │ Extract sub: "chat-api-service"
    │                                    │                            │ Recognize SERVICE token
    │                                    │                            │ Check scope: groups:read ✅
    │  200 OK                            │                            │ Return members (admin)
    │  {members: [...]}                  │                            │
    │<────────────────────────────────────┼────────────────────────────┤
    │                                    │                            │
    ✅ Got member list                    │                            │


┌─────────────────────────────────────────────────────────────────────┐
│ STEP 4 (FIXED): Message Created Successfully                        │
└─────────────────────────────────────────────────────────────────────┘

Chat-API                                                     MongoDB
    │                                                            │
    │ Group validated ✅                                         │
    │ Members retrieved ✅                                       │
    │ Authorization passed ✅                                    │
    │ org_id extracted ✅                                        │
    │                                                            │
    │  Create message:                                          │
    │  {                                                         │
    │    group_id: "...",                                        │
    │    sender_id: "alice_uuid",                               │
    │    content: "Hello via OAuth!",                           │
    │    org_id: "..." ← from group                             │
    │  }                                                         │
    ├───────────────────────────────────────────────────────────>│
    │                                                            │ Insert message
    │  201 Created                                              │
    │  {message object}                                         │
    │<────────────────────────────────────────────────────────────┤
    │                                                            │
    ✅ Message stored in MongoDB                                 │
    │                                                            │
    │  Return to Alice                                          │
    │<─────────────────────────────────────────────────────────────────
    │                                                                  │
Alice Browser                                                         │
    │  201 Created                                                    │
    │  {message object}                                               │
    │<────────────────────────────────────────────────────────────────┘
    │
    ✅ Alice sees message sent successfully!


════════════════════════════════════════════════════════════════════════

## Token Comparison

### USER Token (Alice's Token)
```json
{
  "sub": "4c52f4f6-6afe-4203-8761-9d30f0382695",  ← UUID (valid user_id)
  "email": "alice.admin@example.com",
  "type": "access",
  "exp": 1762986879
}
```
**Used for**: Alice accessing Chat-API endpoints
**Works on**: `/api/chat/groups/{id}/messages`
**Authorization**: User must be group member


### SERVICE Token (Chat-API's Token)
```json
{
  "sub": "chat-api-service",                      ← CLIENT_ID (NOT a UUID!)
  "scope": "groups:read",
  "client_id": "chat-api-service",
  "exp": 1762990000
}
```
**Used for**: Chat-API accessing Auth-API endpoints
**Should work on**: `/api/auth/groups/{id}` and `/api/auth/groups/{id}/members`
**Authorization**: Scope-based (`groups:read`)


════════════════════════════════════════════════════════════════════════

## The Fix (Code Level)

### ❌ Current Code (Auth-API)
```python
# app/routes/groups.py
async def list_group_members(
    group_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),  # ← Expects UUID
    db: asyncpg.Connection = Depends(get_db_connection)
):
    # When service token arrives:
    # current_user_id = "chat-api-service" ← NOT A UUID!
    # ❌ Fails: cannot convert to UUID
```

### ✅ Fixed Code (Auth-API)
```python
# app/dependencies.py (NEW)
async def get_current_principal(
    authorization: Optional[str] = Header(None)
) -> dict:
    """Support both user and service tokens."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ")
        payload = decode_jwt(token)
        sub = payload.get("sub")

        # Try parsing as UUID (user token)
        try:
            user_id = UUID(sub)
            return {
                "type": "user",
                "user_id": user_id,
                "scopes": []
            }
        except ValueError:
            # Not a UUID, it's a service token
            return {
                "type": "service",
                "client_id": sub,
                "scopes": payload.get("scope", "").split()
            }

    raise HTTPException(401, "Authentication required")

# app/routes/groups.py (UPDATED)
async def list_group_members(
    group_id: UUID,
    principal: dict = Depends(get_current_principal),  # ← FLEXIBLE!
    db: asyncpg.Connection = Depends(get_db_connection)
):
    service = GroupService(db)

    # Service token: check scope
    if principal["type"] == "service":
        if "groups:read" not in principal["scopes"]:
            raise HTTPException(403, "Insufficient scope")
        return await service.get_group_members_admin(group_id)  # ← No user check

    # User token: check membership
    return await service.get_group_members(group_id, principal["user_id"])
```

════════════════════════════════════════════════════════════════════════

## Summary (Crystal Clear)

### 🟢 What Works (100%)
1. ✅ Alice can log in and get USER token
2. ✅ Alice can send message to Chat-API with her token
3. ✅ Chat-API can get SERVICE token from Auth-API OAuth
4. ✅ Chat-API can get GROUP details from Auth-API with service token

### 🔴 What's Broken (1 Issue)
1. ❌ Chat-API CANNOT get MEMBERS from Auth-API with service token
   - Reason: Members endpoint expects USER UUID, gets SERVICE client_id
   - Error: "Invalid subject in token"
   - Fix needed: Use `get_current_principal` instead of `get_current_user_id`

### 🎯 What Needs to Happen (1 Change)
1. Auth-API creates `get_current_principal` dependency
2. Auth-API updates members endpoint to use new dependency
3. Auth-API adds scope check for service tokens
4. Done! Everything works 100% 🚀

### 💡 Why This Is the ONLY Issue
- Chat-API side: 100% complete, nothing to change
- Auth-API OAuth: 100% working, issues valid tokens
- Auth-API groups endpoint: Already fixed, accepts service tokens
- Auth-API members endpoint: Still uses old dependency, needs update

**FINAL ANSWER**: ONE dependency change in Auth-API, then EVERYTHING works! 💪
