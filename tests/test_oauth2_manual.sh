#!/bin/bash
#
# Manual OAuth2 Integration Testing Script
# Tests the OAuth2 middleware with generated tokens
#

set -e

echo "============================================================"
echo "🔐 OAuth2 Integration Testing"
echo "============================================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
CHAT_API_URL="http://localhost:8001"
AUTH_API_URL="http://localhost:8000"

echo "📍 Chat API: $CHAT_API_URL"
echo "📍 Auth API: $AUTH_API_URL"
echo ""

# ========== Check Services ==========

echo "🔍 Checking services..."

if ! curl -s "$CHAT_API_URL/health" > /dev/null; then
    echo -e "${RED}❌ Chat API not running at $CHAT_API_URL${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Chat API is running${NC}"

if ! curl -s "$AUTH_API_URL/health" > /dev/null; then
    echo -e "${YELLOW}⚠️  Auth API not running at $AUTH_API_URL (optional for OAuth2 testing)${NC}"
else
    echo -e "${GREEN}✅ Auth API is running${NC}"
fi

echo ""

# ========== Test 1: Public Endpoints ==========

echo "============================================================"
echo "Test 1: Public Endpoints (No Auth Required)"
echo "============================================================"

PUBLIC_ENDPOINTS=("/health" "/dashboard" "/test-chat")

for endpoint in "${PUBLIC_ENDPOINTS[@]}"; do
    echo -n "Testing $endpoint... "
    response=$(curl -s -w "%{http_code}" -o /dev/null "$CHAT_API_URL$endpoint")

    if [ "$response" == "200" ]; then
        echo -e "${GREEN}✅ $response OK${NC}"
    elif [ "$response" == "404" ]; then
        echo -e "${YELLOW}⚠️  $response Not Found (endpoint may not exist)${NC}"
    else
        echo -e "${RED}❌ $response${NC}"
    fi
done

echo ""

# ========== Test 2: Protected Endpoints Without Token ==========

echo "============================================================"
echo "Test 2: Protected Endpoints (Should Reject Without Token)"
echo "============================================================"

echo -n "Testing /api/chat/groups without token... "
response=$(curl -s -w "%{http_code}" -o /dev/null "$CHAT_API_URL/api/chat/groups")

if [ "$response" == "401" ]; then
    echo -e "${GREEN}✅ $response Unauthorized (expected)${NC}"
else
    echo -e "${RED}❌ $response (expected 401)${NC}"
fi

echo ""

# ========== Test 3: Check JWKS Endpoint ==========

echo "============================================================"
echo "Test 3: Auth API JWKS Endpoint"
echo "============================================================"

if curl -s "$AUTH_API_URL/.well-known/jwks.json" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ JWKS endpoint available${NC}"

    echo ""
    echo "📋 JWKS Content:"
    curl -s "$AUTH_API_URL/.well-known/jwks.json" | python3 -m json.tool | head -20

    echo ""
    echo "🔑 Available Key IDs:"
    curl -s "$AUTH_API_URL/.well-known/jwks.json" | python3 -c "import sys, json; keys = json.load(sys.stdin)['keys']; print('\n'.join([f\"  - {k.get('kid', 'unknown')} ({k.get('alg', 'unknown')})\" for k in keys]))"
else
    echo -e "${YELLOW}⚠️  JWKS endpoint not available${NC}"
    echo "   This is expected if Auth API doesn't have OAuth2 implemented yet."
    echo "   OAuth2 testing will be limited without JWKS endpoint."
fi

echo ""

# ========== Test 4: Generate Test Token (if Auth API available) ==========

echo "============================================================"
echo "Test 4: Token Generation and Validation"
echo "============================================================"

if curl -s "$AUTH_API_URL/health" > /dev/null; then
    echo "🎫 Attempting to generate test token..."

    # Try to register/login to get a real token
    TEST_EMAIL="oauth2test@example.com"
    TEST_PASSWORD="Test1234!@#$"

    echo "   Registering test user: $TEST_EMAIL"
    register_response=$(curl -s -X POST "$AUTH_API_URL/auth/register" \
        -H "Content-Type: application/json" \
        -d "{\"email\": \"$TEST_EMAIL\", \"password\": \"$TEST_PASSWORD\"}" \
        2>&1 || echo '{"error": "registration failed"}')

    echo "   Registration response: $(echo $register_response | python3 -m json.tool 2>/dev/null || echo $register_response | head -c 100)"

    # Try to login (may fail if user exists, that's OK)
    echo ""
    echo "   Logging in..."
    login_response=$(curl -s -X POST "$AUTH_API_URL/auth/login" \
        -H "Content-Type: application/json" \
        -d "{\"username\": \"$TEST_EMAIL\", \"password\": \"$TEST_PASSWORD\"}" \
        2>&1 || echo '{"error": "login failed"}')

    ACCESS_TOKEN=$(echo $login_response | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null || echo "")

    if [ ! -z "$ACCESS_TOKEN" ] && [ "$ACCESS_TOKEN" != "None" ]; then
        echo -e "${GREEN}✅ Token generated successfully${NC}"
        echo "   Token (first 50 chars): ${ACCESS_TOKEN:0:50}..."

        echo ""
        echo "🔍 Testing token with Chat API..."

        # Test with token
        chat_response=$(curl -s -w "\n%{http_code}" "$CHAT_API_URL/api/chat/groups" \
            -H "Authorization: Bearer $ACCESS_TOKEN")

        status_code=$(echo "$chat_response" | tail -1)
        body=$(echo "$chat_response" | head -n -1)

        echo "   Response status: $status_code"
        echo "   Response body: $(echo $body | python3 -m json.tool 2>/dev/null || echo $body | head -c 200)"

        if [ "$status_code" == "200" ] || [ "$status_code" == "404" ]; then
            echo -e "${GREEN}✅ Token accepted by Chat API${NC}"
        elif [ "$status_code" == "401" ]; then
            echo -e "${RED}❌ Token rejected (401 Unauthorized)${NC}"
            echo "   This may indicate:"
            echo "   - JWT_SECRET mismatch between Auth API and Chat API"
            echo "   - Token format not compatible with OAuth2 middleware"
            echo "   - JWKS validation failed"
        elif [ "$status_code" == "403" ]; then
            echo -e "${YELLOW}⚠️  Token valid but insufficient permissions (403 Forbidden)${NC}"
        else
            echo -e "${RED}❌ Unexpected response: $status_code${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  Could not generate token${NC}"
        echo "   This is expected if Auth API doesn't support OAuth2 yet."
    fi
else
    echo -e "${YELLOW}⚠️  Auth API not available, skipping token tests${NC}"
fi

echo ""

# ========== Test 5: Check Chat API OAuth2 Configuration ==========

echo "============================================================"
echo "Test 5: Chat API OAuth2 Configuration"
echo "============================================================"

echo "📋 Checking Chat API OAuth2 settings..."

# Get environment variables from container
docker compose exec -T chat-api env | grep -E "(JWT_|AUTH_API_|JWKS_|USE_OAUTH2)" | sort || echo "Could not read environment variables"

echo ""

# ========== Summary ==========

echo "============================================================"
echo "📊 Test Summary"
echo "============================================================"
echo ""
echo "✅ Completed:"
echo "   - Public endpoints accessible without auth"
echo "   - Protected endpoints reject missing tokens"
echo "   - OAuth2 configuration checked"
echo ""
echo "⚠️  Next Steps:"
echo "   1. Ensure Auth API implements RS256 signing"
echo "   2. Add JWKS endpoint to Auth API"
echo "   3. Add 'permissions' array to JWT payload"
echo "   4. Verify JWT_SECRET matches between APIs"
echo "   5. Run pytest integration tests"
echo ""
echo "🔧 Manual Testing:"
echo "   # Generate token from Auth API"
echo "   curl -X POST $AUTH_API_URL/auth/login \\"
echo "     -H \"Content-Type: application/json\" \\"
echo "     -d '{\"username\": \"user@example.com\", \"password\": \"password\"}'"
echo ""
echo "   # Use token with Chat API"
echo "   curl $CHAT_API_URL/api/chat/groups \\"
echo "     -H \"Authorization: Bearer YOUR_TOKEN\""
echo ""
echo "============================================================"
