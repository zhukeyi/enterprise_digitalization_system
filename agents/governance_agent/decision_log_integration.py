"""Integration adapter: connect decision logging to the orchestrator graph.

Provides factory functions that wrap supervisor and worker nodes
with decision chain logging (M2-T2).

Usage:
    # In graph builder:
    from agents.governance_agent.decision_log_integration import (
        wrap_supervisor_with_logging,
        wrap_worker_with_logging,
    )

    supervisor = SupervisorNode(...)
    logged_supervisor = wrap_supervisor_with_logging(
        supervisor, decision_logger, get_session_factory
    )

    rag_worker = RAGWorker(registry)
    logged_rag = wrap_worker_with_logging(
        rag_worker, "rag", decision_logger, get_session_factory
    )
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from agents.governance_agent.decision_log import DecisionLogger

logger = logging.getLogger("fde.governance.decision_integration")


def _generate_session_id() -> str:
    """Generate a unique UUID for each orchestration session."""
    return str(uuid.uuid4())


def _extract_query_from_state(state: Any) -> str:
    """Extract the original user query from orchestrator state."""
    from langchain_core.messages import HumanMessage

    for msg in reversed(getattr(state, "messages", [])):
        if isinstance(msg, HumanMessage):
            content = msg.content
            return content if isinstance(content, str) else str(content)
    return ""


class LoggedSupervisorNode:
    """Supervisor node wrapper that records plan decisions in the decision log.

    Delegates to the inner supervisor node, then records the produced plan.
    """

    def __init__(
        self,
        inner: Any,
        decision_logger: DecisionLogger,
        session_factory: Any,
    ) -> None:
        self._inner = inner
        self._logger = decision_logger
        self._session_factory = session_factory

    def __call__(self, state: Any) -> dict[str, Any]:
        result = self._inner(state)

        # Extract plan details for logging
        plan = result.get("plan")
        if plan is not None:
            asyncio = __import__("asyncio")

            async def _log() -> None:
                session_id = _generate_session_id()
                query = _extract_query_from_state(state)

                # Store session_id in state for subsequent worker logs
                state.metadata["decision_session_id"] = session_id
                self._logger.start_session(session_id)

                plan_dict = {
                    "steps": [
                        {
                            "worker": s.worker,
                            "task": s.task,
                            "tool": s.tool,
                        }
                        for s in (plan.steps or [])
                    ],
                    "reasoning": plan.reasoning if hasattr(plan, "reasoning") else "",
                    "complexity": (plan.complexity if hasattr(plan, "complexity") else "unknown"),
                    "finish": plan.finish if hasattr(plan, "finish") else False,
                }

                try:
                    async with self._session_factory() as session:
                        await self._logger.log_plan(
                            session=session,
                            session_id=session_id,
                            user_id=getattr(state, "user_id", None),
                            query=query,
                            plan=plan_dict,
                        )
                except Exception as e:
                    logger.debug("Failed to log plan: %s", e)

            try:
                asyncio.run(_log())
            except Exception as e:
                logger.debug("Decision logging unavailable: %s", e)

        return result  # type: ignore[no-any-return]


class LoggedWorkerNode:
    """Worker node wrapper that records execution results in the decision log.

    Delegates to the inner worker, then records the result.
    """

    def __init__(
        self,
        inner: Any,
        worker_name: str,
        decision_logger: DecisionLogger,
        session_factory: Any,
    ) -> None:
        self._inner = inner
        self._worker_name = worker_name
        self._logger = decision_logger
        self._session_factory = session_factory

    def __call__(self, state: Any) -> dict[str, Any]:
        result = self._inner(state)

        session_id = state.metadata.get("decision_session_id")
        if session_id is None:
            return result  # type: ignore[no-any-return]

        asyncio = __import__("asyncio")

        async def _log() -> None:
            try:
                worker_output = result.get("worker_outputs", {}).get(self._worker_name, {})
                async with self._session_factory() as session:
                    await self._logger.log_worker_result(
                        session=session,
                        session_id=session_id,
                        user_id=getattr(state, "user_id", None),
                        worker_name=self._worker_name,
                        result=worker_output if isinstance(worker_output, dict) else {},
                    )
            except Exception as e:
                logger.debug("Failed to log worker result: %s", e)

        try:
            asyncio.run(_log())
        except Exception as e:
            logger.debug("Decision logging unavailable: %s", e)

        return result  # type: ignore[no-any-return]


def wrap_supervisor_with_logging(
    supervisor_node: Any,
    decision_logger: DecisionLogger,
    session_factory: Any,
) -> LoggedSupervisorNode:
    """Wrap a SupervisorNode with decision chain logging."""
    return LoggedSupervisorNode(supervisor_node, decision_logger, session_factory)


def wrap_worker_with_logging(
    worker_node: Any,
    worker_name: str,
    decision_logger: DecisionLogger,
    session_factory: Any,
) -> LoggedWorkerNode:
    """Wrap a worker node with decision chain logging."""
    return LoggedWorkerNode(worker_node, worker_name, decision_logger, session_factory)
