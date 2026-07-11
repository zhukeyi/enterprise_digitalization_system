"""Async SQLAlchemy session factory for Governance Agent.

Uses asyncpg for PostgreSQL (production) or aiosqlite for testing.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class DatabaseConfig(BaseSettings):
    """Database connection configuration."""

    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://fde:fde_dev_2026@localhost:5432/fde_platform",
    )
    database_echo: bool = os.getenv("DATABASE_ECHO", "false").lower() == "true"
    pool_size: int = int(os.getenv("DB_POOL_SIZE", "5"))
    pool_overflow: int = int(os.getenv("DB_POOL_OVERFLOW", "10"))

    model_config = {"env_prefix": "DB_", "case_sensitive": False}


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    pass


_db_config = DatabaseConfig()

# Module-level engine and session factory (lazy init)
_engine = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine() -> AsyncEngine:
    """Get or create the SQLAlchemy async engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            _db_config.database_url,
            echo=_db_config.database_echo,
            pool_size=_db_config.pool_size,
            max_overflow=_db_config.pool_overflow,
        )
    return _engine


def get_engine() -> AsyncEngine:
    """Public accessor for the shared async engine (used by migrations)."""
    return _get_engine()


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session factory."""
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            _get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory


async def init_database(drop_all: bool = False) -> None:
    """Initialize database — create tables on first run."""
    engine = _get_engine()
    async with engine.begin() as conn:
        if drop_all:
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()
