#!/bin/bash
#
# Customer Support Agent Demo - Setup & Teardown Script
#
# Usage:
#   ./demo.sh start     Start all services (database, server, UI)
#   ./demo.sh stop      Stop all services
#   ./demo.sh reset     Reset database and stop services
#   ./demo.sh status    Check status of services
#
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
SERVER_DIR="$ROOT_DIR/server"
UI_DIR="$ROOT_DIR/ui"

# PID files for tracking background processes
SERVER_PID_FILE="/tmp/agent-control-server.pid"
UI_PID_FILE="/tmp/agent-control-ui.pid"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}==>${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}Warning:${NC} $1"
}

print_error() {
    echo -e "${RED}Error:${NC} $1"
}

check_dependencies() {
    local missing=()

    if ! command -v docker &> /dev/null; then
        missing+=("docker")
    fi

    if ! command -v python &> /dev/null; then
        missing+=("python")
    fi

    if ! command -v pnpm &> /dev/null; then
        missing+=("pnpm")
    fi

    if [ ${#missing[@]} -ne 0 ]; then
        print_error "Missing dependencies: ${missing[*]}"
        exit 1
    fi
}

start_database() {
    print_status "Starting database..."
    cd "$SERVER_DIR"
    docker compose up -d

    # Wait for database to be ready
    print_status "Waiting for database to be ready..."
    for i in {1..30}; do
        if docker compose exec -T postgres pg_isready -U agent_control -d agent_control &> /dev/null; then
            print_status "Database is ready"
            return 0
        fi
        sleep 1
    done
    print_error "Database failed to start"
    exit 1
}

stop_database() {
    print_status "Stopping database..."
    cd "$SERVER_DIR"
    docker compose down
}

run_migrations() {
    print_status "Running database migrations..."
    cd "$SERVER_DIR"
    make alembic-upgrade
}

start_server() {
    print_status "Starting server..."
    cd "$SERVER_DIR"

    # Check if server is already running
    if [ -f "$SERVER_PID_FILE" ] && kill -0 "$(cat "$SERVER_PID_FILE")" 2>/dev/null; then
        print_warning "Server is already running (PID: $(cat "$SERVER_PID_FILE"))"
        return 0
    fi

    # Start server in background
    uv run --package agent-control-server uvicorn agent_control_server.main:app --reload &> /tmp/agent-control-server.log &
    echo $! > "$SERVER_PID_FILE"

    # Wait for server to be ready
    print_status "Waiting for server to be ready..."
    for i in {1..30}; do
        if curl -s http://localhost:8000/health &> /dev/null; then
            print_status "Server is ready at http://localhost:8000"
            return 0
        fi
        sleep 1
    done
    print_error "Server failed to start. Check /tmp/agent-control-server.log"
    exit 1
}

stop_server() {
    print_status "Stopping server..."
    if [ -f "$SERVER_PID_FILE" ]; then
        local pid=$(cat "$SERVER_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            # Also kill any child processes (uvicorn workers)
            pkill -P "$pid" 2>/dev/null || true
        fi
        rm -f "$SERVER_PID_FILE"
    fi
    # Kill any remaining uvicorn processes for this project
    pkill -f "uvicorn agent_control_server.main:app" 2>/dev/null || true
}

start_ui() {
    print_status "Starting UI..."
    cd "$UI_DIR"

    # Check if UI is already running
    if [ -f "$UI_PID_FILE" ] && kill -0 "$(cat "$UI_PID_FILE")" 2>/dev/null; then
        print_warning "UI is already running (PID: $(cat "$UI_PID_FILE"))"
        return 0
    fi

    # Install dependencies if needed
    if [ ! -d "node_modules" ]; then
        print_status "Installing UI dependencies..."
        pnpm install
    fi

    # Start UI in background
    pnpm dev &> /tmp/agent-control-ui.log &
    echo $! > "$UI_PID_FILE"

    # Wait for UI to be ready
    print_status "Waiting for UI to be ready..."
    for i in {1..30}; do
        if curl -s http://localhost:4000 &> /dev/null; then
            print_status "UI is ready at http://localhost:4000"
            return 0
        fi
        sleep 1
    done
    print_warning "UI may still be starting. Check /tmp/agent-control-ui.log"
}

stop_ui() {
    print_status "Stopping UI..."
    if [ -f "$UI_PID_FILE" ]; then
        local pid=$(cat "$UI_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            pkill -P "$pid" 2>/dev/null || true
        fi
        rm -f "$UI_PID_FILE"
    fi
    # Kill any remaining next.js processes for this project
    pkill -f "next dev.*4000" 2>/dev/null || true
}

reset_database() {
    print_status "Resetting database..."
    cd "$SERVER_DIR"

    # Stop the container and remove the volume
    docker compose down -v

    print_status "Database volume deleted"
}

show_status() {
    echo ""
    echo "Service Status:"
    echo "---------------"

    # Database
    cd "$SERVER_DIR"
    if docker compose ps 2>/dev/null | grep -q "postgres.*running"; then
        echo -e "Database:  ${GREEN}Running${NC}"
    else
        echo -e "Database:  ${RED}Stopped${NC}"
    fi

    # Server
