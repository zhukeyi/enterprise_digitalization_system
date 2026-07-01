"""IM Agent tools — message sending, broadcasting, and session queries (M2-T3).

All handlers are pure Python functions with zero IM API dependencies.
Production replacements would swap in real WeCom/Feishu/DingTalk API calls.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.im_agent.adapters import AdapterRegistry
from agents.im_agent.models import (
    IMBroadcastRequest,
    IMSendRequest,
    MessageType,
    Platform,
)

logger = logging.getLogger("fde.im.tools")

# Module-level registry (configured at startup)
_registry: AdapterRegistry = AdapterRegistry()


def get_registry() -> AdapterRegistry:
    """Get the global adapter registry.

    Call this to configure custom adapters at startup.
    """
    return _registry


def set_registry(registry: AdapterRegistry) -> None:
    """Replace the global adapter registry.

    Use in tests to inject mock registries.
    """
    global _registry
    _registry = registry


# ══════════════════════════════════════════════════════════════════
# Tool Handlers
# ══════════════════════════════════════════════════════════════════


async def _send_message_handler(
    platform: str = "mock",
    target_id: str = "",
    content: str = "",
    message_type: str = "text",
) -> dict[str, Any]:
    """Send a message to a specific IM target.

    Args:
        platform: Target platform (wecom, feishu, dingtalk, mock).
        target_id: Target user/group/chat ID.
        content: Message content (text or markdown).
        message_type: text or markdown.
    """
    if not target_id:
        return {"error": "target_id is required", "success": False}

    if not content:
        return {"error": "content is required", "success": False}

    try:
        plat = Platform(platform)
    except ValueError:
        return {
            "error": f"Unknown platform '{platform}'. " f"Valid: {[p.value for p in Platform]}",
            "success": False,
        }

    try:
        msg_type = MessageType(message_type)
    except ValueError:
        msg_type = MessageType.TEXT

    try:
        adapter = _registry.get(plat)
        response = await adapter.send(
            IMSendRequest(
                platform=plat,
                target_id=target_id,
                content=content,
                message_type=msg_type,
            )
        )

        return {
            "success": response.success,
            "message_id": response.message_id,
            "platform": response.platform.value,
            "latency_ms": response.latency_ms,
            "note": "Mock send — production uses real IM platform APIs",
        }
    except Exception as e:
        logger.error("Failed to send message via %s: %s", platform, e)
        return {"error": str(e), "success": False}


async def _broadcast_handler(
    targets: list[dict[str, Any]],
) -> dict[str, Any]:
    """Broadcast a message to multiple IM targets/platforms.

    Args:
        targets: List of {platform, target_id, content, message_type} dicts.
    """
    if not targets:
        return {"error": "targets list is required", "success": False}

    send_requests: list[IMSendRequest] = []
    errors: list[str] = []

    for i, t in enumerate(targets):
        try:
            platform_str = t.get("platform", "mock")
            plat = Platform(platform_str)
            msg_type_str = t.get("message_type", "text")
            try:
                msg_type = MessageType(msg_type_str)
            except ValueError:
                msg_type = MessageType.TEXT

            send_requests.append(
                IMSendRequest(
                    platform=plat,
                    target_id=t.get("target_id", f"target-{i}"),
                    content=t.get("content", ""),
                    message_type=msg_type,
                )
            )
        except ValueError as e:
            errors.append(f"Target[{i}]: {e}")

    if not send_requests:
        return {"error": f"All targets invalid: {errors}", "success": False}

    try:
        broadcast = IMBroadcastRequest(targets=send_requests)
        response = await _registry.broadcast(broadcast)

        result = {
            "total": response.total,
            "succeeded": response.succeeded,
            "failed": response.failed,
            "results": [
                {
                    "platform": r.platform.value,
                    "success": r.success,
                    "message_id": r.message_id,
                    "error": r.error,
                }
                for r in response.results
            ],
            "note": "Mock broadcast — production uses real IM platform APIs",
        }

        if errors:
            result["parse_errors"] = errors

        return result
    except Exception as e:
        logger.error("Broadcast failed: %s", e)
        return {"error": str(e), "success": False}


async def _query_session_handler(
    session_id: str = "",
) -> dict[str, Any]:
    """Query cross-platform session context.

    Args:
        session_id: FDE internal session identifier.
    """
    if not session_id:
        return {"error": "session_id is required", "success": False}

    # Try all adapters for the session
    for platform in Platform:
        try:
            adapter = _registry.get(platform)
            session = await adapter.get_session(session_id)
            if session is not None:
                return {
                    "found": True,
                    "session_id": session.session_id,
                    "user_id": session.user_id,
                    "platforms": [p.value for p in session.platforms],
                    "message_count": len(session.messages),
                    "created_at": session.created_at.isoformat(),
                    "last_active": session.last_active.isoformat(),
                    "note": "Mock session — production uses Redis",
                }
        except KeyError:
            continue

    return {
        "found": False,
        "session_id": session_id,
        "message": "Session not found in any adapter",
        "note": "Mock session — production uses Redis",
    }
