# Chat API Integration Test Guide

**For:** Claude Code AI Assistant
**Purpose:** Complete end-to-end testing of Chat API with Auth API integration
**Status:** Auth API client_credentials flow ✅ WORKING | Login code skip ✅ ENABLED

---

## 🎯 What You Need to Know

### System Architecture
```
User (Bob/Carol) → Auth API → JWT Token
                ↓
Chat API ← Service Token ← Auth API (client_credentials)
                ↓
Chat API validates: user token + fetches group from Auth API
                ↓
Message stored with org_id + group_id
```

**Key Concept:** Chat API acts as a SERVICE (machine-to-machine) but handles USER requests.

---

## ✅ Verified Working Test Users

### Test User 1: Bob Developer
```json
{
  "email": "bob.developer@example.com",
  "password": "DevSecure2024!Bob",
  "user_id": "5b6b84b5-01fe-46b1-827a-ed23548ac59c",
  "status": "✅ Verified in database"
}
```

### Test User 2: Carol Manager
```json
{
  "email": "carol.manager@example.com",
  "password": "Manager!Strong789",
  "user_id": "<will be returned on login>",
  "status": "✅ Verified in database"
}
```

**Important:** Email login code is SKIPPED in development (`SKIP_LOGIN_CODE=true`). You get tokens immediately!

---

## 🚀 Step-by-Step Testing Guide

### Step 1: Verify Services Are Running

```bash
# Check Auth API (port 8000)
curl -s http://localhost:8000/health | jq

# Expected:
{
  "status": "healthy",
  "timestamp": "2025-11-12T..."
}

# Check Chat API (port 8001)
curl -s http://localhost:8001/health | jq

# Expected:
{
  "status": "healthy"
}
```

### Step 2: Get User Tokens (Bob & Carol)

**Login Bob:**
```bash
curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "bob.developer@example.com",
    "password": "DevSecure2024!Bob"
  }' | jq

# Response:
{
  "access_token": "eyJ...",  # ← Save this as BOB_TOKEN
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "org_id": null
}
```

**Login Carol:**
```bash
curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "carol.manager@example.com",
    "password": "Manager!Strong789"
  }' | jq

# Response:
{
  "access_token": "eyJ...",  # ← Save this as CAROL_TOKEN
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "org_id": null
}
```

**💡 Pro Tip:** Save tokens as shell variables:
```bash
BOB_TOKEN="eyJ..."
CAROL_TOKEN="eyJ..."
```

### Step 3: Verify Existing Groups in Auth API

```bash
# Check what groups exist
docker exec activity-postgres-db psql -U auth_api_user -d activitydb -c \
  "SELECT id, name, organization_id FROM activity.groups LIMIT 5;"

# Example output:
                  id                  |     name      |           organization_id
--------------------------------------+---------------+--------------------------------------
 0fdf3a76-674b-4118-b6f1-e0a88982d0d5 | photographers | 7d22afb7-90e7-4b4b-a093-91d1e0da2c8f
 8211a1e2-90a2-495a-8cd0-2d18768ae56e | photographers | 91a8821f-879e-4ba3-ae71-4499b96b52f4
```

**Pick a group ID to use for testing. Example:**
```bash
GROUP_ID="0fdf3a76-674b-4118-b6f1-e0a88982d0d5"
ORG_ID="7d22afb7-90e7-4b4b-a093-91d1e0da2c8f"
```

### Step 4: Send Messages via Chat API

**Bob sends a message:**
```bash
curl -s -X POST http://localhost:8001/api/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $BOB_TOKEN" \
  -d '{
    "group_id": "'$GROUP_ID'",
    "content": "Hello from Bob! Testing Chat API integration with Auth API."
  }' | jq

# Expected Response:
{
  "id": "...",
  "group_id": "0fdf3a76-674b-4118-b6f1-e0a88982d0d5",
  "org_id": "7d22afb7-90e7-4b4b-a093-91d1e0da2c8f",
  "group_name": "photographers",
  "content": "Hello from Bob! Testing Chat API integration with Auth API.",
  "sender_id": "5b6b84b5-01fe-46b1-827a-ed23548ac59c",
  "created_at": "2025-11-12T..."
}
```

**Carol sends a message:**
```bash
curl -s -X POST http://localhost:8001/api/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $CAROL_TOKEN" \
  -d '{
    "group_id": "'$GROUP_ID'",
    "content": "Hi Bob! Carol here. This multi-tenant chat system works perfectly!"
  }' | jq

# Expected Response:
{
  "id": "...",
  "group_id": "0fdf3a76-674b-4118-b6f1-e0a88982d0d5",
  "org_id": "7d22afb7-90e7-4b4b-a093-91d1e0da2c8f",
  "group_name": "photographers",
  "content": "Hi Bob! Carol here. This multi-tenant chat system works perfectly!",
  "sender_id": "<carol's user_id>",
  "created_at": "2025-11-12T..."
}
```

### Step 5: Retrieve Messages

**Get all messages in the group:**
```bash
curl -s -X GET "http://localhost:8001/api/messages?group_id=$GROUP_ID" \
  -H "Authorization: Bearer $BOB_TOKEN" | jq

# Expected:
{
  "messages": [
    {
      "id": "...",
      "content": "Hello from Bob!...",
      "sender_id": "5b6b84b5-01fe-46b1-827a-ed23548ac59c",
      "created_at": "..."
    },
    {
      "id": "...",
      "content": "Hi Bob! Carol here...",
      "sender_id": "<carol_id>",
      "created_at": "..."
    }
  ],
  "total": 2
}
```

### Step 6: Verify MongoDB Storage

```bash
# Connect to Chat API MongoDB
docker exec -it chat-mongodb mongosh chatdb

# Query messages
db.messages.find({
  group_id: "0fdf3a76-674b-4118-b6f1-e0a88982d0d5"
}).pretty()

# Expected fields:
{
  _id: ObjectId("..."),
  group_id: "0fdf3a76-674b-4118-b6f1-e0a88982d0d5",
  org_id: "7d22afb7-90e7-4b4b-a093-91d1e0da2c8f",
  group_name: "photographers",
  content: "Hello from Bob!...",
  sender_id: "5b6b84b5-01fe-46b1-827a-ed23548ac59c",
  created_at: ISODate("2025-11-12T...")
}
```

---

## 🔍 What Chat API Does Behind the Scenes

### When Bob sends a message:

1. **Receives request** with Bob's JWT token
2. **Validates JWT** (checks signature, expiration)
3. **Extracts user_id** from token: `5b6b84b5-01fe-46b1-827a-ed23548ac59c`
4. **Gets service token** from Auth API using client_credentials:
   ```bash
   POST /oauth/token
   grant_type=client_credentials
   client_id=chat-api-service
   client_secret=your-service-secret-change-in-production
   ```
5. **Fetches group** from Auth API:
   ```bash
   GET /api/groups/0fdf3a76-674b-4118-b6f1-e0a88982d0d5
   Authorization: Bearer <service_token>
   ```
6. **Validates org_id** matches user's organization
7. **Stores message** in MongoDB with:
   - `group_id`: `0fdf3a76-674b-4118-b6f1-e0a88982d0d5`
   - `org_id`: `7d22afb7-90e7-4b4b-a093-91d1e0da2c8f`
   - `group_name`: `photographers`
   - `sender_id`: `5b6b84b5-01fe-46b1-827a-ed23548ac59c`
   - `content`: message text

---

## ✅ Success Criteria

### Checklist for Complete Verification:

- [ ] **Auth API Health Check** passes
- [ ] **Chat API Health Check** passes
- [ ] **Bob can login** and get tokens (no email code needed)
- [ ] **Carol can login** and get tokens (no email code needed)
- [ ] **Bob can send message** → response includes `org_id` + `group_name`
- [ ] **Carol can send message** → response includes `org_id` + `group_name`
- [ ] **Messages are stored** in MongoDB with all required fields
- [ ] **Messages can be retrieved** by group_id
- [ ] **org_id validation works** (messages only visible to same org)

---

## 🐛 Troubleshooting

### Problem: "Invalid credentials"
**Solution:** Check password is exactly `DevSecure2024!Bob` (case-sensitive)

### Problem: "Group not found"
**Solution:** Use `docker exec activity-postgres-db psql...` to get valid group IDs

### Problem: "Service token acquisition failed"
**Solution:** Verify Auth API client_credentials is working:
```bash
curl -X POST http://localhost:8000/oauth/token \
  -d "grant_type=client_credentials" \
  -d "client_id=chat-api-service" \
  -d "client_secret=your-service-secret-change-in-production" \
  -d "scope=groups:read"

# Should return:
{
  "access_token": "eyJ...",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "groups:read"
}
```

### Problem: "401 Unauthorized"
**Solution:** Check token is valid and not expired (15 min expiration). Re-login if needed.

---

## 🎯 Next Steps After Verification

Once basic messaging works:

1. **WebSocket Testing** - Real-time message delivery
2. **Multi-Tenant Isolation** - Verify org separation
3. **Performance Testing** - Load test with multiple users
4. **Dashboard Verification** - Check metrics and stats

---

## 📝 Important Notes for AI Testing

1. **SKIP_LOGIN_CODE is enabled** - You get tokens immediately, no email verification
2. **Test users are pre-verified** - Ready to use, no registration needed
3. **Service token is automatic** - Chat API handles this, you don't need to worry
4. **org_id comes from Auth API** - Chat API fetches this via GroupService
5. **All tokens expire** - Access tokens: 15 min, Refresh tokens: 30 days

---

## 🔗 API Endpoints Reference

### Auth API (port 8000)
- `POST /api/auth/login` - User login (get JWT tokens)
- `POST /oauth/token` - Service token (client_credentials)
- `GET /api/groups/{id}` - Get group details (requires service token)

### Chat API (port 8001)
- `POST /api/messages` - Send message (requires user token)
- `GET /api/messages?group_id={id}` - Get messages (requires user token)
- `GET /health` - Health check

---

## 💡 Quick Test Script

Save this as `test_chat.sh`:

```bash
#!/bin/bash

# Login Bob
echo "🔐 Logging in Bob..."
BOB_RESPONSE=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"bob.developer@example.com","password":"DevSecure2024!Bob"}')

BOB_TOKEN=$(echo $BOB_RESPONSE | jq -r '.access_token')
echo "✅ Bob token: ${BOB_TOKEN:0:20}..."

# Login Carol
echo "🔐 Logging in Carol..."
CAROL_RESPONSE=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"carol.manager@example.com","password":"Manager!Strong789"}')

CAROL_TOKEN=$(echo $CAROL_RESPONSE | jq -r '.access_token')
echo "✅ Carol token: ${CAROL_TOKEN:0:20}..."

# Get a group ID
echo "📋 Fetching group ID..."
GROUP_ID="0fdf3a76-674b-4118-b6f1-e0a88982d0d5"
echo "✅ Using group: $GROUP_ID"

# Bob sends message
echo "💬 Bob sending message..."
curl -s -X POST http://localhost:8001/api/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $BOB_TOKEN" \
  -d "{\"group_id\":\"$GROUP_ID\",\"content\":\"Test message from Bob at $(date)\"}" | jq

# Carol sends message
echo "💬 Carol sending message..."
curl -s -X POST http://localhost:8001/api/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $CAROL_TOKEN" \
  -d "{\"group_id\":\"$GROUP_ID\",\"content\":\"Reply from Carol at $(date)\"}" | jq

# Get messages
echo "📬 Retrieving messages..."
curl -s "http://localhost:8001/api/messages?group_id=$GROUP_ID" \
  -H "Authorization: Bearer $BOB_TOKEN" | jq

echo "✅ Test complete!"
```

Make executable: `chmod +x test_chat.sh`
Run: `./test_chat.sh`

---

**Status:** All systems operational! Auth API client_credentials ✅ | Login skip ✅ | Test users ✅

**Ready to test!** 🚀
