# OAuth 2.0 Resource Server Migration Plan

## Executive Summary

This document outlines the migration from remote Auth API permission checks to local JWT validation using OAuth 2.0 Resource Server patterns. This upgrade delivers significant performance, security, and resilience improvements.

## Current Architecture (Before)

```
Request → Chat-API → Extract JWT → Call Auth-API → Get Permissions → Check Permission → Response
                                    ^^^^^^^^^^^^^^^
                                    PERFORMANCE BOTTLENECK
                                    - 50-200ms per request
                                    - Network dependency
                                    - Auth API load
```

**Problems:**
- **Performance**: 2-3 network calls per request (JWT validation + permission check)
- **Latency**: 50-200ms overhead per request
- **Coupling**: Chat-API depends on Auth-API availability
- **Scalability**: Auth-API becomes bottleneck under load
- **Single Point of Failure**: Auth-API down = Chat-API down

## New Architecture (After)

```
Request → Chat-API → Extract JWT → Validate Locally (JWKS) → Check Claims → Response
                                    ^^^^^^^^^^^^^^^^^^^^^^
                                    <1ms OVERHEAD
                                    - No network calls
                                    - Crypto validation
                                    - Claims-based auth
```

**Benefits:**
- **Performance**: <1ms overhead (99% reduction)
- **Latency**: Sub-millisecond JWT validation
- **Decoupling**: Chat-API independent of Auth-API (cached keys)
- **Scalability**: Linear scaling, no bottlenecks
- **Resilience**: Continues working if Auth-API temporarily down

## Prerequisites

### Auth-API Must Provide

1. **RS256 Signing**
   - All access tokens must be signed with RS256 (asymmetric)
   - Currently uses HS256 (symmetric) - needs upgrade

2. **JWKS Endpoint**
   ```
   GET /.well-known/jwks.json

   Response:
   {
     "keys": [
       {
         "kty": "RSA",
         "kid": "key-2024-01",
         "use": "sig",
         "n": "...",  // public key modulus
         "e": "AQAB"  // public exponent
       }
     ]
   }
   ```

3. **Enhanced JWT Claims**
   ```json
   {
     "iss": "http://auth-api:8000",
     "aud": "chat-api",
     "sub": "user-uuid-12345",
     "org_id": "org-uuid-67890",
     "roles": ["admin", "member"],
     "permissions": [
       "groups:read",
       "groups:create",
       "groups:update",
       "groups:delete",
       "messages:send",
       "messages:edit",
       "messages:delete"
     ],
     "exp": 1678886400,
     "iat": 1678882800,
     "username": "john.doe",
       "email": "john@example.com"
   }
   ```

## Implementation Status

### ✅ Completed

1. **Configuration** (`app/config.py`)
   - OAuth 2.0 settings (issuer, audience, JWKS URL)
   - JWKS cache and refresh configuration
   - Backward compatibility settings marked as deprecated

2. **JWKS Manager** (`app/core/jwks_manager.py`)
   - Production-grade key fetching and caching
   - Automatic background refresh (every 30 minutes)
   - Exponential backoff retry logic
   - Thread-safe key storage
   - Comprehensive error handling

3. **OAuth2 Middleware** (`app/middleware/oauth2.py`)
   - Local JWT validation (RS256)
   - Public key lookup via JWKS manager
   - Claims extraction and validation
   - AuthContext with permissions
   - Detailed error responses

4. **Dependencies Module** (`app/dependencies.py` - NEW VERSION READY)
   - `get_auth_context()` - Full auth context
   - `get_current_user()` - Simple user ID
   - `require_permission()` - Permission-based auth
   - `require_any_permission()` - OR logic
   - `require_all_permissions()` - AND logic
   - `require_role()` - Role-based auth

### 🚧 Pending

5. **Main Application** (`app/main.py`)
   - Replace old auth middleware with OAuth2Middleware
   - Initialize JWKS manager on startup
   - Close JWKS manager on shutdown

6. **Route Updates**
   - Update imports to use new dependencies
   - Test permission checks work with JWT claims

7. **Legacy Code Removal**
   - Remove `app/core/authorization.py` (remote Auth API calls)
   - Remove old `app/middleware/auth.py` (keep for backward compat during transition)
   - Remove circuit breaker, cache logic (no longer needed)

8. **Testing**
   - Generate test JWT tokens with Auth-API
   - Validate all endpoints work with new auth
   - Performance benchmarks (before/after)

9. **Documentation**
   - Update API documentation
   - Create runbook for operations
   - Document troubleshooting scenarios

## Migration Steps

### Phase 1: Auth-API Prerequisites (EXTERNAL)

**Not part of this PR - Auth-API team must implement:**

```bash
# Auth-API must:
1. Implement RS256 signing
2. Create JWKS endpoint
3. Add permissions array to JWT payload
4. Test with sample tokens
```

### Phase 2: Chat-API Implementation (THIS PR)

**Step 1: Enable OAuth2 Middleware**

```python
# app/main.py

from app.middleware.oauth2 import OAuth2Middleware
from app.core.jwks_manager import get_jwks_manager, close_jwks_manager

@app.on_event("startup")
async def startup():
    # Initialize JWKS manager (fetch keys)
    await get_jwks_manager()
    logger.info("jwks_manager_ready")

@app.on_event("shutdown")
async def shutdown():
    # Cleanup JWKS manager
    await close_jwks_manager()

# Add OAuth2 middleware
app.add_middleware(OAuth2Middleware)
```

**Step 2: Update Route Dependencies**

```python
# OLD (remote Auth API calls)
from app.dependencies import require_permission as old_require_permission

@router.get("/groups")
async def list_groups(
    auth: AuthContext = Depends(old_require_permission("groups:read"))
):
    # Slow: Makes Auth API call
    ...

# NEW (JWT claims only)
from app.dependencies import require_permission, get_auth_context

@router.get("/groups")
async def list_groups(
    auth: AuthContext = Depends(require_permission("groups:read"))
):
    # Fast: Reads from JWT claims (<1ms)
    if auth.has_permission("groups:read"):
        ...
```

**Step 3: Remove Legacy Code**

```bash
# After all routes updated and tested:
rm app/core/authorization.py  # Old Auth API client
rm app/core/cache.py  # No longer needed
# Keep app/middleware/auth.py temporarily for backward compat
```

### Phase 3: Testing & Validation

**Generate Test Token (with Auth-API)**

```python
# On Auth-API side
import jwt
from datetime import datetime, timedelta

payload = {
    "iss": "http://auth-api:8000",
    "aud": "chat-api",
    "sub": "test-user-123",
    "org_id": "test-org-456",
    "username": "testuser",
    "email": "test@example.com",
    "roles": ["member"],
    "permissions": [
        "groups:read",
        "groups:create",
        "messages:send"
    ],
    "exp": datetime.utcnow() + timedelta(hours=1),
    "iat": datetime.utcnow()
}

# Sign with RS256 private key
token = jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": "key-2024-01"})
```

**Test Requests**

```bash
# Test authentication
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8001/api/chat/groups

# Test permission denied
curl -H "Authorization: Bearer $LIMITED_TOKEN" \
  http://localhost:8001/api/chat/groups
# Should return 403 if token lacks groups:read permission

# Test expired token
curl -H "Authorization: Bearer $EXPIRED_TOKEN" \
  http://localhost:8001/api/chat/groups
# Should return 401 with "token_expired" error
```

### Phase 4: Performance Validation

**Benchmark Results (Expected)**

| Metric | Before (Remote) | After (Local) | Improvement |
|--------|----------------|---------------|-------------|
| Auth Overhead | 50-200ms | <1ms | 99% faster |
| Requests/sec | 500 | 50,000+ | 100x |
| Auth API Load | 100% | 0% | Eliminated |
| Failure Coupling | Yes | No | Resilient |

## Rollback Plan

**If Issues Arise:**

1. **Revert Middleware**
   ```python
   # In main.py - comment out OAuth2Middleware
   # app.add_middleware(OAuth2Middleware)
   ```

2. **Use Feature Flag**
   ```python
   # config.py
   USE_OAUTH2_AUTH: bool = False  # Set to False to disable

   # main.py
   if settings.USE_OAUTH2_AUTH:
       app.add_middleware(OAuth2Middleware)
   else:
       # Use old auth
       pass
   ```

3. **Gradual Rollout**
   - Enable OAuth2 for specific endpoints first
   - Monitor error rates and performance
   - Gradually expand coverage

## Troubleshooting

### Common Issues

**"JWKS fetch failed"**
- Check `AUTH_API_JWKS_URL` is correct
- Verify Auth-API's JWKS endpoint is accessible
- Check network connectivity

**"Key ID 'xyz' not found"**
- Auth-API rotated keys
- JWKS manager will auto-refresh
- If persistent, check Auth-API is publishing correct keys

**"Token validation failed"**
- Check `AUTH_API_ISSUER` matches token's `iss` claim
- Check `JWT_AUDIENCE` matches token's `aud` claim
- Verify token not expired
- Check token signature (RS256 vs HS256)

**Performance regression**
- Check JWKS keys are cached (not fetching on every request)
- Monitor `/metrics` for auth timing
- Review logs for errors

## Monitoring & Observability

**Key Metrics**

```
# Prometheus metrics
oauth2_token_validations_total
oauth2_token_validation_duration_seconds
oauth2_permission_checks_total
jwks_refresh_total
jwks_refresh_failures_total
jwks_key_cache_hits_total
jwks_key_cache_misses_total
```

**Dashboard Queries**

```promql
# Average auth latency
rate(oauth2_token_validation_duration_seconds_sum[5m]) /
rate(oauth2_token_validation_duration_seconds_count[5m])

# Permission denial rate
rate(oauth2_permission_denied_total[5m]) /
rate(oauth2_token_validations_total[5m])

# JWKS health
1 - rate(jwks_refresh_failures_total[5m])
```

## Security Considerations

### What's Improved

- **Signature Validation**: Cryptographic RS256 validation
- **Issuer Validation**: Prevents tokens from other systems
- **Audience Validation**: Prevents token reuse across services
- **Expiration Validation**: Prevents replay attacks
- **Key Rotation Support**: Seamless key updates

### What to Monitor

- Invalid token attempts (potential attacks)
- Permission denial patterns (enumeration attempts)
- JWKS fetch failures (Auth-API availability)
- Expired token rate (client token management)

## Timeline

- **Day 1**: Implement JWKS manager and OAuth2 middleware ✅
- **Day 2**: Update dependencies and main.py (pending)
- **Day 3**: Update all route handlers (pending)
- **Day 4**: Testing and validation (pending)
- **Day 5**: Performance benchmarks and documentation (pending)
- **Day 6**: Production deployment

## Success Criteria

- ✅ All endpoints use JWT claims for authorization
- ✅ No remote Auth API calls during request handling
- ✅ <1ms auth overhead per request
- ✅ Zero downtime deployment
- ✅ Backward compatibility maintained
- ✅ Comprehensive test coverage
- ✅ Documentation complete
- ✅ Monitoring dashboards updated

## Team Responsibilities

### Chat-API Team (This PR)
- Implement OAuth2 Resource Server
- Update route dependencies
- Testing and validation
- Documentation

### Auth-API Team (External)
- Implement RS256 signing
- Create JWKS endpoint
- Add permissions to JWT
- Coordinate key rotation

### DevOps Team
- Update environment variables
- Monitor metrics during rollout
- Update dashboards and alerts

## References

- [RFC 6750: Bearer Token Usage](https://tools.ietf.org/html/rfc6750)
- [RFC 7519: JSON Web Token](https://tools.ietf.org/html/rfc7519)
- [RFC 7517: JSON Web Key](https://tools.ietf.org/html/rfc7517)
- [OAuth 2.0 Resource Server Best Practices](https://oauth.net/2/resource-servers/)

## Questions?

Contact: Engineering Team
Slack: #chat-api-migration
