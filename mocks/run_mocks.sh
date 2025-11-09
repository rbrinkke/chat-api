#!/bin/bash

# ============================================================================
# Mock Server Management Script
# ============================================================================
# Manages the lifecycle of all mock servers for chat-api development.
#
# Usage:
#   ./run_mocks.sh start    - Start all mock servers
#   ./run_mocks.sh stop     - Stop all mock servers
#   ./run_mocks.sh restart  - Restart all mock servers
#   ./run_mocks.sh status   - Check status of all mock servers
#   ./run_mocks.sh logs     - Show logs from all mock servers
#   ./run_mocks.sh health   - Check health of all mock servers
# ============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# PID file directory
PID_DIR="$SCRIPT_DIR/.pids"
mkdir -p "$PID_DIR"

# Log file directory
LOG_DIR="$SCRIPT_DIR/.logs"
mkdir -p "$LOG_DIR"

# Mock server configurations
# Format: "name:script:port"
MOCK_SERVERS=(
    "auth-api:auth_api_mock.py:8000"
)

# ============================================================================
# Helper Functions
# ============================================================================

print_header() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

# Check if a process is running
is_running() {
    local pid_file="$1"
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0  # Running
        fi
    fi
    return 1  # Not running
}

# ============================================================================
# Start Mock Servers
# ============================================================================

start_server() {
    local name="$1"
    local script="$2"
    local port="$3"
    local pid_file="$PID_DIR/${name}.pid"
    local log_file="$LOG_DIR/${name}.log"

    # Check if already running
    if is_running "$pid_file"; then
        print_warning "$name is already running (PID: $(cat $pid_file))"
        return 0
    fi

    # Check if script exists
    if [ ! -f "$script" ]; then
        print_error "$name: Script not found: $script"
        return 1
    fi

    # Check if port is available
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        print_error "$name: Port $port is already in use"
        return 1
    fi

    # Start the server
    print_info "Starting $name on port $port..."
    nohup python "$script" > "$log_file" 2>&1 &
    local pid=$!
    echo $pid > "$pid_file"

    # Wait a moment and check if it started successfully
    sleep 2
    if is_running "$pid_file"; then
        print_success "$name started successfully (PID: $pid)"
        print_info "  Log file: $log_file"
        print_info "  Health check: http://localhost:$port/health"
        print_info "  API docs: http://localhost:$port/docs"
        return 0
    else
        print_error "$name failed to start. Check logs: $log_file"
        rm -f "$pid_file"
        return 1
    fi
}

start_all() {
    print_header "Starting Mock Servers"

    # Check for Python
    if ! command -v python &> /dev/null; then
        print_error "Python is not installed or not in PATH"
        exit 1
    fi

    # Check for dependencies
    if ! python -c "import fastapi" &> /dev/null; then
        print_warning "FastAPI not installed. Installing dependencies..."
        pip install -r requirements.txt
    fi

    # Check for .env file
    if [ ! -f ".env" ]; then
        print_warning ".env file not found. Creating from .env.example..."
        cp .env.example .env
        print_info "Please review and customize .env if needed"
    fi

    local success=0
    local failed=0

    # Start each server
    for server_config in "${MOCK_SERVERS[@]}"; do
        IFS=':' read -r name script port <<< "$server_config"
        echo ""
        if start_server "$name" "$script" "$port"; then
            ((success++))
        else
            ((failed++))
        fi
    done

    echo ""
    print_header "Summary"
    print_success "Started: $success server(s)"
    if [ $failed -gt 0 ]; then
        print_error "Failed: $failed server(s)"
    fi
    echo ""
}

# ============================================================================
# Stop Mock Servers
# ============================================================================

stop_server() {
    local name="$1"
    local pid_file="$PID_DIR/${name}.pid"

    if ! is_running "$pid_file"; then
        print_warning "$name is not running"
        return 0
    fi

    local pid=$(cat "$pid_file")
    print_info "Stopping $name (PID: $pid)..."

    # Try graceful shutdown first
    kill "$pid" 2>/dev/null || true
    sleep 1

    # Force kill if still running
    if ps -p "$pid" > /dev/null 2>&1; then
        print_warning "Forcing shutdown of $name..."
        kill -9 "$pid" 2>/dev/null || true
    fi

    # Remove PID file
    rm -f "$pid_file"

    if ! ps -p "$pid" > /dev/null 2>&1; then
        print_success "$name stopped"
        return 0
    else
        print_error "Failed to stop $name"
        return 1
    fi
}

stop_all() {
    print_header "Stopping Mock Servers"

    local success=0
    local failed=0

    for server_config in "${MOCK_SERVERS[@]}"; do
        IFS=':' read -r name script port <<< "$server_config"
        echo ""
        if stop_server "$name"; then
            ((success++))
        else
            ((failed++))
        fi
    done

    echo ""
    print_header "Summary"
    print_success "Stopped: $success server(s)"
    if [ $failed -gt 0 ]; then
        print_error "Failed: $failed server(s)"
    fi
    echo ""
}

# ============================================================================
# Check Status
# ============================================================================

status_server() {
    local name="$1"
    local port="$2"
    local pid_file="$PID_DIR/${name}.pid"

    if is_running "$pid_file"; then
        local pid=$(cat "$pid_file")
        print_success "$name is running (PID: $pid, Port: $port)"
        return 0
    else
        print_error "$name is not running"
        return 1
    fi
}

check_status() {
    print_header "Mock Server Status"

    local running=0
    local stopped=0

    for server_config in "${MOCK_SERVERS[@]}"; do
        IFS=':' read -r name script port <<< "$server_config"
        echo ""
        if status_server "$name" "$port"; then
            ((running++))
        else
            ((stopped++))
        fi
    done

    echo ""
    print_header "Summary"
    echo -e "Running: ${GREEN}$running${NC}"
    echo -e "Stopped: ${RED}$stopped${NC}"
    echo ""
}

# ============================================================================
# Check Health
# ============================================================================

health_check() {
    print_header "Health Check"

    for server_config in "${MOCK_SERVERS[@]}"; do
        IFS=':' read -r name script port <<< "$server_config"
        echo ""
        print_info "Checking $name..."

        # Check if running
        local pid_file="$PID_DIR/${name}.pid"
        if ! is_running "$pid_file"; then
            print_error "$name is not running"
            continue
        fi

        # Check health endpoint
        if command -v curl &> /dev/null; then
            local health_url="http://localhost:$port/health"
            if curl -s -f "$health_url" > /dev/null 2>&1; then
                local response=$(curl -s "$health_url")
                print_success "$name is healthy"
                echo -e "  ${BLUE}Response:${NC} $response"
            else
                print_error "$name health check failed"
            fi
        else
            print_warning "curl not available, skipping health check"
        fi
    done
    echo ""
}

# ============================================================================
# Show Logs
# ============================================================================

show_logs() {
    print_header "Mock Server Logs"

    for server_config in "${MOCK_SERVERS[@]}"; do
        IFS=':' read -r name script port <<< "$server_config"
        local log_file="$LOG_DIR/${name}.log"

        echo ""
        print_info "Logs for $name:"
        echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

        if [ -f "$log_file" ]; then
            tail -n 50 "$log_file"
        else
            print_warning "Log file not found: $log_file"
        fi

        echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    done
    echo ""
}

# ============================================================================
# Restart Servers
# ============================================================================

restart_all() {
    print_header "Restarting Mock Servers"
    stop_all
    sleep 2
    start_all
}

# ============================================================================
# Main Script
# ============================================================================

case "${1:-}" in
    start)
        start_all
        ;;
    stop)
        stop_all
        ;;
    restart)
        restart_all
        ;;
    status)
        check_status
        ;;
    health)
        health_check
        ;;
    logs)
        show_logs
        ;;
    *)
        echo "Mock Server Management Script"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|health|logs}"
        echo ""
        echo "Commands:"
        echo "  start    - Start all mock servers"
        echo "  stop     - Stop all mock servers"
        echo "  restart  - Restart all mock servers"
        echo "  status   - Check status of all mock servers"
        echo "  health   - Check health endpoints of running servers"
        echo "  logs     - Show recent logs from all servers"
        echo ""
        exit 1
        ;;
esac

exit 0
