# Chat API Authorization Flow

**Laatst bijgewerkt**: 2025-11-20
**Versie**: 2.0

## Inhoudsopgave

1. [Overview](#overview)
2. [Belangrijkste Concepten](#belangrijkste-concepten)
3. [Authorization Flow](#authorization-flow)
4. [Permission Levels](#permission-levels)
5. [Runtime Permission Checks](#runtime-permission-checks)
6. [Test Data Setup](#test-data-setup)
7. [Testing Guide](#testing-guide)
8. [Troubleshooting](#troubleshooting)

---

## Overview

De Chat API gebruikt **runtime permission validation** via de Auth API. In tegenstelling tot traditionele OAuth scope-based authorization, bevat de JWT token GEEN permissions of scopes. In plaats daarvan valideert de Chat API bij elke request de permissions door de Auth API te raadplegen.

### Kernprincipes

1. **JWT tokens bevatten GEEN permissions** - alleen `user_id` en `org_id`
2. **Runtime validation** - Bij elke request wordt Auth API geraadpleegd
3. **Service-to-service authentication** - Chat API authenticeert via `X-Service-Token`
4. **Group-based RBAC** - Permissions worden toegekend via group membership
5. **Multi-tenant isolation** - Strikte org_id validatie

---

## Belangrijkste Concepten

### JWT Token Structuur

```json
{
  "sub": "ffffffff-ffff-ffff-ffff-ffffffffffff",  // user_id
  "org_id": "99999999-9999-9999-9999-999999999999",  // organization_id
  "type": "access",
  "exp": 1700000000,
  "iat": 1699999100
}
```

**Let op**: Geen `scope` of `permissions` velden!

### Authorization Endpoint

**Auth API Endpoint**: `POST /api/v1/authorization/check`

**Headers**:
```
X-Service-Token: <SERVICE_TOKEN>
Content-Type: application/json
```

**Request Body**:
```json
{
  "org_id": "99999999-9999-9999-9999-999999999999",
  "user_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
  "permission": "chat:read"
}
```

**Response (Allowed)**:
```json
{
  "allowed": true,
  "groups": ["vrienden", "moderators"],
  "reason": null
}
```

**Response (Denied)**:
```json
{
  "allowed": false,
  "groups": null,
  "reason": "User does not have permission 'chat:read'"
}
```

### Database Schema (Auth API)

**Relevante tabellen**:
- `activity.users` - Gebruikers
- `activity.organizations` - Organisaties
- `activity.organization_members` - Org membership
- `activity.groups` - Groepen binnen organisaties
- `activity.user_groups` - User-groep koppeling
- `activity.permissions` - Beschikbare permissions (chat:read, chat:write, chat:admin)
- `activity.group_permissions` - Groep-permission koppeling

**Stored Procedure** (kern van authorization):
```sql
activity.sp_user_has_permission(
    p_user_id UUID,
    p_organization_id UUID,
    p_resource VARCHAR(50),  -- 'chat'
    p_action VARCHAR(50)     -- 'read', 'write', 'admin'
) RETURNS BOOLEAN
```

---

## Authorization Flow

### Volledige Request Flow

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ 1. HTTP Request
       │    Authorization: Bearer <JWT>
       │    POST /api/chat/groups/{group_id}/messages
       ▼
┌─────────────────────────────────────────────────────────┐
│                    Chat API                             │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 2. JWT Validation                               │   │
│  │    • Decode JWT (shared secret)                 │   │
│  │    • Validate signature + expiration            │   │
│  │    • Extract: user_id, org_id                   │   │
│  └─────────┬───────────────────────────────────────┘   │
│            │                                            │
│            ▼                                            │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 3. Permission Check (CRITICAL)                  │   │
│  │    HTTP POST to Auth API:                       │   │
│  │    /api/v1/authorization/check                  │   │
│  │                                                  │   │
│  │    Headers:                                     │   │
│  │      X-Service-Token: <SERVICE_TOKEN>           │   │
│  │                                                  │   │
│  │    Body:                                        │   │
│  │    {                                            │   │
│  │      "org_id": "999...",                        │   │
│  │      "user_id": "fff...",                       │   │
│  │      "permission": "chat:write"                 │   │
│  │    }                                            │   │
│  └─────────┬───────────────────────────────────────┘   │
│            │                                            │
└────────────┼────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│                    Auth API                             │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 4. Service Authentication                       │   │
│  │    • Validate X-Service-Token header            │   │
│  │    • Verify matches SERVICE_AUTH_TOKEN          │   │
│  └─────────┬───────────────────────────────────────┘   │
│            │                                            │
│            ▼                                            │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 5. Database Permission Check                    │   │
│  │    Call stored procedure:                       │   │
│  │    sp_user_has_permission(                      │   │
│  │      user_id='fff...',                          │   │
│  │      org_id='999...',                           │   │
│  │      resource='chat',                           │   │
│  │      action='write'                             │   │
│  │    )                                            │   │
│  │                                                  │   │
│  │    Logic:                                       │   │
│  │    1. Check org membership                      │   │
│  │    2. Find user's groups in org                 │   │
│  │    3. Check if any group has permission         │   │
│  │    4. Return true/false                         │   │
│  └─────────┬───────────────────────────────────────┘   │
│            │                                            │
│            ▼                                            │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 6. Return Authorization Result                  │   │
│  │    {                                            │   │
│  │      "allowed": true,                           │   │
│  │      "groups": ["vrienden"],                    │   │
│  │      "reason": null                             │   │
│  │    }                                            │   │
│  └─────────┬───────────────────────────────────────┘   │
│            │                                            │
└────────────┼────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│                    Chat API                             │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 7. Process Authorization Result                 │   │
│  │    • If allowed=false → 403 Forbidden           │   │
│  │    • If allowed=true → Continue to business     │   │
│  │      logic                                      │   │
│  └─────────┬───────────────────────────────────────┘   │
│            │                                            │
│            ▼                                            │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 8. Execute Business Logic                       │   │
│  │    • Create message in MongoDB                  │   │
│  │    • Set org_id, group_id, sender_id            │   │
│  │    • Broadcast via WebSocket                    │   │
│  └─────────┬───────────────────────────────────────┘   │
│            │                                            │
└────────────┼────────────────────────────────────────────┘
             │
             ▼
      ┌─────────────┐
      │   Response  │
      │ 201 Created │
      └─────────────┘
```

### Belangrijke Validatie Stappen

1. **JWT Validation** - Verifieer token signature en expiration
2. **Permission Check** - Vraag Auth API: "Heeft deze user deze permission?"
3. **Service Auth** - Chat API authenticeert zichzelf met X-Service-Token
4. **Database Lookup** - Auth API checkt via stored procedure
5. **Response Processing** - Chat API verwerkt allowed/denied response

---

## Permission Levels

### chat:read

**Beschrijving**: Berichten lezen in groepen waar gebruiker lid van is

**Rechten**:
- ✅ GET /api/chat/groups/{group_id}/messages - Berichten ophalen
- ✅ WebSocket connection voor real-time updates

**Database Setup**:
```sql
-- Permission bestaat al in database
SELECT * FROM activity.permissions
WHERE resource = 'chat' AND action = 'read';
-- Result: 79d465c7-35c5-4398-b789-5d340b14fc63
```

### chat:write

**Beschrijving**: Berichten aanmaken, eigen berichten wijzigen/verwijderen

**Rechten**:
- ✅ POST /api/chat/groups/{group_id}/messages - Bericht aanmaken
- ✅ PUT /api/chat/messages/{message_id} - Eigen bericht wijzigen
- ✅ DELETE /api/chat/messages/{message_id} - Eigen bericht soft-delete
- ✅ Impliceert ook chat:read rechten

**Database Setup**:
```sql
SELECT * FROM activity.permissions
WHERE resource = 'chat' AND action = 'write';
-- Result: 2d05eb16-3c8e-4f9c-bb45-fd0c7e5a5c14
```

### chat:admin

**Beschrijving**: Volledige chat beheer, inclusief moderatie

**Rechten**:
- ✅ Alle chat:write rechten
- ✅ DELETE /api/chat/messages/{message_id} - Berichten van ANDEREN verwijderen
- ✅ Moderatie acties (bans, mutes - indien geïmplementeerd)
- ✅ Groep management rechten

**Database Setup**:
```sql
SELECT * FROM activity.permissions
WHERE resource = 'chat' AND action = 'admin';
-- Result: d607efa1-f06b-456b-8de4-630f4f8c7ce8
```

### Permission Hiërarchie

```
chat:admin
    ├── Alle chat:write rechten
    │       ├── Alle chat:read rechten
    │       ├── Berichten aanmaken
    │       ├── Eigen berichten wijzigen
    │       └── Eigen berichten verwijderen
    ├── Berichten van anderen verwijderen
    ├── Moderatie acties
    └── Groep management
```

---

## Runtime Permission Checks

### Implementation in Chat API

**Code Referentie**: `app/services/chat_service.py`

```python
async def create_message(
    self,
    group_id: str,
    org_id: str,
    sender_id: str,
    content: str
) -> Message:
    """
    Create a new message with runtime permission check.

    Flow:
    1. Check user has chat:write permission (via Auth API)
    2. Validate group access
    3. Create message in MongoDB
    """

    # CRITICAL: Runtime permission check
    has_permission = await self._check_permission(
        org_id=org_id,
        user_id=sender_id,
        permission="chat:write"
    )

    if not has_permission:
        logger.warning(
            "permission_denied",
            user_id=sender_id,
            org_id=org_id,
            permission="chat:write"
        )
        raise ForbiddenError("You don't have permission to write messages")

    # Continue with business logic...
    message = Message(
        org_id=org_id,
        group_id=group_id,
        sender_id=sender_id,
        content=content,
        created_at=datetime.utcnow(),
        is_deleted=False
    )

    await message.save()
    return message
```

### Permission Check Implementation

**Code Referentie**: `app/services/auth_service.py` (nieuw)

```python
import httpx
from app.core.config import get_settings

class AuthService:
    """Service for communicating with Auth API."""

    def __init__(self):
        self.settings = get_settings()
        self.auth_api_url = self.settings.AUTH_API_URL
        self.service_token = self.settings.SERVICE_AUTH_TOKEN

    async def check_permission(
        self,
        org_id: str,
        user_id: str,
        permission: str
    ) -> bool:
        """
        Check if user has permission via Auth API.

        Args:
            org_id: Organization UUID
            user_id: User UUID
            permission: Permission string (e.g., "chat:read", "chat:write")

        Returns:
            True if user has permission, False otherwise
        """
        url = f"{self.auth_api_url}/api/v1/authorization/check"

        headers = {
            "X-Service-Token": self.service_token,
            "Content-Type": "application/json"
        }

        payload = {
            "org_id": org_id,
            "user_id": user_id,
            "permission": permission
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=5.0
                )

                if response.status_code == 200:
                    data = response.json()
                    allowed = data.get("allowed", False)

                    if allowed:
                        logger.info(
                            "permission_check_granted",
                            user_id=user_id,
                            org_id=org_id,
                            permission=permission,
                            groups=data.get("groups", [])
                        )
                    else:
                        logger.warning(
                            "permission_check_denied",
                            user_id=user_id,
                            org_id=org_id,
                            permission=permission,
                            reason=data.get("reason")
                        )

                    return allowed
                else:
                    logger.error(
                        "permission_check_failed",
                        status_code=response.status_code,
                        user_id=user_id,
                        org_id=org_id,
                        permission=permission
                    )
                    return False

        except httpx.TimeoutException:
            logger.error(
                "permission_check_timeout",
                user_id=user_id,
                org_id=org_id,
                permission=permission
            )
            return False
        except Exception as e:
            logger.error(
                "permission_check_error",
                user_id=user_id,
                org_id=org_id,
                permission=permission,
                error=str(e)
            )
            return False
```

### Environment Configuration

**Required in `.env`**:

```bash
# Auth API Configuration
AUTH_API_URL=http://auth-api:8000
SERVICE_AUTH_TOKEN=your-service-token-change-in-production

# JWT Secret (MUST match auth-api)
JWT_SECRET_KEY=your-jwt-secret-min-32-chars-change-in-production
```

---

## Test Data Setup

### Complete Test Scenario

Het bestand `test_rbac_setup.sql` bevat complete test data voor alle permission levels.

**Test Organization**:
- ID: `99999999-9999-9999-9999-999999999999`
- Name: `Chat Test Organization`
- Slug: `test-org-chat`

**Test Users** (4 users):
1. **Admin** (`eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee`)
   - Email: chattest-admin@example.com
   - Groups: vrienden (chat:read + chat:write)

2. **User1** (`ffffffff-ffff-ffff-ffff-ffffffffffff`)
   - Email: chattest-user1@example.com
   - Groups: vrienden (chat:read + chat:write)

3. **User2** (`dddddddd-dddd-dddd-dddd-dddddddddddd`)
   - Email: chattest-user2@example.com
   - Groups: observers (NO permissions)

4. **Moderator** (`aaaabbbb-cccc-dddd-eeee-ffffffff1111`)
   - Email: chattest-moderator@example.com
   - Groups: moderators (chat:admin)

**Test Groups** (3 groups):
1. **vrienden** (`aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa`)
   - Permissions: chat:read, chat:write
   - Members: admin, user1

2. **observers** (`bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb`)
   - Permissions: NONE
   - Members: user2

3. **moderators** (`cccccccc-cccc-cccc-cccc-cccccccccccc`)
   - Permissions: chat:admin
   - Members: moderator

### Running Test Setup

```bash
# Load test data into PostgreSQL
docker exec -i activity-postgres-db psql -U postgres -d activitydb < /mnt/d/activity/chat-api/test_rbac_setup.sql
```

**Expected Output**:
```
✓ Cleanup complete
✓ Organization created: test-org-chat
✓ Users created (4 users)
✓ All users added to organization
✓ Groups created (3 groups)
✓ Permissions linked
✓ Users added to groups

Test 1: Admin heeft chat:read? ✓ PASS
Test 2: Admin heeft chat:write? ✓ PASS
Test 3: User1 heeft chat:read? ✓ PASS
Test 4: User2 heeft chat:read? ✓ PASS (correct: geen rechten)
Test 5: Moderator heeft chat:admin? ✓ PASS
Test 6: User1 heeft GEEN chat:admin? ✓ PASS (correct: geen admin rechten)
```

### Verification Queries

**Check user permissions via Auth API**:

```bash
# Test admin user (should have chat:read and chat:write)
curl -X POST http://localhost:8000/api/v1/authorization/check \
  -H "X-Service-Token: your-service-token" \
  -H "Content-Type: application/json" \
  -d '{
    "org_id": "99999999-9999-9999-9999-999999999999",
    "user_id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
    "permission": "chat:read"
  }'

# Expected: {"allowed":true,"groups":["vrienden"],"reason":null}
```

```bash
# Test user2 (should NOT have chat:read - observers group has no permissions)
curl -X POST http://localhost:8000/api/v1/authorization/check \
  -H "X-Service-Token: your-service-token" \
  -H "Content-Type: application/json" \
  -d '{
    "org_id": "99999999-9999-9999-9999-999999999999",
    "user_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
    "permission": "chat:read"
  }'

# Expected: {"allowed":false,"groups":null,"reason":"User does not have permission 'chat:read'"}
```

```bash
# Test moderator (should have chat:admin)
curl -X POST http://localhost:8000/api/v1/authorization/check \
  -H "X-Service-Token: your-service-token" \
  -H "Content-Type: application/json" \
  -d '{
    "org_id": "99999999-9999-9999-9999-999999999999",
    "user_id": "aaaabbbb-cccc-dddd-eeee-ffffffff1111",
    "permission": "chat:admin"
  }'

# Expected: {"allowed":true,"groups":["moderators"],"reason":null}
```

---

## Testing Guide

### End-to-End Testing Flow

**1. Start Infrastructure**:
```bash
# Start PostgreSQL, Redis, etc.
./scripts/start-infra.sh

# Verify Auth API is running
curl http://localhost:8000/health

# Verify Chat API is running
curl http://localhost:8001/health
```

**2. Load Test Data**:
```bash
docker exec -i activity-postgres-db psql -U postgres -d activitydb < /mnt/d/activity/chat-api/test_rbac_setup.sql
```

**3. Get JWT Token for Test User**:
```bash
# Login as admin user
curl -X POST http://localhost:8000/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "chattest-admin@example.com",
    "password": "$argon2id$v=19$m=65536,t=3,p=4$dummy_hash"
  }'

# IMPORTANT: Test users have dummy password hash!
# For real testing, update password in database:
docker exec -i activity-postgres-db psql -U postgres -d activitydb -c \
  "UPDATE activity.users SET password_hash = '<real_hash>'
   WHERE email = 'chattest-admin@example.com';"
```

**4. Test Permission Checks via Auth API**:
```bash
# Set service token
export SERVICE_TOKEN="your-service-token"

# Test chat:read permission for admin
curl -X POST http://localhost:8000/api/v1/authorization/check \
  -H "X-Service-Token: $SERVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "org_id": "99999999-9999-9999-9999-999999999999",
    "user_id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
    "permission": "chat:read"
  }'

# Expected: {"allowed":true,"groups":["vrienden"],"reason":null}
```

**5. Test Chat API Endpoints** (requires Chat API implementation):
```bash
# Get JWT token first
export JWT_TOKEN="<your-jwt-token>"

# Test reading messages (requires chat:read)
curl -X GET "http://localhost:8001/api/chat/groups/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/messages" \
  -H "Authorization: Bearer $JWT_TOKEN"

# Test creating message (requires chat:write)
curl -X POST "http://localhost:8001/api/chat/groups/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/messages" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Test message"}'
```

### Test Scenarios

**Scenario 1: User with chat:read + chat:write**
- User: admin or user1
- Expected: Can read AND write messages
- Test: GET and POST to /api/chat/groups/{group_id}/messages

**Scenario 2: User without permissions**
- User: user2 (observers group)
- Expected: CANNOT read or write messages
- Test: GET returns 403 Forbidden

**Scenario 3: Moderator with chat:admin**
- User: moderator
- Expected: Can delete ANY message (not just own)
- Test: DELETE /api/chat/messages/{message_id} (even if not sender)

**Scenario 4: Cross-org access attempt**
- User from Org A tries to access group in Org B
- Expected: 403 Forbidden (after permission check fails)
- Security logging should trigger

---

## Troubleshooting

### Problem: "Permission denied" maar user zit in juiste groep

**Mogelijke oorzaken**:
1. Group heeft permission niet gekoppeld in `group_permissions` tabel
2. User is geen lid van organization
3. Permission naam is incorrect (typo in resource of action)

**Debug**:
```bash
# Check group permissions
docker exec -i activity-postgres-db psql -U postgres -d activitydb -c "
SELECT
    g.name as group_name,
    p.resource,
    p.action,
    p.description
FROM activity.groups g
JOIN activity.group_permissions gp ON g.id = gp.group_id
JOIN activity.permissions p ON gp.permission_id = p.id
WHERE g.id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
"

# Check user group membership
docker exec -i activity-postgres-db psql -U postgres -d activitydb -c "
SELECT
    u.email,
    g.name as group_name,
    ug.added_at
FROM activity.users u
JOIN activity.user_groups ug ON u.user_id = ug.user_id
JOIN activity.groups g ON ug.group_id = g.id
WHERE u.user_id = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee';
"
```

### Problem: "Service authentication failed"

**Oorzaak**: X-Service-Token header niet correct of matcht niet met Auth API configuratie

**Oplossing**:
```bash
# Check service token in Auth API
cat /mnt/d/activity/auth-api/.env | grep SERVICE_AUTH_TOKEN

# Check service token in Chat API
cat /mnt/d/activity/chat-api/.env | grep SERVICE_AUTH_TOKEN

# Moeten EXACT gelijk zijn!
```

### Problem: Auth API connection timeout

**Oorzaak**: Chat API kan Auth API niet bereiken via netwerk

**Debug**:
```bash
# Test connectivity from Chat API container
docker exec -it chat-api curl http://auth-api:8000/health

# Check if both containers are on same network
docker network inspect activity-network

# Verify Auth API is actually running
docker ps | grep auth-api
curl http://localhost:8000/health
```

### Problem: Permission check werkt lokaal maar niet in Docker

**Oorzaak**: Environment variabelen niet correct in Docker container

**Oplossing**:
```bash
# Check environment variables IN container
docker exec -it chat-api env | grep AUTH_API_URL
docker exec -it chat-api env | grep SERVICE_AUTH_TOKEN

# Verify docker-compose.yml has correct env_file
cat docker-compose.yml | grep env_file

# Rebuild container after .env changes
docker compose build chat-api --no-cache
docker compose restart chat-api
```

### Problem: Stored procedure returns false maar user heeft permission

**Debug via database**:
```bash
# Direct stored procedure test
docker exec -i activity-postgres-db psql -U postgres -d activitydb -c "
SELECT activity.sp_user_has_permission(
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID,  -- user_id
    '99999999-9999-9999-9999-999999999999'::UUID,  -- org_id
    'chat',                                         -- resource
    'read'                                          -- action
);
"

# Check organization membership
docker exec -i activity-postgres-db psql -U postgres -d activitydb -c "
SELECT * FROM activity.organization_members
WHERE user_id = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'
  AND organization_id = '99999999-9999-9999-9999-999999999999';
"

# If no result → User is NOT a member of organization!
# Add user to org:
docker exec -i activity-postgres-db psql -U postgres -d activitydb -c "
INSERT INTO activity.organization_members (user_id, organization_id, added_by)
VALUES (
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID,
    '99999999-9999-9999-9999-999999999999'::UUID,
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID  -- self-add for testing
);
"
```

---

## Security Considerations

### 1. Service Token Protection

**CRITICAL**: `SERVICE_AUTH_TOKEN` moet geheim blijven en NOOIT in JWT tokens

```bash
# Generate strong service token
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Set in .env (Auth API)
SERVICE_AUTH_TOKEN=<generated-token>

# Set in .env (Chat API) - EXACT SAME VALUE
SERVICE_AUTH_TOKEN=<generated-token>
```

### 2. Permission Caching

**Overweging**: Permission checks bij elke request kunnen traag zijn

**Oplossing**: Cache permission check results in Redis

```python
# Example caching implementation
async def check_permission_cached(
    org_id: str,
    user_id: str,
    permission: str
) -> bool:
    cache_key = f"perm:{org_id}:{user_id}:{permission}"

    # Try cache first
    cached = await redis.get(cache_key)
    if cached is not None:
        return cached == "1"

    # Cache miss - check Auth API
    allowed = await check_permission(org_id, user_id, permission)

    # Cache result for 5 minutes
    await redis.setex(cache_key, 300, "1" if allowed else "0")

    return allowed
```

**Invalidation**: Cache MOET geïnvalideerd worden bij:
- User wordt toegevoegd/verwijderd uit groep
- Group permissions worden gewijzigd
- User wordt verwijderd uit organisatie

### 3. Rate Limiting

**Bescherming**: Voorkom abuse van authorization endpoint

```python
# In Auth API
@router.post("/api/v1/authorization/check")
@limiter.limit("100/minute")  # Per service
async def check_authorization(...):
    ...
```

### 4. Audit Logging

**Vereiste**: Log ALLE permission checks voor audit trail

```python
# In Auth API
logger.info(
    "permission_check",
    org_id=org_id,
    user_id=user_id,
    permission=permission,
    allowed=allowed,
    groups=groups if allowed else None,
    service="chat-api",
    timestamp=datetime.utcnow().isoformat()
)
```

---

## Next Steps

### Implementation Checklist

- [ ] **Auth API**: Authorization endpoint volledig geïmplementeerd
- [ ] **Chat API**: AuthService implementeren voor permission checks
- [ ] **Chat API**: Integreer permission checks in alle endpoints
- [ ] **Configuration**: SERVICE_AUTH_TOKEN instellen in beide APIs
- [ ] **Testing**: Alle test scenarios doorlopen
- [ ] **Monitoring**: Logging en metrics voor permission checks
- [ ] **Caching**: Redis caching implementeren (optioneel)
- [ ] **Documentation**: API docs updaten met permission requirements

### Future Enhancements

1. **Permission Caching**: Redis cache voor snellere checks
2. **Bulk Permission Checks**: Check meerdere permissions in één call
3. **Permission Management UI**: Admin interface voor permission management
4. **Audit Dashboard**: Visualisatie van permission checks en denials
5. **Rate Limiting**: Bescherming tegen abuse
6. **Webhook Notifications**: Real-time notificaties bij permission changes

---

## References

- **Test Data**: `/mnt/d/activity/chat-api/test_rbac_setup.sql`
- **Auth API Docs**: `/mnt/d/activity/auth-api/CLAUDE.md`
- **Chat API Docs**: `/mnt/d/activity/chat-api/CLAUDE.md`
- **Stored Procedure**: `activity.sp_user_has_permission()` in Auth API database
- **Authorization Endpoint**: Auth API `/api/v1/authorization/check`

---

**Document Version**: 2.0
**Last Updated**: 2025-11-20
**Author**: System Documentation (gebaseerd op werkelijke implementatie en tests)
