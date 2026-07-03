#!/bin/bash
# FDE AI Platform — Database Migration Script
# Usage: bash deploy/scripts/migrate.sh [up|down|status]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
ACTION="${1:-up}"

echo "=== FDE Database Migration: $ACTION ==="

# Check DATABASE_URL
DB_URL="${DATABASE_URL:-}"
if [ -z "$DB_URL" ]; then
    echo "ERROR: DATABASE_URL environment variable not set"
    echo "  export DATABASE_URL=postgresql://user:pass@host:5432/fde_platform"
    exit 1
fi

# Run Alembic migrations
cd "$PROJECT_DIR"

case "$ACTION" in
    up)
        echo "Running migrations UP..."
        alembic upgrade head
        ;;
    down)
        echo "Running migrations DOWN..."
        alembic downgrade -1
        ;;
    status)
        echo "Migration status:"
        alembic current
        ;;
    *)
        echo "Usage: $0 [up|down|status]"
        exit 1
        ;;
esac

echo "=== Migration $ACTION complete ==="