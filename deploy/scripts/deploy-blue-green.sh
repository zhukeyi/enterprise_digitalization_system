#!/bin/bash
# FDE AI Platform — Blue-Green Deployment Script
# Switches traffic between blue (active) and green (standby) deployments.
#
# Usage:
#   bash deploy/scripts/deploy-blue-green.sh <environment> [blue|green]
#
# Examples:
#   bash deploy/scripts/deploy-blue-green.sh production blue
#   bash deploy/scripts/deploy-blue-green.sh staging green

set -euo pipefail

ENVIRONMENT="${1:-production}"
TARGET="${2:-blue}"
NAMESPACE="fde-${ENVIRONMENT}"
RELEASE="${NAMESPACE}"

echo "=== FDE Blue-Green Deploy: $ENVIRONMENT → $TARGET ==="

# Determine current active slot
CURRENT=$(helm get values "$RELEASE" -n "$NAMESPACE" 2>/dev/null | grep "slot:" | awk '{print $2}' || echo "none")
if [ "$CURRENT" = "none" ]; then
    CURRENT="blue"
    echo "No existing deployment found. First deployment → $CURRENT"
fi

# If target is same as current, deploy to current (in-place update)
if [ "$TARGET" = "$CURRENT" ]; then
    echo "Deploying to active slot: $TARGET"
    SLOT_COLOR="$TARGET"
else
    echo "Deploying to standby slot: $TARGET (current active: $CURRENT)"
    SLOT_COLOR="$TARGET"
fi

# Deploy new version to target slot
echo ""
echo "[1/3] Deploying to $SLOT_COLOR slot..."
helm upgrade --install "${RELEASE}-${SLOT_COLOR}" ./deploy/helm/fde-platform \
    --namespace "$NAMESPACE" --create-namespace \
    --set slot="$SLOT_COLOR" \
    --set backend.image.tag="${IMAGE_TAG:-latest}" \
    --wait --timeout 5m

# Health check
echo ""
echo "[2/3] Health check..."
HEALTH_URL=$(kubectl get svc -n "$NAMESPACE" "${RELEASE}-${SLOT_COLOR}-backend" -o jsonpath='{.spec.clusterIP}' 2>/dev/null || echo "")
if [ -n "$HEALTH_URL" ]; then
    kubectl run health-check-$$ --rm -i --restart=Never --image=curlimages/curl:latest -n "$NAMESPACE" -- \
        curl -sf "http://${HEALTH_URL}:8000/health" || {
        echo "Health check FAILED. Aborting switch."
        exit 1
    }
    echo "Health check PASSED"
fi

# Switch traffic
if [ "$TARGET" != "$CURRENT" ]; then
    echo ""
    echo "[3/3] Switching traffic from $CURRENT → $TARGET..."
    kubectl patch svc "${RELEASE}-backend" -n "$NAMESPACE" \
        -p "{\"spec\":{\"selector\":{\"slot\":\"${TARGET}\"}}}" 2>/dev/null || \
    kubectl patch ingress "${RELEASE}" -n "$NAMESPACE" \
        -p "{\"spec\":{\"rules\":[{\"host\":\"fde.example.com\",\"http\":{\"paths\":[{\"path\":\"/\",\"pathType\":\"Prefix\",\"backend\":{\"service\":{\"name\":\"${RELEASE}-${TARGET}-backend\",\"port\":{\"number\":8000}}}}}]}}]}" 2>/dev/null || true
    echo "Traffic switched to $TARGET"
fi

echo ""
echo "=== Blue-Green Deploy Complete: $ENVIRONMENT is now on $TARGET ==="