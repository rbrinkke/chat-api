#!/bin/bash
# Rebuild script for chat-api
# Steps:
# 1. Stop all containers
# 2. Remove chat-api images (NOT volumes!)
# 3. Rebuild and start
# 4. Show running containers

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Chat-API Rebuild Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Step 1: Stop all containers
echo -e "${YELLOW}Step 1: Stopping all containers...${NC}"
docker compose down
echo -e "${GREEN}✅ Containers stopped${NC}"
echo ""

# Step 2: Remove chat-api images (NOT volumes!)
echo -e "${YELLOW}Step 2: Removing chat-api images...${NC}"
# Get image names for this project
IMAGE_NAMES=$(docker images --format "{{.Repository}}:{{.Tag}}" | grep "chat-api" || true)

if [ -n "$IMAGE_NAMES" ]; then
    echo "Found images to remove:"
    echo "$IMAGE_NAMES"
    echo ""

    # Remove each image
    for img in $IMAGE_NAMES; do
        echo "Removing $img..."
        docker rmi "$img" 2>/dev/null || echo "  (already removed)"
    done
    echo -e "${GREEN}✅ Images removed${NC}"
else
    echo "No chat-api images found to remove"
    echo -e "${GREEN}✅ No images to remove${NC}"
fi
echo ""

# Step 3: Rebuild and start
echo -e "${YELLOW}Step 3: Building and starting services...${NC}"
echo "This may take a few minutes..."
echo ""
docker compose build --no-cache chat-api
echo ""
docker compose up -d
echo ""
echo -e "${GREEN}✅ Services started${NC}"
echo ""

# Wait a moment for containers to stabilize
echo "Waiting 3 seconds for containers to stabilize..."
sleep 3
echo ""

# Step 4: Show running containers
echo -e "${YELLOW}Step 4: Running containers:${NC}"
echo ""
docker compose ps
echo ""

# Show chat-api logs (last 10 lines)
echo -e "${YELLOW}Chat-API Logs (last 10 lines):${NC}"
echo ""
docker compose logs --tail 10 chat-api
echo ""

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✅ Rebuild complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "Useful commands:"
echo "  docker compose logs -f chat-api    # Follow logs"
echo "  docker compose ps                  # Check status"
echo "  curl http://localhost:8001/health  # Test API"
echo "  open http://localhost:8001/dashboard  # View dashboard"
echo ""
