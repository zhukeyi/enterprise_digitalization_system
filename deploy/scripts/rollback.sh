#!/bin/bash
# FDE AI Platform — Rollback Script
# Usage: bash deploy/scripts/rollback.sh <environment>

set -euo pipefail

ENVIRONMENT="${1:-production}"
NAMESPACE="fde-${ENVIRONMENT}"
RELEASE="${NAMESPACE}"

echo "=== FDE Rollback: $ENVIRONMENT ==="

# Helm rollback to previous revision
echo "Rolling back Helm release..."
helm rollback "$RELEASE" -n "$NAMESPACE"

echo "Rollback complete. Checking health..."
kubectl rollout status deployment -n "$NAMESPACE" --timeout=2m

echo "=== Rollback Complete ==="