#!/bin/bash

# ═══════════════════════════════════════════════════════════════════
# TEST USERPROFILE FULL - COMPREHENSIVE TEST SUITE
# ═══════════════════════════════════════════════════════════════════

# Stop execution immediately if a command exits with a non-zero status
set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Global Variables
API_URL="http://localhost:8008/api/v1"
AUTH_API_URL="http://localhost:8000/api/auth"
DB_CONTAINER="activity-postgres-db"

# Service Keys (must match .env file!)
ACTIVITIES_API_KEY="dev-activities-key"
PAYMENT_API_KEY="dev-payment-key"

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
    exit 1
}

assert_status() {
    local response_code=$1
    local expected_code=$2
    local message=$3

    if [ "$response_code" -eq "$expected_code" ]; then
        log_success "$message (Status: $response_code)"
    else
        log_fail "$message - Expected $expected_code, got $response_code"
    fi
}

# No wrapper needed - will source utils/create_user.sh directly

# ═══════════════════════════════════════════════════════════════════
# MAIN TEST EXECUTION
# ═══════════════════════════════════════════════════════════════════

echo -e "${YELLOW}Starting User Profile API Full Test Suite...${NC}"

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
USER_A_PASSWORD="$USER_PASSWORD"
log_info "✅ User A: $USER_A_EMAIL (ID: $USER_A_ID)"

# User B (Bob)
log_info "Creating User B (Bob)..."
source utils/create_user.sh > /dev/null 2>&1
USER_B_EMAIL="$USER_EMAIL"
USER_B_ID="$USER_ID"
USER_B_TOKEN="$JWT_TOKEN"
USER_B_PASSWORD="$USER_PASSWORD"
log_info "✅ User B: $USER_B_EMAIL (ID: $USER_B_ID)"

# User Admin (Charlie)
log_info "Creating Admin (Charlie)..."
source utils/create_user.sh > /dev/null 2>&1
ADMIN_EMAIL="$USER_EMAIL"
ADMIN_ID="$USER_ID"
ADMIN_TOKEN="$JWT_TOKEN"
ADMIN_PASSWORD="$USER_PASSWORD"
log_info "✅ Admin: $ADMIN_EMAIL (ID: $ADMIN_ID)"

# Make Charlie an Admin
log_info "Promoting $ADMIN_EMAIL to Admin..."
docker exec "$DB_CONTAINER" psql -U postgres -d activitydb -c \
  "UPDATE activity.users SET roles='[\"admin\"]'::jsonb WHERE user_id='$ADMIN_ID';" > /dev/null 2>&1

# Verify Admin Token has admin role (Usually requires re-login to get new claims,
# but our check is DB-backed fallback in security.py, so strictly speaking current token might work
# if the endpoint checks DB. However, let's re-login to be safe if claims are checked first)
log_info "Re-logging in Admin to refresh claims..."
LOGIN_RESPONSE=$(curl -s -X POST "$AUTH_API_URL/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}") # Use exported password

# Update ADMIN_TOKEN with the new token that has updated claims
ADMIN_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token')

log_info "Admin DB role updated. Using refreshed token."

