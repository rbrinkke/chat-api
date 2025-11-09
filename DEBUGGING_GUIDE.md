# Debugging Guide - Chat API

Complete gids voor het gebruik van het geavanceerde logging systeem voor debugging en troubleshooting.

## 🎯 Snelle Start

### Debug Mode Activeren

```bash
# Optie 1: Via environment variabele
export LOG_LEVEL=DEBUG
uvicorn app.main:app --reload

# Optie 2: Direct in .env file
LOG_LEVEL="DEBUG"

# Optie 3: Via command line
uvicorn app.main:app --log-level debug --reload
```

### Logs Bekijken

```bash
# Volg logs real-time
docker logs -f <container_name>

# Of met filtering
docker logs -f <container_name> 2>&1 | grep "ERROR"

# Laatste 100 regels
docker logs --tail 100 <container_name>
```

## 📊 Log Levels Uitgelegd

| Level | Gebruik | Wat zie je |
|-------|---------|------------|
| **DEBUG** | Local development, deep troubleshooting | Alles: requests, database queries, function calls, variables |
| **INFO** | Normal operation, production default | Important events: startup, requests, user actions |
| **WARNING** | Potential issues | Deprecated features, slow queries, recoverable errors |
| **ERROR** | Errors that need attention | Failed operations, exceptions, validation errors |
| **CRITICAL** | System failures | Database down, critical service failures |

## 🔍 Debugging Scenarios

### Scenario 1: Request Niet Werkt

**Probleem**: API endpoint geeft 500 error

**Debugging Steps**:

```bash
# 1. Zet DEBUG logging aan
export LOG_LEVEL=DEBUG

# 2. Start applicatie
uvicorn app.main:app --reload --log-level debug

# 3. Maak de request opnieuw
curl -X POST http://localhost:8001/api/chat/groups/123/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"content": "test"}'

# 4. Zoek in logs naar correlation_id
# Je ziet output zoals:
{
  "event": "http_request",
  "correlation_id": "abc-123-def",
  "method": "POST",
  "path": "/api/chat/groups/123/messages",
  "status_code": 500,
  "duration_ms": 45.2,
  "error_type": "NotFoundError"
}

# 5. Filter op die correlation_id voor ALLE logs van die request
docker logs <container> | grep "abc-123-def"
```

**Wat je ziet in DEBUG mode**:

```
[debug] request_started method=POST path=/api/chat/groups/123/messages
[debug] auth_check user_id=user-456
[debug] get_group group_id=123 user_id=user-456
[error] group_not_found group_id=123
[error] http_request status_code=404 duration_ms=12.5
```

### Scenario 2: Performance Issues

**Probleem**: Requests zijn langzaam

**Debugging**:

```bash
# Logs tonen automatisch performance metrics
export LOG_LEVEL=INFO

# Filter op slow requests
docker logs <container> | grep "slow_request.*true"

# Voorbeeld output:
{
  "event": "http_request",
  "path": "/api/chat/groups/123/messages",
  "duration_ms": 2450.5,
  "slow_request": true,
  "very_slow_request": false
}

# Alerts voor very slow requests (>5s)
{
  "event": "performance_degradation",
  "message": "Request took longer than 5 seconds",
  "path": "/api/chat/groups/456/messages",
  "duration_ms": 6234.1
}
```

**Performance Metrics per Request**:
- `duration_ms`: Totale request tijd
- `slow_request`: true als >1000ms
- `very_slow_request`: true als >5000ms

### Scenario 3: Database Issues

**Probleem**: MongoDB errors

**Debugging**:

```bash
# Enable MongoDB query logging (LET OP: zeer verbose!)
# In .env:
LOG_SQL_QUERIES=true
LOG_LEVEL=DEBUG

# Je ziet nu alle database operaties:
[debug] database_query operation=find collection=groups
[debug] query_result count=5 duration_ms=23.4
```

**MongoDB Connection Errors**:

```json
{
  "event": "database_initialization_failed",
  "error": "Connection refused",
  "database_url": "mongodb://localhost:27017",
  "exc_info": "... stack trace ..."
}
```

### Scenario 4: WebSocket Debugging

**Probleem**: WebSocket verbinding faalt

**Debugging**:

```bash
# WebSocket logs zijn ook gestructureerd
export LOG_LEVEL=DEBUG

# Check connection logs:
[info] websocket_auth user_id=user-123
[info] websocket_connected group_id=group-456 user_id=user-123
[info] user_joined group_id=group-456 connection_count=3

# Check disconnect logs:
[info] websocket_disconnected group_id=group-456
[info] user_left group_id=group-456 connection_count=2
```

### Scenario 5: Authentication Failures

**Probleem**: JWT token wordt rejected

**Debugging**:

```bash
# Auth logs tonen precies wat er mis gaat
[warning] jwt_validation_failed error="Signature has expired"
[debug] token_payload sub=user-123 exp=2024-01-01T12:00:00

# Security: Tokens worden automatisch gecensored in logs
[info] auth_attempt token=***REDACTED*** user_id=user-123
```

## 🛠️ Advanced Debugging

### Correlation IDs voor Distributed Tracing

Elke request krijgt een unieke `correlation_id`:

```bash
# Client stuurt eigen ID mee (optioneel)
curl -H "X-Correlation-ID: my-debug-id-123" \
     http://localhost:8001/api/chat/groups

# Of gebruik automatisch gegenereerde ID
# Response bevat altijd:
X-Correlation-ID: abc-123-def-456

# Filter ALLE logs van één request:
docker logs <container> | grep "abc-123-def-456"
```

**Voorbeeld output**:

```json
{"event": "request_started", "correlation_id": "abc-123-def-456", "method": "GET"}
{"event": "auth_check", "correlation_id": "abc-123-def-456", "user_id": "user-123"}
{"event": "database_query", "correlation_id": "abc-123-def-456", "collection": "groups"}
{"event": "http_request", "correlation_id": "abc-123-def-456", "status_code": 200}
```

### Third-Party Library Noise Filtering

**Probleem**: Te veel logs van SQLAlchemy, httpx, etc.

**Oplossing**: Automatisch gefilterd!

```python
# In logging_config.py staat:
"sqlalchemy.engine": {
    "level": "WARNING",  # Alleen warnings en errors
}
```

**Handmatig aanpassen**:

```yaml
# In logging.yaml:
loggers:
  sqlalchemy.engine:
    level: DEBUG  # Nu zie je SQL queries
```

### Performance Timing

Gebruik de `PerformanceLogger` voor custom timing:

```python
from app.core.logging_config import get_logger, PerformanceLogger

logger = get_logger(__name__)

# Automatische timing
with PerformanceLogger("expensive_operation", logger, user_id="123"):
    result = perform_expensive_operation()

# Output:
# [debug] operation_completed operation=expensive_operation duration_ms=234.5 user_id=123
```

### Error Context Enrichment

Errors bevatten automatisch volledige context:

```json
{
  "event": "request_error_unhandled",
  "correlation_id": "abc-123",
  "method": "POST",
  "path": "/api/chat/messages",
  "error_type": "ValueError",
  "error": "Invalid message content",
  "client_ip": "192.168.1.1",
  "user_id": "user-456",
  "exc_info": "Traceback (most recent call last):\n  File..."
}
```

## 🐳 Docker Debugging

### Docker Compose Logging

```yaml
# docker-compose.yml
services:
  chat-api:
    environment:
      - LOG_LEVEL=DEBUG
      - ENVIRONMENT=development
    # Optioneel: log level voor uvicorn
    command: uvicorn app.main:app --host 0.0.0.0 --log-level debug
```

### Production Logging (JSON Format)

```bash
# .env voor productie:
ENVIRONMENT="production"
LOG_LEVEL="INFO"
LOG_JSON_FORMAT=true

# Output wordt pure JSON:
{"event":"http_request","timestamp":"2024-01-15T10:30:45.123Z","level":"info",...}

# Perfect voor log aggregators (ELK, Datadog, CloudWatch)
```

### Gunicorn + Uvicorn Workers

```bash
# Voor productie met Gunicorn:
gunicorn app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8001 \
  --access-logfile '-' \
  --error-logfile '-' \
  --log-level debug

# Beide streams gaan naar Docker logs
```

## 📈 Log Aggregation

### Searching in Production Logs

**Kibana / Elasticsearch**:

```
# Find all errors for a user
user_id:"user-123" AND level:"error"

# Find slow requests
duration_ms:>1000 AND event:"http_request"

# Find specific error types
error_type:"NotFoundError" AND path:"/api/chat/groups/*"
```

**CloudWatch Insights**:

```
fields @timestamp, event, error, duration_ms
| filter correlation_id = "abc-123-def"
| sort @timestamp desc
```

**Datadog**:

```
@correlation_id:abc-123-def @env:production
```

## 🔒 Security Considerations

**Automatische Data Censoring**:

```python
# Deze velden worden ALTIJD geredacted:
logger.info("login_attempt",
    password="secret123",  # Wordt ***REDACTED***
    api_key="key-456",     # Wordt ***REDACTED***
    token="jwt-token"      # Wordt ***REDACTED***
)

# Output:
{"event":"login_attempt","password":"***REDACTED***","api_key":"***REDACTED***"}
```

## 💡 Best Practices

### ✅ DO's

```python
# Gebruik structured logging
logger.info("user_login", user_id="123", ip="1.2.3.4", success=True)

# Niet
logger.info(f"User 123 logged in from 1.2.3.4")
```

```python
# Gebruik correlation IDs
from fastapi import Request

async def my_endpoint(request: Request):
    correlation_id = request.state.correlation_id
    logger.info("processing", correlation_id=correlation_id)
```

```python
# Gebruik performance logging
with PerformanceLogger("db_query", logger, query_type="select"):
    result = await db.execute(query)
```

### ❌ DON'Ts

```python
# NOOIT plaintext passwords of tokens
logger.info(f"Auth with token: {jwt_token}")  # ❌

# NOOIT excessive logging in loops
for item in items:  # Als items = 10,000
    logger.debug(f"Processing {item}")  # ❌ Log explosie!

# NOOIT persoonlijke data zonder toestemming
logger.info("email", email="user@example.com")  # ❌ GDPR issue
```

## 🚀 Quick Debug Checklist

Bij een bug:

- [ ] Zet `LOG_LEVEL=DEBUG` in .env
- [ ] Reproduceer de bug
- [ ] Kopieer de `correlation_id` uit de error
- [ ] Filter logs: `grep <correlation_id>`
- [ ] Analyseer de volledige request flow
- [ ] Check performance metrics (`duration_ms`)
- [ ] Bekijk error context (`error_type`, `exc_info`)
- [ ] Verlaag LOG_LEVEL weer naar INFO na debugging

## 📞 Troubleshooting

### Geen Logs Zichtbaar

```bash
# Check of logging is geïnitialiseerd
docker logs <container> | grep "logging_configured"

# Check log level
docker logs <container> | grep "log_level"

# Verify STDOUT
docker logs <container> | head -10
```

### Te Veel Logs

```bash
# Verhoog log level
export LOG_LEVEL=WARNING

# Of filter third-party libraries (in logging.yaml)
loggers:
  sqlalchemy.engine:
    level: CRITICAL  # Vrijwel uit
```

### Logs Niet in JSON

```bash
# Check ENVIRONMENT setting
echo $ENVIRONMENT  # Moet "production" zijn voor JSON

# Or override in code
# app/config.py
ENVIRONMENT = "production"
```

## 📚 Meer Informatie

- FastAPI Logging: https://fastapi.tiangolo.com/
- Structlog Docs: https://www.structlog.org/
- Docker Logging: https://docs.docker.com/config/containers/logging/
- Uvicorn Logging: https://www.uvicorn.org/settings/#logging

---

Succes met debuggen! 🎉
