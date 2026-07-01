"""Unified IM message models — cross-platform abstraction for WeCom/Feishu/DingTalk.

M2-T3: Defines the canonical message format that all platform adapters
translate to/from. This is the backbone of the IM Agent's type system.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ══════════════════════════════════════════════════════════════════
# Platform enum
# ══════════════════════════════════════════════════════════════════


class Platform(StrEnum):
    """Supported IM platforms."""

    WECOM = "wecom"  # 企业微信
    FEISHU = "feishu"  # 飞书
    DINGTALK = "dingtalk"  # 钉钉
    MOCK = "mock"  # 测试用


# ══════════════════════════════════════════════════════════════════
# Message types
# ══════════════════════════════════════════════════════════════════


class MessageType(StrEnum):
    """Types of IM messages."""

    TEXT = "text"
    MARKDOWN = "markdown"
    IMAGE = "image"
    FILE = "file"
    CARD = "card"  # Rich card (adaptive cards / template cards)
    EVENT = "event"  # System events (join/leave/bot added)


class MessageDirection(StrEnum):
    """Direction of message flow."""

    INBOUND = "inbound"  # Platform → FDE
    OUTBOUND = "outbound"  # FDE → Platform


# ══════════════════════════════════════════════════════════════════
# Unified message model
# ══════════════════════════════════════════════════════════════════


class IMSender(BaseModel):
    """Sender identity in a unified IM message."""

    user_id: str = Field(description="Platform user ID")
    display_name: str = Field(default="", description="User display name")
    platform: Platform = Field(description="Which IM platform")
    group_id: str | None = Field(default=None, description="Group chat ID if in a group")
    is_bot: bool = Field(default=False)


class IMContent(BaseModel):
    """Content payload of a unified IM message."""

    body: str = Field(default="", description="Main text/body content")
    mime_type: str = Field(default="text/plain", description="Content MIME type")
    attachments: list[IMAttachment] = Field(
        default_factory=list, description="File/image attachments"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Platform-specific or enriched metadata",
    )


class IMAttachment(BaseModel):
    """File or image attachment in an IM message."""

    name: str = Field(default="", description="File name")
    url: str = Field(default="", description="Download URL")
    content_type: str = Field(default="application/octet-stream")
    size_bytes: int = Field(default=0, ge=0)


class IMMessage(BaseModel):
    """Unified IM message — canonical format for all platforms.

    All platform adapters must convert their native formats to/from this model.
    """

    message_id: str = Field(description="Unique message ID (platform-native or generated)")
    platform: Platform = Field(description="Source/destination platform")
    direction: MessageDirection = Field(description="Inbound or outbound")
    message_type: MessageType = Field(default=MessageType.TEXT)
    sender: IMSender = Field(description="Message sender identity")
    content: IMContent = Field(default_factory=IMContent)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Message timestamp (UTC)",
    )
    reply_to: str | None = Field(default=None, description="Message ID being replied to")
    session_id: str | None = Field(
        default=None, description="FDE internal session ID for cross-platform sync"
    )
    raw_payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Original platform payload for debugging/replay",
    )


# ══════════════════════════════════════════════════════════════════
# Send request/response models
# ══════════════════════════════════════════════════════════════════


class IMSendRequest(BaseModel):
    """Request to send a message via a specific platform adapter."""

    platform: Platform = Field(description="Target IM platform")
    target_id: str = Field(description="Target user/group/chat ID")
    content: str = Field(description="Message content (text or markdown)")
    message_type: MessageType = Field(default=MessageType.TEXT)
    reply_to: str | None = Field(default=None)
    attachments: list[IMAttachment] = Field(default_factory=list)


class IMSendResponse(BaseModel):
    """Result of a message send operation."""

    success: bool
    message_id: str = Field(default="")
    platform: Platform
    error: str | None = Field(default=None)
    latency_ms: int = Field(default=0)


class IMBroadcastRequest(BaseModel):
    """Request to broadcast a message to multiple targets/platforms."""

    targets: list[IMSendRequest] = Field(description="List of send targets")
    group_by: str = Field(
        default="platform",
        description="Grouping strategy: 'platform' or 'sequential'",
    )


class IMBroadcastResponse(BaseModel):
    """Result of a broadcast operation."""

    total: int = Field(description="Total targets")
    succeeded: int = Field(default=0)
    failed: int = Field(default=0)
    results: list[IMSendResponse] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════════
# Session context model
# ══════════════════════════════════════════════════════════════════


class IMSession(BaseModel):
    """Cross-platform session context.

    Tracks a conversation across multiple IM platforms so users
    can switch between WeCom/Feishu/DingTalk without losing context.
    """

    session_id: str = Field(description="FDE internal session ID")
    user_id: str = Field(description="Unified user identifier")
    platforms: set[Platform] = Field(
        default_factory=set, description="Active platforms in this session"
    )
    messages: list[str] = Field(default_factory=list, description="Ordered list of message IDs")
    context: dict[str, Any] = Field(
        default_factory=dict, description="Conversation context (worker outputs, plan, etc.)"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_active: datetime = Field(default_factory=lambda: datetime.now(UTC))
