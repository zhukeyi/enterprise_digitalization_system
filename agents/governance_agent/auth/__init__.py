"""Governance Agent — authentication and authorization."""

from agents.governance_agent.auth.dependencies import (
    get_current_active_user,
    get_current_user,
)
from agents.governance_agent.auth.models import (
    ApiKeyCreateRequest,
    ApiKeyResponse,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    TokenRefreshRequest,
    TokenResponse,
    UserResponse,
)
from agents.governance_agent.auth.router import router as auth_router
from agents.governance_agent.auth.security import (
    create_access_token,
    create_api_key,
    hash_api_key,
    hash_password,
    verify_api_key,
    verify_password,
)

__all__ = [
    "ApiKeyCreateRequest",
    "ApiKeyResponse",
    "LoginRequest",
    "MessageResponse",
    "RegisterRequest",
    "TokenRefreshRequest",
    "TokenResponse",
    "UserResponse",
    "auth_router",
    "create_access_token",
    "create_api_key",
    "get_current_active_user",
    "get_current_user",
    "hash_api_key",
    "hash_password",
    "verify_api_key",
    "verify_password",
]
