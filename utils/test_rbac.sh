#!/bin/bash

# ═══════════════════════════════════════════════════════════════════
# RBAC PERMISSION TESTING SCRIPT - REUSABLE
# Tests group-based permission validation via Auth API
# Creates user ONCE, then reuses for all future tests
# ═══════════════════════════════════════════════════════════════════

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Fixed test credentials (REUSABLE!)
TEST_EMAIL="rbac_test_user@example.com"
TEST_PASSWORD="RbacTestPass123!"

# Test organization and groups (from test_rbac_setup.sql)
TEST_ORG_ID="99999999-9999-9999-9999-999999999999"
VRIENDEN_GROUP_ID="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OBSERVERS_GROUP_ID="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
MODERATORS_GROUP_ID="cccccccc-cccc-cccc-cccc-cccccccccccc"

echo "═══════════════════════════════════════════════════════════"
echo "🧪 RBAC PERMISSION TEST SUITE (REUSABLE)"
echo "═══════════════════════════════════════════════════════════"
echo ""

# ═══════════════════════════════════════════════════════════════════
# STEP 1: GET OR CREATE TEST USER
# ═══════════════════════════════════════════════════════════════════

echo "📝 Step 1: Getting or creating test user..."

# Check if user exists
USER_ID=$(docker exec activity-postgres-db psql -U postgres -d activitydb -t -c \
  "SELECT user_id FROM activity.users WHERE email='$TEST_EMAIL';" | xargs)

if [ -z "$USER_ID" ]; then
    echo -e "${YELLOW}ℹ️  User doesn't exist, creating...${NC}"

    # Register new user
    REGISTER_RESPONSE=$(curl -s -X POST http://localhost:8000/api/auth/register \
      -H "Content-Type: application/json" \
      -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\",\"confirm_password\":\"$TEST_PASSWORD\"}")

    if echo "$REGISTER_RESPONSE" | grep -q "detail"; then
        ERROR=$(echo "$REGISTER_RESPONSE" | jq -r '.detail')
        if ! echo "$ERROR" | grep -qi "already exists"; then
            echo -e "${RED}❌ Registration failed: $ERROR${NC}"
            exit 1
        fi
    fi

    # Activate user
    docker exec activity-postgres-db psql -U postgres -d activitydb -c \
      "UPDATE activity.users SET is_verified=true WHERE email='$TEST_EMAIL';" > /dev/null 2>&1

    # Get user ID
    USER_ID=$(docker exec activity-postgres-db psql -U postgres -d activitydb -t -c \
      "SELECT user_id FROM activity.users WHERE email='$TEST_EMAIL';" | xargs)

    echo -e "${GREEN}✅ User created and activated${NC}"
else
    echo -e "${GREEN}✅ Using existing test user${NC}"
fi

echo -e "${BLUE}User ID: $USER_ID${NC}"

# ═══════════════════════════════════════════════════════════════════
# STEP 2: ENSURE USER IS IN TEST ORGANIZATION
# ═══════════════════════════════════════════════════════════════════

echo "👥 Step 2: Ensuring user is in test organization..."

# Update user to test organization (INSERT if not exists, UPDATE if exists)
docker exec activity-postgres-db psql -U postgres -d activitydb -c "
INSERT INTO activity.organization_members (user_id, organization_id)
VALUES ('$USER_ID'::UUID, '$TEST_ORG_ID'::UUID)
ON CONFLICT (user_id, organization_id) DO NOTHING;

UPDATE activity.organization_members
SET organization_id = '$TEST_ORG_ID'::UUID
WHERE user_id = '$USER_ID'::UUID
  AND organization_id != '$TEST_ORG_ID'::UUID;
" > /dev/null

echo -e "${GREEN}✅ User in test organization${NC}"
echo ""

# ═══════════════════════════════════════════════════════════════════
# STEP 3: LOGIN TO GET JWT WITH CORRECT ORG_ID
# ═══════════════════════════════════════════════════════════════════

echo "🔑 Step 3: Getting JWT token with test org_id..."

# Login to get JWT
LOGIN_RESPONSE=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}")

JWT_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token')

if [ "$JWT_TOKEN" = "null" ] || [ -z "$JWT_TOKEN" ]; then
    echo -e "${RED}❌ Login failed${NC}"
    echo "$LOGIN_RESPONSE" | jq '.'
    exit 1
fi

echo -e "${GREEN}✅ JWT token obtained${NC}"
echo ""

# ═══════════════════════════════════════════════════════════════════
# TEST SCENARIO 1: VRIENDEN GROUP (chat:read + chat:write)
# ═══════════════════════════════════════════════════════════════════

echo "═══════════════════════════════════════════════════════════"
echo "🧪 SCENARIO 1: User in VRIENDEN group (chat:read + chat:write)"
echo "═══════════════════════════════════════════════════════════"
echo "   Expected: GET 200 OK, POST 201 Created"
echo "═══════════════════════════════════════════════════════════"

# Set user to vrienden group
docker exec activity-postgres-db psql -U postgres -d activitydb -c "
DELETE FROM activity.user_groups WHERE user_id = '$USER_ID'::UUID;
INSERT INTO activity.user_groups (user_id, group_id, added_by)
VALUES ('$USER_ID'::UUID, '$VRIENDEN_GROUP_ID'::UUID, '$USER_ID'::UUID);
" > /dev/null

echo -e "${BLUE}👤 User now in VRIENDEN group${NC}"
echo ""

# Test 1.1: GET messages (requires chat:read)
echo "TEST 1.1: GET messages (requires chat:read)"
RESPONSE=$(curl -s -w "\n%{http_code}" -X GET \
  "http://localhost:8001/api/chat/conversations/$VRIENDEN_GROUP_ID/messages" \
  -H "Authorization: Bearer $JWT_TOKEN")

HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✅ PASS - GET returned 200 OK${NC}"
else
    echo -e "${RED}❌ FAIL - Expected 200, got $HTTP_CODE${NC}"
    echo "$BODY" | jq '.'
fi
echo ""

# Test 1.2: POST message (requires chat:write)
echo "TEST 1.2: POST message (requires chat:write)"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  "http://localhost:8001/api/chat/conversations/$VRIENDEN_GROUP_ID/messages" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"content\":\"Test message at $(date +%H:%M:%S)\"}")

HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [ "$HTTP_CODE" = "201" ]; then
    echo -e "${GREEN}✅ PASS - POST returned 201 Created${NC}"
    MESSAGE_ID=$(echo "$BODY" | jq -r '.id')
    echo "Message ID: $MESSAGE_ID"
else
    echo -e "${RED}❌ FAIL - Expected 201, got $HTTP_CODE${NC}"
    echo "$BODY" | jq '.'
fi
echo ""

# ═══════════════════════════════════════════════════════════════════
# TEST SCENARIO 2: OBSERVERS GROUP (NO PERMISSIONS)
# ═══════════════════════════════════════════════════════════════════

echo "═══════════════════════════════════════════════════════════"
echo "🧪 SCENARIO 2: User in OBSERVERS group (NO permissions)"
echo "═══════════════════════════════════════════════════════════"
echo "   Expected: GET 403 Forbidden, POST 403 Forbidden"
echo "═══════════════════════════════════════════════════════════"

# Set user to observers group
docker exec activity-postgres-db psql -U postgres -d activitydb -c "
DELETE FROM activity.user_groups WHERE user_id = '$USER_ID'::UUID;
INSERT INTO activity.user_groups (user_id, group_id, added_by)
VALUES ('$USER_ID'::UUID, '$OBSERVERS_GROUP_ID'::UUID, '$USER_ID'::UUID);
" > /dev/null

echo -e "${BLUE}👤 User now in OBSERVERS group${NC}"
echo ""

# Test 2.1: GET messages WITHOUT permission (should FAIL)
echo "TEST 2.1: GET messages WITHOUT permission (should FAIL with 403)"
RESPONSE=$(curl -s -w "\n%{http_code}" -X GET \
  "http://localhost:8001/api/chat/conversations/$VRIENDEN_GROUP_ID/messages" \
  -H "Authorization: Bearer $JWT_TOKEN")

HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [ "$HTTP_CODE" = "403" ]; then
    echo -e "${GREEN}✅ PASS - GET returned 403 Forbidden (correct!)${NC}"
    echo "Reason: $(echo "$BODY" | jq -r '.detail')"
else
    echo -e "${RED}❌ FAIL - Expected 403, got $HTTP_CODE${NC}"
    echo "$BODY" | jq '.'
fi
echo ""

# Test 2.2: POST message WITHOUT permission (should FAIL)
echo "TEST 2.2: POST message WITHOUT permission (should FAIL with 403)"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  "http://localhost:8001/api/chat/conversations/$VRIENDEN_GROUP_ID/messages" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"content\":\"This should fail\"}")

HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [ "$HTTP_CODE" = "403" ]; then
    echo -e "${GREEN}✅ PASS - POST returned 403 Forbidden (correct!)${NC}"
else
    echo -e "${RED}❌ FAIL - Expected 403, got $HTTP_CODE${NC}"
    echo "$BODY" | jq '.'
fi
echo ""

# ═══════════════════════════════════════════════════════════════════
# TEST SCENARIO 3: MODERATORS GROUP (chat:admin)
# ═══════════════════════════════════════════════════════════════════

echo "═══════════════════════════════════════════════════════════"
echo "🧪 SCENARIO 3: User in MODERATORS group (chat:admin)"
echo "═══════════════════════════════════════════════════════════"
echo "   Expected: GET 200 OK (admin has all permissions)"
echo "═══════════════════════════════════════════════════════════"

# Set user to moderators group
docker exec activity-postgres-db psql -U postgres -d activitydb -c "
DELETE FROM activity.user_groups WHERE user_id = '$USER_ID'::UUID;
INSERT INTO activity.user_groups (user_id, group_id, added_by)
VALUES ('$USER_ID'::UUID, '$MODERATORS_GROUP_ID'::UUID, '$USER_ID'::UUID);
" > /dev/null

echo -e "${BLUE}👤 User now in MODERATORS group${NC}"
echo ""

# Test 3.1: GET messages WITH admin permission (in THEIR OWN group)
echo "TEST 3.1: GET messages (admin in their own group)"
RESPONSE=$(curl -s -w "\n%{http_code}" -X GET \
  "http://localhost:8001/api/chat/conversations/$MODERATORS_GROUP_ID/messages" \
  -H "Authorization: Bearer $JWT_TOKEN")

HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✅ PASS - GET returned 200 OK${NC}"
else
    echo -e "${RED}❌ FAIL - Expected 200, got $HTTP_CODE${NC}"
fi
echo ""

# ═══════════════════════════════════════════════════════════════════
# CHECK LOGS
# ═══════════════════════════════════════════════════════════════════

echo "═══════════════════════════════════════════════════════════"
echo "📋 Recent Chat API Logs (last 30 lines with permission checks)"
echo "═══════════════════════════════════════════════════════════"

docker logs chat-api --tail 30 2>&1 | grep -i "permission\|auth" || echo "No permission logs found"
echo ""

# ═══════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════

echo "═══════════════════════════════════════════════════════════"
echo "✅ TEST SUITE COMPLETED"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "Test user credentials (REUSABLE):"
echo "  Email:    $TEST_EMAIL"
echo "  Password: $TEST_PASSWORD"
echo "  User ID:  $USER_ID"
echo ""
echo "Run this script anytime to test RBAC permissions!"
echo "═══════════════════════════════════════════════════════════"
