"""Pydantic models for auth API request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

# ══════════════════════════════════════════════════════════════════
# Request Models
# ══════════════════════════════════════════════════════════════════


class LoginRequest(BaseModel):
    """Login with username + password."""

    username: str = Field(..., min_length=1, max_length=128, description="Username")
    password: str = Field(..., min_length=1, description="Password")


class RegisterRequest(BaseModel):
    """Register a new user account."""

    username: str = Field(..., min_length=3, max_length=128, pattern=r"^[a-zA-Z0-9_]+$")
    email: EmailStr = Field(..., description="Email address")
    password: str = Field(..., min_length=8, max_length=128, description="Password (min 8 chars)")
    display_name: str | None = Field(default=None, max_length=256)


class TokenRefreshRequest(BaseModel):
    """Refresh an access token."""

    refresh_token: str = Field(..., description="Long-lived refresh token")


class ApiKeyCreateRequest(BaseModel):
    """Create a new API key."""

    name: str = Field(..., min_length=1, max_length=128, description="Human-readable key name")
    expires_in_days: int | None = Field(default=None, ge=1, le=365, description="Validity in days")


# ══════════════════════════════════════════════════════════════════
# Response Models
# ══════════════════════════════════════════════════════════════════


class TokenResponse(BaseModel):
    """JWT token pair response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Seconds until expiry")


class UserResponse(BaseModel):
    """Public user profile (never exposes password_hash)."""

    id: str
    username: str
    email: str
    display_name: str | None = None
    is_active: bool = True
    roles: list[str] = []
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ApiKeyResponse(BaseModel):
    """API key response — raw key is only shown once at creation."""

    id: str
    name: str
    raw_key: str | None = Field(
        None, description="The actual API key (only returned once on creation)"
    )
    prefix: str = Field(..., description="First 8 chars for identification")
    is_active: bool = True
    expires_at: datetime | None = None
    created_at: datetime | None = None


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str
    detail: str | None = None
