# Auth API Integration - Chat API

**Auth API Client voor permission checks vanuit Chat API**

---

## Quick Start

### 1. Configuration (.env)

De configuratie is al compleet! Check `.env`:

```bash
# Auth API Integration
AUTH_API_URL="http://auth-api:8000"
SERVICE_AUTH_TOKEN="5XFXyEFX5p4qxWK6pYGDibG3YM-r3WqagY3VzFkAVqW3WU00ngh8K7eh4ka-44VJ5WksrfDspeer2Hx8AQOk5A"
```

**BELANGRIJK:** `SERVICE_AUTH_TOKEN` moet matchen met auth-api `.env`!

---

## 2. Usage in Code

### Voorbeeld 1: Check Permission (met error handling)

```python
from fastapi import APIRouter, Depends, HTTPException
from app.services.auth_api_client import get_auth_api_client, AuthAPIClient
from app.core.oauth_validator import validate_oauth_token, OAuthToken

router = APIRouter()

@router.post("/send-message")
async def send_message(
    token: OAuthToken = Depends(validate_oauth_token),
    auth_client: AuthAPIClient = Depends(get_auth_api_client)
):
    """Send chat message - requires chat:write permission."""

    # Check permission (fail-closed: deny on errors)
    has_permission = await auth_client.check_permission_safe(
        user_id=token.user_id,
        org_id=token.org_id,
        permission="chat:write"
    )

    if not has_permission:
        raise HTTPException(status_code=403, detail="No chat:write permission")

    # Permission granted - proceed
    return {"success": True}
```

### Voorbeeld 2: Check Permission (gedetailleerd resultaat)

```python
@router.post("/send-message")
async def send_message(
    token: OAuthToken = Depends(validate_oauth_token),
    auth_client: AuthAPIClient = Depends(get_auth_api_client)
):
    """Send message with detailed permission info."""

    # Get detailed result
    result = await auth_client.check_permission(
        user_id=token.user_id,
        org_id=token.org_id,
        permission="chat:write"
    )

    if not result["allowed"]:
        logger.warning(
            "permission_denied",
            reason=result["reason"],
            user_id=token.user_id
        )
        raise HTTPException(status_code=403, detail=result["reason"])

    logger.info(
        "permission_granted",
        groups=result["groups"],  # Which groups granted permission
        user_id=token.user_id
    )

    # Proceed with action
    return {"success": True}
```

### Voorbeeld 3: Multiple Permission Checks

```python
@router.get("/my-permissions")
async def get_my_permissions(
    token: OAuthToken = Depends(validate_oauth_token),
    auth_client: AuthAPIClient = Depends(get_auth_api_client)
):
    """Check what permissions user has."""

    permissions_to_check = ["chat:read", "chat:write", "groups:read"]

    results = {}
    for permission in permissions_to_check:
        has_permission = await auth_client.check_permission_safe(
            user_id=token.user_id,
            org_id=token.org_id,
            permission=permission
        )
        results[permission] = has_permission

    return {"permissions": results}
```

---

## 3. Test Endpoints

De Chat API heeft nu voorbeeld endpoints om de integratie te testen:

### Test Permission Check
```bash
# Get access token from auth-api first
TOKEN="your-jwt-token-here"

# Check if you have chat:write permission
curl -X POST http://localhost:8001/api/chat/example/check-permission \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"permission": "chat:write"}'
```

**Response:**
```json
{
  "allowed": true,
  "permission": "chat:write",
  "groups": ["vrienden"],
  "reason": "User has permission"
}
```

### Test Protected Endpoint
```bash
curl -X POST http://localhost:8001/api/chat/example/send-message-with-auth-check \
  -H "Authorization: Bearer $TOKEN"
```

### Get My Permissions
```bash
curl http://localhost:8001/api/chat/example/my-permissions \
  -H "Authorization: Bearer $TOKEN"
```

---

## 4. How It Works

### Flow Diagram

```
User Request with JWT
     ↓
Chat API validates JWT (local)
     ↓
Chat API calls Auth API: "Does user have chat:write?"
     ↓
Auth API checks RBAC:
  - Is user in organization?
  - Is user in any group with chat:write permission?
     ↓
Auth API returns: {"allowed": true/false, "groups": [...]}
     ↓
Chat API allows or denies action
```

### Authentication Methods

Chat API → Auth API communication uses **API Key** (X-Service-Token header):

```python
# In AuthAPIClient (app/services/auth_api_client.py)
headers = {
    "X-Service-Token": settings.SERVICE_AUTH_TOKEN,  # ⬅️ Shared secret
    "Content-Type": "application/json"
}

response = await client.post(
    "http://auth-api:8000/api/v1/authorization/check",
    headers=headers,
    json={"user_id": ..., "org_id": ..., "permission": "chat:write"}
)
```

**Waarom API Key en niet OAuth?**
- ✅ Simpel: 1 env var, instant setup
- ✅ Snel: geen extra token request
- ✅ Goed voor interne microservices
- ❌ Geen rotation (manual update needed)

---

## 5. Available Permissions

| Permission | Beschrijving |
|------------|-------------|
| `chat:read` | Berichten en groepsgesprekken bekijken |
| `chat:write` | Berichten versturen en groepsgesprekken bewerken |
| `groups:read` | Groepen en leden bekijken |
| `groups:write` | Groepen en leden beheren |

**Gebruik minimal scopes principe!** Vraag alleen wat je echt nodig hebt.

---

## 6. Error Handling

### Network Errors

```python
try:
    result = await auth_client.check_permission(...)
except httpx.TimeoutException:
    # Auth API niet bereikbaar binnen timeout (3 seconden)
    logger.error("auth_api_timeout")
    # Fail-closed: deny access on timeout
    raise HTTPException(503, "Authorization service unavailable")
except httpx.HTTPStatusError as e:
    # Auth API returned error status (e.g., 500)
    logger.error("auth_api_error", status_code=e.response.status_code)
    raise HTTPException(503, "Authorization service error")
```

### Fail-Closed Security

```python
# ✅ GOED: Fail-closed (deny on errors)
has_permission = await auth_client.check_permission_safe(...)
if not has_permission:
    raise HTTPException(403)  # Deny on error OR permission denial

# ❌ SLECHT: Fail-open (allow on errors) - GEVAARLIJK!
try:
    result = await auth_client.check_permission(...)
    if result["allowed"]:
        # allow
except:
    # allow anyway (DANGEROUS!)
```

**Gebruik altijd `check_permission_safe()` voor fail-closed behavior!**

---

## 7. Caching (Future)

Auth API heeft al caching (L1 + L2 cache, 5 min TTL). Chat API hoeft GEEN extra cache te doen.

Als je toch wilt cachen in Chat API:
```python
# Optional: Cache in Chat API Redis
cache_key = f"perm:{user_id}:{org_id}:{permission}"
cached = await redis.get(cache_key)
if cached:
    return json.loads(cached)

# Cache miss: call Auth API
result = await auth_client.check_permission(...)

# Store in cache (2 min TTL)
await redis.setex(cache_key, 120, json.dumps(result))
```

**Maar:** Auth API cache is al snel genoeg (~2ms). Extra cache = extra complexity.

---

## 8. Troubleshooting

### Error: "Service authentication required"

**Oorzaak:** `SERVICE_AUTH_TOKEN` mismatch of ontbreekt.

**Oplossing:**
```bash
# Check auth-api .env
grep SERVICE_AUTH_TOKEN /mnt/d/activity/auth-api/.env

# Check chat-api .env
grep SERVICE_AUTH_TOKEN /mnt/d/activity/chat-api/.env

# Moeten EXACT matchen!
```

### Error: "Auth API unavailable"

**Oorzaak:** Auth API container is niet running of niet bereikbaar.

**Oplossing:**
```bash
# Check auth-api status
docker ps | grep auth-api

# Check logs
docker logs auth-api

# Start if needed
cd /mnt/d/activity/auth-api
docker compose up -d
```

### Permission altijd denied

**Oorzaak:** User heeft permissie niet via groepen.

**Debug:**
```sql
-- Check user's permissions in Auth API database
docker exec activity-postgres-db psql -U postgres -d activitydb -c "
SELECT * FROM activity.sp_get_user_permissions(
    'USER_UUID'::uuid,
    'ORG_UUID'::uuid
);
"
```

---

## 9. Testing

### Unit Test Voorbeeld

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.services.auth_api_client import AuthAPIClient

@pytest.mark.asyncio
async def test_check_permission_allowed():
    """Test permission check when allowed."""

    # Mock httpx client
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        "allowed": True,
        "groups": ["vrienden"],
        "reason": "User has permission"
    }

    with patch("httpx.AsyncClient.post", return_value=mock_response):
        client = AuthAPIClient()
        result = await client.check_permission(
            user_id="user-123",
            org_id="org-456",
            permission="chat:write"
        )

        assert result["allowed"] is True
        assert "vrienden" in result["groups"]

@pytest.mark.asyncio
async def test_check_permission_safe_on_error():
    """Test fail-closed behavior on errors."""

    # Mock httpx to raise exception
    with patch("httpx.AsyncClient.post", side_effect=Exception("Network error")):
        client = AuthAPIClient()
        result = await client.check_permission_safe(
            user_id="user-123",
            org_id="org-456",
            permission="chat:write"
        )

        # Should return False on errors (fail-closed)
        assert result is False
```

---

## 10. Production Checklist

Voordat je live gaat:

- [ ] `SERVICE_AUTH_TOKEN` is strong random string (64+ chars)
- [ ] `SERVICE_AUTH_TOKEN` matcht tussen auth-api en chat-api
- [ ] `AUTH_API_TIMEOUT` is ingesteld (default 3.0 seconden)
- [ ] Error logging is enabled (`LOG_LEVEL=INFO`)
- [ ] Test alle permission checks met echte users
- [ ] Verify fail-closed behavior werkt (deny on Auth API down)
- [ ] Monitor Auth API latency (p95 < 100ms)

---

## Contact

Vragen? Check:
- Auth API docs: `/mnt/d/activity/auth-api/docs/CHAT_API_OAUTH_HOWTO.md`
- Example code: `app/routes/example_auth_check.py`
- Logs: `docker logs -f chat-api | grep auth_api`
