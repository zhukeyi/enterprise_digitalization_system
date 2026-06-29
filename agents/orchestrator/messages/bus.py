"""Message Bus — LangChain Message-based communication layer.

Provides a unified message interface for all orchestrator components.
Messages flow through the LangGraph state and are visible to both
the supervisor and workers.

M1-T6: Message bus for inter-agent communication
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

logger = logging.getLogger("fde.orchestrator.messages")


# ══════════════════════════════════════════════════════════════════
# Message Types
# ══════════════════════════════════════════════════════════════════


class MessageType:
    """Message type constants for structured communication."""

    USER_INPUT = "user_input"
    SUPERVISOR_PLAN = "supervisor_plan"
    WORKER_RESULT = "worker_result"
    WORKER_ERROR = "worker_error"
    SYSTEM_LOG = "system_log"
    FOOLPROOF_ALERT = "foolproof_alert"


# ══════════════════════════════════════════════════════════════════
# Message Factory
# ══════════════════════════════════════════════════════════════════


def create_user_message(content: str, metadata: dict[str, Any] | None = None) -> HumanMessage:
    """Create a user input message."""
    return HumanMessage(
        content=content,
        additional_kwargs={"type": MessageType.USER_INPUT, "metadata": metadata or {}},
    )


def create_supervisor_message(plan_json: str, reasoning: str = "") -> AIMessage:
    """Create a supervisor plan message."""
    return AIMessage(
        content=reasoning,
        additional_kwargs={"type": MessageType.SUPERVISOR_PLAN, "plan": plan_json},
    )


def create_worker_message(worker_name: str, result: Any, is_error: bool = False) -> AIMessage:
    """Create a worker result message."""
    msg_type = MessageType.WORKER_ERROR if is_error else MessageType.WORKER_RESULT
    content = str(result) if not isinstance(result, str) else result

    return AIMessage(
        content=f"[{worker_name}] {content}",
        additional_kwargs={
            "type": msg_type,
            "worker": worker_name,
            "timestamp": time.time(),
            "is_error": is_error,
        },
    )


def create_system_message(content: str) -> SystemMessage:
    """Create a system-level message (logs, alerts)."""
    return SystemMessage(content=content)


def create_foolproof_alert(action: str, reason: str, severity: str = "high") -> SystemMessage:
    """Create a foolproof alert message for dangerous operations."""
    return SystemMessage(
        content=f"⚠️ FOOLPROOF ALERT: {reason}",
        additional_kwargs={
            "type": MessageType.FOOLPROOF_ALERT,
            "action": action,
            "severity": severity,
            "timestamp": time.time(),
        },
    )


# ══════════════════════════════════════════════════════════════════
# Message History
# ══════════════════════════════════════════════════════════════════


class MessageHistory:
    """In-memory message history for tracking conversation flow.

    Stores all messages exchanged during an orchestrator session,
    with filtering capabilities by type, worker, etc.
    """

    def __init__(self) -> None:
        self._messages: list[BaseMessage] = []
        self._trace_id: str = str(uuid.uuid4())[:8]

    def add(self, message: BaseMessage) -> None:
        """Add a message to the history."""
        self._messages.append(message)

    def get_all(self) -> list[BaseMessage]:
        """Get all messages."""
        return list(self._messages)

    def get_by_type(self, msg_type: str) -> list[BaseMessage]:
        """Filter messages by type."""
        return [m for m in self._messages if m.additional_kwargs.get("type") == msg_type]

    def get_by_worker(self, worker_name: str) -> list[BaseMessage]:
        """Filter messages by worker name."""
        return [m for m in self._messages if m.additional_kwargs.get("worker") == worker_name]

    def get_user_messages(self) -> list[HumanMessage]:
        """Get all user input messages."""
        return [m for m in self._messages if isinstance(m, HumanMessage)]

    def get_worker_results(self) -> list[BaseMessage]:
        """Get all worker result messages."""
        return self.get_by_type(MessageType.WORKER_RESULT)

    def get_errors(self) -> list[BaseMessage]:
        """Get all error messages."""
        return self.get_by_type(MessageType.WORKER_ERROR)

    def get_foolproof_alerts(self) -> list[BaseMessage]:
        """Get all foolproof alert messages."""
        return self.get_by_type(MessageType.FOOLPROOF_ALERT)

    def clear(self) -> None:
        """Clear all messages."""
        self._messages.clear()

    def to_dict(self) -> dict[str, Any]:
        """Serialize message history to a dictionary."""
        return {
            "trace_id": self._trace_id,
            "message_count": len(self._messages),
            "messages": [
                {
                    "type": m.additional_kwargs.get("type", "unknown"),
                    "role": m.type,
                    "content": m.content[:200],
                    "timestamp": m.additional_kwargs.get("timestamp"),
                }
                for m in self._messages
            ],
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @property
    def trace_id(self) -> str:
        """Get the trace ID for this message history."""
        return self._trace_id
