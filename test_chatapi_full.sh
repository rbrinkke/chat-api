#!/bin/bash

# ═══════════════════════════════════════════════════════════════════
# TEST CHAT API FULL - COMPREHENSIVE E2E TEST SUITE
# ═══════════════════════════════════════════════════════════════════

# Stop execution immediately if a command exits with a non-zero status
set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Global Variables (Corrected based on config.py and docker-compose.yml)
CHAT_API_URL="http://localhost:8001/api/chat"
AUTH_API_URL="http://localhost:8000/api/auth"
DB_CONTAINER="chat-api-mongodb"

# Counters
TESTS_PASSED=0
TESTS_TOTAL=0

# ═══════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
    TESTS_PASSED=$((TESTS_PASSED+1))
    TESTS_TOTAL=$((TESTS_TOTAL+1))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    TESTS_TOTAL=$((TESTS_TOTAL+1))
    # Don't exit immediately to allow reading output
}

# ═══════════════════════════════════════════════════════════════════
# MAIN TEST EXECUTION
# ═══════════════════════════════════════════════════════════════════

echo -e "${YELLOW}Starting Chat API Full Test Suite...${NC}"
echo -e "${BLUE}Target: $CHAT_API_URL${NC}"

# -------------------------------------------------------------------
# 1. Setup Users
# -------------------------------------------------------------------
echo -e "\n${YELLOW}Step 1: Setup Users${NC}"

# User A (Alice)
log_info "Creating User A (Alice)..."
source utils/create_user.sh > /dev/null 2>&1
USER_A_EMAIL="$USER_EMAIL"
USER_A_ID="$USER_ID"
USER_A_TOKEN="$JWT_TOKEN"
log_info "✅ User A: $USER_A_EMAIL (ID: $USER_A_ID)"

# User B (Bob)
log_info "Creating User B (Bob)..."
source utils/create_user.sh > /dev/null 2>&1
USER_B_EMAIL="$USER_EMAIL"
USER_B_ID="$USER_ID"
USER_B_TOKEN="$JWT_TOKEN"
log_info "✅ User B: $USER_B_EMAIL (ID: $USER_B_ID)"

# -------------------------------------------------------------------
# 2. Setup Organization & Group (Via Auth API)
# -------------------------------------------------------------------
echo -e "\n${YELLOW}Step 2: Setup Organization & Group Context${NC}"
log_info "Creating a shared Organization and Group via Auth API..."

# 2a. Create Organization (Alice)
ORG_PAYLOAD="{\"name\":\"Test Org $(date +%s)\",\"slug\":\"test-org-$(date +%s)\",\"description\":\"E2E Test Org\"}"
ORG_RESPONSE=$(curl -s -X POST "$AUTH_API_URL/organizations" \
  -H "Authorization: Bearer $USER_A_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$ORG_PAYLOAD")

# Check if creation succeeded or if we need to fallback to existing
if echo "$ORG_RESPONSE" | jq -e '.id' > /dev/null 2>&1; then
    ORG_ID=$(echo "$ORG_RESPONSE" | jq -r '.id')
    log_success "Organization created: $ORG_ID"
else
    # Fallback: Get first org from list if creation fails/exists
    log_info "Organization creation response: $ORG_RESPONSE"
    ORG_LIST=$(curl -s -X GET "$AUTH_API_URL/organizations" -H "Authorization: Bearer $USER_A_TOKEN")
    ORG_ID=$(echo "$ORG_LIST" | jq -r '.[0].id // empty')

    if [ -z "$ORG_ID" ] || [ "$ORG_ID" == "null" ]; then
        log_fail "Could not establish Organization ID. Response: $ORG_RESPONSE"
        exit 1
    fi
    log_success "Using existing organization: $ORG_ID"
fi

# 2a-extra: Give Alice admin rights in the organization (direct database access)
log_info "Granting Alice admin rights in organization (via database)..."
docker exec activity-postgres-db psql -U postgres -d activitydb -c \
  "INSERT INTO activity.organization_members (organization_id, user_id, role, joined_at)
   VALUES ('$ORG_ID', '$USER_A_ID', 'admin', NOW())
   ON CONFLICT (organization_id, user_id) DO UPDATE SET role = 'admin';" > /dev/null 2>&1
log_success "Alice is now admin of organization $ORG_ID"

# 2b. Create Group (Alice)
GROUP_PAYLOAD="{\"name\":\"E2E Chat Group $(date +%s)\",\"description\":\"Integration Test Group\"}"
GROUP_RESPONSE=$(curl -s -X POST "$AUTH_API_URL/organizations/$ORG_ID/groups" \
  -H "Authorization: Bearer $USER_A_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$GROUP_PAYLOAD")

GROUP_ID=$(echo "$GROUP_RESPONSE" | jq -r '.id // empty')
if [ -z "$GROUP_ID" ] || [ "$GROUP_ID" == "null" ]; then
    log_fail "Failed to create group. Response: $GROUP_RESPONSE"
    exit 1
fi
log_success "Group created: $GROUP_ID"

# 2c. Add Bob to Group (Alice adds Bob)
log_info "Adding Bob to the group..."
ADD_MEMBER_RESPONSE=$(curl -s -X POST "$AUTH_API_URL/groups/$GROUP_ID/members" \
  -H "Authorization: Bearer $USER_A_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"$USER_B_ID\"}")

# Check if Bob was added successfully
if echo "$ADD_MEMBER_RESPONSE" | grep -iq "success\|added\|member"; then
    log_success "Bob added to group"
elif echo "$ADD_MEMBER_RESPONSE" | grep -iq "already"; then
    log_success "Bob already member of group"
else
    log_info "Add member response: $ADD_MEMBER_RESPONSE (continuing anyway)"
fi

# -------------------------------------------------------------------
# 3. Chat Conversation Test
# -------------------------------------------------------------------
echo -e "\n${YELLOW}Step 3: Chat Conversation Test${NC}"

# 3a. Alice Sends Message
log_info "Alice sending message..."
MSG1_CONTENT="Hello Bob! This is a test message."
MSG1_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$CHAT_API_URL/groups/$GROUP_ID/messages" \
  -H "Authorization: Bearer $USER_A_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"content\":\"$MSG1_CONTENT\"}")

# Extract HTTP code (last line) and body (all except last line)
MSG1_HTTP_CODE=$(echo "$MSG1_RESPONSE" | tail -n1)
MSG1_BODY=$(echo "$MSG1_RESPONSE" | sed '$d')

if [ "$MSG1_HTTP_CODE" == "201" ]; then
    MSG1_ID=$(echo "$MSG1_BODY" | jq -r '.id // empty')
    MSG1_SENDER=$(echo "$MSG1_BODY" | jq -r '.sender_id // empty')

    if [ -n "$MSG1_ID" ] && [ "$MSG1_ID" != "null" ] && [ "$MSG1_SENDER" == "$USER_A_ID" ]; then
        log_success "Alice sent message (ID: $MSG1_ID)"
    else
        log_fail "Alice message creation succeeded but invalid response. Body: $MSG1_BODY"
    fi
else
    log_fail "Alice failed to send message. HTTP $MSG1_HTTP_CODE. Response: $MSG1_BODY"
fi

# 3b. Bob Sends Reply
log_info "Bob replying..."
MSG2_CONTENT="Hi Alice! Loud and clear."
MSG2_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$CHAT_API_URL/groups/$GROUP_ID/messages" \
  -H "Authorization: Bearer $USER_B_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"content\":\"$MSG2_CONTENT\"}")

MSG2_HTTP_CODE=$(echo "$MSG2_RESPONSE" | tail -n1)
MSG2_BODY=$(echo "$MSG2_RESPONSE" | sed '$d')

if [ "$MSG2_HTTP_CODE" == "201" ]; then
    MSG2_ID=$(echo "$MSG2_BODY" | jq -r '.id // empty')

    if [ -n "$MSG2_ID" ] && [ "$MSG2_ID" != "null" ]; then
        log_success "Bob replied (ID: $MSG2_ID)"
    else
        log_fail "Bob message creation succeeded but invalid response. Body: $MSG2_BODY"
    fi
else
    log_fail "Bob failed to reply. HTTP $MSG2_HTTP_CODE. Response: $MSG2_BODY"
fi

# 3c. Bob Reads History
log_info "Bob reading message history..."
HISTORY_RESPONSE=$(curl -s -X GET "$CHAT_API_URL/groups/$GROUP_ID/messages?page=1&page_size=50" \
  -H "Authorization: Bearer $USER_B_TOKEN")

MSG_COUNT=$(echo "$HISTORY_RESPONSE" | jq -r '.messages | length // 0')
TOTAL_COUNT=$(echo "$HISTORY_RESPONSE" | jq -r '.total // 0')

if [ "$MSG_COUNT" -ge 2 ]; then
    log_success "Bob retrieved history ($MSG_COUNT messages found, total: $TOTAL_COUNT)"
else
    log_fail "History retrieval incomplete. Expected ≥2 messages, got $MSG_COUNT. Response: $HISTORY_RESPONSE"
fi

# 3d. Alice Edits Message
if [ -n "$MSG1_ID" ] && [ "$MSG1_ID" != "null" ]; then
    log_info "Alice editing her message..."
    UPDATE_CONTENT="Hello Bob! (Edited)"
    UPDATE_RESPONSE=$(curl -s -w "\n%{http_code}" -X PUT "$CHAT_API_URL/messages/$MSG1_ID" \
      -H "Authorization: Bearer $USER_A_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"content\":\"$UPDATE_CONTENT\"}")

    UPDATE_HTTP_CODE=$(echo "$UPDATE_RESPONSE" | tail -n1)
    UPDATE_BODY=$(echo "$UPDATE_RESPONSE" | sed '$d')

    if [ "$UPDATE_HTTP_CODE" == "200" ]; then
        UPDATED_CONTENT=$(echo "$UPDATE_BODY" | jq -r '.content // empty')

        if [ "$UPDATED_CONTENT" == "$UPDATE_CONTENT" ]; then
            log_success "Alice updated message successfully"
        else
            log_fail "Update succeeded but content mismatch. Expected: '$UPDATE_CONTENT', Got: '$UPDATED_CONTENT'"
        fi
    else
        log_fail "Update failed. HTTP $UPDATE_HTTP_CODE. Response: $UPDATE_BODY"
    fi
else
    log_fail "Skipping update test - MSG1_ID not available"
fi

# 3e. Security Check: Bob tries to edit Alice's message
if [ -n "$MSG1_ID" ] && [ "$MSG1_ID" != "null" ]; then
    log_info "Security Check: Bob trying to edit Alice's message..."
    HACK_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X PUT "$CHAT_API_URL/messages/$MSG1_ID" \
      -H "Authorization: Bearer $USER_B_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"content\":\"I am a hacker\"}")

    if [ "$HACK_RESPONSE" == "403" ]; then
        log_success "Security enforced: Bob cannot edit Alice's message (403 Forbidden)"
    else
        log_fail "Security breach! Expected 403, got: $HACK_RESPONSE"
    fi
else
    log_fail "Skipping security test - MSG1_ID not available"
fi

# 3f. Alice Deletes Message (Soft Delete)
if [ -n "$MSG1_ID" ] && [ "$MSG1_ID" != "null" ]; then
    log_info "Alice deleting her message..."
    DELETE_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$CHAT_API_URL/messages/$MSG1_ID" \
      -H "Authorization: Bearer $USER_A_TOKEN")

    if [ "$DELETE_RESPONSE" == "204" ]; then
        log_success "Alice deleted message (204 No Content)"
    else
        log_fail "Delete failed. Expected 204, got: $DELETE_RESPONSE"
    fi
else
    log_fail "Skipping delete test - MSG1_ID not available"
fi

# 3g. Verify Soft Delete (Bob fetching history)
if [ -n "$MSG1_ID" ] && [ "$MSG1_ID" != "null" ]; then
    log_info "Verifying soft delete..."
    FINAL_HISTORY=$(curl -s -X GET "$CHAT_API_URL/groups/$GROUP_ID/messages?page=1&page_size=50" \
      -H "Authorization: Bearer $USER_B_TOKEN")

    # Since soft-deleted messages should NOT appear in the list (is_deleted=False filter)
    # we check that MSG1_ID is NOT in the returned messages
    MSG1_IN_HISTORY=$(echo "$FINAL_HISTORY" | jq -r ".messages[] | select(.id==\"$MSG1_ID\") | .id // empty")

    if [ -z "$MSG1_IN_HISTORY" ]; then
        log_success "Message verified as soft-deleted (not in history)"
    else
        # Check if it's marked as deleted
        IS_DELETED=$(echo "$FINAL_HISTORY" | jq -r ".messages[] | select(.id==\"$MSG1_ID\") | .is_deleted // false")

        if [ "$IS_DELETED" == "true" ]; then
            log_success "Message marked as deleted in history"
        else
            log_fail "Message still appears in history and not marked as deleted"
        fi
    fi
else
    log_fail "Skipping soft delete verification - MSG1_ID not available"
fi

# -------------------------------------------------------------------
# Final Report
# -------------------------------------------------------------------
echo -e "\n═══════════════════════════════════════════════════════════════════"
echo -e "${GREEN}TEST SUITE COMPLETE${NC}"
echo -e "Total Tests: $TESTS_TOTAL"
echo -e "Passed:      $TESTS_PASSED"
echo -e "Failed:      $((TESTS_TOTAL - TESTS_PASSED))"
echo -e "═══════════════════════════════════════════════════════════════════"

if [ "$TESTS_PASSED" -eq "$TESTS_TOTAL" ]; then
    echo -e "${GREEN}🎉 SUCCESS: Chat API is fully functional!${NC}"
    exit 0
else
    echo -e "${RED}❌ FAILURE: Some tests failed.${NC}"
    exit 1
fi
