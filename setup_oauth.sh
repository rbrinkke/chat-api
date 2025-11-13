#!/bin/bash

################################################################################
# OAuth 2.0 Setup Automation - Chat API
#
# Automates the complete OAuth setup process:
# 1. Validates Auth API is running
# 2. Fetches JWT_SECRET_KEY from Auth API
# 3. Updates Chat API .env configuration
# 4. Rebuilds Chat API container
# 5. Runs integration tests
# 6. Reports success/failure
#
# This script is IDEMPOTENT - safe to run multiple times.
#
# Usage:
#   ./setup_oauth.sh                # Full setup + tests
#   ./setup_oauth.sh --skip-tests   # Setup only, skip tests
#   ./setup_oauth.sh --force        # Force rebuild even if already configured
################################################################################

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
AUTH_API_CONTAINER="auth-api"
CHAT_API_CONTAINER="chat-api"
AUTH_API_URL="http://localhost:8000"
ENV_FILE=".env"

# Flags
SKIP_TESTS=false
FORCE_SETUP=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        --force)
            FORCE_SETUP=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --skip-tests    Setup only, skip integration tests"
            echo "  --force         Force rebuild even if already configured"
            echo "  --help          Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Run with --help for usage information"
            exit 1
            ;;
    esac
done

# ============================================================================
# Helper Functions
# ============================================================================

print_header() {
    echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

print_step() {
    echo -e "${BLUE}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ️  $1${NC}"
}

# ============================================================================
# Validation Functions
# ============================================================================

check_auth_api() {
    print_step "Checking Auth API availability..."

    if ! docker ps | grep -q "$AUTH_API_CONTAINER"; then
        print_error "Auth API container is not running"
        print_info "Start Auth API with: cd ../auth-api && docker compose up -d"
        exit 1
    fi

    print_success "Auth API container is running"

    # Check if Auth API is responding
    if curl -s -f "$AUTH_API_URL/health" > /dev/null 2>&1; then
        print_success "Auth API is healthy and responding"
    else
        print_error "Auth API is running but not responding at $AUTH_API_URL/health"
        print_info "Check Auth API logs: docker compose -f ../auth-api/docker-compose.yml logs auth-api"
        exit 1
    fi
}

fetch_jwt_secret() {
    print_step "Fetching JWT_SECRET_KEY from Auth API..."

    JWT_SECRET=$(docker exec "$AUTH_API_CONTAINER" env | grep "^JWT_SECRET_KEY=" | cut -d'=' -f2-)

    if [ -z "$JWT_SECRET" ]; then
        print_error "Failed to fetch JWT_SECRET_KEY from Auth API"
        print_info "Verify Auth API has JWT_SECRET_KEY configured"
        exit 1
    fi

    print_success "JWT_SECRET_KEY fetched successfully"
    print_info "Secret: ${JWT_SECRET:0:20}... (${#JWT_SECRET} chars)"

    # Validate secret length
    if [ ${#JWT_SECRET} -lt 32 ]; then
        print_warning "JWT_SECRET_KEY is shorter than 32 characters (not recommended for production)"
    fi
}

check_current_config() {
    print_step "Checking current Chat API configuration..."

    if [ ! -f "$ENV_FILE" ]; then
        print_error ".env file not found in current directory"
        exit 1
    fi

    if grep -q "^JWT_SECRET_KEY=" "$ENV_FILE"; then
        CURRENT_SECRET=$(grep "^JWT_SECRET_KEY=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')

        if [ "$CURRENT_SECRET" = "$JWT_SECRET" ]; then
            print_success "JWT_SECRET_KEY already configured correctly"
            if [ "$FORCE_SETUP" = false ]; then
                print_info "Use --force to rebuild anyway"
                return 0
            else
                print_info "Force rebuild requested"
                return 1
            fi
        else
            print_warning "JWT_SECRET_KEY exists but doesn't match Auth API"
            print_info "Current: ${CURRENT_SECRET:0:20}..."
            print_info "Auth API: ${JWT_SECRET:0:20}..."
            return 1
        fi
    else
        print_warning "JWT_SECRET_KEY not found in .env"
        return 1
    fi
}

# ============================================================================
# Configuration Functions
# ============================================================================

update_env_file() {
    print_step "Updating .env configuration..."

    # Backup original .env
    cp "$ENV_FILE" "${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    print_info "Backup created: ${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"

    # Update or add JWT_SECRET_KEY
    if grep -q "^JWT_SECRET_KEY=" "$ENV_FILE"; then
        # Update existing
        sed -i "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=\"$JWT_SECRET\"|" "$ENV_FILE"
        print_success "Updated JWT_SECRET_KEY in .env"
    else
        # Add new
        echo "" >> "$ENV_FILE"
        echo "# OAuth 2.0 JWT Validation (auto-configured)" >> "$ENV_FILE"
        echo "JWT_SECRET_KEY=\"$JWT_SECRET\"" >> "$ENV_FILE"
        print_success "Added JWT_SECRET_KEY to .env"
    fi

    # Ensure JWT_ALGORITHM is set to HS256
    if grep -q "^JWT_ALGORITHM=" "$ENV_FILE"; then
        sed -i 's|^JWT_ALGORITHM=.*|JWT_ALGORITHM="HS256"|' "$ENV_FILE"
    else
        echo "JWT_ALGORITHM=\"HS256\"" >> "$ENV_FILE"
    fi

    print_success "Configuration updated successfully"
}

rebuild_container() {
    print_step "Rebuilding Chat API container..."

    if ! docker compose build chat-api 2>&1 | grep -q "Successfully"; then
        # Build failed, but let's check if it's because no docker-compose.yml exists
        if [ ! -f "docker-compose.yml" ]; then
            print_warning "No docker-compose.yml found - skipping container rebuild"
            print_info "You'll need to restart Chat API manually to pick up .env changes"
            return 0
        fi

        print_error "Failed to rebuild Chat API container"
        exit 1
    fi

    print_success "Container rebuilt successfully"

    print_step "Restarting Chat API..."
    docker compose restart chat-api > /dev/null 2>&1 || {
        print_warning "Failed to restart via docker compose"
        print_info "If Chat API is running differently, restart it manually"
        return 0
    }

    # Wait for Chat API to be ready
    print_step "Waiting for Chat API to be ready..."
    sleep 3

    print_success "Chat API restarted"
}

# ============================================================================
# Testing Functions
# ============================================================================

run_integration_tests() {
    print_step "Running OAuth integration tests..."

    if [ ! -f "test_chat_oauth_integration.sh" ]; then
        print_warning "Integration test script not found"
        print_info "Create test_chat_oauth_integration.sh to enable automated testing"
        return 0
    fi

    if ! chmod +x test_chat_oauth_integration.sh; then
        print_warning "Failed to make test script executable"
        return 0
    fi

    if ./test_chat_oauth_integration.sh; then
        print_success "All integration tests passed!"
        return 0
    else
        print_error "Some integration tests failed"
        print_info "Run './test_chat_oauth_integration.sh --verbose' for details"
        return 1
    fi
}

# ============================================================================
# Main Execution
# ============================================================================

main() {
    print_header "OAuth 2.0 Setup Automation - Chat API"

    echo -e "${CYAN}This script will:${NC}"
    echo "  1. Validate Auth API is running"
    echo "  2. Fetch JWT_SECRET_KEY from Auth API"
    echo "  3. Update Chat API .env configuration"
    echo "  4. Rebuild Chat API container"
    if [ "$SKIP_TESTS" = false ]; then
        echo "  5. Run integration tests"
    fi
    echo ""

    # Step 1: Check Auth API
    print_header "Step 1: Validate Auth API"
    check_auth_api

    # Step 2: Fetch JWT secret
    print_header "Step 2: Fetch JWT Configuration"
    fetch_jwt_secret

    # Step 3: Check current config
    print_header "Step 3: Check Current Configuration"
    if check_current_config; then
        if [ "$FORCE_SETUP" = false ]; then
            print_header "Setup Complete"
            print_success "Chat API OAuth is already configured correctly!"
            print_info "No changes needed. Use --force to rebuild anyway."

            if [ "$SKIP_TESTS" = false ]; then
                print_header "Step 4: Run Integration Tests"
                run_integration_tests || exit 1
            fi

            exit 0
        fi
    fi

    # Step 4: Update configuration
    print_header "Step 4: Update Configuration"
    update_env_file

    # Step 5: Rebuild container
    print_header "Step 5: Rebuild Container"
    rebuild_container

    # Step 6: Run tests (unless skipped)
    if [ "$SKIP_TESTS" = false ]; then
        print_header "Step 6: Run Integration Tests"
        run_integration_tests || {
            print_warning "Tests failed but setup is complete"
            print_info "You can fix issues and run tests manually: ./test_chat_oauth_integration.sh"
        }
    fi

    # Success summary
    print_header "🎉 Setup Complete!"

    echo -e "${GREEN}✅ OAuth 2.0 is now configured and ready to use!${NC}"
    echo ""
    echo -e "${CYAN}Next steps:${NC}"
    echo "  1. Integrate oauth_validator.py into your endpoints"
    echo "  2. Test with example endpoints: /api/oauth/examples/*"
    echo "  3. Read OAUTH_IMPLEMENTATION_STATUS.md for complete guide"
    echo ""
    echo -e "${CYAN}Test OAuth integration:${NC}"
    echo "  ./test_chat_oauth_integration.sh --verbose"
    echo ""
    echo -e "${CYAN}View example endpoints:${NC}"
    echo "  curl http://localhost:8001/api/oauth/examples/public"
    echo "  curl http://localhost:8001/api/oauth/examples/protected -H \"Authorization: Bearer \$TOKEN\""
    echo ""

    print_success "Setup automation completed successfully! 🚀"
}

# Run main
main
