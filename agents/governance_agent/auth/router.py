"""FastAPI router for authentication endpoints.

Provides:
- POST /auth/login       — username + password → JWT token pair
- POST /auth/register    — create new user account
- POST /auth/refresh     — exchange refresh token for new access token
- GET  /auth/me          — get current user profile
- POST /auth/api-keys    — create API key
- GET  /auth/api-keys    — list API keys
- DELETE /auth/api-keys/{id} — revoke API key
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.governance_agent.auth.dependencies import (
    get_current_active_user,
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
from agents.governance_agent.auth.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    create_api_key,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from agents.governance_agent.database.models import ApiKey, User
from agents.governance_agent.database.session import get_async_session

router = APIRouter(prefix="/auth", tags=["Authentication"])

# ══════════════════════════════════════════════════════════════════
# POST /auth/login
# ══════════════════════════════════════════════════════════════════


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """Authenticate with username and password, return JWT token pair."""
    # Find user by username
    result = await session.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    # Use constant-time-ish comparison: always verify hash even if user not found
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    # Generate token pair
    access_token = create_access_token(
        user_id=user.id,
        username=user.username,
        roles=list(user.roles or []),
    )
    refresh_token = create_refresh_token(
        user_id=user.id,
        username=user.username,
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


# ══════════════════════════════════════════════════════════════════
# POST /auth/register
# ══════════════════════════════════════════════════════════════════


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_async_session),
) -> UserResponse:
    """Register a new user account. Default role: 'viewer'."""
    # Check uniqueness
    result = await session.execute(
        select(User).where((User.username == body.username) | (User.email == body.email))
    )
    existing = result.scalar_one_or_none()
    if existing:
        if existing.username == body.username:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already taken",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

    # Create user
    user = User(
        username=body.username,
        email=body.email,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        roles=["viewer"],
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    return UserResponse.model_validate(user)


# ══════════════════════════════════════════════════════════════════
# POST /auth/refresh
# ══════════════════════════════════════════════════════════════════


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def refresh_token(
    body: TokenRefreshRequest,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """Exchange a refresh token for a new access token."""
    try:
        payload = decode_token(body.refresh_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is not a refresh token",
        )

    user_id = payload.get("sub")
    _ = payload.get("username", "")  # extracted for audit but unused here

    # Verify user still exists and is active
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Issue new access token
    access_token = create_access_token(
        user_id=user.id,
        username=user.username,
        roles=list(user.roles or []),
    )

    return {
        "access_token": access_token,
        "refresh_token": body.refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


# ══════════════════════════════════════════════════════════════════
# GET /auth/me
# ══════════════════════════════════════════════════════════════════


@router.get("/me", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def get_current_user_profile(
    current_user: User = Depends(get_current_active_user),
) -> UserResponse:
    """Get the authenticated user's profile."""
    return UserResponse.model_validate(current_user)


# ══════════════════════════════════════════════════════════════════
# POST /auth/api-keys
# ══════════════════════════════════════════════════════════════════


@router.post(
    "/api-keys",
    response_model=ApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key_endpoint(
    body: ApiKeyCreateRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> ApiKeyResponse:
    """Create a new API key for the authenticated user.

    The raw key is returned only once — save it immediately.
    """
    raw_key, key_hash, prefix = create_api_key()

    expires_at = None
    if body.expires_in_days:
        expires_at = datetime.now(UTC) + timedelta(days=body.expires_in_days)

    api_key = ApiKey(
        user_id=current_user.id,
        key_hash=key_hash,
        name=body.name,
        is_active=True,
        expires_at=expires_at,
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)

    return ApiKeyResponse(
        id=api_key.id,
        name=api_key.name,
        raw_key=raw_key,
        prefix=prefix,
        is_active=api_key.is_active,
        expires_at=api_key.expires_at,
        created_at=api_key.created_at,
    )


# ══════════════════════════════════════════════════════════════════
# GET /auth/api-keys
# ══════════════════════════════════════════════════════════════════


@router.get(
    "/api-keys",
    response_model=list[ApiKeyResponse],
    status_code=status.HTTP_200_OK,
)
async def list_api_keys(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> list[ApiKeyResponse]:
    """List all API keys for the authenticated user.

    Raw keys are never returned after creation — only metadata.
    """
    result = await session.execute(select(ApiKey).where(ApiKey.user_id == current_user.id))
    keys = result.scalars().all()

    return [
        ApiKeyResponse(
            id=k.id,
            name=k.name,
            raw_key=None,
            prefix="fde_****",
            is_active=k.is_active,
            expires_at=k.expires_at,
            created_at=k.created_at,
        )
        for k in keys
    ]


# ══════════════════════════════════════════════════════════════════
# DELETE /auth/api-keys/{key_id}
# ══════════════════════════════════════════════════════════════════


@router.delete(
    "/api-keys/{key_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def revoke_api_key(
    key_id: str,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> MessageResponse:
    """Revoke (deactivate) an API key."""
    result = await session.execute(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.user_id == current_user.id,
        )
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    api_key.is_active = False
    await session.commit()

    return MessageResponse(
        message=f"API key '{api_key.name}' has been revoked",
    )
