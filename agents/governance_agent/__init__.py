"""Governance Agent — Identity, Authorization & Observability.

Responsibilities (per v2.0 plan):
- M2-T1: Unified identity authentication (OAuth2/OIDC, AD/LDAP)  ← CURRENT
- M2-T2: Fine-grained permission engine (RBAC + ABAC)             ← CURRENT
- M4-T1: Full-link tracing (OpenTelemetry)
- M4-T2: Audit log center
- M4-T3: Cost control module
"""

from agents.governance_agent.auth import (
    auth_router,
    create_access_token,
    create_api_key,
    get_current_active_user,
    get_current_user,
    hash_password,
    verify_password,
)
from agents.governance_agent.middleware import AuthMiddleware, create_auth_middleware

__all__ = [
    "AuthMiddleware",
    "auth_router",
    "create_access_token",
    "create_api_key",
    "create_auth_middleware",
    "get_current_active_user",
    "get_current_user",
    "hash_password",
    "verify_password",
]
