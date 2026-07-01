"""Platform adapter ABC for IM Agent (M2-T3).

Defines the abstract interface that all IM platform adapters (WeCom, Feishu,
DingTalk) must implement. Each adapter handles:
1. Receiving messages (webhook/event → IMMessage)
2. Sending messages (IMMessage → platform API)
3. Session sync (cross-platform context)
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any

from agents.im_agent.models import (
    IMBroadcastRequest,
    IMBroadcastResponse,
    IMContent,
    IMMessage,
    IMSender,
    IMSendRequest,
    IMSendResponse,
    IMSession,
    MessageDirection,
    Platform,
)

# ══════════════════════════════════════════════════════════════════
# Abstract Base Adapter
# ══════════════════════════════════════════════════════════════════


class BaseIMAdapter(ABC):
    """Abstract base for all IM platform adapters."""

    platform: Platform  # Must be set by subclass

    @abstractmethod
    async def send(self, request: IMSendRequest) -> IMSendResponse:
        """Send a message via the platform.

        Args:
            request: Unified send request with target and content.

        Returns:
            Send response with success status and platform message ID.
        """
        ...

    @abstractmethod
    async def receive(self, raw_payload: dict[str, Any]) -> IMMessage:
        """Parse a platform-native webhook/event payload into a unified message.

        Args:
            raw_payload: Raw JSON from the platform's webhook callback.

        Returns:
            Normalized IMMessage.
        """
        ...

    @abstractmethod
    async def get_session(self, session_id: str) -> IMSession | None:
        """Retrieve session context for a given session ID.

        Args:
            session_id: FDE internal session identifier.

        Returns:
            Session object or None if not found.
        """
        ...

    @abstractmethod
    async def save_session(self, session: IMSession) -> None:
        """Persist session context.

        Args:
            session: Session object to save.
        """
        ...

    @staticmethod
    def _generate_message_id() -> str:
        return f"msg-{uuid.uuid4().hex[:12]}"


# ══════════════════════════════════════════════════════════════════
# Mock Adapters (for development and testing)
# ══════════════════════════════════════════════════════════════════


class MockAdapter(BaseIMAdapter):
    """Mock IM adapter for local development and testing.

    Simulates message sending and receiving without any external API calls.
    Stores sessions in memory.
    """

    platform = Platform.MOCK

    def __init__(self) -> None:
        self._sessions: dict[str, IMSession] = {}
        self._sent_messages: list[IMMessage] = []
        self._call_count_send: int = 0
        self._call_count_receive: int = 0

    async def send(self, request: IMSendRequest) -> IMSendResponse:
        self._call_count_send += 1
        msg_id = self._generate_message_id()

        msg = IMMessage(
            message_id=msg_id,
            platform=self.platform,
            direction=MessageDirection.OUTBOUND,
            content=IMContent(body=request.content),
            sender=IMSender(
                user_id="bot",
                display_name="FDE Bot",
                platform=self.platform,
                is_bot=True,
            ),
        )
        self._sent_messages.append(msg)

        return IMSendResponse(
            success=True,
            message_id=msg_id,
            platform=self.platform,
            latency_ms=5,
        )

    async def receive(self, raw_payload: dict[str, Any]) -> IMMessage:
        self._call_count_receive += 1

        return IMMessage(
            message_id=raw_payload.get("message_id", self._generate_message_id()),
            platform=self.platform,
            direction=MessageDirection.INBOUND,
            message_type=raw_payload.get("message_type", "text"),
            sender=IMSender(
                user_id=raw_payload.get("user_id", "mock-user"),
                display_name=raw_payload.get("display_name", "Mock User"),
                platform=self.platform,
            ),
            content=IMContent(
                body=raw_payload.get("content", raw_payload.get("text", "")),
            ),
            raw_payload=raw_payload,
        )

    async def get_session(self, session_id: str) -> IMSession | None:
        return self._sessions.get(session_id)

    async def save_session(self, session: IMSession) -> None:
        self._sessions[session.session_id] = session

    @property
    def call_count_send(self) -> int:
        return self._call_count_send

    @property
    def call_count_receive(self) -> int:
        return self._call_count_receive

    @property
    def sent_messages(self) -> list[IMMessage]:
        return list(self._sent_messages)


class WeComStubAdapter(MockAdapter):
    """企业微信适配器桩 — same as MockAdapter but with WeCom platform tag.

    In production, this would:
    - Receive: Parse WeCom XML callbacks, verify CorpID signature
    - Send: Call WeCom API /cgi-bin/message/send with access_token
    - Session: Use WeCom external_userid as session key
    """

    platform = Platform.WECOM


class FeishuStubAdapter(MockAdapter):
    """飞书适配器桩 — same as MockAdapter but with Feishu platform tag.

    In production, this would:
    - Receive: Verify Feishu event subscription (challenge/verification)
    - Send: Call Feishu API /open-apis/im/v1/messages with tenant_access_token
    - Session: Use Feishu open_id as session key
    """

    platform = Platform.FEISHU


class DingTalkStubAdapter(MockAdapter):
    """钉钉适配器桩 — same as MockAdapter but with DingTalk platform tag.

    In production, this would:
    - Receive: Verify DingTalk webhook HMAC-SHA256 signature
    - Send: Call DingTalk robot webhook with sign/timestamp
    - Session: Use DingTalk userId as session key
    """

    platform = Platform.DINGTALK


# ══════════════════════════════════════════════════════════════════
# Adapter Registry — factory for platform adapters
# ══════════════════════════════════════════════════════════════════


class AdapterRegistry:
    """Manages platform adapters and provides broadcast capability.

    In production, adapters would be configured with platform credentials
    (app_id, app_secret, webhook_url, etc.) from environment variables.
    """

    def __init__(self) -> None:
        self._adapters: dict[Platform, BaseIMAdapter] = {
            Platform.MOCK: MockAdapter(),
            Platform.WECOM: WeComStubAdapter(),
            Platform.FEISHU: FeishuStubAdapter(),
            Platform.DINGTALK: DingTalkStubAdapter(),
        }

    def get(self, platform: Platform) -> BaseIMAdapter:
        """Get the adapter for a specific platform.

        Raises:
            KeyError: If the platform has no registered adapter.
        """
        adapter = self._adapters.get(platform)
        if adapter is None:
            raise KeyError(f"No adapter registered for platform '{platform}'")
        return adapter

    def register(self, platform: Platform, adapter: BaseIMAdapter) -> None:
        """Register or override an adapter."""
        self._adapters[platform] = adapter

    async def broadcast(self, request: IMBroadcastRequest) -> IMBroadcastResponse:
        """Broadcast a message to multiple targets.

        Sends messages concurrently to all targets via their platform adapters.
        """
        import asyncio

        async def _send_one(req: IMSendRequest) -> IMSendResponse:
            try:
                adapter = self.get(req.platform)
                return await adapter.send(req)
            except Exception as e:
                return IMSendResponse(
                    success=False,
                    platform=req.platform,
                    error=str(e),
                )

        results = await asyncio.gather(*(_send_one(t) for t in request.targets))

        succeeded = sum(1 for r in results if r.success)
        failed = len(results) - succeeded

        return IMBroadcastResponse(
            total=len(request.targets),
            succeeded=succeeded,
            failed=failed,
            results=list(results),
        )
