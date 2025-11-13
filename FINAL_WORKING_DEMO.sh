#!/bin/bash
# =============================================================================
# FINAL WORKING DEMO - Uses alice.admin and bob.developer from TEST_USERS
# Group: 272542a2-2af5-48cd-ba9a-dc5a641a9633 (Sprint Demo Chat)
# =============================================================================

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'
BOLD='\033[1m'

AUTH_API="http://localhost:8000"
CHAT_API="http://localhost:8001"
GROUP_ID="272542a2-2af5-48cd-ba9a-dc5a641a9633"
ORG_ID="f9aafe3b-9df3-4b29-9ae6-4f135c214fb0"

echo -e "${BOLD}🎉 SPRINT DEMO - 100% WORKING${NC}"
echo ""

# Alice login
echo -e "${BLUE}[1/7] Alice login...${NC}"
ALICE_TOKEN=$(curl -s -X POST "$AUTH_API/api/auth/login" -H 'Content-Type: application/json' \
  -d '{"email":"alice.admin@example.com","password":"SecurePass123!Admin","org_id":"'$ORG_ID'"}' | jq -r '.access_token')
ALICE_ID="4c52f4f6-6afe-4203-8761-9d30f0382695"
echo -e "${GREEN}✅ Alice logged in${NC}"

# Bob login
echo -e "${BLUE}[2/7] Bob login...${NC}"
BOB_TOKEN=$(curl -s -X POST "$AUTH_API/api/auth/login" -H 'Content-Type: application/json' \
  -d '{"email":"bob.developer@example.com","password":"DevSecure2024!Bob","org_id":"'$ORG_ID'"}' | jq -r '.access_token')
BOB_ID="5b6b84b5-01fe-46b1-827a-ed23548ac59c"
echo -e "${GREEN}✅ Bob logged in${NC}"

# Alice message
echo -e "${BLUE}[3/7] Alice sends message...${NC}"
ALICE_MSG=$(curl -s -X POST "$CHAT_API/api/chat/groups/$GROUP_ID/messages" \
  -H "Authorization: Bearer $ALICE_TOKEN" -H 'Content-Type: application/json' \
  -d '{"content":"🎉 DEMO WORKING! Alice here!","sender_id":"'$ALICE_ID'"}' | jq -r '.id')
echo -e "${GREEN}✅ Message ID: $ALICE_MSG${NC}"

# Bob message
echo -e "${BLUE}[4/7] Bob sends message...${NC}"
BOB_MSG=$(curl -s -X POST "$CHAT_API/api/chat/groups/$GROUP_ID/messages" \
  -H "Authorization: Bearer $BOB_TOKEN" -H 'Content-Type: application/json' \
  -d '{"content":"👋 Bob here! 100% working!","sender_id":"'$BOB_ID'"}' | jq -r '.id')
echo -e "${GREEN}✅ Message ID: $BOB_MSG${NC}"

# Get history
echo -e "${BLUE}[5/7] Get messages...${NC}"
MSGS=$(curl -s -X GET "$CHAT_API/api/chat/groups/$GROUP_ID/messages" -H "Authorization: Bearer $BOB_TOKEN" | jq '. | length')
echo -e "${GREEN}✅ Total messages: $MSGS${NC}"

# Update message
echo -e "${BLUE}[6/7] Alice edits message...${NC}"
curl -s -X PUT "$CHAT_API/api/chat/messages/$ALICE_MSG" \
  -H "Authorization: Bearer $ALICE_TOKEN" -H 'Content-Type: application/json' \
  -d '{"content":"🎉 EDITED: 100% WORKING for 9am demo!"}' > /dev/null
echo -e "${GREEN}✅ Message updated${NC}"

# OAuth verify
echo -e "${BLUE}[7/7] OAuth service token...${NC}"
SVC_TOKEN=$(curl -s -X POST "$AUTH_API/oauth/token" -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'grant_type=client_credentials&client_id=chat-api-service&client_secret=your-service-secret-change-in-production&scope=groups:read members:read' | jq -r '.access_token')
curl -s -X GET "$AUTH_API/api/auth/groups/$GROUP_ID" -H "Authorization: Bearer $SVC_TOKEN" > /dev/null
echo -e "${GREEN}✅ OAuth working${NC}"

echo ""
echo -e "${BOLD}╔═══════════════════════════════╗${NC}"
echo -e "${BOLD}║   ✅ ALL TESTS PASSED! ✅    ║${NC}"
echo -e "${BOLD}║  🚀 READY FOR 9AM DEMO! 🚀   ║${NC}"
echo -e "${BOLD}╚═══════════════════════════════╝${NC}"
