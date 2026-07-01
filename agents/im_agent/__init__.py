"""IM Agent — Unified message hub for WeCom / Feishu / DingTalk.

M2-T3: Multi-platform IM integration with cross-platform session sync.

Tools:
- send_message: Send messages to IM targets (platform-agnostic)
- broadcast: Broadcast messages to multiple targets
- query_session: Query cross-platform session context
"""

from agents.im_agent.worker import register_im_tools

__all__ = ["register_im_tools"]
