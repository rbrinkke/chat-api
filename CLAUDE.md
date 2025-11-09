# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Real-time chat API built with **FastAPI**, **MongoDB/Beanie ODM**, and **WebSocket** support. Features JWT authentication (shared secret with auth-api), group-based authorization, and production-grade structured logging with correlation IDs.

## Common Commands

### Development

```bash
# Install dependencies
pip install -r requirements.txt

# Start MongoDB via Docker
docker run -d -p 27017:27017 --name mongodb mongo:latest

# Start API locally (development with auto-reload)
uvicorn app.main:app --reload --port 8001

# Or via Python module
python -m app.main

# Start full stack with Docker Compose
docker-compose up -d

# View logs with correlation IDs
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

# Create test group
db.groups.insertOne({
  name: "General",
  description: "Test group",
  authorized_user_ids: ["test-user-123"],
  created_at: new Date()
})

# View groups
db.groups.find().pretty()

# View messages
db.messages.find().limit(10).pretty()
```

### Debugging

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
uvicorn app.main:app --reload

# Track specific request via correlation ID
docker logs chat-api | grep "correlation_id.*abc-123"

# Find slow requests (>1000ms)
docker logs chat-api | grep '"slow_request":true'
```

## Architecture Overview

### Backend Structure

```
app/
├── main.py              # FastAPI app, middleware setup, lifespan management
├── config.py            # Pydantic Settings (env vars, JWT_SECRET, MongoDB URL)
├── core/
│   ├── logging_config.py   # Structlog setup, correlation IDs, performance logging
│   └── exceptions.py       # NotFoundError, ForbiddenError
├── db/
│   └── mongodb.py          # MongoDB connection, Beanie initialization
├── middleware/
│   ├── auth.py             # JWT token validation (get_current_user)
│   ├── correlation.py      # Correlation ID injection
│   └── access_log.py       # Request/response logging with metrics
├── models/                 # Beanie ODM documents
│   ├── group.py            # Group(name, description, authorized_user_ids)
│   └── message.py          # Message(group_id, sender_id, content, is_deleted)
├── schemas/                # Pydantic request/response models
│   ├── group.py
│   └── message.py
├── services/               # Business logic
│   ├── chat_service.py        # CRUD + authorization checks
│   └── connection_manager.py  # WebSocket connection pooling
└── routes/                 # API endpoints
    ├── groups.py           # GET /api/chat/groups, GET /api/chat/groups/{id}
    ├── messages.py         # POST/PUT/DELETE /api/chat/groups/{id}/messages
    └── websocket.py        # WS /api/chat/ws/{group_id}
```

### Key Design Patterns

**Authorization Model**: Group-based access control
- Groups store `authorized_user_ids: List[str]` (UUIDs from auth-api)
- `ChatService._get_group_and_verify_access()` enforces authorization on every operation
- Users can only see/interact with groups they're authorized for

**WebSocket Broadcasting**: In-memory connection pooling
- `ConnectionManager` maintains `Dict[group_id, Set[WebSocket]]`
- Message operations (create/update/delete) trigger broadcasts via `manager.broadcast_to_group()`
- Automatic cleanup of disconnected clients

**Soft Deletes**: Messages are never hard-deleted
- `Message.is_deleted` flag for soft deletion
- Queries filter `Message.is_deleted == False`
- Preserves message history for audit/recovery

**Middleware Order** (executes in reverse registration order):
1. `RequestContextMiddleware` - Correlation ID injection (executes last)
2. `AccessLogMiddleware` - Request/response logging with performance metrics
3. `CORSMiddleware` - CORS headers (executes first)

## Authentication Flow

**Critical**: `JWT_SECRET` in `.env` MUST match auth-api's secret. This API validates tokens issued by auth-api.

```python
# Token validation happens in middleware/auth.py:get_current_user()
# Extracts user_id from JWT "sub" claim
# All protected routes use: Depends(get_current_user)
```

**WebSocket Authentication**:
```
ws://localhost:8001/api/chat/ws/{group_id}?token=JWT_TOKEN
```

Token passed as query parameter, validated on connection, user_id extracted for authorization checks.

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/health` | No | Health check |
| GET | `/api/chat/groups` | JWT | Get user's groups |
| GET | `/api/chat/groups/{id}` | JWT | Get specific group |
| GET | `/api/chat/groups/{id}/messages` | JWT | Get paginated messages (50/page) |
| POST | `/api/chat/groups/{id}/messages` | JWT | Create message + broadcast |
| PUT | `/api/chat/messages/{id}` | JWT | Update own message + broadcast |
| DELETE | `/api/chat/messages/{id}` | JWT | Soft delete own message + broadcast |
| WS | `/api/chat/ws/{group_id}?token=JWT` | JWT | Real-time chat connection |

## WebSocket Message Types

**Client → Server**:
```json
{"type": "ping"}
{"type": "typing"}
```

**Server → Client**:
```json
{"type": "connected", "message": "Connected to group {id}", "user_id": "..."}
{"type": "new_message", "message": {...}}
{"type": "message_updated", "message": {...}}
{"type": "message_deleted", "message_id": "..."}
{"type": "user_joined", "user_id": "...", "connection_count": 3}
{"type": "user_left", "user_id": "...", "connection_count": 2}
```

## Structured Logging

Production-grade logging with `structlog`:

**Features**:
- JSON output in production (`ENVIRONMENT=production`)
- Correlation IDs for request tracking (`X-Correlation-ID` header)
- Automatic performance metrics (`duration_ms`, `slow_request` flags)
- Security redaction (passwords/tokens censored)
- Third-party library filtering (SQLAlchemy logs suppressed)

**Usage in Code**:
```python
from app.core.logging_config import get_logger, PerformanceLogger

logger = get_logger(__name__)

# Structured logging
logger.info("user_action", user_id="123", action="send_message")

# Performance timing
with PerformanceLogger("db_query", logger, query_type="select"):
    result = await db.execute(query)
```

**Log Levels**:
- `DEBUG`: All operations, function calls, variables (development only)
- `INFO`: Important events, requests, user actions (production default)
- `WARNING`: Slow queries, deprecated features
- `ERROR`: Failed operations, exceptions

**Performance Alerts**:
- `slow_request: true` when `duration_ms > 1000`
- `very_slow_request: true` when `duration_ms > 5000`

See `DEBUGGING_GUIDE.md` for complete debugging scenarios and log aggregation queries.

## Configuration

All settings in `.env` or environment variables (see `app/config.py`):

**Critical Settings**:
- `JWT_SECRET`: **MUST match auth-api** (default: "your-secret-key-change-in-production")
- `MONGODB_URL`: MongoDB connection string (default: "mongodb://localhost:27017")
- `DATABASE_NAME`: Database name (default: "chat_db")

**API Settings**:
- `PORT`: API port (default: 8001)
- `API_PREFIX`: Route prefix (default: "/api/chat")

**Logging Settings**:
- `LOG_LEVEL`: DEBUG | INFO | WARNING | ERROR | CRITICAL (default: "INFO")
- `LOG_JSON_FORMAT`: `true` for production, `false` for development (default: false)
- `LOG_SQL_QUERIES`: Enable MongoDB query logging - very verbose! (default: false)

**CORS**:
- `CORS_ORIGINS`: Allowed origins (default: `["http://localhost:3000", "http://localhost:8000"]`)

## Integration with Auth-API

1. Ensure `JWT_SECRET` matches between both APIs
2. Use user UUIDs from auth-api in `Group.authorized_user_ids`
3. This API validates tokens issued by auth-api but doesn't issue tokens itself

## Database Models

**Group Document**:
```python
{
  "_id": ObjectId,
  "name": str,  # max 100 chars
  "description": str,  # max 500 chars
  "authorized_user_ids": List[str],  # User UUIDs from auth-api
  "created_at": datetime
}
```

**Message Document**:
```python
{
  "_id": ObjectId,
  "group_id": str,  # References Group._id
  "sender_id": str,  # User UUID from auth-api
  "content": str,  # max 10,000 chars
  "created_at": datetime,
  "updated_at": datetime,
  "is_deleted": bool  # Soft delete flag
}
```

**Indexes**:
- Groups: `name`, `authorized_user_ids`
- Messages: `group_id`, `sender_id`, compound index on `(group_id, created_at)` for pagination

## Troubleshooting

**MongoDB connection failed**:
```bash
docker ps  # Check if MongoDB is running
mongosh mongodb://localhost:27017  # Test connection
```

**JWT validation fails**:
- Verify `JWT_SECRET` matches auth-api
- Check token hasn't expired
- Ensure token format: `Authorization: Bearer <token>`

**Import errors**:
```bash
pwd  # Must be in /path/to/chat-api (where app/ folder is)
which python  # Should be in venv if using virtual environment
```

**Port already in use**:
```bash
lsof -ti:8001 | xargs kill  # Kill process on port 8001
# Or change PORT in .env
```

**WebSocket disconnects**:
- Check JWT token validity
- Verify user is in `authorized_user_ids` for the group
- Check `LOG_LEVEL=DEBUG` for WebSocket-specific errors

## Testing Strategy

No formal test suite currently exists. For manual testing:

**Generate Test JWT Token**:
```python
# generate_token.py
from jose import jwt
from datetime import datetime, timedelta

secret = "dev-secret-key-change-in-production"  # Match .env
payload = {
    "sub": "test-user-123",  # User UUID
    "exp": datetime.utcnow() + timedelta(days=1)
}
token = jwt.encode(payload, secret, algorithm="HS256")
print(f"Token: {token}")
```

**Test REST Endpoints**:
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8001/api/chat/groups
```

**Test WebSocket**:
```javascript
const ws = new WebSocket('ws://localhost:8001/api/chat/ws/GROUP_ID?token=YOUR_TOKEN');
ws.onmessage = (event) => console.log(JSON.parse(event.data));
ws.send(JSON.stringify({type: "ping"}));
```

## Production Deployment

Checklist before deploying:

1. Change `JWT_SECRET` to strong random string (32+ chars)
2. Set `DEBUG=false`
3. Set `ENVIRONMENT=production` (enables JSON logging)
4. Set `LOG_LEVEL=INFO`
5. Use production MongoDB (e.g., MongoDB Atlas)
6. Configure HTTPS/TLS termination
7. Review `CORS_ORIGINS` for production domains
8. Setup log aggregation (ELK, Datadog, CloudWatch)
9. Configure health check monitoring on `/health`
10. Setup backup strategy for MongoDB

See `docker-compose.yml` for Docker deployment configuration.
