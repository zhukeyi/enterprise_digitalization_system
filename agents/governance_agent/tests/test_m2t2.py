"""Tests for RAG permission filter and decision chain logging (M2-T2)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agents.governance_agent.database import Base
from agents.governance_agent.database.models import (
    DecisionChainLog,
    Permission,
    User,
)
from agents.governance_agent.decision_log import DecisionLogger

# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════


def _uid() -> str:
    return str(uuid.uuid4())


# ══════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════


@pytest.fixture
async def engine():
    """Create async SQLite engine for testing."""
    db_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield db_engine
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await db_engine.dispose()


@pytest.fixture
async def session(engine):
    """Create an async session."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest.fixture
async def analyst_user(session: AsyncSession) -> User:
    """Create a test user with 'analyst' role."""
    from agents.governance_agent.auth.security import hash_password

    user = User(
        username="analyst1",
        email="analyst@test.com",
        password_hash=hash_password("pass123"),
        roles=["analyst"],
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    # Grant read access to specific resources
    for resource_type, resource_id in [
        ("knowledge_base", "kb-public"),
        ("document", "doc-001"),
        ("collection", "col-alpha"),
    ]:
        perm = Permission(
            subject_type="role",
            subject_id="analyst",
            resource_type=resource_type,
            resource_id=resource_id,
            action="read",
        )
        session.add(perm)
    await session.commit()

    return user


@pytest.fixture
async def admin_user(session: AsyncSession) -> User:
    """Create an admin user."""
    from agents.governance_agent.auth.security import hash_password

    user = User(
        username="admin1",
        email="admin@test.com",
        password_hash=hash_password("admin123"),
        roles=["admin"],
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


# ══════════════════════════════════════════════════════════════════
# Auth Filter Tests
# ══════════════════════════════════════════════════════════════════


class TestAuthFilter:
    async def test_admin_bypass_all_results(self, session: AsyncSession, admin_user: User) -> None:
        """Admin should see all results without any filtering."""
        from agents.rag_agent.auth_filter import filter_by_permission

        results = [
            {"content": "Public doc", "source": "doc-001"},
            {"content": "Secret doc", "source": "doc-secret"},
        ]

        filtered = await filter_by_permission(results, admin_user, session)
        assert len(filtered) == 2

    async def test_role_based_filtering(self, session: AsyncSession, analyst_user: User) -> None:
        """Analyst should only see results for permitted resources."""
        from agents.rag_agent.auth_filter import filter_by_permission

        results = [
            {
                "content": "Public doc",
                "source": "doc-001",
                "metadata": {"document_id": "doc-001"},
            },
            {
                "content": "Forbidden doc",
                "source": "doc-secret",
                "metadata": {"document_id": "doc-secret"},
            },
        ]

        filtered = await filter_by_permission(results, analyst_user, session)
        assert len(filtered) == 1
        assert filtered[0]["source"] == "doc-001"

    async def test_collection_filtering(self, session: AsyncSession, analyst_user: User) -> None:
        """Should filter by collection_id in metadata."""
        from agents.rag_agent.auth_filter import filter_by_permission

        results = [
            {
                "content": "In collection alpha",
                "metadata": {"collection_id": "col-alpha"},
            },
            {
                "content": "In collection beta",
                "metadata": {"collection_id": "col-beta"},
            },
        ]

        filtered = await filter_by_permission(results, analyst_user, session)
        assert len(filtered) == 1
        assert "alpha" in filtered[0]["content"]

    async def test_no_permissions_returns_empty(
        self, session: AsyncSession, analyst_user: User
    ) -> None:
        """Should return empty if no results have permitted resource IDs."""
        from agents.rag_agent.auth_filter import filter_by_permission

        results = [
            {"content": "Unknown source", "source": "no-permission-doc"},
        ]

        filtered = await filter_by_permission(results, analyst_user, session)
        assert len(filtered) == 0

    async def test_empty_results(self, session: AsyncSession, admin_user: User) -> None:
        """Empty results should remain empty."""
        from agents.rag_agent.auth_filter import filter_by_permission

        filtered = await filter_by_permission([], admin_user, session)
        assert filtered == []

    async def test_kb_level_permission(self, session: AsyncSession, analyst_user: User) -> None:
        """Knowledge base level permission should pass."""
        from agents.rag_agent.auth_filter import filter_by_permission

        results = [
            {
                "content": "KB public doc",
                "metadata": {"kb_id": "kb-public"},
            },
        ]

        filtered = await filter_by_permission(results, analyst_user, session)
        assert len(filtered) == 1


# ══════════════════════════════════════════════════════════════════
# Decision Logger Tests
# ══════════════════════════════════════════════════════════════════


class TestDecisionLogger:
    async def test_log_plan(self, session: AsyncSession) -> None:
        """Should create a DecisionChainLog entry for a supervisor plan."""
        logger_instance = DecisionLogger()
        session_id = _uid()
        logger_instance.start_session(session_id)

        await logger_instance.log_plan(
            session=session,
            session_id=session_id,
            user_id=_uid(),
            query="search knowledge base",
            plan={
                "steps": [{"worker": "rag", "task": "search", "tool": "rag_search"}],
                "reasoning": "Knowledge query",
                "complexity": "simple",
            },
            trace_id=_uid(),
        )

        result = await session.execute(
            select(DecisionChainLog).where(DecisionChainLog.session_id == session_id)
        )
        entries = result.scalars().all()
        assert len(entries) == 1

        entry = entries[0]
        assert entry.query == "search knowledge base"
        assert entry.context is not None
        assert entry.context["type"] == "plan"

    async def test_log_worker_result(self, session: AsyncSession) -> None:
        """Should create a DecisionChainLog entry for worker execution."""
        logger_instance = DecisionLogger()
        session_id = _uid()
        logger_instance.start_session(session_id)

        await logger_instance.log_worker_result(
            session=session,
            session_id=session_id,
            user_id=_uid(),
            worker_name="rag",
            result={"total_results": 5, "query": "test"},
        )

        result = await session.execute(
            select(DecisionChainLog).where(DecisionChainLog.session_id == session_id)
        )
        entries = result.scalars().all()
        assert len(entries) == 1

        entry = entries[0]
        assert entry.context is not None
        assert entry.context["type"] == "worker"
        assert entry.context["worker"] == "rag"

    async def test_log_final_with_latency(self, session: AsyncSession) -> None:
        """Should record final response with latency."""
        logger_instance = DecisionLogger()
        session_id = _uid()
        logger_instance.start_session(session_id)

        await logger_instance.log_final(
            session=session,
            session_id=session_id,
            user_id=_uid(),
            response="Here is the search result.",
            model_used="deepseek-chat",
        )

        result = await session.execute(
            select(DecisionChainLog).where(DecisionChainLog.session_id == session_id)
        )
        entries = result.scalars().all()
        assert len(entries) == 1

        entry = entries[0]
        assert entry.context is not None
        assert entry.context["type"] == "final"
        assert entry.response == "Here is the search result."
        assert entry.model_used == "deepseek-chat"
        assert entry.latency_ms is not None
        assert entry.latency_ms >= 0

    async def test_full_decision_chain(self, session: AsyncSession) -> None:
        """Should record a complete plan → worker → final chain."""
        logger_instance = DecisionLogger()
        session_id = _uid()

        # Plan
        logger_instance.start_session(session_id)
        await logger_instance.log_plan(
            session=session,
            session_id=session_id,
            user_id=_uid(),
            query="search",
            plan={
                "steps": [{"worker": "rag"}],
                "reasoning": "test",
                "complexity": "simple",
            },
        )

        # Worker
        await logger_instance.log_worker_result(
            session=session,
            session_id=session_id,
            user_id=_uid(),
            worker_name="rag",
            result={"count": 3},
        )

        # Final
        await logger_instance.log_final(
            session=session,
            session_id=session_id,
            user_id=_uid(),
            response="Found 3 results.",
        )

        result = await session.execute(
            select(DecisionChainLog)
            .where(DecisionChainLog.session_id == session_id)
            .order_by(DecisionChainLog.created_at)
        )
        entries = result.scalars().all()
        assert len(entries) == 3
        assert entries[0].context is not None
        assert entries[0].context["type"] == "plan"
        assert entries[1].context is not None
        assert entries[1].context["type"] == "worker"
        assert entries[2].context is not None
        assert entries[2].context["type"] == "final"

    async def test_latency_positive(self, session: AsyncSession) -> None:
        """Latency should be non-negative after session execution."""
        import time

        logger_instance = DecisionLogger()
        session_id = _uid()
        logger_instance.start_session(session_id)
        time.sleep(0.01)  # Small delay to ensure measurable latency

        await logger_instance.log_worker_result(
            session=session,
            session_id=session_id,
            user_id=_uid(),
            worker_name="test",
            result={},
        )

        result = await session.execute(
            select(DecisionChainLog).where(DecisionChainLog.session_id == session_id)
        )
        entry = result.scalar_one()
        assert entry.latency_ms is not None
        assert entry.latency_ms >= 0


# ══════════════════════════════════════════════════════════════════
# DecisionChainLog ORM Model Tests
# ══════════════════════════════════════════════════════════════════


class TestDecisionChainLogModel:
    async def test_create_and_persist(self, session: AsyncSession) -> None:
        """DecisionChainLog should be created and persisted."""
        entry = DecisionChainLog(
            user_id=_uid(),
            session_id=_uid(),
            query="What is FDE?",
            context={"type": "plan", "steps": []},
            trace_id=_uid(),
        )
        session.add(entry)
        await session.commit()
        await session.refresh(entry)

        assert entry.id is not None
        assert entry.query == "What is FDE?"
        assert entry.created_at is not None

    async def test_nullable_fields(self, session: AsyncSession) -> None:
        """Optional fields should accept None."""
        sess_id = _uid()
        entry = DecisionChainLog(
            session_id=sess_id,
            query="test query",
        )
        session.add(entry)
        await session.commit()

        result = await session.execute(
            select(DecisionChainLog).where(DecisionChainLog.session_id == sess_id)
        )
        fetched = result.scalar_one()
        assert fetched.user_id is None
        assert fetched.context is None
        assert fetched.response is None
        assert fetched.model_used is None
        assert fetched.latency_ms is None
        assert fetched.trace_id is None
