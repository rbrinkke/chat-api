# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Chat API** is a real-time messaging service built with **FastAPI**, **MongoDB/Beanie ODM**, and **WebSocket** support. It integrates with Auth API for **runtime permission validation** using a group-based RBAC system.

### Key Features

- **Real-time messaging** via WebSocket
- **Runtime permission checks** via Auth API (NOT token-based scopes)
- **Group-based RBAC** - permissions granted through group membership
- **Multi-tenant isolation** - strict org_id validation
- **MongoDB storage** with Beanie ODM
- **Structured logging** with correlation IDs

### Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ JWT Token (user_id + org_id)
       │ NO permissions in token!
       ▼
┌─────────────────────────────────┐
│        Chat API (FastAPI)       │
│  1. Validate JWT                │
│  2. Check permission via        │
│     Auth API (runtime)          │
│  3. Execute business logic      │
└─────────┬───────────────────────┘
          │
          ▼
┌─────────────────────────────────┐
│     Auth API                    │
│  POST /api/v1/authorization/    │
│       check                     │
│  • X-Service-Token auth         │
│  • Checks database via          │
│    sp_user_has_permission()     │
└─────────────────────────────────┘
```

## Critical Concept: Runtime Permission Validation

**⚠️ BELANGRIJK**: Chat API gebruikt GEEN OAuth scopes in JWT tokens!

### Hoe het NIET werkt
```json
❌ JWT Token bevat GEEN permissions:
{
  "sub": "user-id",
  "org_id": "org-id",
  "scope": "chat:read chat:write"  // ← Dit bestaat NIET!
}
```

### Hoe het WEL werkt
```json
✅ JWT Token bevat ALLEEN identifiers:
{
  "sub": "user-id",
  "org_id": "org-id",
  "type": "access"
}
```

Bij elke request:
1. Chat API valideert JWT token (signature + expiration)
2. Chat API vraagt Auth API: "Heeft user X permission Y?"
3. Auth API checkt database via stored procedure
4. Auth API antwoordt: `{"allowed": true/false}`
5. Chat API accepteert of weigert request

**Zie `AUTHORIZATION.md` voor volledige flow documentatie.**

## Quick Start

### 1. Start Infrastructure

```bash
# Start PostgreSQL, Redis, MongoDB
./scripts/start-infra.sh

# Verify services
./scripts/status.sh
```

### 2. Configure Environment

Create `.env` file:

```bash
# MongoDB
MONGODB_URI=mongodb://mongodb:27017
MONGODB_DB=chat_db

# JWT Configuration (MUST match auth-api)
JWT_SECRET_KEY=your-jwt-secret-min-32-chars-change-in-production

# Auth API Integration (CRITICAL for permission checks)
AUTH_API_URL=http://auth-api:8000
SERVICE_AUTH_TOKEN=your-service-token-change-in-production

# Server
HOST=0.0.0.0
PORT=8001
ENVIRONMENT=development

# Logging
LOG_LEVEL=INFO
LOG_JSON_FORMAT=false
```

### 3. Start Service

```bash
# Via Docker Compose
docker compose up -d

# Or locally
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

### 4. Load Test Data

```bash
# Load RBAC test data into Auth API database
docker exec -i activity-postgres-db psql -U postgres -d activitydb < test_rbac_setup.sql

# Verify test setup
# See TEST_DATA_README.md for details
```

### 5. Test Permission Checks

```bash
# Test via Auth API authorization endpoint
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

## Common Commands

### Development

```bash
# Install dependencies
pip install -r requirements.txt

# Start MongoDB
docker run -d -p 27017:27017 --name mongodb mongo:latest

# Start API with auto-reload
uvicorn app.main:app --reload --port 8001

# Enable debug logging
export LOG_LEVEL=DEBUG
uvicorn app.main:app --reload
```

### Docker Operations

```bash
# Build and start
docker compose up -d

# Rebuild after code changes (CRITICAL!)
docker compose build chat-api --no-cache
docker compose restart chat-api

# View logs
docker logs -f chat-api

# Filter logs by level
docker logs chat-api | grep '"level":"error"'
```

### MongoDB Operations

```bash
# Access MongoDB shell
mongosh

# Switch to database
use chat_db

# View all groups
db.groups.find().pretty()

# View messages
db.messages.find().limit(10).pretty()

# Count messages per group
db.messages.aggregate([
  { $match: { is_deleted: false } },
  { $group: { _id: "$group_id", count: { $sum: 1 } } },
  { $sort: { count: -1 } }
])
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_authorization.py -v

# Test with Auth API integration
pytest tests/test_integration.py -v
```

## Permission Levels

### chat:read
- View messages in authorized groups
- WebSocket connection for real-time updates

### chat:write
- Create messages
- Edit own messages
- Delete own messages (soft delete)
- Includes all chat:read rights

### chat:admin
- Delete ANY message (including others)
- Moderate users
- Group management
- Includes all chat:write rights

**See `AUTHORIZATION.md` for complete permission documentation.**

## Test Users

Quick reference for test data (loaded via `test_rbac_setup.sql`):

| User | Email | Groups | Permissions |
|------|-------|--------|-------------|
| Admin | chattest-admin@example.com | vrienden | chat:read, chat:write |
| User1 | chattest-user1@example.com | vrienden | chat:read, chat:write |
| User2 | chattest-user2@example.com | observers | NONE |
| Moderator | chattest-moderator@example.com | moderators | chat:admin |

**Organization ID**: `99999999-9999-9999-9999-999999999999`

**See `TEST_DATA_README.md` for complete test data documentation.**

## Critical Configuration

### JWT Secret Matching

**⚠️ CRITICAL**: JWT_SECRET_KEY MUST match between auth-api and chat-api!

```bash
# Check both secrets
cat /mnt/d/activity/auth-api/.env | grep JWT_SECRET_KEY
cat /mnt/d/activity/chat-api/.env | grep JWT_SECRET_KEY

# Must be IDENTICAL!
```

If secrets don't match:
- JWT validation will ALWAYS fail
- All requests will return 401 Unauthorized
- Error: "Invalid token signature"

### Service Token Configuration

**⚠️ CRITICAL**: SERVICE_AUTH_TOKEN required for Auth API communication!

```bash
# Generate strong service token
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Set in .env
SERVICE_AUTH_TOKEN=<generated-token>
```

Chat API uses this token to authenticate as a service when calling Auth API's `/api/v1/authorization/check` endpoint.

## Development Patterns

### Always Rebuild After Code Changes

**CRITICAL**: `docker compose restart` does NOT pick up code changes!

```bash
# Wrong (uses old cached image)
docker compose restart chat-api

# Right (rebuilds with new code)
docker compose build chat-api --no-cache
docker compose restart chat-api
```

Rebuild required after:
- Python code changes
- Dependency updates (requirements.txt)
- Environment variable changes
- Dockerfile modifications

### Debug Permission Issues

If permissions are denied unexpectedly:

```bash
# 1. Check Auth API is accessible
docker exec -it chat-api curl http://auth-api:8000/health

# 2. Test permission check directly
curl -X POST http://localhost:8000/api/v1/authorization/check \
  -H "X-Service-Token: $SERVICE_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "org_id": "99999999-9999-9999-9999-999999999999",
    "user_id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
    "permission": "chat:read"
  }'

# 3. Check Chat API logs
docker logs chat-api | grep permission_check

# 4. Check Auth API logs
docker logs auth-api | grep authorization

# 5. Test stored procedure directly
docker exec -i activity-postgres-db psql -U postgres -d activitydb -c "
SELECT activity.sp_user_has_permission(
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID,
    '99999999-9999-9999-9999-999999999999'::UUID,
    'chat', 'read'
);
"
```

### Structured Logging

All log messages use structured format with correlation IDs:

```python
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Log permission check
logger.info(
    "permission_check",
    user_id=user_id,
    org_id=org_id,
    permission="chat:read",
    allowed=True
)

# Log permission denial
logger.warning(
    "permission_denied",
    user_id=user_id,
    org_id=org_id,
    permission="chat:write",
    reason="User not in any group with permission"
)
```

Correlation ID automatically injected via middleware for request tracing.

## Troubleshooting

### "Invalid token" on every request

**Cause**: JWT_SECRET_KEY mismatch between auth-api and chat-api

**Solution**:
```bash
# Verify both secrets match
diff <(cat ../auth-api/.env | grep JWT_SECRET_KEY) \
     <(cat .env | grep JWT_SECRET_KEY)

# Should show NO differences
```

### "Service authentication failed"

**Cause**: X-Service-Token doesn't match Auth API's SERVICE_AUTH_TOKEN

**Solution**:
```bash
# Check Auth API service token
cat ../auth-api/.env | grep SERVICE_AUTH_TOKEN

# Update Chat API .env to match
SERVICE_AUTH_TOKEN=<same-value-as-auth-api>

# Restart service
docker compose restart chat-api
```

### "Permission denied" but user is in correct group

**Debug steps**:
```bash
# 1. Verify user is in organization
docker exec -i activity-postgres-db psql -U postgres -d activitydb -c "
SELECT * FROM activity.organization_members
WHERE user_id = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'
  AND organization_id = '99999999-9999-9999-9999-999999999999';
"

# 2. Verify user is in group
docker exec -i activity-postgres-db psql -U postgres -d activitydb -c "
SELECT g.name, ug.added_at
FROM activity.user_groups ug
JOIN activity.groups g ON ug.group_id = g.id
WHERE ug.user_id = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee';
"

# 3. Verify group has permission
docker exec -i activity-postgres-db psql -U postgres -d activitydb -c "
SELECT p.resource, p.action
FROM activity.group_permissions gp
JOIN activity.permissions p ON gp.permission_id = p.id
WHERE gp.group_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
"
```

### Auth API connection timeout

**Cause**: Chat API container can't reach Auth API

**Debug**:
```bash
# Test connectivity from Chat API container
docker exec -it chat-api curl -v http://auth-api:8000/health

# Check network configuration
docker network inspect activity-network

# Verify both services on same network
docker inspect chat-api | grep NetworkMode
docker inspect auth-api | grep NetworkMode

# Check AUTH_API_URL in Chat API
docker exec -it chat-api env | grep AUTH_API_URL
```

### Code changes not reflected

**Cause**: Forgot to rebuild Docker image

**Solution**:
```bash
# Always rebuild after code changes
docker compose build chat-api --no-cache
docker compose restart chat-api

# Verify new code is running
docker compose logs chat-api | head -20
```

## Documentation

### Primary Documentation
- **`AUTHORIZATION.md`** - Complete authorization flow, permission levels, runtime checks
- **`TEST_DATA_README.md`** - Test data setup, test users, verification queries
- **`CLAUDE.md`** - This file (quick start, troubleshooting)

### Related Documentation
- **Auth API**: `/mnt/d/activity/auth-api/CLAUDE.md`
- **Database Schema**: Auth API migrations (`/mnt/d/activity/auth-api/migrations/`)
- **Main Project**: `/mnt/d/activity/CLAUDE.md`

## Service Integration

### Calling Auth API for Permission Checks

**Endpoint**: `POST /api/v1/authorization/check`

**Example**:
```python
import httpx
from app.core.config import get_settings

settings = get_settings()

async def check_permission(org_id: str, user_id: str, permission: str) -> bool:
    url = f"{settings.AUTH_API_URL}/api/v1/authorization/check"

    headers = {
        "X-Service-Token": settings.SERVICE_AUTH_TOKEN,
        "Content-Type": "application/json"
    }

    payload = {
        "org_id": org_id,
        "user_id": user_id,
        "permission": permission
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload, timeout=5.0)

        if response.status_code == 200:
            data = response.json()
            return data.get("allowed", False)

        return False
```

**See `AUTHORIZATION.md` for complete implementation guide.**

## Production Checklist

Before deploying to production:

**Security**:
- [ ] Change JWT_SECRET_KEY to strong random string (64+ chars)
- [ ] Change SERVICE_AUTH_TOKEN to strong random string (32+ chars)
- [ ] Set ENVIRONMENT=production
- [ ] Configure HTTPS/TLS termination
- [ ] Review CORS origins for production domains

**Infrastructure**:
- [ ] Use managed MongoDB (e.g., MongoDB Atlas)
- [ ] Configure connection pooling
- [ ] Setup log aggregation (Loki, ELK, CloudWatch)
- [ ] Configure monitoring alerts
- [ ] Setup automated backups

**Services**:
- [ ] Set LOG_LEVEL=INFO or WARNING
- [ ] Enable JSON logging (LOG_JSON_FORMAT=true)
- [ ] Configure rate limiting
- [ ] Review resource limits (CPU, memory)
- [ ] Test failover scenarios

**Performance**:
- [ ] Implement Redis caching for permission checks (5 min TTL)
- [ ] Setup MongoDB indexes for common queries
- [ ] Configure connection pooling for Auth API calls
- [ ] Load test permission check performance

## Development Best Practices

1. **Always rebuild after code changes**: `docker compose build --no-cache`
2. **Test permission checks locally** before implementing endpoints
3. **Use structured logging** with correlation IDs
4. **Never bypass permission checks** for "convenience"
5. **Keep JWT secrets in sync** between auth-api and chat-api
6. **Monitor Auth API connectivity** - permission checks fail gracefully
7. **Cache permission checks** in production (with proper invalidation)
8. **Document all new permissions** in AUTHORIZATION.md
9. **Test cross-org access attempts** for security validation
10. **Follow stored procedure pattern** for Auth API database operations

## Need Help?

1. **Authorization Issues**: See `AUTHORIZATION.md`
2. **Test Data**: See `TEST_DATA_README.md`
3. **Service Status**: Run `./scripts/status.sh`
4. **Check Logs**: `docker logs -f chat-api`
5. **Database Access**: `mongosh` or Auth API PostgreSQL
6. **Auth API**: See `../auth-api/CLAUDE.md`

## Key Files

```
/mnt/d/activity/chat-api/
├── CLAUDE.md                  # This file (quick start)
├── AUTHORIZATION.md           # Complete authorization documentation
├── TEST_DATA_README.md        # Test data documentation
├── test_rbac_setup.sql        # SQL script for test data
├── app/
│   ├── main.py               # FastAPI application
│   ├── core/
│   │   ├── oauth_validator.py # JWT validation
│   │   └── logging_config.py  # Structured logging
│   ├── services/
│   │   ├── auth_service.py   # Auth API integration
│   │   └── chat_service.py   # Business logic
│   └── routes/
│       └── messages.py       # API endpoints
├── .env                      # Configuration (not in git)
└── docker-compose.yml        # Docker setup
```

---

**Last Updated**: 2025-11-20
**Version**: 2.0 (Runtime Permission Validation)
