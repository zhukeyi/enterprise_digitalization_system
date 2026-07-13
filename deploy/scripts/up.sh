#!/usr/bin/env bash
# ===================================================================
# FDE AI Platform — One-click production up (P0-B)
# ===================================================================
# Brings up the full stack defined in docker-compose.prod.yml, which now
# includes the LiteLLM gateway (P0-A) wired into fde-backend via
# LITELLM_PROXY_URL (gray rollout).
#
# Usage:
#   export FDE_ENV=production
#   ./deploy/scripts/up.sh
#
# Pre-req: copy and fill the env template first:
#   cp deploy/config-templates/.env.prod.example deploy/.env.prod
#   ${EDITOR} deploy/.env.prod   # set POSTGRES_*, JWT_*, LITELLM_*, provider keys
# ===================================================================
set -euo pipefail

cd "$(dirname "$0")/../.."   # repo root

if [ ! -f deploy/.env.prod ]; then
  echo "ERROR: deploy/.env.prod not found. Copy the template and fill it:" >&2
  echo "  cp deploy/config-templates/.env.prod.example deploy/.env.prod" >&2
  exit 1
fi

echo "==> Validating compose configuration"
docker compose --env-file deploy/.env.prod -f deploy/docker-compose.prod.yml config >/dev/null

echo "==> Pulling images"
docker compose --env-file deploy/.env.prod -f deploy/docker-compose.prod.yml pull

echo "==> Starting stack (LiteLLM + Postgres + FDE backend + Qdrant + nginx + observability)"
docker compose --env-file deploy/.env.prod -f deploy/docker-compose.prod.yml up -d

echo "==> Waiting for fde-backend health"
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    echo "fde-backend healthy."
    break
  fi
  sleep 2
done

echo "==> Verifying LiteLLM gateway registered in /v1/models"
curl -s http://localhost:8000/v1/models | grep -o '"id":"fde-default"' && \
  echo "OK: LiteLLM model aliases exposed by the gateway."

echo "==> Done. Portals: https://<host>:8443/{portal,hr,pricing,marketing,intel,hub,obs}"
