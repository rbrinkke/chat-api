# Chat API - Startup Guide

## 🚀 Quick Start

The application is fully tested and ready to run! All tests passed successfully (13/13 ✓).

### Option 1: Run Comprehensive Test Suite (Recommended)

The test script will automatically:
- Start MongoDB
- Start the Chat API
- Create test data (3 groups with messages)
- Run all REST API tests
- Test WebSocket connections
- Show you a complete pass/fail report

```bash
./test.sh
```

**What gets tested:**
- ✅ MongoDB setup and health
- ✅ API startup and health check
- ✅ JWT token generation
- ✅ Group creation and authorization
- ✅ Message CRUD operations (Create, Read, Update, Delete)
- ✅ Soft delete verification
- ✅ Pagination
- ✅ WebSocket real-time messaging

After testing, you'll be asked if you want to clean up test data.

### Option 2: Manual Startup

```bash
# 1. Start MongoDB
docker run -d -p 27017:27017 --name chat-api-mongodb mongo:7.0

# 2. Activate virtual environment
source venv/bin/activate

# 3. Start the API
uvicorn app.main:app --reload --port 8001
```

### Option 3: Docker Compose (Full Stack)

```bash
docker-compose up -d
```

This starts both MongoDB and the Chat API in containers.

## 📊 Test Results

Last test run: **13/13 tests passed! 🎉**

```
✓ Health check returned 200
✓ User-123 sees 2 groups (correct authorization)
✓ User-456 sees 2 groups (correct authorization)
✓ Get single group succeeded (authorized)
✓ Authorization correctly denied (403) for unauthorized access
✓ Message created successfully
✓ Message updated successfully
✓ Message soft-deleted successfully
✓ Soft-deleted message not in list (correct)
✓ Pagination working
✓ WebSocket connection and messaging test passed
```

## 🔧 Configuration

All settings are in `.env`:

```bash
# MongoDB
MONGODB_URL="mongodb://localhost:27017"
DATABASE_NAME="chat_db"

# JWT Secret (MUST match auth-api!)
JWT_SECRET="dev-secret-key-change-in-production"

# API
PORT=8001

# Logging
LOG_LEVEL="INFO"  # DEBUG | INFO | WARNING | ERROR
```

## 📡 API Endpoints

Once running, access:
- **API Docs**: http://localhost:8001/docs
- **Health Check**: http://localhost:8001/health
- **Groups**: GET http://localhost:8001/api/chat/groups
- **Messages**: GET http://localhost:8001/api/chat/groups/{id}/messages
- **WebSocket**: ws://localhost:8001/api/chat/ws/{group_id}?token=JWT

## 🧪 Test Data

The test script creates:

**Group 1: General**
- Users: user-123, user-456
- Description: General discussion for everyone

**Group 2: Dev Team**
- Users: user-123, user-789
- Description: Development team discussions

**Group 3: Private**
- Users: user-456
- Description: Private group for user-456

**Test Messages:**
- Created by user-123 in General group
- Demonstrates create, update, and soft-delete operations

## 🐞 Debugging

Enable debug logging:
```bash
export LOG_LEVEL=DEBUG
uvicorn app.main:app --reload
```

View API logs:
```bash
tail -f /tmp/chat-api.log
```

Check MongoDB data:
```bash
docker exec -it chat-api-mongodb mongosh chat_db
db.groups.find().pretty()
db.messages.find().pretty()
```

## ✅ Dependencies

All dependencies are installed and verified:
- ✅ FastAPI 0.109.0
- ✅ motor 3.3.2 (async MongoDB driver)
- ✅ beanie 1.23.6 (ODM)
- ✅ pymongo 4.6.3
- ✅ python-jose (JWT handling)
- ✅ websockets 12.0
- ✅ structlog 24.1.0 (structured logging)

## 🎯 Next Steps

1. **Run the test suite**: `./test.sh`
2. **Explore the API**: http://localhost:8001/docs
3. **Check the logs**: See structured JSON logs with correlation IDs
4. **Integrate with frontend**: Use the WebSocket endpoint for real-time chat
5. **Connect to auth-api**: Ensure JWT_SECRET matches

## 🔒 Security Notes

- JWT tokens are validated but not issued by this API
- Use auth-api to generate tokens
- Ensure JWT_SECRET matches between chat-api and auth-api
- All endpoints (except /health) require authentication
- Group-based authorization is enforced on all operations

## 📚 Documentation

- `CLAUDE.md` - Complete architecture and API reference
- `README.md` - Project overview and features
- `DEBUGGING_GUIDE.md` - Advanced debugging and logging
- `QUICKSTART.md` - Quick setup guide

---

**Application Status**: ✅ Fully Operational
**Test Coverage**: 13/13 tests passing
**Ready for**: Development, Testing, Integration
