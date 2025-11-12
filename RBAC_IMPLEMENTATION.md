# RBAC Implementation Guide - Chat API

## Overview

The Chat API implements **Role-Based Access Control (RBAC)** using a centralized authorization architecture:

- **Auth API**: Central source of truth for permissions
- **Redis Cache**: Local cache for authorization decisions with intelligent TTL
- **Circuit Breaker**: Resilience pattern for Auth API failures
- **Fail-Closed**: Denies access by default if Auth API unavailable (configurable)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CHAT API                              │
│                                                              │
│  ┌────────────┐         ┌──────────────────┐               │
│  │   Route    │────────▶│  Authorization   │               │
│  │  Handler   │         │   Dependency     │               │
│  └────────────┘         └─────────┬────────┘               │
│                                    │                         │
│                         ┌──────────▼──────────┐             │
│                         │  Authorization      │             │
│                         │     Service         │             │
│                         │  (Orchestrator)     │             │
│                         └──┬────────────┬─────┘             │
│                            │            │                    │
│                   ┌────────▼──┐    ┌───▼──────────┐        │
│                   │  Redis    │    │ Auth API     │        │
│                   │  Cache    │    │   Client     │        │
│                   │  (Fast)   │    │ (HTTP calls) │        │
│                   └───────────┘    └───┬──────────┘        │
│                                        │                    │
│                                ┌───────▼────────┐          │
│                                │ Circuit Breaker│          │
│                                │ (Resilience)   │          │
│                                └────────────────┘          │
└─────────────────────────────────────────────────────────────┘
                                    │
                            ┌───────▼────────┐
                            │   AUTH API     │
                            │ (Source of     │
                            │   Truth)       │
                            └────────────────┘
```

## Permissions

### Chat Permissions

| Permission | Description | Used In |
|------------|-------------|---------|
| `chat:create` | Create new chat groups | Future: group creation endpoint |
| `chat:read` | Read messages and groups | GET /groups, GET /messages, WebSocket |
| `chat:send_message` | Send and edit messages | POST /messages, PUT /messages |
| `chat:delete` | Delete messages | DELETE /messages |
| `chat:manage_members` | Add/remove group members | Future: member management |

### Dashboard Permissions

| Permission | Description | Used In |
|------------|-------------|---------|
| `dashboard:read_metrics` | View monitoring dashboard | GET /dashboard (optional) |

## Configuration

### Environment Variables

```env
# Auth API
AUTH_API_URL="http://auth-api:8000"
AUTH_API_TIMEOUT=3.0
AUTH_API_PERMISSION_CHECK_ENDPOINT="/api/v1/authorization/check"

# Caching
AUTH_CACHE_ENABLED=true
AUTH_CACHE_TTL_READ=300       # 5 minutes
AUTH_CACHE_TTL_WRITE=60        # 1 minute
AUTH_CACHE_TTL_ADMIN=30        # 30 seconds
AUTH_CACHE_TTL_DENIED=120      # 2 minutes

# Circuit Breaker
CIRCUIT_BREAKER_THRESHOLD=5
CIRCUIT_BREAKER_TIMEOUT=30
CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS=3

# Fail Policy (CRITICAL!)
AUTH_FAIL_OPEN=false  # false = Fail-Closed (RECOMMENDED)
```

### JWT Token Requirements

Tokens MUST include:
- `sub`: User ID (required)
- `org_id`: Organization ID (required for RBAC)

Example JWT payload:
```json
{
  "sub": "user-123",
  "org_id": "org-456",
  "username": "john",
  "email": "john@example.com",
  "exp": 1234567890
}
```

**Backward Compatibility**: Tokens without `org_id` will default to `"default-org"` with a warning log. This allows gradual migration.

## Usage in Routes

### Basic Permission Check

```python
from fastapi import APIRouter, Depends
from app.dependencies import require_permission, AuthContext

@router.post("/messages")
async def create_message(
    auth_context: AuthContext = Depends(require_permission("chat:send_message"))
):
    # User has permission, proceed
    user_id = auth_context.user_id
    org_id = auth_context.org_id
    ...
```

### Multiple Permissions (OR logic)

```python
from app.dependencies import require_any_permission

@router.get("/admin")
async def admin_endpoint(
    auth_context: AuthContext = Depends(
        require_any_permission("chat:admin", "dashboard:read_metrics")
    )
):
    # User has at least ONE of the permissions
    ...
```

### Multiple Permissions (AND logic)

```python
from app.dependencies import require_all_permissions

@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: str,
    auth_context: AuthContext = Depends(
        require_all_permissions("chat:delete", "chat:manage_members")
    )
):
    # User has ALL permissions
    ...
```

## Caching Strategy

### Cache Keys
```
auth:permission:{org_id}:{user_id}:{permission}
```

### TTL Logic
- **Read operations**: 5 minutes (frequent, safe)
- **Write operations**: 1 minute (data might change)
- **Admin operations**: 30 seconds (sensitive)
- **Denied permissions**: 2 minutes (prevent Auth API hammering)

### Cache Invalidation

```python
from app.core.authorization import get_authorization_service

auth_service = await get_authorization_service()

# Invalidate all permissions for a user (e.g., after role change)
await auth_service.invalidate_user_permissions(
    org_id="org-123",
    user_id="user-456"
)
```

**When to invalidate**:
- User's role changes
- User removed from groups
- Permissions modified
- User deleted

## Circuit Breaker

### States

- **CLOSED**: Normal operation, requests go to Auth API
- **OPEN**: Auth API failing, block all requests (Fail-Closed) or allow all (Fail-Open)
- **HALF_OPEN**: Testing if Auth API recovered

### State Transitions

```
CLOSED ──────────────────────> OPEN
  │       (N failures)           │
  │                              │
  │ (success)          (timeout) │
  │                              ▼
  └──────────── HALF_OPEN <──────┘
      (test success │
       returns to   │ (test failure
       CLOSED)      └──────> OPEN
```

### Thresholds

- Opens after **5 consecutive failures**
- Stays open for **30 seconds**
- Allows **3 test calls** in HALF_OPEN state

## Fail-Open vs Fail-Closed

### Fail-Closed (AUTH_FAIL_OPEN=false) - RECOMMENDED

**Behavior**: Denies access if Auth API unavailable

✅ **Advantages**:
- Secure by default
- Prevents unauthorized access during outages
- Compliant with security best practices

❌ **Disadvantages**:
- Service unavailable during Auth API outages
- Requires Auth API high availability

**Use when**: Security is paramount (production, sensitive data)

**HTTP Response**: `503 Service Unavailable`

### Fail-Open (AUTH_FAIL_OPEN=true) - DANGEROUS

**Behavior**: Allows access if Auth API unavailable

✅ **Advantages**:
- High availability
- Service continues during Auth API outages

❌ **Disadvantages**:
- **SECURITY RISK**: Anyone can access during outages
- NOT recommended for production

**Use when**: Development, testing, or internal tools only

## API Endpoints

All endpoints now require RBAC permissions:

| Method | Endpoint | Permission | Description |
|--------|----------|------------|-------------|
| GET | `/health` | None | Health check (includes Auth API status) |
| GET | `/api/chat/groups` | `chat:read` | Get user's groups |
| GET | `/api/chat/groups/{id}` | `chat:read` | Get specific group |
| GET | `/api/chat/groups/{id}/messages` | `chat:read` | Get paginated messages |
| POST | `/api/chat/groups/{id}/messages` | `chat:send_message` | Create message |
| PUT | `/api/chat/messages/{id}` | `chat:send_message` | Update own message |
| DELETE | `/api/chat/messages/{id}` | `chat:delete` | Delete own message |
| WS | `/api/chat/ws/{group_id}` | `chat:read` | Real-time chat connection |

## Monitoring

### Structured Logs

The authorization system logs detailed events:

**Permission Granted**:
```json
{
  "event": "permission_check_passed",
  "user_id": "user-123",
  "org_id": "org-456",
  "permission": "chat:send_message",
  "cached": true,
  "source": "cache"
}
```

**Permission Denied**:
```json
{
  "event": "permission_denied",
  "user_id": "user-123",
  "org_id": "org-456",
  "permission": "chat:admin",
  "source": "auth_api"
}
```

**Circuit Breaker Opened**:
```json
{
  "event": "circuit_breaker_opened",
  "failure_count": 5,
  "threshold": 5
}
```

**Auth API Unavailable (Fail-Closed)**:
```json
{
  "event": "auth_unavailable_fail_closed",
  "user_id": "user-123",
  "org_id": "org-456",
  "permission": "chat:read",
  "policy": "fail_closed"
}
```

### Health Check

```bash
curl http://localhost:8001/health | jq
```

Response includes Auth API status:
```json
{
  "status": "healthy",
  "service": "chat-api",
  "timestamp": "2025-11-12T10:00:00Z",
  "checks": {
    "mongodb": "healthy",
    "redis": "healthy",
    "auth_api": "healthy"
  }
}
```

**Auth API States**:
- `"healthy"` - Auth API responding normally
- `"degraded: circuit_breaker_open_or_unavailable"` - Circuit breaker open or Auth API down
- `"unhealthy: ConnectionError"` - Cannot connect to Auth API

## Troubleshooting

### Permission Denied Errors

**Symptom**: `403 Forbidden` response

**Diagnosis**:

1. **Check JWT token includes org_id**:
   ```bash
   # Decode token (requires jwt-cli or similar)
   echo $TOKEN | jwt decode
   ```

   Should show:
   ```json
   {
     "sub": "user-123",
     "org_id": "org-456",
     ...
   }
   ```

2. **Verify permission exists in Auth API**:
   ```bash
   curl -X POST http://auth-api:8000/api/v1/authorization/check \
     -H "Content-Type: application/json" \
     -d '{
       "organization_id": "org-123",
       "user_id": "user-456",
       "permission": "chat:read"
     }'
   ```

3. **Check cache**:
   ```bash
   redis-cli GET "auth:permission:org-123:user-456:chat:read"
   ```

4. **Review logs**:
   ```bash
   docker logs chat-api | grep "permission_check_failed"
   ```

**Solutions**:
- Ensure user has correct role in Auth API
- Verify Auth API permissions table includes `chat:*` permissions
- Clear cache if stale: `redis-cli DEL "auth:permission:org-123:user-456:*"`

### Auth API Unavailable

**Symptom**: `503 Service Unavailable` response (Fail-Closed mode)

**Diagnosis**:

1. **Check circuit breaker state**:
   ```bash
   redis-cli GET "auth:circuit_breaker"
   ```

   Example output:
   ```json
   {
     "state": "open",
     "failure_count": 5,
     "last_failure_time": "2025-11-12T10:00:00"
   }
   ```

2. **Verify Auth API connectivity**:
   ```bash
   curl http://auth-api:8000/health
   ```

3. **Check logs**:
   ```bash
   docker logs chat-api | grep "auth_api"
   ```

**Solutions**:
- Restart Auth API if down
- Wait for circuit breaker timeout (30s) to auto-recover
- Manually reset circuit breaker: `redis-cli DEL "auth:circuit_breaker"`
- Temporarily enable Fail-Open for emergency access (NOT recommended)

### Cache Issues

**Symptom**: Stale permissions or slow permission checks

**Diagnosis**:

1. **Verify Redis connection**:
   ```bash
   redis-cli PING
   # Should return: PONG
   ```

2. **Check cache configuration**:
   ```bash
   echo $REDIS_URL
   echo $AUTH_CACHE_ENABLED
   ```

3. **Inspect cache contents**:
   ```bash
   redis-cli KEYS "auth:permission:*"
   ```

**Solutions**:
- Ensure Redis is running
- Verify `REDIS_URL` is correct
- Clear all auth cache: `redis-cli DEL $(redis-cli KEYS "auth:permission:*")`
- Disable caching temporarily: `AUTH_CACHE_ENABLED=false`

### WebSocket Connection Fails

**Symptom**: WebSocket immediately closes after connection

**Diagnosis**:

1. **Check token format**:
   ```javascript
   // Correct: token as query parameter
   ws://localhost:8001/api/chat/ws/group-123?token=YOUR_JWT

   // WRONG: token in headers (WebSocket doesn't support custom headers)
   ```

2. **Verify permission**:
   - WebSocket requires `chat:read` permission
   - Check if user has this permission

3. **Review logs**:
   ```bash
   docker logs chat-api | grep "websocket"
   ```

**Solutions**:
- Ensure token is passed as query parameter
- Grant `chat:read` permission to user
- Check token expiration

## Testing

### Manual Testing

#### 1. Generate Test JWT Token

```python
# generate_test_token.py
from jose import jwt
from datetime import datetime, timedelta

SECRET = "your-secret-key-change-in-production"  # Match .env JWT_SECRET

payload = {
    "sub": "test-user-123",
    "org_id": "test-org-456",
    "username": "testuser",
    "email": "test@example.com",
    "exp": datetime.utcnow() + timedelta(days=1)
}

token = jwt.encode(payload, SECRET, algorithm="HS256")
print(f"Token: {token}")
```

Run:
```bash
python generate_test_token.py
export TOKEN="eyJ..."
```

#### 2. Test REST Endpoints

```bash
# Test GET /groups (requires chat:read)
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8001/api/chat/groups

# Test POST /messages (requires chat:send_message)
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Hello World"}' \
  http://localhost:8001/api/chat/groups/GROUP_ID/messages

# Test health check (no auth required)
curl http://localhost:8001/health | jq '.checks.auth_api'
```

#### 3. Test WebSocket

```javascript
// test_websocket.js
const ws = new WebSocket(
  `ws://localhost:8001/api/chat/ws/GROUP_ID?token=${TOKEN}`
);

ws.onopen = () => {
  console.log('Connected');
  ws.send(JSON.stringify({ type: 'ping' }));
};

ws.onmessage = (event) => {
  console.log('Received:', JSON.parse(event.data));
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};
```

#### 4. Test Permission Denial

```bash
# Remove permission from user in Auth API
curl -X DELETE \
  http://auth-api:8000/api/v1/users/USER_ID/permissions/chat:read

# Clear cache
redis-cli DEL "auth:permission:org-456:user-123:chat:read"

# Try to access endpoint - should get 403
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8001/api/chat/groups
```

#### 5. Test Circuit Breaker

```bash
# Stop Auth API
docker stop auth-api

# Make 5+ requests to trigger circuit breaker
for i in {1..6}; do
  curl -H "Authorization: Bearer $TOKEN" \
    http://localhost:8001/api/chat/groups
  sleep 1
done

# Check circuit breaker state
redis-cli GET "auth:circuit_breaker"

# Restart Auth API
docker start auth-api

# Wait 30s for circuit breaker to recover
sleep 30

# Try again - should work
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8001/api/chat/groups
```

### Integration Tests

```python
# tests/test_rbac_integration.py
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_permission_check_success():
    """Test successful permission check"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/chat/groups",
            headers={"Authorization": f"Bearer {valid_token}"}
        )
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_permission_denied():
    """Test permission denial"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/chat/groups",
            headers={"Authorization": f"Bearer {invalid_token}"}
        )
        assert response.status_code == 403

@pytest.mark.asyncio
async def test_auth_api_unavailable_fail_closed():
    """Test Fail-Closed behavior when Auth API is down"""
    # Mock Auth API client to return None
    # ...

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/chat/groups",
            headers={"Authorization": f"Bearer {valid_token}"}
        )
        assert response.status_code == 503
```

## Migration from Legacy Auth

### Phase 1: Backward Compatible (Current)

- ✅ JWT tokens without `org_id` use `"default-org"`
- ✅ Legacy `get_current_user()` still works
- ✅ New routes use `require_permission()`

### Phase 2: Full RBAC (Future)

- ❌ Require `org_id` in all JWT tokens
- ❌ Deprecate `get_current_user()`
- ❌ Update all routes to use RBAC

### Migration Steps

1. **Update Auth API** to include `org_id` in JWT tokens:
   ```python
   # In Auth API token generation
   payload = {
       "sub": user.id,
       "org_id": user.organization_id,  # ADD THIS
       "exp": ...
   }
   ```

2. **Test with new tokens** in development environment

3. **Enable strict mode** by removing fallback:
   ```python
   # In app/middleware/auth.py
   if org_id is None:
       raise UnauthorizedError("Token missing org_id")
   ```

4. **Remove legacy code**:
   - Remove `get_current_user()` function
   - Update any remaining routes to use `require_permission()`

## Security Best Practices

1. ✅ **Always use Fail-Closed** in production (`AUTH_FAIL_OPEN=false`)
2. ✅ **Require org_id in tokens** for multi-tenancy
3. ✅ **Use short TTL** for admin permissions (30s)
4. ✅ **Monitor circuit breaker** state changes
5. ✅ **Log all permission denials** for audit trail
6. ✅ **Invalidate cache** immediately after role changes
7. ✅ **Test Auth API failure scenarios** before production
8. ✅ **Use HTTPS** for Auth API communication
9. ✅ **Rotate JWT secrets** regularly
10. ✅ **Monitor health endpoint** for Auth API status

## Performance Considerations

### Cache Hit Rate

Target: **>90% cache hit rate** for production traffic

Monitor:
```bash
# Count cache hits vs misses in logs
docker logs chat-api | grep "auth_cache_hit" | wc -l
docker logs chat-api | grep "auth_cache_miss" | wc -l
```

Improve:
- Increase TTL for read operations if acceptable
- Warm cache on startup for common permissions
- Use batch permission checks (future enhancement)

### Auth API Load

Expected reduction: **90-95%** with caching enabled

Monitor:
```bash
# Check Auth API request rate
docker logs chat-api | grep "auth_api_check" | wc -l
```

### Redis Memory Usage

Estimate: **~100 bytes per cached permission**

For 10,000 users × 5 permissions = **~5MB**

Monitor:
```bash
redis-cli INFO memory | grep used_memory_human
redis-cli DBSIZE
```

## Future Enhancements

- [ ] Add permission caching warming on startup
- [ ] Implement batch permission checks for efficiency
- [ ] Add Prometheus metrics for authorization (hit rate, latency, etc.)
- [ ] Support hierarchical permissions (e.g., `chat:*` for all chat permissions)
- [ ] Add permission auditing/logging to separate system
- [ ] Implement rate limiting per user/org at authorization level
- [ ] Add GraphQL support for permission checks
- [ ] Create admin API for cache invalidation
- [ ] Support dynamic TTL based on permission sensitivity
- [ ] Add circuit breaker dashboard visualization

## Support

For issues or questions:
1. Check logs: `docker logs chat-api`
2. Review this documentation
3. Check Auth API documentation
4. Open GitHub issue with:
   - Logs (sanitized)
   - Configuration (sanitized)
   - Steps to reproduce

## License

See main project LICENSE file.
