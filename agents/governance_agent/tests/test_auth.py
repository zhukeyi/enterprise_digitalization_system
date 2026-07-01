"""Tests for Governance Agent — Auth & Authorization (M2-T1).

Uses SQLite in-memory for test database isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agents.governance_agent.auth.models import (
    ApiKeyCreateRequest,
    LoginRequest,
    RegisterRequest,
    TokenRefreshRequest,
    TokenResponse,
    UserResponse,
)
from agents.governance_agent.auth.security import (
    create_access_token,
    create_api_key,
    create_refresh_token,
    decode_token,
    hash_api_key,
    hash_password,
    verify_api_key,
    verify_password,
)
from agents.governance_agent.database import Base
from agents.governance_agent.database.models import ApiKey, Permission, User

# ══════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════


@pytest.fixture
async def engine():
    """Create async SQLite engine for testing."""
    db_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield db_engine

    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await db_engine.dispose()


@pytest.fixture
async def session(engine):
    """Create an async session bound to the test DB."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest.fixture
async def test_user(session: AsyncSession) -> User:
    """Create a test user with 'analyst' role."""
    user = User(
        username="testuser",
        email="test@example.com",
        display_name="Test User",
        password_hash=hash_password("password123"),
        roles=["analyst"],
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.fixture
async def admin_user(session: AsyncSession) -> User:
    """Create an admin user."""
    user = User(
        username="admin",
        email="admin@example.com",
        display_name="Admin",
        password_hash=hash_password("admin123"),
        roles=["admin"],
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


# ══════════════════════════════════════════════════════════════════
# Password Hashing
# ══════════════════════════════════════════════════════════════════


class TestPasswordHashing:
    def test_hash_and_verify(self) -> None:
        """Hashed password should verify correctly."""
        hashed = hash_password("mypassword")
        assert hashed != "mypassword"
        assert verify_password("mypassword", hashed) is True

    def test_wrong_password(self) -> None:
        """Wrong password should not verify."""
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_unique_hashes(self) -> None:
        """Each hash should be unique (random salt)."""
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2
        assert verify_password("same", h1)
        assert verify_password("same", h2)


# ══════════════════════════════════════════════════════════════════
# JWT Token Operations
# ══════════════════════════════════════════════════════════════════


class TestJWT:
    def test_create_and_decode_access_token(self) -> None:
        """Access token should round-trip encode/decode."""
        token = create_access_token(user_id="user-1", username="alice", roles=["analyst"])
        payload = decode_token(token)
        assert payload["sub"] == "user-1"
        assert payload["username"] == "alice"
        assert payload["roles"] == ["analyst"]
        assert payload["type"] == "access"

    def test_create_and_decode_refresh_token(self) -> None:
        """Refresh token should have refresh type."""
        token = create_refresh_token(user_id="user-1", username="alice")
        payload = decode_token(token)
        assert payload["type"] == "refresh"
        assert payload["sub"] == "user-1"

    def test_expired_token(self) -> None:
        """Expired token should raise JWTError."""
        from jose import JWTError

        token = create_access_token(
            user_id="u1",
            username="x",
            expires_delta=timedelta(seconds=-1),  # already expired
        )
        with pytest.raises(JWTError):
            decode_token(token)

    def test_valid_access_token_accepts_roles(self) -> None:
        """Multiple roles should be encoded correctly."""
        token = create_access_token(
            user_id="u2", username="bob", roles=["admin", "analyst", "viewer"]
        )
        payload = decode_token(token)
        assert set(payload["roles"]) == {"admin", "analyst", "viewer"}


# ══════════════════════════════════════════════════════════════════
# API Key Operations
# ══════════════════════════════════════════════════════════════════


class TestApiKeys:
    def test_create_api_key(self) -> None:
        """API key creation should return raw key, hash, and prefix."""
        raw, key_hash, prefix = create_api_key()
        assert raw.startswith("fde_")
        assert len(raw) > 30
        assert len(key_hash) == 64  # SHA256 hex digest
        assert prefix == raw[:12]

    def test_verify_api_key(self) -> None:
        """Correct key should verify, wrong key should not."""
        _raw, key_hash, _prefix = create_api_key()
        assert verify_api_key(_raw, key_hash) is True
        assert verify_api_key("wrong_key", key_hash) is False

    def test_hash_api_key_deterministic(self) -> None:
        """Same raw key should produce same hash."""
        h1 = hash_api_key("key123")
        h2 = hash_api_key("key123")
        assert h1 == h2


# ══════════════════════════════════════════════════════════════════
# Pydantic Models (Validation)
# ══════════════════════════════════════════════════════════════════


class TestAuthModels:
    def test_register_request_valid(self) -> None:
        """Valid registration data should parse."""
        req = RegisterRequest(
            username="newuser",
            email="new@example.com",
            password="securepass123",
        )
        assert req.username == "newuser"

    def test_register_request_short_password(self) -> None:
        """Password < 8 chars should fail."""
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="newuser",
                email="new@example.com",
                password="short",
            )

    def test_register_request_invalid_username(self) -> None:
        """Invalid username characters should fail."""
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="user name",
                email="x@y.com",
                password="password123",
            )

    def test_login_request_valid(self) -> None:
        """Valid login data should parse."""
        req = LoginRequest(username="alice", password="pass123")
        assert req.username == "alice"

    def test_api_key_create_request(self) -> None:
        """API key create request should accept optional expiry."""
        req = ApiKeyCreateRequest(name="My Key", expires_in_days=30)
        assert req.name == "My Key"
        assert req.expires_in_days == 30

    def test_api_key_create_request_no_expiry(self) -> None:
        """API key without expiry should be None."""
        req = ApiKeyCreateRequest(name="Forever Key")
        assert req.expires_in_days is None


# ══════════════════════════════════════════════════════════════════
# DB Models
# ══════════════════════════════════════════════════════════════════


class TestUserModel:
    async def test_create_user(self, session: AsyncSession) -> None:
        """User should be created and persisted."""
        user = User(
            username="dbuser",
            email="db@test.com",
            password_hash="hashed",
            roles=["viewer"],
        )
        session.add(user)
        await session.commit()

        result = await session.execute(
            __import__("sqlalchemy").select(User).where(User.username == "dbuser")
        )
        fetched = result.scalar_one()
        assert fetched.email == "db@test.com"
        assert fetched.roles == ["viewer"]

    async def test_user_unique_username(self, session: AsyncSession, test_user: User) -> None:
        """Duplicate username should raise integrity error."""
        duplicate = User(
            username="testuser",  # Same as fixture
            email="other@test.com",
            password_hash="hashed",
        )
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            await session.commit()

    async def test_user_inactive_flag(self, session: AsyncSession) -> None:
        """Inactive user should be queryable."""
        user = User(
            username="inactive",
            email="inactive@test.com",
            password_hash="hashed",
            is_active=False,
        )
        session.add(user)
        await session.commit()

        result = await session.execute(
            __import__("sqlalchemy").select(User).where(User.username == "inactive")
        )
        fetched = result.scalar_one()
        assert fetched.is_active is False


class TestApiKeyModel:
    async def test_create_api_key_record(self, session: AsyncSession, test_user: User) -> None:
        """API key should be created and linked to user."""
        _raw, key_hash, _prefix = create_api_key()
        api_key = ApiKey(
            user_id=test_user.id,
            key_hash=key_hash,
            name="Test Key",
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        session.add(api_key)
        await session.commit()
        await session.refresh(api_key)

        assert api_key.user_id == test_user.id
        assert api_key.key_hash == key_hash
        assert api_key.is_active is True

    async def test_revoke_api_key(self, session: AsyncSession, test_user: User) -> None:
        """API key should be revocable."""
        _raw, key_hash, _prefix = create_api_key()
        api_key = ApiKey(user_id=test_user.id, key_hash=key_hash, name="To Revoke")
        session.add(api_key)
        await session.commit()

        api_key.is_active = False
        await session.commit()

        result = await session.execute(
            __import__("sqlalchemy").select(ApiKey).where(ApiKey.key_hash == key_hash)
        )
        fetched = result.scalar_one()
        assert fetched.is_active is False


class TestPermissionModel:
    async def test_create_permission(self, session: AsyncSession, test_user: User) -> None:
        """Permission should grant access to a resource."""
        perm = Permission(
            subject_type="user",
            subject_id=test_user.id,
            resource_type="knowledge_base",
            resource_id="kb-001",
            action="read",
        )
        session.add(perm)
        await session.commit()

        result = await session.execute(
            __import__("sqlalchemy")
            .select(Permission)
            .where(
                Permission.subject_id == test_user.id,
                Permission.resource_type == "knowledge_base",
            )
        )
        perms = result.scalars().all()
        assert len(perms) == 1
        assert perms[0].action == "read"

    async def test_role_based_permission(self, session: AsyncSession) -> None:
        """Role-based permission should be queryable."""
        perm = Permission(
            subject_type="role",
            subject_id="analyst",
            resource_type="document",
            resource_id="doc-100",
            action="write",
        )
        session.add(perm)
        await session.commit()

        result = await session.execute(
            __import__("sqlalchemy")
            .select(Permission)
            .where(
                Permission.subject_type == "role",
                Permission.subject_id == "analyst",
            )
        )
        perms = result.scalars().all()
        assert len(perms) == 1


# ══════════════════════════════════════════════════════════════════
# UserResponse serialization
# ══════════════════════════════════════════════════════════════════


class TestUserResponse:
    async def test_serialize_user(self, test_user: User) -> None:
        """UserResponse should serialize ORM User correctly."""
        resp = UserResponse.model_validate(test_user)
        assert resp.id == test_user.id
        assert resp.username == "testuser"
        assert resp.email == "test@example.com"
        # password_hash should NEVER be in response
        assert not hasattr(resp, "password_hash")
        assert "analyst" in resp.roles


# ══════════════════════════════════════════════════════════════════
# Pydantic Models (Validation) — Request models
# ══════════════════════════════════════════════════════════════════


class TestTokenModels:
    def test_token_response_structure(self) -> None:
        """TokenResponse should have required fields."""
        response = TokenResponse(
            access_token="abc.def.ghi",
            refresh_token="jkl.mno.pqr",
            token_type="bearer",
            expires_in=1800,
        )
        assert response.token_type == "bearer"
        assert response.expires_in == 1800

    def test_token_refresh_request(self) -> None:
        """TokenRefreshRequest should parse correctly."""
        req = TokenRefreshRequest(refresh_token="my.refresh.token")
        assert req.refresh_token == "my.refresh.token"
