"""Tests for Message Bus."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.orchestrator.messages.bus import (
    MessageHistory,
    MessageType,
    create_foolproof_alert,
    create_supervisor_message,
    create_system_message,
    create_user_message,
    create_worker_message,
)

# ══════════════════════════════════════════════════════════════════
# Message Factory Tests
# ══════════════════════════════════════════════════════════════════


class TestMessageFactories:
    """Tests for message creation functions."""

    def test_create_user_message(self) -> None:
        msg = create_user_message("Hello", metadata={"user_id": "1"})
        assert isinstance(msg, HumanMessage)
        assert msg.content == "Hello"
        assert msg.additional_kwargs["type"] == MessageType.USER_INPUT
        assert msg.additional_kwargs["metadata"]["user_id"] == "1"

    def test_create_supervisor_message(self) -> None:
        msg = create_supervisor_message('{"steps": []}', reasoning="No action needed")
        assert isinstance(msg, AIMessage)
        assert msg.content == "No action needed"
        assert msg.additional_kwargs["type"] == MessageType.SUPERVISOR_PLAN

    def test_create_worker_result_message(self) -> None:
        msg = create_worker_message("rag", "Found 3 documents")
        assert isinstance(msg, AIMessage)
        assert "[rag]" in msg.content
        assert msg.additional_kwargs["type"] == MessageType.WORKER_RESULT
        assert msg.additional_kwargs["worker"] == "rag"
        assert msg.additional_kwargs["is_error"] is False

    def test_create_worker_error_message(self) -> None:
        msg = create_worker_message("hr", "Tool crashed", is_error=True)
        assert isinstance(msg, AIMessage)
        assert msg.additional_kwargs["type"] == MessageType.WORKER_ERROR
        assert msg.additional_kwargs["is_error"] is True

    def test_create_system_message(self) -> None:
        msg = create_system_message("System maintenance")
        assert isinstance(msg, SystemMessage)
        assert msg.content == "System maintenance"

    def test_create_foolproof_alert(self) -> None:
        msg = create_foolproof_alert("delete_all", "Irreversible operation", severity="critical")
        assert isinstance(msg, SystemMessage)
        assert "FOOLPROOF ALERT" in msg.content
        assert msg.additional_kwargs["type"] == MessageType.FOOLPROOF_ALERT
        assert msg.additional_kwargs["action"] == "delete_all"
        assert msg.additional_kwargs["severity"] == "critical"


# ══════════════════════════════════════════════════════════════════
# MessageHistory Tests
# ══════════════════════════════════════════════════════════════════


class TestMessageHistory:
    """Tests for MessageHistory."""

    def test_empty_history(self) -> None:
        history = MessageHistory()
        assert len(history.get_all()) == 0
        assert history.trace_id is not None

    def test_add_and_get_messages(self) -> None:
        history = MessageHistory()
        history.add(create_user_message("Hello"))
        history.add(create_worker_message("rag", "Found docs"))

        assert len(history.get_all()) == 2

    def test_filter_by_type(self) -> None:
        history = MessageHistory()
        history.add(create_user_message("Hello"))
        history.add(create_worker_message("rag", "Found docs"))
        history.add(create_worker_message("hr", "Error", is_error=True))

        user_msgs = history.get_by_type(MessageType.USER_INPUT)
        assert len(user_msgs) == 1

        worker_results = history.get_by_type(MessageType.WORKER_RESULT)
        assert len(worker_results) == 1

        errors = history.get_by_type(MessageType.WORKER_ERROR)
        assert len(errors) == 1

    def test_filter_by_worker(self) -> None:
        history = MessageHistory()
        history.add(create_worker_message("rag", "Result 1"))
        history.add(create_worker_message("hr", "Result 2"))
        history.add(create_worker_message("rag", "Result 3"))

        rag_msgs = history.get_by_worker("rag")
        assert len(rag_msgs) == 2

    def test_get_user_messages(self) -> None:
        history = MessageHistory()
        history.add(create_user_message("Hello"))
        history.add(create_worker_message("rag", "Result"))

        user_msgs = history.get_user_messages()
        assert len(user_msgs) == 1

    def test_get_worker_results(self) -> None:
        history = MessageHistory()
        history.add(create_worker_message("rag", "Result"))
        history.add(create_worker_message("hr", "Error", is_error=True))

        results = history.get_worker_results()
        assert len(results) == 1

    def test_get_errors(self) -> None:
        history = MessageHistory()
        history.add(create_worker_message("rag", "OK"))
        history.add(create_worker_message("hr", "Failed", is_error=True))

        errors = history.get_errors()
        assert len(errors) == 1

    def test_get_foolproof_alerts(self) -> None:
        history = MessageHistory()
        history.add(create_foolproof_alert("delete", "Dangerous"))
        history.add(create_user_message("Hello"))

        alerts = history.get_foolproof_alerts()
        assert len(alerts) == 1

    def test_clear(self) -> None:
        history = MessageHistory()
        history.add(create_user_message("Hello"))
        history.clear()
        assert len(history.get_all()) == 0

    def test_to_dict(self) -> None:
        history = MessageHistory()
        history.add(create_user_message("Hello"))

        d = history.to_dict()
        assert "trace_id" in d
        assert d["message_count"] == 1
        assert len(d["messages"]) == 1

    def test_to_json(self) -> None:
        history = MessageHistory()
        history.add(create_user_message("Hello"))

        json_str = history.to_json()
        assert "trace_id" in json_str
        assert "Hello" in json_str
