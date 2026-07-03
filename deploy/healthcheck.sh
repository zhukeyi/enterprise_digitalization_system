#!/bin/bash
# FDE AI Platform — Health Check Script
# Validates all services are running and healthy.
# Usage: bash deploy/healthcheck.sh

set -euo pipefail

RESULT=0
check() {
    local name="$1" url="$2"
    if curl -sf -o /dev/null --max-time 5 "$url"; then
        echo "  OK   $name"
    else
        echo "  FAIL $name -> $url"
        RESULT=1
    fi
}

echo "=== FDE Health Check $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo ""

echo "[Backend]"
check "FDE API"      "http://localhost:8000/health"
check "FDE API (nginx)" "http://localhost:80/health"

echo ""
echo "[Database]"
check "PostgreSQL"    "http://localhost:8000/health/db" 2>/dev/null || echo "  WARN PostgreSQL (check via backend logs)"

echo ""
echo "[Services]"
check "Qdrant"       "http://localhost:6333/health"
check "MinIO"        "http://localhost:9000/minio/health/live"

echo ""
echo "[Observability]"
check "Prometheus"   "http://localhost:9090/-/healthy" 2>/dev/null || echo "  SKIP Prometheus (not deployed)"
check "Grafana"      "http://localhost:3000/api/health" 2>/dev/null || echo "  SKIP Grafana (not deployed)"

echo ""
if [ $RESULT -eq 0 ]; then
    echo "=== All checks passed ==="
else
    echo "=== Some checks FAILED ==="
fi

exit $RESULT