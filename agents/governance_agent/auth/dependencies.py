"""FastAPI dependency injection for authentication and authorization.

Provides:
- get_current_user: Extracts and validates JWT/API-Key from request
- require_role: Checks RBAC role membership
- require_permission: Checks ABAC resource-level permission
"""

from __future__ import annotations

from datetime import UTC

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.governance_agent.auth.security import decode_token
from agents.governance_agent.database.models import ApiKey, Permission, User
from agents.governance_agent.database.session import get_async_session

# ══════════════════════════════════════════════════════════════════
# HTTP Bearer scheme
# ══════════════════════════════════════════════════════════════════

bearer_scheme = HTTPBearer(auto_error=False)

# Header name for API key authentication
API_KEY_HEADER = "X-API-Key"

# ══════════════════════════════════════════════════════════════════
# Token extraction
# ══════════════════════════════════════════════════════════════════


async def _extract_credentials(
    request: Request,
) -> tuple[str, str] | None:
    """Extract authentication credentials from request.

    Tries in order:
    1. Authorization: Bearer <token> (JWT)
    2. X-API-Key: <key> (API Key)

    Returns:
        Tuple of (auth_type, credential) or None if no auth found.
    """
    # Try Bearer token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
        if token:
            return ("jwt", token)

    # Try API key header
    api_key = request.headers.get(API_KEY_HEADER, "").strip()
    if api_key:
        return ("api_key", api_key)

    return None


# ══════════════════════════════════════════════════════════════════
# User resolution
# ══════════════════════════════════════════════════════════════════


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> User:
    """Resolve the authenticated user from JWT or API Key.

    This is the primary dependency for protected endpoints.

    Raises:
        HTTPException 401: Invalid or expired credentials.
    """
    credentials = await _extract_credentials(request)

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_type, credential = credentials

    if auth_type == "jwt":
        return await _authenticate_jwt(credential, session)
    elif auth_type == "api_key":
        return await _authenticate_api_key(credential, session)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unknown authentication type",
    )


async def _authenticate_jwt(token: str, session: AsyncSession) -> User:
    """Authenticate via JWT access token."""
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify token type
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is not an access token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim",
        )

    # Fetch user from database
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


async def _authenticate_api_key(raw_key: str, session: AsyncSession) -> User:
    """Authenticate via API key."""
    from datetime import datetime

    from agents.governance_agent.auth.security import hash_api_key

    key_hash = hash_api_key(raw_key)
    result = await session.execute(
        select(ApiKey).where(
            ApiKey.key_hash == key_hash,
            ApiKey.is_active == True,  # noqa: E712
        )
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    # Check expiration
    if api_key.expires_at and api_key.expires_at < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has expired",
        )

    # Fetch associated user
    user_result = await session.execute(select(User).where(User.id == api_key.user_id))
    user = user_result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require an active (non-disabled) user.

    Use this for endpoints that should reject disabled accounts.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )
    return current_user


# ══════════════════════════════════════════════════════════════════
# RBAC Authorization
# ══════════════════════════════════════════════════════════════════


class RoleChecker:
    """Dependency factory for role-based access control.

    Usage:
        @router.get("/admin")
        async def admin_endpoint(user = Depends(require_role("admin"))):
            ...
    """

    def __init__(self, *required_roles: str) -> None:
        self.required_roles = set(required_roles)

    async def __call__(
        self,
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        user_roles: set[str] = set(current_user.roles or [])
        if not user_roles & self.required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {sorted(self.required_roles)}",
            )
        return current_user


def require_role(*roles: str) -> RoleChecker:
    """Require at least one of the given roles.

    Args:
        roles: Role names (e.g., "admin", "analyst", "viewer").

    Returns:
        A FastAPI dependency that checks role membership.

    Example:
        @router.get("/dashboard")
        async def dashboard(user = Depends(require_role("analyst", "admin"))):
            ...
    """
    return RoleChecker(*roles)


# ══════════════════════════════════════════════════════════════════
# ABAC Authorization
# ══════════════════════════════════════════════════════════════════


async def check_permission(
    current_user: User,
    resource_type: str,
    resource_id: str,
    action: str,
    session: AsyncSession,
) -> bool:
    """Check if a user has permission to perform an action on a resource.

    Permission resolution order:
    1. "admin" role → always granted
    2. Direct user permission entry in permissions table
    3. Role-based permission entry (any of user's roles)

    Args:
        current_user: The authenticated user.
        resource_type: "knowledge_base" | "document" | "paragraph" | "collection"
        resource_id: The resource identifier.
        action: "read" | "write" | "delete" | "admin"
        session: Database session.

    Returns:
        True if permission is granted.
    """
    # Admin role bypasses all permission checks
    user_roles: set[str] = set(current_user.roles or [])
    if "admin" in user_roles:
        return True

    # Build query: check direct user permission + role-based permissions
    subjects = [("user", current_user.id)]
    for role in user_roles:
        subjects.append(("role", role))

    from sqlalchemy import or_

    conditions = []
    for subject_type, subject_id in subjects:
        conditions.append(
            (Permission.subject_type == subject_type) & (Permission.subject_id == subject_id)
        )

    result = await session.execute(
        select(Permission).where(
            or_(*conditions),
            Permission.resource_type == resource_type,
            Permission.resource_id == resource_id,
            Permission.action == action,
        )
    )
    permission = result.scalar_one_or_none()

    return permission is not None


async def require_permission_dependency(
    resource_type: str,
    resource_id: str,
    action: str,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> User:
    """Check ABAC permission for a resource+action. Raises 403 if denied.

    Usage:
        @router.get("/kb/{kb_id}")
        async def get_kb(
            kb_id: str,
            user = Depends(get_current_user),
            session = Depends(get_async_session),
        ):
            if not await check_permission(user, "knowledge_base", kb_id, "read", session):
                raise HTTPException(403, "Access denied")

    Note: For path-param resource IDs, use check_permission() inline
    in the endpoint body instead of this dependency.
    """
    granted = await check_permission(
        current_user=current_user,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        session=session,
    )
    if not granted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: {action} on {resource_type}/{resource_id}",
        )
    return current_user
