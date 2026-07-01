"""IM Agent tool registration (M2-T3).

Registers IM tools (send_message, broadcast, query_session) with the
orchestrator ToolRegistry. The IMWorker class lives in orchestrator's
workers.py to avoid circular imports.
"""

from __future__ import annotations

import logging

from agents.orchestrator.tools.registry import ToolDefinition, ToolRegistry

logger = logging.getLogger("fde.im.integration")


def register_im_tools(registry: ToolRegistry) -> None:
    """Register all IM agent tools with the orchestrator registry.

    M2-T3: Connects IM tools to the Supervisor-Worker framework.

    Args:
        registry: The orchestrator's ToolRegistry instance.
    """
    from agents.im_agent.tools import (
        _broadcast_handler,
        _query_session_handler,
        _send_message_handler,
    )

    registry.register(
        ToolDefinition(
            name="send_message",
            description="Send a message to a user or group on WeCom/Feishu/DingTalk",
            worker="im",
            handler=_send_message_handler,
            parameters={
                "platform": {
                    "type": "string",
                    "required": False,
                    "default": "mock",
                    "description": "Target platform: wecom, feishu, dingtalk, mock",
                },
                "target_id": {
                    "type": "string",
                    "required": True,
                    "description": "Target user ID, group ID, or chat ID",
                },
                "content": {
                    "type": "string",
                    "required": True,
                    "description": "Message content (text or markdown)",
                },
                "message_type": {
                    "type": "string",
                    "required": False,
                    "default": "text",
                    "description": "text or markdown",
                },
            },
            category="messaging",
        )
    )

    registry.register(
        ToolDefinition(
            name="broadcast",
            description="Broadcast a message to multiple IM targets across platforms",
            worker="im",
            handler=_broadcast_handler,
            parameters={
                "targets": {
                    "type": "array",
                    "required": True,
                    "description": "List of {platform, target_id, content, message_type} objects",
                },
            },
            category="messaging",
        )
    )

    registry.register(
        ToolDefinition(
            name="query_session",
            description="Query cross-platform IM session context by session ID",
            worker="im",
            handler=_query_session_handler,
            parameters={
                "session_id": {
                    "type": "string",
                    "required": True,
                    "description": "FDE internal session identifier",
                },
            },
            category="messaging",
        )
    )

    logger.info(
        "Registered %d IM tools",
        len(registry.get_tools_for_worker("im")),
    )
