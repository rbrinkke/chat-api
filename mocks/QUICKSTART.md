# Mock Server Quick Start

Get the Auth API Mock server running in 60 seconds!

## 🚀 Quick Start

```bash
# 1. Navigate to mocks directory
cd mocks

# 2. Install dependencies (one-time setup)
pip install -r requirements.txt

# 3. Create environment file (one-time setup)
cp .env.example .env

# 4. Start the mock server
python auth_api_mock.py
```

That's it! The server is now running at http://localhost:8000

## ✅ Verify Installation

```bash
# Health check
curl http://localhost:8000/health | jq

# Expected output:
# {
#   "status": "healthy",
#   "service": "auth-api-mock",
#   "timestamp": "2025-01-15T10:30:00",
#   "metrics": {...}
# }
```

## 🧪 Quick Test

```bash
# Login with test user
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice@example.com",
    "password": "password123"
  }' | jq

# You'll get back:
# - access_token (JWT token)
# - refresh_token
# - user information
```

## 📝 Test Credentials

The mock comes with 5 pre-loaded test users:

| Email | Password | Name |
|-------|----------|------|
| alice@example.com | password123 | Alice Johnson |
| bob@example.com | password123 | Bob Smith |
| charlie@example.com | password123 | Charlie Brown |
| diana@example.com | password123 | Diana Prince |
| ethan@example.com | password123 | Ethan Hunt |

## 🔗 Integration with Chat API

```bash
# Terminal 1: Start mock auth server
cd mocks
python auth_api_mock.py

# Terminal 2: Start chat API
cd ..
uvicorn app.main:app --reload --port 8001

# Terminal 3: Test integration
# 1. Get token from mock
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"password123"}' \
  | jq -r '.access_token')

# 2. Use token with chat API
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8001/api/chat/groups | jq
```

## 📚 Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Full README**: [README.md](README.md)
- **Examples**: [collections/EXAMPLES.md](collections/EXAMPLES.md)

## 🛠️ Using the Management Script

```bash
# Start all mocks
./run_mocks.sh start

# Check status
./run_mocks.sh status

# View logs
./run_mocks.sh logs

# Stop all mocks
./run_mocks.sh stop
```

## 🎯 Common Use Cases

### Get JWT Token for Testing

```bash
# Save token to variable
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"password123"}' \
  | jq -r '.access_token')

# Use it
echo "Token: $TOKEN"
```

### Test Error Handling

```bash
# Simulate 401 Unauthorized
curl -X POST "http://localhost:8000/api/auth/login?simulate_error=401" \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"password123"}'
```

### Register New Test User

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "testuser@example.com",
    "password": "testpass123",
    "name": "Test User"
  }' | jq
```

## 🔧 Configuration

Edit `mocks/.env` to customize:

```env
# Change JWT secret (must match chat-api!)
JWT_SECRET=your-secret-here

# Change port
PORT=8002

# Disable network delays for faster testing
SIMULATE_DELAYS=false

# Enable random errors for resilience testing
ERROR_RATE=0.1  # 10% error rate
```

## 🆘 Troubleshooting

### Port Already in Use

```bash
# Check what's using port 8000
lsof -ti:8000

# Kill it
lsof -ti:8000 | xargs kill

# Or change PORT in .env
echo "PORT=8002" >> .env
```

### Token Validation Fails in Chat API

**Problem**: Chat API returns 401 when using mock token.

**Solution**: Ensure `JWT_SECRET` matches in both `.env` files:

```bash
# Check secrets match
grep JWT_SECRET ../chat-api/.env
grep JWT_SECRET mocks/.env
```

## 📦 What You Get

- ✅ Production-quality mock server
- ✅ JWT token generation compatible with chat-api
- ✅ 5 pre-loaded test users
- ✅ Auto-generated API documentation
- ✅ Error simulation for testing
- ✅ Network delay simulation
- ✅ Request metrics and monitoring
- ✅ Comprehensive examples and tests

## 🚦 Next Steps

1. ✅ **Start the mock** - `python auth_api_mock.py`
2. 📖 **Read the docs** - Visit http://localhost:8000/docs
3. 🧪 **Run tests** - `./test_mock.sh`
4. 🔗 **Integrate with chat-api** - See README.md
5. 🎯 **Test your application** - Use test credentials above

## 📞 Need Help?

- 📚 Full documentation: [README.md](README.md)
- 💻 Code examples: [collections/EXAMPLES.md](collections/EXAMPLES.md)
- 🧪 Test script: `./test_mock.sh`
- 🌐 API docs: http://localhost:8000/docs

Happy testing! 🎉
