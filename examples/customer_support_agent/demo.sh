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
