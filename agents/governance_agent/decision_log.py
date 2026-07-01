"""Decision chain logging for orchestrator tracing (M2-T2).

Records the full decision chain from supervisor plans through worker
executions for audit, debugging, and compliance purposes.

Logs are written to the decision_chain_logs PostgreSQL table via the
governance database layer.

Usage:
    from agents.governance_agent.decision_log import DecisionLogger

    logger = DecisionLogger()
    await logger.log_plan(session_id, user_id, query, plan_dict)
    await logger.log_worker_result(session_id, worker_name, result)
    await logger.log_final(session_id, response_text, model_used, latency_ms)
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agents.governance_agent.database.models import DecisionChainLog

logger = logging.getLogger("fde.governance.decision_log")


class DecisionLogger:
    """Records supervisor-worker decision chains for audit trails.

    A single session (e.g. one user query) may generate multiple log entries:
    - One for the supervisor plan
    - One per worker execution
    - One final summary with latency and response

    All entries share the same session_id.
    """

    def __init__(self) -> None:
        self._session_start: dict[str, float] = {}

    def start_session(self, session_id: str) -> None:
        """Mark the start of a decision session for latency tracking."""
        self._session_start[session_id] = time.monotonic()

    def _elapsed_ms(self, session_id: str) -> int | None:
        """Get elapsed milliseconds for a session."""
        start = self._session_start.get(session_id)
        if start is None:
            return None
        return int((time.monotonic() - start) * 1000)

    # ── Log Methods ────────────────────────────────────────────────

    async def log_plan(
        self,
        session: AsyncSession,
        *,
        session_id: str,
        user_id: str | None,
        query: str,
        plan: dict[str, Any],
        trace_id: str | None = None,
    ) -> DecisionChainLog:
        """Log a supervisor plan entry.

        Args:
            session: Database session.
            session_id: Unique session identifier.
            user_id: Authenticated user ID (None if unauthenticated).
            query: The original user query.
            plan: Supervisor plan as dict (steps, reasoning, complexity, etc.).
            trace_id: Optional trace/request ID.
        """
        entry = DecisionChainLog(
            user_id=user_id,
            session_id=session_id,
            query=query,
            context={
                "type": "plan",
                "plan": plan,
            },
            model_used=plan.get("complexity", "unknown"),
            trace_id=trace_id,
        )
        session.add(entry)
        await session.commit()
        await session.refresh(entry)
        logger.debug("Decision log: plan for session=%s", session_id)
        return entry

    async def log_worker_result(
        self,
        session: AsyncSession,
        *,
        session_id: str,
        user_id: str | None,
        worker_name: str,
        result: dict[str, Any],
        trace_id: str | None = None,
    ) -> DecisionChainLog:
        """Log a worker execution result.

        Args:
            session: Database session.
            session_id: Unique session identifier.
            user_id: Authenticated user ID.
            worker_name: Name of the worker that executed.
            result: Worker output dict.
            trace_id: Optional trace/request ID.
        """
        entry = DecisionChainLog(
            user_id=user_id,
            session_id=session_id,
            query="",  # worker results link to plan via session_id
            context={
                "type": "worker",
                "worker": worker_name,
                "result": result,
            },
            latency_ms=self._elapsed_ms(session_id),
            trace_id=trace_id,
        )
        session.add(entry)
        await session.commit()
        await session.refresh(entry)
        logger.debug("Decision log: worker '%s' for session=%s", worker_name, session_id)
        return entry

    async def log_final(
        self,
        session: AsyncSession,
        *,
        session_id: str,
        user_id: str | None,
        response: str,
        model_used: str | None = None,
        trace_id: str | None = None,
    ) -> DecisionChainLog:
        """Log the final response and session summary.

        Args:
            session: Database session.
            session_id: Unique session identifier.
            user_id: Authenticated user ID.
            response: Final response text sent to the user.
            model_used: Name of the model used (if applicable).
            trace_id: Optional trace/request ID.
        """
        latency = self._elapsed_ms(session_id)

        entry = DecisionChainLog(
            user_id=user_id,
            session_id=session_id,
            query="",  # final response linked via session_id
            context={
                "type": "final",
                "summary": response[:500],
            },
            response=response,
            model_used=model_used,
            latency_ms=latency,
            trace_id=trace_id,
        )
        session.add(entry)
        await session.commit()
        await session.refresh(entry)

        # Cleanup session timing
        self._session_start.pop(session_id, None)

        logger.info(
            "Decision log: final for session=%s latency=%sms",
            session_id,
            latency,
        )
        return entry
