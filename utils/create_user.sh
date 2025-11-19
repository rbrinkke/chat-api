#!/bin/bash

# ═══════════════════════════════════════════════════════════════════
# CREATE USER UTILITY - SIMPLE VERSION
# ═══════════════════════════════════════════════════════════════════

set -e

# 1. Random credentials
EMAIL="test_$(date +%s)_$(shuf -i 1000-9999 -n 1)@example.com"
PASSWORD="Pass$(date +%s)Str0ng!"

echo "🚀 Creating user: $EMAIL"

# 2. Register via API (password wordt correct gehashed!)
echo "📝 Registering via API..."
REGISTER_RESPONSE=$(curl -s -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"confirm_password\":\"$PASSWORD\"}")

# Check for errors
if echo "$REGISTER_RESPONSE" | grep -q "detail"; then
    ERROR=$(echo "$REGISTER_RESPONSE" | jq -r '.detail // "Unknown error"')
    if ! echo "$ERROR" | grep -qi "already exists"; then
        echo "❌ Registration failed: $ERROR"
        return 1 2>/dev/null || exit 1
    fi
    echo "⚠️  User already exists, continuing..."
fi

# 3. Database: set is_verified = true
echo "🔓 Activating user in database..."
docker exec activity-postgres-db psql -U postgres -d activitydb -c \
  "UPDATE activity.users SET is_verified=true WHERE email='$EMAIL';" > /dev/null 2>&1

# 4. Get USER_ID from database
USER_ID=$(docker exec activity-postgres-db psql -U postgres -d activitydb -t -c \
  "SELECT user_id FROM activity.users WHERE email='$EMAIL';" | xargs)

if [ -z "$USER_ID" ]; then
    echo "❌ User not found in database"
    return 1 2>/dev/null || exit 1
fi

echo "✅ User activated (ID: $USER_ID)"

# 5. Login (SKIP_LOGIN_CODE=true → krijgt DIRECT tokens!)
echo "🔑 Logging in..."
LOGIN_RESPONSE=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")

# Extract tokens
JWT_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token')
REFRESH_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.refresh_token')

if [ "$JWT_TOKEN" = "null" ] || [ -z "$JWT_TOKEN" ]; then
    echo "❌ Login failed"
    echo "Response: $LOGIN_RESPONSE"
    return 1 2>/dev/null || exit 1
fi

echo "✅ Login successful"

# 6. Export variables
export USER_EMAIL="$EMAIL"
export USER_PASSWORD="$PASSWORD"
export USER_ID="$USER_ID"
export JWT_TOKEN="$JWT_TOKEN"
export REFRESH_TOKEN="$REFRESH_TOKEN"

# 7. Summary
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✅ USER CREATED SUCCESSFULLY"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "USER_EMAIL    = $EMAIL"
echo "USER_PASSWORD = $PASSWORD"
echo "USER_ID       = $USER_ID"
echo "JWT_TOKEN     = ${JWT_TOKEN:0:50}..."
echo "REFRESH_TOKEN = ${REFRESH_TOKEN:0:50}..."
echo ""
echo "Use in your scripts:"
echo '  curl -H "Authorization: Bearer $JWT_TOKEN" http://localhost:8001/api/chat/groups'
echo ""
echo "═══════════════════════════════════════════════════════════"
