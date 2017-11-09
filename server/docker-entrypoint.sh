#!/bin/bash
set -e

echo "==================================="
echo "Agent Control Server - Starting"
echo "==================================="

# Run database migrations
echo "Running database migrations..."
if [ -f "/app/alembic.ini" ]; then
    alembic upgrade head
