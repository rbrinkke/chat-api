# OAuth 2.0 Quick Start - Chat API

**TL;DR**: Chat API can validate Auth API tokens using shared `JWT_SECRET_KEY` (HS256)

---

## ⚡ 5-Minute Setup

### 1. Copy Secret

```bash
# Get secret from Auth API
docker exec auth-api env | grep JWT_SECRET_KEY

# Add to Chat API .env
JWT_SECRET_KEY=<paste-from-above>
JWT_ALGORITHM=HS256
AUTH_API_URL=http://auth-api:8000
```

### 2. Install Package

```bash
pip install pyjwt[crypto]
```

### 3. Add Validator

```python
# app/core/oauth.py
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

JWT_SECRET_KEY = "your-shared-secret"
JWT_ALGORITHM = "HS256"
security = HTTPBearer()

def get_current_user(credentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

### 4. Protect Endpoints

```python
from app.core.oauth import get_current_user

@app.get("/api/v1/messages")
async def get_messages(user = Depends(get_current_user)):
    return {"user_id": user["sub"], "messages": [...]}
```

---

## 🧪 Test

```bash
# Get token from Auth API (test user)
# Email: grace.oauth@yahoo.com
# Password: OAuth!Testing321

# Use token
curl http://localhost:8080/api/v1/messages \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 📚 Full Guide

See `OAUTH_INTEGRATION_GUIDE.md` for:
- Complete token validation
- Scope-based authorization
- Refresh token flow
- Security best practices
- Test users list

---

## ✅ Test Users Available

```bash
cd /mnt/d/activity/auth-api
./test_oauth.sh --show-users
```

**10 test users** ready with all scopes configured!

---

## 🆘 Troubleshooting

**"Invalid signature"** → JWT_SECRET_KEY doesn't match Auth API
**"Token expired"** → Use refresh token (15 min lifetime)
**"Insufficient scope"** → Request correct scope in OAuth flow

---

**Auth API Status:** ✅ 23/23 tests passing, production ready!
