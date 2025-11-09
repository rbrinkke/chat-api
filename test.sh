#!/bin/bash

# ==============================================================================
# Chat API - Comprehensive Test Suite
# ==============================================================================
# Tests MongoDB setup, API startup, REST endpoints, and WebSocket connections
# Usage: ./test.sh [--cleanup]
# ==============================================================================

set -e  # Exit on error (will be disabled for expected failures)

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_URL="http://localhost:8001"
MONGODB_CONTAINER="chat-api-mongodb"
MONGODB_PORT=27017
API_PORT=8001
DB_NAME="chat_db"
JWT_SECRET="dev-secret-key-change-in-production"

# Activate virtual environment if it exists
if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ==============================================================================
# Helper Functions
# ==============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

log_section() {
    echo ""
    echo -e "${BLUE}===================================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}===================================================${NC}"
}

test_result() {
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    if [ $1 -eq 0 ]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        log_success "$2"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        log_error "$2"
    fi
}

cleanup() {
    log_section "Cleanup"

    if [ "$1" == "--full" ]; then
        log_info "Stopping API..."
        pkill -f "uvicorn app.main:app" 2>/dev/null || true

        log_info "Removing test data from MongoDB..."
        docker exec $MONGODB_CONTAINER mongosh $DB_NAME --quiet --eval "
            db.groups.deleteMany({name: {\$in: ['General', 'Dev Team', 'Private']}});
            db.messages.deleteMany({});
        " 2>/dev/null || true

        log_info "Stopping MongoDB container..."
        docker stop $MONGODB_CONTAINER 2>/dev/null || true
        docker rm $MONGODB_CONTAINER 2>/dev/null || true

        log_success "Full cleanup completed"
    else
        log_info "Partial cleanup - removing test data only..."
        docker exec $MONGODB_CONTAINER mongosh $DB_NAME --quiet --eval "
            db.groups.deleteMany({name: {\$in: ['General', 'Dev Team', 'Private']}});
            db.messages.deleteMany({});
        " 2>/dev/null || true
        log_success "Test data removed"
    fi
}

# Trap to cleanup on script exit
trap 'cleanup' EXIT

wait_for_service() {
    local url=$1
    local max_attempts=${2:-30}
    local attempt=1

    log_info "Waiting for service at $url..."

    while [ $attempt -le $max_attempts ]; do
        if curl -s -f "$url" > /dev/null 2>&1; then
            log_success "Service is ready!"
            return 0
        fi

        echo -n "."
        sleep 1
        attempt=$((attempt + 1))
    done

    log_error "Service did not become ready in time"
    return 1
}

generate_jwt_token() {
    local user_id=$1
    python3 -c "
from jose import jwt
from datetime import datetime, timedelta
import sys

try:
    payload = {
        'sub': '$user_id',
        'exp': datetime.utcnow() + timedelta(hours=24)
    }
    token = jwt.encode(payload, '$JWT_SECRET', algorithm='HS256')
    print(token)
except Exception as e:
    print(f'Error generating token: {e}', file=sys.stderr)
    sys.exit(1)
"
}

# ==============================================================================
# Prerequisites Check
# ==============================================================================

log_section "Prerequisites Check"

# Check Docker
if ! command -v docker &> /dev/null; then
    log_error "Docker is not installed"
    exit 1
fi
log_success "Docker is installed"

# Check curl
if ! command -v curl &> /dev/null; then
    log_error "curl is not installed"
    exit 1
fi
log_success "curl is installed"

# Check jq
if ! command -v jq &> /dev/null; then
    log_warning "jq is not installed (JSON parsing will be limited)"
else
    log_success "jq is installed"
fi

# Check Python3 and required libraries
if ! command -v python3 &> /dev/null; then
    log_error "Python3 is not installed"
    exit 1
fi
log_success "Python3 is installed"

# Check python-jose
if ! python3 -c "import jose" 2>/dev/null; then
    log_error "python-jose is not installed (run: pip install python-jose[cryptography])"
    exit 1
fi
log_success "python-jose is installed"

# ==============================================================================
# MongoDB Setup
# ==============================================================================

log_section "MongoDB Setup"

# Check if MongoDB container exists
if docker ps -a --format '{{.Names}}' | grep -q "^${MONGODB_CONTAINER}$"; then
    log_info "MongoDB container exists"

    # Check if it's running
    if docker ps --format '{{.Names}}' | grep -q "^${MONGODB_CONTAINER}$"; then
        log_success "MongoDB container is already running"
    else
        log_info "Starting existing MongoDB container..."
        docker start $MONGODB_CONTAINER
        sleep 3
    fi
else
    log_info "Creating new MongoDB container..."
    docker run -d \
        --name $MONGODB_CONTAINER \
        -p $MONGODB_PORT:27017 \
        mongo:7.0

    sleep 5
fi

# Wait for MongoDB to be ready
log_info "Checking MongoDB health..."
max_attempts=30
attempt=1

while [ $attempt -le $max_attempts ]; do
    if docker exec $MONGODB_CONTAINER mongosh --quiet --eval "db.runCommand({ping: 1})" > /dev/null 2>&1; then
        log_success "MongoDB is ready!"
        break
    fi

    echo -n "."
    sleep 1
    attempt=$((attempt + 1))

    if [ $attempt -gt $max_attempts ]; then
        log_error "MongoDB did not become ready in time"
        exit 1
    fi
done

# ==============================================================================
# Environment Setup
# ==============================================================================

log_section "Environment Setup"

# Check if .env exists
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    log_warning ".env file not found, creating default..."
    cat > "$SCRIPT_DIR/.env" << EOF
# Application
APP_NAME="Chat API"
APP_VERSION="1.0.0"
DEBUG=true
ENVIRONMENT="development"

# API
API_PREFIX="/api/chat"
HOST="0.0.0.0"
PORT=8001

# MongoDB
MONGODB_URL="mongodb://localhost:27017"
DATABASE_NAME="chat_db"

# JWT Authentication (MUST match auth-api)
JWT_SECRET="dev-secret-key-change-in-production"
JWT_ALGORITHM="HS256"

# Logging
LOG_LEVEL="INFO"
LOG_JSON_FORMAT=false
LOG_SQL_QUERIES=false

# CORS
CORS_ORIGINS='["http://localhost:3000","http://localhost:8000"]'
EOF
    log_success ".env file created"
else
    log_success ".env file exists"
fi

# ==============================================================================
# API Startup
# ==============================================================================

log_section "API Startup"

# Check if API is already running
if lsof -Pi :$API_PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    log_warning "Port $API_PORT is already in use"
    log_info "Attempting to stop existing process..."
    pkill -f "uvicorn app.main:app" || true
    sleep 2
fi

# Start API in background
log_info "Starting Chat API..."
cd "$SCRIPT_DIR"
python3 -m uvicorn app.main:app --host 0.0.0.0 --port $API_PORT > /tmp/chat-api.log 2>&1 &
API_PID=$!

log_info "API started with PID: $API_PID"

# Wait for API to be ready
if ! wait_for_service "$API_URL/health" 30; then
    log_error "API failed to start"
    log_info "Last 20 lines of log:"
    tail -n 20 /tmp/chat-api.log
    exit 1
fi

# Verify health endpoint
HEALTH_RESPONSE=$(curl -s "$API_URL/health")
if echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
    log_success "API is healthy: $HEALTH_RESPONSE"
else
    log_error "API health check failed: $HEALTH_RESPONSE"
    exit 1
fi

# ==============================================================================
# Generate JWT Tokens
# ==============================================================================

log_section "JWT Token Generation"

log_info "Generating test tokens..."

TOKEN_USER_123=$(generate_jwt_token "user-123")
if [ -z "$TOKEN_USER_123" ]; then
    log_error "Failed to generate token for user-123"
    exit 1
fi
log_success "Token generated for user-123"

TOKEN_USER_456=$(generate_jwt_token "user-456")
if [ -z "$TOKEN_USER_456" ]; then
    log_error "Failed to generate token for user-456"
    exit 1
fi
log_success "Token generated for user-456"

TOKEN_USER_789=$(generate_jwt_token "user-789")
if [ -z "$TOKEN_USER_789" ]; then
    log_error "Failed to generate token for user-789"
    exit 1
fi
log_success "Token generated for user-789"

# ==============================================================================
# Test Data Creation
# ==============================================================================

log_section "Test Data Creation"

log_info "Creating test groups in MongoDB..."

# Create Group 1: General (user-123, user-456)
GROUP_1_OUTPUT=$(docker exec $MONGODB_CONTAINER mongosh $DB_NAME --quiet --eval "
    JSON.stringify(db.groups.insertOne({
        name: 'General',
        description: 'General discussion for everyone',
        authorized_user_ids: ['user-123', 'user-456'],
        created_at: new Date()
    }))
")

if command -v jq &> /dev/null; then
    GROUP_1_ID=$(echo "$GROUP_1_OUTPUT" | jq -r '.insertedId')
else
    GROUP_1_ID=$(echo "$GROUP_1_OUTPUT" | grep -o '"insertedId":"[^"]*"' | cut -d'"' -f4)
fi

if [ -z "$GROUP_1_ID" ] || [ "$GROUP_1_ID" == "null" ]; then
    log_error "Failed to create Group 1 (General)"
    exit 1
fi
log_success "Group 1 created: General (ID: $GROUP_1_ID)"

# Create Group 2: Dev Team (user-123, user-789)
GROUP_2_OUTPUT=$(docker exec $MONGODB_CONTAINER mongosh $DB_NAME --quiet --eval "
    JSON.stringify(db.groups.insertOne({
        name: 'Dev Team',
        description: 'Development team discussions',
        authorized_user_ids: ['user-123', 'user-789'],
        created_at: new Date()
    }))
")

if command -v jq &> /dev/null; then
    GROUP_2_ID=$(echo "$GROUP_2_OUTPUT" | jq -r '.insertedId')
else
    GROUP_2_ID=$(echo "$GROUP_2_OUTPUT" | grep -o '"insertedId":"[^"]*"' | cut -d'"' -f4)
fi

if [ -z "$GROUP_2_ID" ] || [ "$GROUP_2_ID" == "null" ]; then
    log_error "Failed to create Group 2 (Dev Team)"
    exit 1
fi
log_success "Group 2 created: Dev Team (ID: $GROUP_2_ID)"

# Create Group 3: Private (user-456 only)
GROUP_3_OUTPUT=$(docker exec $MONGODB_CONTAINER mongosh $DB_NAME --quiet --eval "
    JSON.stringify(db.groups.insertOne({
        name: 'Private',
        description: 'Private group for user-456',
        authorized_user_ids: ['user-456'],
        created_at: new Date()
    }))
")

if command -v jq &> /dev/null; then
    GROUP_3_ID=$(echo "$GROUP_3_OUTPUT" | jq -r '.insertedId')
else
    GROUP_3_ID=$(echo "$GROUP_3_OUTPUT" | grep -o '"insertedId":"[^"]*"' | cut -d'"' -f4)
fi

if [ -z "$GROUP_3_ID" ] || [ "$GROUP_3_ID" == "null" ]; then
    log_error "Failed to create Group 3 (Private)"
    exit 1
fi
log_success "Group 3 created: Private (ID: $GROUP_3_ID)"

# ==============================================================================
# REST API Tests
# ==============================================================================

log_section "REST API Tests"

# Test 1: Health check (no auth)
log_info "Test 1: Health check endpoint"
RESPONSE=$(curl -s -w "\n%{http_code}" "$API_URL/health")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 200 ]; then
    test_result 0 "Health check returned 200"
else
    test_result 1 "Health check failed with code $HTTP_CODE"
fi

# Test 2: Get groups for user-123 (should see General + Dev Team = 2 groups)
log_info "Test 2: List groups for user-123"
RESPONSE=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $TOKEN_USER_123" "$API_URL/api/chat/groups")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 200 ]; then
    if command -v jq &> /dev/null; then
        GROUP_COUNT=$(echo "$BODY" | jq '. | length')
        if [ "$GROUP_COUNT" -eq 2 ]; then
            test_result 0 "User-123 sees 2 groups (correct)"
        else
            test_result 1 "User-123 sees $GROUP_COUNT groups (expected 2)"
        fi
    else
        test_result 0 "Groups listed successfully (jq not available for count validation)"
    fi
else
    test_result 1 "List groups failed with code $HTTP_CODE"
fi

# Test 3: Get groups for user-456 (should see General + Private = 2 groups)
log_info "Test 3: List groups for user-456"
RESPONSE=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $TOKEN_USER_456" "$API_URL/api/chat/groups")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 200 ]; then
    if command -v jq &> /dev/null; then
        GROUP_COUNT=$(echo "$BODY" | jq '. | length')
        if [ "$GROUP_COUNT" -eq 2 ]; then
            test_result 0 "User-456 sees 2 groups (correct)"
        else
            test_result 1 "User-456 sees $GROUP_COUNT groups (expected 2)"
        fi
    else
        test_result 0 "Groups listed successfully"
    fi
else
    test_result 1 "List groups failed with code $HTTP_CODE"
fi

# Test 4: Get single group (authorized)
log_info "Test 4: Get single group (user-123 accessing General)"
RESPONSE=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $TOKEN_USER_123" "$API_URL/api/chat/groups/$GROUP_1_ID")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

if [ "$HTTP_CODE" -eq 200 ]; then
    test_result 0 "Get single group succeeded (authorized)"
else
    test_result 1 "Get single group failed with code $HTTP_CODE"
fi

# Test 5: Get single group (unauthorized - user-123 accessing Private)
log_info "Test 5: Get single group (user-123 accessing Private - should fail)"
RESPONSE=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $TOKEN_USER_123" "$API_URL/api/chat/groups/$GROUP_3_ID")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

if [ "$HTTP_CODE" -eq 403 ]; then
    test_result 0 "Authorization correctly denied (403)"
else
    test_result 1 "Expected 403, got $HTTP_CODE"
fi

# Test 6: Create message in General group
log_info "Test 6: Create message in General group"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
    -H "Authorization: Bearer $TOKEN_USER_123" \
    -H "Content-Type: application/json" \
    -d '{"content": "Hello from user-123! This is a test message."}' \
    "$API_URL/api/chat/groups/$GROUP_1_ID/messages")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 201 ] || [ "$HTTP_CODE" -eq 200 ]; then
    if command -v jq &> /dev/null; then
        MESSAGE_1_ID=$(echo "$BODY" | jq -r '.id')
        test_result 0 "Message created successfully (ID: $MESSAGE_1_ID)"
    else
        test_result 0 "Message created successfully"
        MESSAGE_1_ID=""
    fi
else
    test_result 1 "Create message failed with code $HTTP_CODE: $BODY"
    MESSAGE_1_ID=""
fi

# Test 7: Create another message (for update/delete tests)
log_info "Test 7: Create second message"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
    -H "Authorization: Bearer $TOKEN_USER_123" \
    -H "Content-Type: application/json" \
    -d '{"content": "Second test message for editing"}' \
    "$API_URL/api/chat/groups/$GROUP_1_ID/messages")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 201 ] || [ "$HTTP_CODE" -eq 200 ]; then
    if command -v jq &> /dev/null; then
        MESSAGE_2_ID=$(echo "$BODY" | jq -r '.id')
        test_result 0 "Second message created (ID: $MESSAGE_2_ID)"
    else
        test_result 0 "Second message created"
        MESSAGE_2_ID=""
    fi
else
    test_result 1 "Create second message failed with code $HTTP_CODE"
    MESSAGE_2_ID=""
fi

# Test 8: Get messages from group
log_info "Test 8: Get messages from General group"
RESPONSE=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $TOKEN_USER_123" "$API_URL/api/chat/groups/$GROUP_1_ID/messages")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 200 ]; then
    if command -v jq &> /dev/null; then
        MESSAGE_COUNT=$(echo "$BODY" | jq -r '.messages | length')
        test_result 0 "Retrieved $MESSAGE_COUNT messages"
    else
        test_result 0 "Messages retrieved successfully"
    fi
else
    test_result 1 "Get messages failed with code $HTTP_CODE"
fi

# Test 9: Update message (own message)
if [ -n "$MESSAGE_2_ID" ]; then
    log_info "Test 9: Update own message"
    RESPONSE=$(curl -s -w "\n%{http_code}" -X PUT \
        -H "Authorization: Bearer $TOKEN_USER_123" \
        -H "Content-Type: application/json" \
        -d '{"content": "Updated message content!"}' \
        "$API_URL/api/chat/messages/$MESSAGE_2_ID")
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

    if [ "$HTTP_CODE" -eq 200 ]; then
        test_result 0 "Message updated successfully"
    else
        test_result 1 "Update message failed with code $HTTP_CODE"
    fi
else
    log_warning "Test 9 skipped: No message ID available"
fi

# Test 10: Delete message (own message)
if [ -n "$MESSAGE_2_ID" ]; then
    log_info "Test 10: Soft delete own message"
    RESPONSE=$(curl -s -w "\n%{http_code}" -X DELETE \
        -H "Authorization: Bearer $TOKEN_USER_123" \
        "$API_URL/api/chat/messages/$MESSAGE_2_ID")
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

    if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 204 ]; then
        test_result 0 "Message soft-deleted successfully"
    else
        test_result 1 "Delete message failed with code $HTTP_CODE"
    fi

    # Verify soft delete - message should not appear in list
    log_info "Test 10b: Verify soft delete"
    RESPONSE=$(curl -s -H "Authorization: Bearer $TOKEN_USER_123" "$API_URL/api/chat/groups/$GROUP_1_ID/messages")
    if command -v jq &> /dev/null; then
        DELETED_MSG=$(echo "$RESPONSE" | jq -r ".messages[] | select(.id == \"$MESSAGE_2_ID\")")
        if [ -z "$DELETED_MSG" ]; then
            test_result 0 "Soft-deleted message not in list (correct)"
        else
            test_result 1 "Soft-deleted message still appears in list"
        fi
    else
        log_warning "Test 10b skipped: jq not available"
    fi
else
    log_warning "Test 10 skipped: No message ID available"
fi

# Test 11: Pagination test
log_info "Test 11: Test pagination"
RESPONSE=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $TOKEN_USER_123" "$API_URL/api/chat/groups/$GROUP_1_ID/messages?page=1&page_size=10")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 200 ]; then
    if command -v jq &> /dev/null; then
        TOTAL=$(echo "$BODY" | jq -r '.total')
        test_result 0 "Pagination working (total: $TOTAL messages)"
    else
        test_result 0 "Pagination endpoint accessible"
    fi
else
    test_result 1 "Pagination test failed with code $HTTP_CODE"
fi

# ==============================================================================
# WebSocket Test
# ==============================================================================

log_section "WebSocket Tests"

log_info "Creating WebSocket test client..."

cat > /tmp/ws_test.py << 'WSPYTHON'
import asyncio
import websockets
import json
import sys

async def test_websocket(url, token, group_id):
    """Test WebSocket connection and basic message handling."""
    ws_url = f"{url}?token={token}"

    try:
        async with websockets.connect(ws_url) as websocket:
            print("✓ WebSocket connected successfully")

            # Wait for connection message
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                data = json.loads(response)

                if data.get("type") == "connected":
                    print(f"✓ Received connection confirmation: {data.get('message')}")
                else:
                    print(f"! Unexpected message type: {data.get('type')}")

            except asyncio.TimeoutError:
                print("✗ Timeout waiting for connection message")
                return False

            # Send ping
            await websocket.send(json.dumps({"type": "ping"}))
            print("✓ Sent ping message")

            # Wait briefly to see if server responds
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                print(f"✓ Received response: {response}")
            except asyncio.TimeoutError:
                print("✓ No response to ping (expected)")

            print("✓ WebSocket test completed successfully")
            return True

    except websockets.exceptions.InvalidStatusCode as e:
        print(f"✗ WebSocket connection failed with status code: {e.status_code}")
        return False
    except Exception as e:
        print(f"✗ WebSocket test failed: {str(e)}")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python ws_test.py <ws_url> <token> <group_id>")
        sys.exit(1)

    url = sys.argv[1]
    token = sys.argv[2]
    group_id = sys.argv[3]

    success = asyncio.run(test_websocket(url, token, group_id))
    sys.exit(0 if success else 1)
WSPYTHON

# Check if websockets library is available
if python3 -c "import websockets" 2>/dev/null; then
    log_info "Testing WebSocket connection..."

    WS_URL="ws://localhost:$API_PORT/api/chat/ws/$GROUP_1_ID"

    if python3 /tmp/ws_test.py "$WS_URL" "$TOKEN_USER_123" "$GROUP_1_ID"; then
        test_result 0 "WebSocket connection and messaging test passed"
    else
        test_result 1 "WebSocket test failed"
    fi
else
    log_warning "websockets library not installed (pip install websockets)"
    log_warning "WebSocket tests skipped"
fi

# ==============================================================================
# Test Summary
# ==============================================================================

log_section "Test Summary"

echo ""
echo -e "${BLUE}Total Tests:${NC} $TESTS_TOTAL"
echo -e "${GREEN}Passed:${NC} $TESTS_PASSED"
echo -e "${RED}Failed:${NC} $TESTS_FAILED"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    log_success "All tests passed! 🎉"
    EXIT_CODE=0
else
    log_error "Some tests failed"
    EXIT_CODE=1
fi

# ==============================================================================
# Cleanup Prompt
# ==============================================================================

echo ""
read -p "Do you want to clean up test data? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    cleanup --full
else
    log_info "Test data preserved for manual inspection"
    log_info "MongoDB: docker exec -it $MONGODB_CONTAINER mongosh $DB_NAME"
    log_info "API logs: tail -f /tmp/chat-api.log"
fi

exit $EXIT_CODE
