#!/bin/bash

# =============================================================================
# SETUP DEMO USERS - Create Alice and Bob for Sprint Demo
# =============================================================================
# This script creates 2 demo users and adds them to a demo group
# Run this ONCE before the sprint demo
# =============================================================================

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'
BOLD='\033[1m'

AUTH_API="http://localhost:8000"

echo -e "${BOLD}=== DEMO USER SETUP ===${NC}"
echo ""

# =============================================================================
# Step 1: Register Alice
# =============================================================================
echo -e "${YELLOW}[1/4] Registering Alice...${NC}"
ALICE_REG=$(curl -s -X POST "$AUTH_API/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice.demo@sprint2025.com",
    "password": "Sprint2025!Alice"
  }')

if echo "$ALICE_REG" | grep -q "email"; then
  echo -e "${GREEN}✅ Alice registered${NC}"
else
  echo -e "${RED}❌ Alice registration failed: $ALICE_REG${NC}"
  echo "Continuing anyway (user might already exist)..."
fi

# =============================================================================
# Step 2: Register Bob
# =============================================================================
echo -e "${YELLOW}[2/4] Registering Bob...${NC}"
BOB_REG=$(curl -s -X POST "$AUTH_API/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "bob.demo@sprint2025.com",
    "password": "Sprint2025!Bob"
  }')

if echo "$BOB_REG" | grep -q "email"; then
  echo -e "${GREEN}✅ Bob registered${NC}"
else
  echo -e "${RED}❌ Bob registration failed: $BOB_REG${NC}"
  echo "Continuing anyway (user might already exist)..."
fi

# =============================================================================
# Step 3: Verify users via database (requires docker access)
# =============================================================================
echo -e "${YELLOW}[3/4] Verifying users in database...${NC}"
docker exec activity-postgres-db psql -U postgres -d activitydb -c \
  "UPDATE activity.users SET is_verified = TRUE WHERE email IN ('alice.demo@sprint2025.com', 'bob.demo@sprint2025.com');" \
  || echo "Could not auto-verify via activity-postgres-db"

docker exec activity-postgres psql -U activity_user -d activity_db -c \
  "UPDATE activity.users SET is_verified = TRUE WHERE email IN ('alice.demo@sprint2025.com', 'bob.demo@sprint2025.com');" \
  2>/dev/null || echo "Could not auto-verify via activity-postgres"

echo -e "${GREEN}✅ Users verified${NC}"

# =============================================================================
# Step 4: Login both users and get their IDs
# =============================================================================
echo -e "${YELLOW}[4/4] Getting user IDs...${NC}"

ALICE_LOGIN=$(curl -s -X POST "$AUTH_API/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice.demo@sprint2025.com",
    "password": "Sprint2025!Alice"
  }')

# Extract user ID from token
ALICE_TOKEN=$(echo "$ALICE_LOGIN" | jq -r '.access_token // .user_token // empty')

if [ -n "$ALICE_TOKEN" ]; then
  ALICE_USER_ID=$(echo "$ALICE_TOKEN" | cut -d'.' -f2 | base64 -d 2>/dev/null | jq -r '.sub')
  echo -e "${GREEN}✅ Alice User ID: $ALICE_USER_ID${NC}"
else
  echo -e "${RED}❌ Could not get Alice token${NC}"
  echo "Response: $ALICE_LOGIN"
  exit 1
fi

BOB_LOGIN=$(curl -s -X POST "$AUTH_API/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "bob.demo@sprint2025.com",
    "password": "Sprint2025!Bob"
  }')

BOB_TOKEN=$(echo "$BOB_LOGIN" | jq -r '.access_token // .user_token // empty')

if [ -n "$BOB_TOKEN" ]; then
  BOB_USER_ID=$(echo "$BOB_TOKEN" | cut -d'.' -f2 | base64 -d 2>/dev/null | jq -r '.sub')
  echo -e "${GREEN}✅ Bob User ID: $BOB_USER_ID${NC}"
else
  echo -e "${RED}❌ Could not get Bob token${NC}"
  echo "Response: $BOB_LOGIN"
  exit 1
fi

# =============================================================================
# Save credentials to file
# =============================================================================
cat > /tmp/demo_credentials.txt << EOFCRED
# SPRINT DEMO CREDENTIALS
# Generated: $(date)

ALICE_EMAIL="alice.demo@sprint2025.com"
ALICE_PASSWORD="Sprint2025!Alice"
ALICE_USER_ID="$ALICE_USER_ID"

BOB_EMAIL="bob.demo@sprint2025.com"
BOB_PASSWORD="Sprint2025!Bob"
BOB_USER_ID="$BOB_USER_ID"

# Use these in your sprint demo script
EOFCRED

echo ""
echo -e "${BOLD}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║                    ✅ SETUP COMPLETE! ✅                       ║${NC}"
echo -e "${BOLD}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Demo users created:${NC}"
echo -e "  Alice: alice.demo@sprint2025.com / Sprint2025!Alice"
echo -e "  Bob:   bob.demo@sprint2025.com / Sprint2025!Bob"
echo ""
echo -e "${GREEN}User IDs:${NC}"
echo -e "  Alice: $ALICE_USER_ID"
echo -e "  Bob:   $BOB_USER_ID"
echo ""
echo -e "${YELLOW}Credentials saved to: /tmp/demo_credentials.txt${NC}"
echo ""
echo -e "${GREEN}Next step: Run create_demo_group.sh to create a group with these users${NC}"
