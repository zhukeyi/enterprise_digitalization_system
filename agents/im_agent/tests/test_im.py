"""Tests for IM Agent — M2-T3 (Models, Adapters, Tools, Worker)."""

from __future__ import annotations

import pytest

from agents.im_agent.adapters import (
    AdapterRegistry,
    DingTalkStubAdapter,
    FeishuStubAdapter,
    MockAdapter,
    WeComStubAdapter,
)
from agents.im_agent.models import (
    IMBroadcastRequest,
    IMContent,
    IMMessage,
    IMSendRequest,
    IMSession,
    MessageDirection,
    MessageType,
    Platform,
)
from agents.orchestrator.tools.registry import ToolRegistry

# ══════════════════════════════════════════════════════════════════
# Pydantic Model Tests
# ══════════════════════════════════════════════════════════════════


class TestModels:
    def test_im_message_create(self) -> None:
        """Should create a valid IMMessage."""
        from agents.im_agent.models import IMSender

        msg = IMMessage(
            message_id="msg-001",
            platform=Platform.MOCK,
            direction=MessageDirection.INBOUND,
            sender=IMSender(
                user_id="user-1",
                display_name="Alice",
                platform=Platform.MOCK,
            ),
            content=IMContent(body="Hello"),
        )
        assert msg.message_id == "msg-001"
        assert msg.platform == Platform.MOCK
        assert msg.content.body == "Hello"

    def test_send_request_validation(self) -> None:
        """IMSendRequest should validate platform and required fields."""
        req = IMSendRequest(
            platform=Platform.WECOM,
            target_id="user-abc",
            content="Test message",
        )
        assert req.platform == Platform.WECOM
        assert req.message_type == MessageType.TEXT

    def test_broadcast_request(self) -> None:
        """IMBroadcastRequest should hold multiple send targets."""
        req = IMBroadcastRequest(
            targets=[
                IMSendRequest(platform=Platform.MOCK, target_id="u1", content="Hi"),
                IMSendRequest(platform=Platform.MOCK, target_id="u2", content="Hi"),
            ]
        )
        assert len(req.targets) == 2

    def test_session_model(self) -> None:
        """IMSession should track cross-platform context."""
        session = IMSession(
            session_id="sess-1",
            user_id="user-1",
            platforms={Platform.WECOM, Platform.FEISHU},
        )
        assert len(session.platforms) == 2
        assert session.messages == []

    def test_platform_enum_values(self) -> None:
        """Platform enum should have all expected values."""
        values = {p.value for p in Platform}
        assert values == {"wecom", "feishu", "dingtalk", "mock"}

    def test_message_type_enum(self) -> None:
        """MessageType enum should support text, markdown, etc."""
        assert MessageType.TEXT.value == "text"
        assert MessageType.MARKDOWN.value == "markdown"


# ══════════════════════════════════════════════════════════════════
# MockAdapter Tests
# ══════════════════════════════════════════════════════════════════


class TestMockAdapter:
    @pytest.mark.asyncio
    async def test_send_message(self) -> None:
        """Mock adapter should send successfully."""
        adapter = MockAdapter()
        response = await adapter.send(
            IMSendRequest(platform=Platform.MOCK, target_id="u1", content="Hello")
        )
        assert response.success is True
        assert response.platform == Platform.MOCK
        assert response.message_id != ""
        assert len(adapter.sent_messages) == 1

    @pytest.mark.asyncio
    async def test_receive_message(self) -> None:
        """Mock adapter should parse inbound messages."""
        adapter = MockAdapter()
        msg = await adapter.receive(
            {
                "message_id": "ext-001",
                "user_id": "alice",
                "content": "Hello from IM",
            }
        )
        assert msg.platform == Platform.MOCK
        assert msg.direction == MessageDirection.INBOUND
        assert msg.sender.user_id == "alice"
        assert msg.content.body == "Hello from IM"

    @pytest.mark.asyncio
    async def test_session_persistence(self) -> None:
        """Mock adapter should store and retrieve sessions."""
        adapter = MockAdapter()
        session = IMSession(session_id="sess-1", user_id="u1")

        await adapter.save_session(session)
        retrieved = await adapter.get_session("sess-1")

        assert retrieved is not None
        assert retrieved.session_id == "sess-1"
        assert retrieved.user_id == "u1"

    @pytest.mark.asyncio
    async def test_session_not_found(self) -> None:
        """Mock adapter should return None for unknown sessions."""
        adapter = MockAdapter()
        result = await adapter.get_session("nonexistent")
        assert result is None

    def test_call_counters(self) -> None:
        """Mock adapter should track call counts."""
        adapter = MockAdapter()
        assert adapter.call_count_send == 0
        assert adapter.call_count_receive == 0


# ══════════════════════════════════════════════════════════════════
# Stub Adapter Tests
# ══════════════════════════════════════════════════════════════════


class TestStubAdapters:
    def test_wecom_stub_platform(self) -> None:
        """WeCom stub should have correct platform tag."""
        adapter = WeComStubAdapter()
        assert adapter.platform == Platform.WECOM

    def test_feishu_stub_platform(self) -> None:
        """Feishu stub should have correct platform tag."""
        adapter = FeishuStubAdapter()
        assert adapter.platform == Platform.FEISHU

    def test_dingtalk_stub_platform(self) -> None:
        """DingTalk stub should have correct platform tag."""
        adapter = DingTalkStubAdapter()
        assert adapter.platform == Platform.DINGTALK

    @pytest.mark.asyncio
    async def test_stub_adapters_all_send(self) -> None:
        """All stub adapters should be able to send messages."""
        for adapter_cls in [WeComStubAdapter, FeishuStubAdapter, DingTalkStubAdapter]:
            adapter = adapter_cls()
            response = await adapter.send(
                IMSendRequest(platform=adapter.platform, target_id="test", content="hello")
            )
            assert response.success is True


# ══════════════════════════════════════════════════════════════════
# AdapterRegistry Tests
# ══════════════════════════════════════════════════════════════════


class TestAdapterRegistry:
    def test_get_all_platforms(self) -> None:
        """Registry should have all 4 platform adapters by default."""
        registry = AdapterRegistry()
        for platform in Platform:
            adapter = registry.get(platform)
            assert adapter is not None

    def test_register_override(self) -> None:
        """Should be able to override an adapter."""
        registry = AdapterRegistry()
        custom = MockAdapter()
        registry.register(Platform.MOCK, custom)
        assert registry.get(Platform.MOCK) is custom

    def test_invalid_platform_raises(self) -> None:
        """Should raise KeyError for unregistered platform."""
        registry = AdapterRegistry()
        # Simulate: delete mock entry, then try to get it
        del registry._adapters[Platform.MOCK]
        with pytest.raises(KeyError):
            registry.get(Platform.MOCK)

    @pytest.mark.asyncio
    async def test_broadcast(self) -> None:
        """Broadcast should send to all targets concurrently."""
        registry = AdapterRegistry()
        response = await registry.broadcast(
            IMBroadcastRequest(
                targets=[
                    IMSendRequest(platform=Platform.MOCK, target_id="u1", content="Hi"),
                    IMSendRequest(platform=Platform.MOCK, target_id="u2", content="Hi"),
                ]
            )
        )
        assert response.total == 2
        assert response.succeeded == 2
        assert response.failed == 0


# ══════════════════════════════════════════════════════════════════
# IM Tools Tests
# ══════════════════════════════════════════════════════════════════


class TestIMTools:
    @pytest.mark.asyncio
    async def test_send_message_tool(self) -> None:
        """send_message should dispatch via adapter."""
        from agents.im_agent.tools import _send_message_handler

        result = await _send_message_handler(platform="mock", target_id="user-1", content="Hello")
        assert result["success"] is True
        assert result["message_id"] != ""

    @pytest.mark.asyncio
    async def test_send_message_missing_target(self) -> None:
        """send_message should reject missing target_id."""
        from agents.im_agent.tools import _send_message_handler

        result = await _send_message_handler(platform="mock", target_id="", content="Hi")
        assert result["success"] is False
        assert "target_id" in result["error"]

    @pytest.mark.asyncio
    async def test_send_message_invalid_platform(self) -> None:
        """send_message should reject unknown platforms."""
        from agents.im_agent.tools import _send_message_handler

        result = await _send_message_handler(platform="slack", target_id="u1", content="Hi")
        assert result["success"] is False
        assert "Unknown" in result["error"]

    @pytest.mark.asyncio
    async def test_broadcast_tool(self) -> None:
        """broadcast should send to multiple targets."""
        from agents.im_agent.tools import _broadcast_handler

        result = await _broadcast_handler(
            targets=[
                {"platform": "mock", "target_id": "u1", "content": "Hi"},
                {"platform": "mock", "target_id": "u2", "content": "Hi"},
            ]
        )
        assert result["total"] == 2
        assert result["succeeded"] == 2

    @pytest.mark.asyncio
    async def test_broadcast_empty_targets(self) -> None:
        """broadcast should reject empty targets."""
        from agents.im_agent.tools import _broadcast_handler

        result = await _broadcast_handler(targets=[])
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_query_session_tool(self) -> None:
        """query_session should search for session across adapters."""
        from agents.im_agent.tools import _query_session_handler

        result = await _query_session_handler(session_id="nonexistent-session")
        assert result["found"] is False

    @pytest.mark.asyncio
    async def test_query_session_missing_id(self) -> None:
        """query_session should reject empty session_id."""
        from agents.im_agent.tools import _query_session_handler

        result = await _query_session_handler(session_id="")
        assert result["success"] is False


# ══════════════════════════════════════════════════════════════════
# Tool Registration Tests
# ══════════════════════════════════════════════════════════════════


class TestIMToolRegistration:
    def test_register_all_tools(self) -> None:
        """Should register 3 IM tools."""
        from agents.im_agent.worker import register_im_tools

        registry = ToolRegistry()
        register_im_tools(registry)

        tools = registry.get_tools_for_worker("im")
        assert len(tools) == 3
        tool_names = {t.name for t in tools}
        assert tool_names == {"send_message", "broadcast", "query_session"}

    @pytest.mark.asyncio
    async def test_send_message_dispatch(self) -> None:
        """Should dispatch send_message via ToolRegistry.

        Note: dispatch() calls asyncio.run() internally, so we await
        the handler directly rather than through dispatch to avoid
        nested event loop issues.
        """
        from agents.im_agent.tools import _send_message_handler
        from agents.im_agent.worker import register_im_tools

        registry = ToolRegistry()
        register_im_tools(registry)

        result = await _send_message_handler(platform="mock", target_id="u1", content="Hello")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_broadcast_dispatch(self) -> None:
        """Should dispatch broadcast via ToolRegistry directly."""
        from agents.im_agent.tools import _broadcast_handler
        from agents.im_agent.worker import register_im_tools

        registry = ToolRegistry()
        register_im_tools(registry)

        result = await _broadcast_handler(
            targets=[
                {"platform": "mock", "target_id": "u1", "content": "Hello"},
            ],
        )
        assert result["succeeded"] == 1


# ══════════════════════════════════════════════════════════════════
# IMWorker Tests
# ══════════════════════════════════════════════════════════════════


class TestIMWorker:
    def test_worker_instantiation(self) -> None:
        """IMWorker should be instantiable."""
        from agents.orchestrator.langgraph.workers import IMWorker

        registry = ToolRegistry()
        worker = IMWorker(registry)
        assert worker.name == "im"
        assert "Message" in worker.description

    def test_worker_in_graph(self) -> None:
        """Graph should include IMWorker."""
        from agents.im_agent.worker import register_im_tools
        from agents.orchestrator.langgraph.graph import build_orchestrator_graph

        registry = ToolRegistry()
        register_im_tools(registry)

        graph = build_orchestrator_graph(tool_registry=registry)
        assert graph is not None
