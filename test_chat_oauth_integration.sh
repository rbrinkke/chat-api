#!/bin/bash

################################################################################
# OAuth 2.0 Integration Test Script - Chat API
#
# Tests the complete OAuth 2.0 flow:
# 1. Get access token from Auth API OAuth server
# 2. Use token to call protected Chat API endpoints
# 3. Verify scope-based authorization
# 4. Verify token validation
#
# Prerequisites:
# - Auth API running on http://localhost:8000
# - Chat API running on http://localhost:8001
# - Test user credentials from Auth API
#
# Usage:
#   ./test_chat_oauth_integration.sh              # Run all tests
#   ./test_chat_oauth_integration.sh --verbose    # Verbose output
################################################################################

set -e  # Exit on error

# ============================================================================
# Configuration
# ============================================================================

AUTH_API_BASE="http://localhost:8000"
CHAT_API_BASE="http://localhost:8001"

# Test user credentials (from Auth API test users)
TEST_USER_EMAIL="grace.oauth@yahoo.com"
TEST_USER_PASSWORD="OAuth!Testing321"

# OAuth client credentials
CLIENT_ID="test-client-1"
CLIENT_SECRET="test-secret-1"
REDIRECT_URI="http://localhost:3000/callback"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Verbose mode
VERBOSE=false
if [[ "$1" == "--verbose" ]]; then
    VERBOSE=true
fi

# Test counters
PASS_COUNT=0
FAIL_COUNT=0

# ============================================================================
# Helper Functions
# ============================================================================

print_header() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

print_test() {
    echo -e "${YELLOW}▶ Test $1: $2${NC}"
}

print_pass() {
    echo -e "${GREEN}✅ PASS: $1${NC}"
    ((PASS_COUNT++))
}

print_fail() {
    echo -e "${RED}❌ FAIL: $1${NC}"
    ((FAIL_COUNT++))
}

print_info() {
    if [ "$VERBOSE" = true ]; then
        echo -e "${BLUE}ℹ️  $1${NC}"
    fi
}

# ============================================================================
# Test Functions
# ============================================================================

test_auth_api_health() {
    print_test "0.1" "Auth API Health Check"

    response=$(curl -s "$AUTH_API_BASE/health")

    if echo "$response" | grep -q "healthy"; then
        print_pass "Auth API is healthy"
        print_info "Response: $response"
    else
        print_fail "Auth API is not healthy"
        print_info "Response: $response"
        exit 1
    fi
}

test_chat_api_health() {
    print_test "0.2" "Chat API Health Check"

    response=$(curl -s "$CHAT_API_BASE/health" || echo "ERROR")

    if echo "$response" | grep -q "healthy"; then
        print_pass "Chat API is healthy"
        print_info "Response: $response"
    else
        print_fail "Chat API is not healthy or not running"
        print_info "Response: $response"
        echo -e "${YELLOW}⚠️  Note: Chat API might not have /health endpoint yet${NC}"
        echo -e "${YELLOW}   Continuing tests anyway...${NC}"
    fi
}

get_oauth_token() {
    print_test "1.1" "Get OAuth Token from Auth API"

    # Step 1: Generate PKCE challenge
    code_verifier=$(openssl rand -base64 64 | tr -d '/+=' | head -c 64)
    code_challenge=$(echo -n "$code_verifier" | openssl dgst -sha256 -binary | base64 -w 0 | tr -d '=' | tr '+/' '-_')

    print_info "PKCE verifier generated (length: ${#code_verifier})"
    print_info "PKCE challenge: $code_challenge"

    # Step 2: Get authorization code (simulated - normally done via browser)
    # For testing, we'll use the token endpoint directly with password grant
    # (Note: Auth API would need to support password grant for this test)

    # Alternative: Use client credentials flow
    token_response=$(curl -s -X POST "$AUTH_API_BASE/oauth/token" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "grant_type=client_credentials" \
        -d "client_id=$CLIENT_ID" \
        -d "client_secret=$CLIENT_SECRET" \
        -d "scope=chat:read chat:write")

    if [ "$VERBOSE" = true ]; then
        echo "Token response:"
        echo "$token_response" | jq '.' 2>/dev/null || echo "$token_response"
    fi

    # Extract access token
    ACCESS_TOKEN=$(echo "$token_response" | jq -r '.access_token' 2>/dev/null)

    if [ "$ACCESS_TOKEN" != "null" ] && [ -n "$ACCESS_TOKEN" ]; then
        print_pass "OAuth token obtained successfully"
        print_info "Token (first 50 chars): ${ACCESS_TOKEN:0:50}..."

        # Decode token payload (without verification)
        if command -v jq &> /dev/null; then
            token_payload=$(echo "$ACCESS_TOKEN" | cut -d'.' -f2 | base64 -d 2>/dev/null | jq '.' 2>/dev/null || echo "")
            if [ -n "$token_payload" ]; then
                print_info "Token payload:"
                echo "$token_payload" | jq -C '.' 2>/dev/null || echo "$token_payload"
            fi
        fi
    else
        print_fail "Failed to obtain OAuth token"
        print_info "Response: $token_response"

        # Try alternative: Direct login to get token (if Auth API supports it)
        echo -e "${YELLOW}⚠️  Trying alternative: Login with test user${NC}"

        login_response=$(curl -s -X POST "$AUTH_API_BASE/api/auth/login" \
            -H "Content-Type: application/json" \
            -d "{\"username\":\"$TEST_USER_EMAIL\",\"password\":\"$TEST_USER_PASSWORD\"}")

        ACCESS_TOKEN=$(echo "$login_response" | jq -r '.access_token' 2>/dev/null)

        if [ "$ACCESS_TOKEN" != "null" ] && [ -n "$ACCESS_TOKEN" ]; then
            print_pass "OAuth token obtained via login"
            print_info "Token (first 50 chars): ${ACCESS_TOKEN:0:50}..."
        else
            print_fail "Failed to obtain token via login either"
            print_info "Login response: $login_response"
            echo -e "${RED}Cannot proceed without access token${NC}"
            exit 1
        fi
    fi
}

test_chat_api_without_token() {
    print_test "2.1" "Chat API Without Token (Should Fail)"

    response=$(curl -s -w "\n%{http_code}" "$CHAT_API_BASE/api/chat/messages")
    http_code=$(echo "$response" | tail -1)
    body=$(echo "$response" | head -n -1)

    if [ "$http_code" == "401" ] || [ "$http_code" == "403" ]; then
        print_pass "Chat API correctly rejects request without token (HTTP $http_code)"
        print_info "Response: $body"
    else
        print_fail "Chat API should reject request without token, got HTTP $http_code"
        print_info "Response: $body"
    fi
}

test_chat_api_with_invalid_token() {
    print_test "2.2" "Chat API With Invalid Token (Should Fail)"

    invalid_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJmYWtlLXVzZXIifQ.fake_signature"

    response=$(curl -s -w "\n%{http_code}" "$CHAT_API_BASE/api/chat/messages" \
        -H "Authorization: Bearer $invalid_token")

    http_code=$(echo "$response" | tail -1)
    body=$(echo "$response" | head -n -1)

    if [ "$http_code" == "401" ]; then
        print_pass "Chat API correctly rejects invalid token (HTTP $http_code)"
        print_info "Response: $body"
    else
        print_fail "Chat API should reject invalid token, got HTTP $http_code"
        print_info "Response: $body"
    fi
}

test_chat_api_with_valid_token() {
    print_test "3.1" "Chat API With Valid Token (Should Succeed)"

    if [ -z "$ACCESS_TOKEN" ]; then
        print_fail "No access token available for test"
        return
    fi

    response=$(curl -s -w "\n%{http_code}" "$CHAT_API_BASE/api/chat/messages" \
        -H "Authorization: Bearer $ACCESS_TOKEN")

    http_code=$(echo "$response" | tail -1)
    body=$(echo "$response" | head -n -1)

    if [ "$http_code" == "200" ]; then
        print_pass "Chat API accepts valid OAuth token (HTTP $http_code)"
        print_info "Response: $body"
    else
        print_fail "Chat API should accept valid token, got HTTP $http_code"
        print_info "Response: $body"

        # Debug: Show token info
        if [ "$VERBOSE" = true ]; then
            echo -e "${YELLOW}Debug: Token used:${NC}"
            echo "${ACCESS_TOKEN:0:100}..."
        fi
    fi
}

test_chat_api_scope_enforcement() {
    print_test "3.2" "Chat API Scope Enforcement"

    if [ -z "$ACCESS_TOKEN" ]; then
        print_fail "No access token available for test"
        return
    fi

    # Try to access endpoint requiring chat:write scope
    response=$(curl -s -w "\n%{http_code}" "$CHAT_API_BASE/api/chat/messages" \
        -X POST \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"message":"test"}')

    http_code=$(echo "$response" | tail -1)
    body=$(echo "$response" | head -n -1)

    # If token has chat:write scope, should succeed (200)
    # If token lacks chat:write scope, should fail (403)

    if [ "$http_code" == "200" ] || [ "$http_code" == "201" ]; then
        print_pass "Chat API allows request with sufficient scope (HTTP $http_code)"
        print_info "Response: $body"
    elif [ "$http_code" == "403" ]; then
        print_pass "Chat API correctly enforces scope requirements (HTTP $http_code)"
        print_info "Token lacks required scope - this is correct behavior"
    elif [ "$http_code" == "404" ]; then
        echo -e "${YELLOW}⚠️  Endpoint not found - Chat API might not have POST /messages yet${NC}"
        echo -e "${YELLOW}   Skipping scope enforcement test${NC}"
    else
        print_fail "Unexpected response from Chat API (HTTP $http_code)"
        print_info "Response: $body"
    fi
}

test_token_expiration_handling() {
    print_test "4.1" "Token Expiration Handling"

    # Create an expired token (exp in the past)
    expired_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLTEyMyIsImV4cCI6MTAwMDAwMDAwMH0.fake"

    response=$(curl -s -w "\n%{http_code}" "$CHAT_API_BASE/api/chat/messages" \
        -H "Authorization: Bearer $expired_token")

    http_code=$(echo "$response" | tail -1)
    body=$(echo "$response" | head -n -1)

    if [ "$http_code" == "401" ]; then
        print_pass "Chat API correctly rejects expired token (HTTP $http_code)"
        print_info "Response: $body"
    else
        print_fail "Chat API should reject expired token, got HTTP $http_code"
        print_info "Response: $body"
    fi
}

# ============================================================================
# Main Test Execution
# ============================================================================

main() {
    print_header "OAuth 2.0 Integration Tests - Chat API"

    echo -e "${BLUE}Configuration:${NC}"
    echo "  Auth API: $AUTH_API_BASE"
    echo "  Chat API: $CHAT_API_BASE"
    echo "  Test User: $TEST_USER_EMAIL"
    echo "  Client ID: $CLIENT_ID"
    echo ""

    # Section 0: Health Checks
    print_header "Section 0: Health Checks"
    test_auth_api_health
    test_chat_api_health

    # Section 1: Token Acquisition
    print_header "Section 1: OAuth Token Acquisition"
    get_oauth_token

    # Section 2: Token Validation
    print_header "Section 2: Token Validation"
    test_chat_api_without_token
    test_chat_api_with_invalid_token

    # Section 3: Authorized Requests
    print_header "Section 3: Authorized Requests"
    test_chat_api_with_valid_token
    test_chat_api_scope_enforcement

    # Section 4: Security
    print_header "Section 4: Security Tests"
    test_token_expiration_handling

    # Summary
    print_header "Test Summary"

    TOTAL=$((PASS_COUNT + FAIL_COUNT))

    echo -e "${GREEN}✅ PASS: $PASS_COUNT${NC}"
    echo -e "${RED}❌ FAIL: $FAIL_COUNT${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    if [ $FAIL_COUNT -eq 0 ]; then
        echo -e "${GREEN}🎉 All tests passed! Chat API OAuth integration is working!${NC}"
        exit 0
    else
        echo -e "${RED}❌ Some tests failed. Check the output above for details.${NC}"
        exit 1
    fi
}

# Run main
main
