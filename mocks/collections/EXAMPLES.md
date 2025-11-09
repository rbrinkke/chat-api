# API Test Examples

Quick reference for testing the Auth API Mock using curl and other tools.

## Table of Contents

- [cURL Examples](#curl-examples)
- [HTTPie Examples](#httpie-examples)
- [Python Examples](#python-examples)
- [JavaScript Examples](#javascript-examples)

## cURL Examples

### Health Check

```bash
curl http://localhost:8000/health | jq
```

### Register New User

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newuser@example.com",
    "password": "securepass123",
    "name": "New User"
  }' | jq
```

### Login

```bash
# Login and save full response
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice@example.com",
    "password": "password123"
  }' | jq

# Login and extract just the access token
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice@example.com",
    "password": "password123"
  }' | jq -r '.access_token')

echo "Access Token: $TOKEN"
```

### Get Current User

```bash
# Using query parameter
curl "http://localhost:8000/api/auth/me?token=$TOKEN" | jq

# Using Authorization header (preferred)
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/auth/me?token=$TOKEN" | jq
```

### Refresh Token

```bash
# Extract refresh token from login
REFRESH_TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice@example.com",
    "password": "password123"
  }' | jq -r '.refresh_token')

# Use refresh token to get new access token
curl -X POST http://localhost:8000/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"$REFRESH_TOKEN\"}" | jq
```

### List All Users (Dev)

```bash
curl http://localhost:8000/api/auth/users | jq
```

### Reset Database (Dev)

```bash
curl -X DELETE http://localhost:8000/api/auth/users/reset | jq
```

### View Metrics (Dev)

```bash
curl http://localhost:8000/api/auth/metrics | jq
```

### Error Simulation

```bash
# Simulate 401 Unauthorized
curl -X POST "http://localhost:8000/api/auth/login?simulate_error=401" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice@example.com",
    "password": "password123"
  }' | jq

# Simulate 500 Internal Server Error
curl -X POST "http://localhost:8000/api/auth/login?simulate_error=500" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice@example.com",
    "password": "password123"
  }' | jq

# Simulate 409 Conflict
curl -X POST "http://localhost:8000/api/auth/register?simulate_error=409" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123",
    "name": "Test User"
  }' | jq
```

## HTTPie Examples

[HTTPie](https://httpie.io/) provides a more user-friendly CLI for HTTP requests.

### Installation

```bash
pip install httpie
```

### Usage

```bash
# Health check
http GET localhost:8000/health

# Register
http POST localhost:8000/api/auth/register \
  email=newuser@example.com \
  password=securepass123 \
  name="New User"

# Login
http POST localhost:8000/api/auth/login \
  email=alice@example.com \
  password=password123

# Login and save token
export TOKEN=$(http POST localhost:8000/api/auth/login \
  email=alice@example.com \
  password=password123 \
  --print=b | jq -r '.access_token')

# Get current user
http GET "localhost:8000/api/auth/me?token=$TOKEN"

# List users
http GET localhost:8000/api/auth/users
```

## Python Examples

### Using requests library

```python
import requests
import json

BASE_URL = "http://localhost:8000"

# Health check
response = requests.get(f"{BASE_URL}/health")
print(response.json())

# Register new user
register_data = {
    "email": "pythonuser@example.com",
    "password": "securepass123",
    "name": "Python User"
}
response = requests.post(f"{BASE_URL}/api/auth/register", json=register_data)
print(response.json())

# Login
login_data = {
    "email": "alice@example.com",
    "password": "password123"
}
response = requests.post(f"{BASE_URL}/api/auth/login", json=login_data)
auth_response = response.json()
access_token = auth_response["access_token"]
print(f"Access Token: {access_token}")

# Get current user
headers = {"Authorization": f"Bearer {access_token}"}
response = requests.get(f"{BASE_URL}/api/auth/me?token={access_token}", headers=headers)
print(response.json())

# Refresh token
refresh_data = {"refresh_token": auth_response["refresh_token"]}
response = requests.post(f"{BASE_URL}/api/auth/refresh", json=refresh_data)
print(response.json())
```

### Using httpx (async)

```python
import httpx
import asyncio

BASE_URL = "http://localhost:8000"

async def test_auth_flow():
    async with httpx.AsyncClient() as client:
        # Login
        login_data = {
            "email": "alice@example.com",
            "password": "password123"
        }
        response = await client.post(f"{BASE_URL}/api/auth/login", json=login_data)
        auth_response = response.json()
        access_token = auth_response["access_token"]

        # Get current user
        headers = {"Authorization": f"Bearer {access_token}"}
        response = await client.get(
            f"{BASE_URL}/api/auth/me?token={access_token}",
            headers=headers
        )
        user = response.json()
        print(f"Logged in as: {user['name']}")

asyncio.run(test_auth_flow())
```

## JavaScript Examples

### Using fetch (Node.js with node-fetch)

```javascript
const fetch = require('node-fetch');

const BASE_URL = 'http://localhost:8000';

async function testAuthFlow() {
  // Login
  const loginResponse = await fetch(`${BASE_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email: 'alice@example.com',
      password: 'password123'
    })
  });

  const authData = await loginResponse.json();
  const accessToken = authData.access_token;
  console.log('Access Token:', accessToken);

  // Get current user
  const userResponse = await fetch(
    `${BASE_URL}/api/auth/me?token=${accessToken}`,
    {
      headers: { 'Authorization': `Bearer ${accessToken}` }
    }
  );

  const user = await userResponse.json();
  console.log('User:', user);
}

testAuthFlow();
```

### Using axios

```javascript
const axios = require('axios');

const BASE_URL = 'http://localhost:8000';

async function testAuthFlow() {
  try {
    // Login
    const loginResponse = await axios.post(`${BASE_URL}/api/auth/login`, {
      email: 'alice@example.com',
      password: 'password123'
    });

    const accessToken = loginResponse.data.access_token;
    console.log('Access Token:', accessToken);

    // Get current user
    const userResponse = await axios.get(
      `${BASE_URL}/api/auth/me?token=${accessToken}`,
      {
        headers: { 'Authorization': `Bearer ${accessToken}` }
      }
    );

    console.log('User:', userResponse.data);

  } catch (error) {
    console.error('Error:', error.response?.data || error.message);
  }
}

testAuthFlow();
```

### Browser JavaScript

```html
<!DOCTYPE html>
<html>
<head>
  <title>Auth API Test</title>
</head>
<body>
  <h1>Auth API Mock Test</h1>
  <button onclick="testAuth()">Test Login</button>
  <pre id="output"></pre>

  <script>
    async function testAuth() {
      const output = document.getElementById('output');

      try {
        // Login
        const loginResponse = await fetch('http://localhost:8000/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: 'alice@example.com',
            password: 'password123'
          })
        });

        const authData = await loginResponse.json();
        output.textContent = JSON.stringify(authData, null, 2);

        // Get current user
        const userResponse = await fetch(
          `http://localhost:8000/api/auth/me?token=${authData.access_token}`,
          {
            headers: { 'Authorization': `Bearer ${authData.access_token}` }
          }
        );

        const user = await userResponse.json();
        output.textContent += '\n\nUser:\n' + JSON.stringify(user, null, 2);

      } catch (error) {
        output.textContent = 'Error: ' + error.message;
      }
    }
  </script>
</body>
</html>
```

## Complete Integration Test Script

Save this as `test_auth_api.sh`:

```bash
#!/bin/bash

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

BASE_URL="http://localhost:8000"

echo -e "${BLUE}=== Auth API Mock Integration Test ===${NC}\n"

# Test 1: Health Check
echo -e "${BLUE}Test 1: Health Check${NC}"
HEALTH=$(curl -s "$BASE_URL/health")
if [ $? -eq 0 ]; then
  echo -e "${GREEN}✓ Health check passed${NC}"
  echo "$HEALTH" | jq
else
  echo -e "${RED}✗ Health check failed${NC}"
  exit 1
fi

echo -e "\n${BLUE}Test 2: Login${NC}"
LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"password123"}')

TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token')
if [ "$TOKEN" != "null" ] && [ -n "$TOKEN" ]; then
  echo -e "${GREEN}✓ Login successful${NC}"
  echo "Token: ${TOKEN:0:20}..."
else
  echo -e "${RED}✗ Login failed${NC}"
  echo "$LOGIN_RESPONSE" | jq
  exit 1
fi

echo -e "\n${BLUE}Test 3: Get Current User${NC}"
USER_RESPONSE=$(curl -s "$BASE_URL/api/auth/me?token=$TOKEN")
USER_EMAIL=$(echo "$USER_RESPONSE" | jq -r '.email')
if [ "$USER_EMAIL" = "alice@example.com" ]; then
  echo -e "${GREEN}✓ Get current user successful${NC}"
  echo "$USER_RESPONSE" | jq
else
  echo -e "${RED}✗ Get current user failed${NC}"
  exit 1
fi

echo -e "\n${BLUE}Test 4: Register New User${NC}"
RANDOM_EMAIL="testuser$(date +%s)@example.com"
REGISTER_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$RANDOM_EMAIL\",\"password\":\"testpass123\",\"name\":\"Test User\"}")

USER_ID=$(echo "$REGISTER_RESPONSE" | jq -r '.id')
if [ "$USER_ID" != "null" ] && [ -n "$USER_ID" ]; then
  echo -e "${GREEN}✓ Registration successful${NC}"
  echo "User ID: $USER_ID"
else
  echo -e "${RED}✗ Registration failed${NC}"
  echo "$REGISTER_RESPONSE" | jq
  exit 1
fi

echo -e "\n${BLUE}Test 5: Error Simulation (401)${NC}"
ERROR_RESPONSE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE_URL/api/auth/login?simulate_error=401" \
  -X POST -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"password123"}')

if [ "$ERROR_RESPONSE" = "401" ]; then
  echo -e "${GREEN}✓ Error simulation working${NC}"
else
  echo -e "${RED}✗ Error simulation failed (got $ERROR_RESPONSE instead of 401)${NC}"
  exit 1
fi

echo -e "\n${GREEN}=== All tests passed! ===${NC}"
```

Make it executable and run:

```bash
chmod +x test_auth_api.sh
./test_auth_api.sh
```

## Testing with Chat API Integration

### Complete E2E Flow

```bash
#!/bin/bash

# Step 1: Get JWT token from auth mock
echo "1. Getting JWT token from auth-api mock..."
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"password123"}' \
  | jq -r '.access_token')

echo "Token received: ${TOKEN:0:20}..."

# Step 2: Use token with chat-api
echo -e "\n2. Accessing chat-api with token..."
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8001/api/chat/groups | jq

# Step 3: Get specific group
echo -e "\n3. Getting specific group..."
GROUP_ID="your-group-id-here"
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8001/api/chat/groups/$GROUP_ID | jq

# Step 4: Send message
echo -e "\n4. Sending message..."
curl -X POST http://localhost:8001/api/chat/groups/$GROUP_ID/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content":"Hello from integration test!"}' | jq

echo -e "\n✓ Integration test complete!"
```

## Quick Test All Seed Users

```bash
#!/bin/bash

USERS=("alice@example.com" "bob@example.com" "charlie@example.com" "diana@example.com" "ethan@example.com")

for email in "${USERS[@]}"; do
  echo "Testing login for: $email"
  curl -s -X POST http://localhost:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$email\",\"password\":\"password123\"}" \
    | jq -r '.user.name'
  echo ""
done
```
