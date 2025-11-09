# Mock Servers for Chat API

Production-quality mock servers for chat-api development and testing. These mocks simulate external services with realistic behavior, comprehensive error handling, and easy configuration.

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Available Mock Servers](#available-mock-servers)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage Examples](#usage-examples)
- [Integration with Chat API](#integration-with-chat-api)
- [Testing Features](#testing-features)
- [API Documentation](#api-documentation)
- [Troubleshooting](#troubleshooting)

## 🚀 Quick Start

```bash
# 1. Install dependencies
cd mocks
pip install -r requirements.txt

# 2. Configure environment (optional)
cp .env.example .env
# Edit .env to customize JWT_SECRET and other settings

# 3. Start auth API mock
python auth_api_mock.py

# 4. Access API documentation
open http://localhost:8000/docs
```

## 📦 Available Mock Servers

### 1. Auth API Mock (`auth_api_mock.py`)

Simulates authentication service with JWT token generation.

- **Port:** 8000 (configurable)
- **Endpoints:** Register, Login, Refresh Token, Get User
- **Features:** JWT tokens compatible with chat-api, password hashing, seed users

**Key Endpoints:**
- `POST /api/auth/register` - Create new user
- `POST /api/auth/login` - Authenticate and get JWT tokens
- `POST /api/auth/refresh` - Refresh access token
- `GET /api/auth/me` - Get current user info
- `GET /health` - Health check

## 🔧 Installation

### Prerequisites

- Python 3.9+
- pip package manager

### Install Dependencies

```bash
cd mocks
pip install -r requirements.txt
```

### Optional: Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate (Linux/Mac)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the `mocks/` directory:

```bash
# JWT Configuration (MUST match chat-api settings)
JWT_SECRET=dev-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRY_HOURS=24
JWT_REFRESH_EXPIRY_DAYS=30

# Server Configuration
HOST=0.0.0.0
PORT=8000

# Mock Behavior
SIMULATE_DELAYS=true        # Enable network delay simulation
MIN_DELAY_MS=50            # Minimum delay in milliseconds
MAX_DELAY_MS=200           # Maximum delay in milliseconds
ERROR_RATE=0.0             # Random error rate (0.0-1.0, 0.1 = 10%)

# Seed Data
DEFAULT_PASSWORD=password123
```

### Critical: JWT Secret Matching

**IMPORTANT:** The `JWT_SECRET` in the mock server **MUST** match the `JWT_SECRET` in your chat-api configuration.

**Chat API `.env`:**
```env
JWT_SECRET=dev-secret-key-change-in-production
```

**Mock Server `mocks/.env`:**
```env
JWT_SECRET=dev-secret-key-change-in-production
```

If these don't match, chat-api will reject tokens issued by the mock.

## 📚 Usage Examples

### Start Mock Server

```bash
# Method 1: Direct Python
python auth_api_mock.py

# Method 2: Uvicorn (with auto-reload)
uvicorn auth_api_mock:app --reload --port 8000

# Method 3: Using the run script
chmod +x run_mocks.sh
./run_mocks.sh
```

### Register a New User

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newuser@example.com",
    "password": "securepass123",
    "name": "New User"
  }'
```

**Response:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "email": "newuser@example.com",
  "name": "New User",
  "created_at": "2024-01-15T10:30:00"
}
```

### Login and Get JWT Token

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice@example.com",
    "password": "password123"
  }'
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "id": "test-user-123",
    "email": "alice@example.com",
    "name": "Alice Johnson",
    "created_at": "2024-01-01T00:00:00"
  }
}
```

### Use Token with Chat API

```bash
# Save token to variable
TOKEN=$(curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"password123"}' \
  | jq -r '.access_token')

# Use token with chat-api
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8001/api/chat/groups
```

### Get Current User Info

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/auth/me?token=$TOKEN
```

### Refresh Access Token

```bash
REFRESH_TOKEN="your_refresh_token_here"

curl -X POST http://localhost:8000/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"$REFRESH_TOKEN\"}"
```

## 🔗 Integration with Chat API

### Complete End-to-End Workflow

```bash
# Terminal 1: Start MongoDB
docker run -d -p 27017:27017 --name mongodb mongo:latest

# Terminal 2: Start Auth API Mock
cd mocks
python auth_api_mock.py

# Terminal 3: Start Chat API
cd ..
uvicorn app.main:app --reload --port 8001

# Terminal 4: Test the integration
# 1. Login to get token
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"password123"}' \
  | jq -r '.access_token')

echo "Token: $TOKEN"

# 2. Access chat-api with token
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8001/api/chat/groups | jq

# 3. Get specific group
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8001/api/chat/groups/GROUP_ID | jq

# 4. Send message
curl -X POST http://localhost:8001/api/chat/groups/GROUP_ID/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content":"Hello from Alice!"}' | jq
```

### WebSocket Integration

```javascript
// Get token first
const loginResponse = await fetch('http://localhost:8000/api/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    email: 'alice@example.com',
    password: 'password123'
  })
});

const { access_token } = await loginResponse.json();

// Connect to chat WebSocket
const ws = new WebSocket(`ws://localhost:8001/api/chat/ws/GROUP_ID?token=${access_token}`);

ws.onopen = () => {
  console.log('Connected to chat!');
  ws.send(JSON.stringify({ type: 'ping' }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received:', data);
};
```

## 🧪 Testing Features

### Seed Users

The mock comes pre-loaded with test users (all with password `password123`):

| Email | Name | User ID |
|-------|------|---------|
| alice@example.com | Alice Johnson | test-user-123 |
| bob@example.com | Bob Smith | test-user-456 |
| charlie@example.com | Charlie Brown | test-user-789 |
| diana@example.com | Diana Prince | test-user-abc |
| ethan@example.com | Ethan Hunt | test-user-def |

### Error Simulation

Test error handling by adding `?simulate_error=CODE` to any request:

```bash
# Simulate 401 Unauthorized
curl -X POST "http://localhost:8000/api/auth/login?simulate_error=401" \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"password123"}'

# Simulate 500 Server Error
curl -X POST "http://localhost:8000/api/auth/login?simulate_error=500" \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"password123"}'

# Simulate 409 Conflict
curl -X POST "http://localhost:8000/api/auth/register?simulate_error=409" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123","name":"Test"}'
```

### Network Delay Simulation

Enable realistic network delays in `.env`:

```env
SIMULATE_DELAYS=true
MIN_DELAY_MS=50
MAX_DELAY_MS=200
```

### Random Error Injection

Test resilience with random errors:

```env
ERROR_RATE=0.1  # 10% of requests will randomly fail
```

### Development Endpoints

**List All Users:**
```bash
curl http://localhost:8000/api/auth/users | jq
```

**Reset to Seed Data:**
```bash
curl -X DELETE http://localhost:8000/api/auth/users/reset
```

**View Metrics:**
```bash
curl http://localhost:8000/api/auth/metrics | jq
```

## 📖 API Documentation

### Interactive Documentation

Once the mock server is running, access interactive API docs:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

These provide:
- Complete endpoint documentation
- Request/response schemas
- Interactive testing interface
- Example requests and responses

### Health Check

```bash
curl http://localhost:8000/health | jq
```

**Response:**
```json
{
  "status": "healthy",
  "service": "auth-api-mock",
  "timestamp": "2024-01-15T10:30:00",
  "metrics": {
    "total_requests": 42,
    "total_errors": 3,
    "error_rate": 0.071,
    "endpoints": {
      "POST /api/auth/login": 15,
      "POST /api/auth/register": 5
    }
  }
}
```

## 🔍 Troubleshooting

### Token Validation Fails in Chat API

**Problem:** Chat API returns 401 Unauthorized when using mock token.

**Solution:**
1. Verify `JWT_SECRET` matches in both `.env` files:
   ```bash
   # Check chat-api secret
   grep JWT_SECRET .env

   # Check mock secret
   grep JWT_SECRET mocks/.env
   ```

2. Ensure secrets are identical:
   ```env
   JWT_SECRET=dev-secret-key-change-in-production
   ```

### Mock Server Won't Start

**Problem:** Port already in use.

**Solution:**
```bash
# Check what's using port 8000
lsof -ti:8000

# Kill process
lsof -ti:8000 | xargs kill

# Or change port in .env
PORT=8002
```

### Import Errors

**Problem:** `ModuleNotFoundError: No module named 'mock_utils'`

**Solution:**
```bash
# Ensure you're in the mocks directory
cd mocks

# Reinstall dependencies
pip install -r requirements.txt

# Run from mocks directory
python auth_api_mock.py
```

### Token Expires Too Quickly

**Problem:** Need longer-lived tokens for testing.

**Solution:** Adjust in `.env`:
```env
JWT_EXPIRY_HOURS=168  # 7 days
JWT_REFRESH_EXPIRY_DAYS=90
```

### Can't Access Swagger Docs

**Problem:** `/docs` returns 404.

**Solution:**
1. Ensure server is running: `curl http://localhost:8000/health`
2. Check correct URL: http://localhost:8000/docs (not /api/docs)
3. Try ReDoc alternative: http://localhost:8000/redoc

### CORS Errors in Browser

**Problem:** Browser blocks requests due to CORS.

**Solution:** Mock already has CORS enabled for all origins. If issues persist:
1. Check browser console for exact error
2. Verify request includes proper headers
3. Use curl to test (bypasses CORS)

## 🎯 Best Practices

### For Development

1. **Use seed users** for consistent test data
2. **Enable delays** to catch race conditions
3. **Check metrics** to verify request patterns
4. **Use error simulation** to test error handling

### For Integration Testing

1. **Match JWT secrets** exactly between services
2. **Use fixed user IDs** (test-user-123, etc.) for predictable tests
3. **Reset database** before test runs
4. **Disable random errors** during CI/CD

### For Debugging

1. **Check health endpoint** to verify server is running
2. **View metrics** to see request counts and errors
3. **Use list users endpoint** to verify registration
4. **Enable debug logging** in uvicorn:
   ```bash
   uvicorn auth_api_mock:app --log-level debug
   ```

## 🚀 Running Multiple Mocks

Use the `run_mocks.sh` script to manage multiple mock servers:

```bash
# Start all mocks
./run_mocks.sh start

# Stop all mocks
./run_mocks.sh stop

# Restart all mocks
./run_mocks.sh restart

# Check status
./run_mocks.sh status
```

## 📝 Adding New Mock Servers

To add a new mock server:

1. Create `{service_name}_mock.py` in `mocks/` directory
2. Follow the pattern from `auth_api_mock.py`
3. Use utilities from `mock_utils.py`
4. Update `run_mocks.sh` to include new server
5. Document endpoints in this README

## 🤝 Contributing

When enhancing mocks:

1. Follow FastAPI best practices
2. Include comprehensive docstrings
3. Add error simulation support
4. Update this README with examples
5. Test integration with chat-api

## 📄 License

Same as parent project.

## 🆘 Support

For issues or questions:
1. Check troubleshooting section above
2. Review API documentation at `/docs`
3. Check chat-api main README
4. Review example requests in this file
