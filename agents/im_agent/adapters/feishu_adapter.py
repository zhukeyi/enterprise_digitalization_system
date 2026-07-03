"""飞书 (Feishu/Lark) 平台适配器 —— 完整实现.

对接飞书开放平台 API:
- 发送: POST /open-apis/im/v1/messages (需 tenant_access_token)
- 接收: 事件订阅 URL 验证 (challenge) + 事件回调
- 会话: 内存存储

API 文档: https://open.feishu.cn/document/server-docs/im-v1/message/create
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

from agents.im_agent.adapters import BaseIMAdapter
from agents.im_agent.models import (
    IMAttachment,
    IMContent,
    IMMessage,
    IMSender,
    IMSendRequest,
    IMSendResponse,
    IMSession,
    MessageDirection,
    MessageType,
    Platform,
)

logger = logging.getLogger("fde.im.feishu")

# ══════════════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════════════


def _get_config(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


FEISHU_APP_ID = _get_config("FEISHU_APP_ID")
FEISHU_APP_SECRET = _get_config("FEISHU_APP_SECRET")
FEISHU_VERIFICATION_TOKEN = _get_config("FEISHU_VERIFICATION_TOKEN")
FEISHU_API_BASE = _get_config("FEISHU_API_BASE", "https://open.feishu.cn")

# Tenant access token cache
_token_cache: dict[str, tuple[str, float]] = {}


# ══════════════════════════════════════════════════════════════════
# Access Token Management
# ══════════════════════════════════════════════════════════════════


async def _get_tenant_access_token(http_client: httpx.AsyncClient) -> str:
    """Get or refresh Feishu tenant_access_token.

    Feishu tokens expire after 7200 seconds (2 hours).
    """
    cache_key = f"{FEISHU_APP_ID}:{FEISHU_APP_SECRET}"

    if cache_key in _token_cache:
        cached_token, expires_at = _token_cache[cache_key]
        if time.time() < expires_at - 300:
            return cached_token

    url = f"{FEISHU_API_BASE}/open-apis/auth/v3/tenant_access_token/internal"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    body = {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}

    response = await http_client.post(url, json=body, headers=headers)
    data = response.json()

    if data.get("code") != 0:
        raise RuntimeError(
            f"Feishu get token failed: code={data.get('code')} "
            f"msg={data.get('msg')}"
        )

    token: str = data["tenant_access_token"]
    expires_in = data.get("expire", 7200)
    _token_cache[cache_key] = (token, time.time() + expires_in)

    logger.info("Feishu tenant_access_token refreshed, expires in %ds", expires_in)
    return token


# ══════════════════════════════════════════════════════════════════
# Event Challenge Utility
# ══════════════════════════════════════════════════════════════════


def _verify_event_challenge(token: str, challenge: str) -> str | None:
    """Verify Feishu event subscription challenge.

    Returns the challenge string if token matches the request token, None otherwise.
    """
    # token here is the expected token (from env), challenge is from Feishu
    if token == challenge:
        return challenge
    logger.warning("Feishu event challenge verification failed")
    return None


# ══════════════════════════════════════════════════════════════════
# Feishu Adapter
# ══════════════════════════════════════════════════════════════════


class FeishuAdapter(BaseIMAdapter):
    """飞书应用消息适配器.

    对接飞书服务端 API, 支持:
    - 文本消息发送 (text)
    - Markdown 消息发送 (interactive / post)
    - 富文本消息 (post)
    - 事件订阅 URL 验证 (challenge)
    - 事件回调接收 (message/event)
    - 会话管理
    """

    platform = Platform.FEISHU

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        app_id: str | None = None,
        app_secret: str | None = None,
    ) -> None:
        self._client = http_client or httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        self._app_id = app_id or FEISHU_APP_ID
        self._app_secret = app_secret or FEISHU_APP_SECRET
        self._sessions: dict[str, IMSession] = {}
        self._call_count_send: int = 0
        self._call_count_receive: int = 0

    # ══════════════════════════════════════════════════════════════
    # Send
    # ══════════════════════════════════════════════════════════════

    async def send(self, request: IMSendRequest) -> IMSendResponse:
        """Send a message via Feishu API.

        API: POST /open-apis/im/v1/messages?receive_id_type=open_id
        """
        self._call_count_send += 1
        start_time = time.time()

        try:
            url = f"{FEISHU_API_BASE}/open-apis/im/v1/messages"
            params = {"receive_id_type": "open_id"}

            token = await _get_tenant_access_token(self._client)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            }

            msg_body = self._build_message_body(request)

            response = await self._client.post(url, json=msg_body, headers=headers, params=params)
            data = response.json()
            latency_ms = int((time.time() - start_time) * 1000)

            if data.get("code") == 0:
                msg_data = data.get("data", {})
                msg_id = msg_data.get("message_id", self._generate_message_id())
                return IMSendResponse(
                    success=True,
                    message_id=msg_id,
                    platform=Platform.FEISHU,
                    latency_ms=latency_ms,
                )
            else:
                return IMSendResponse(
                    success=False,
                    platform=Platform.FEISHU,
                    error=f"code={data.get('code')} msg={data.get('msg')}",
                    latency_ms=latency_ms,
                )
        except Exception as e:
            logger.exception("Feishu send failed: %s", e)
            return IMSendResponse(
                success=False,
                platform=Platform.FEISHU,
                error=str(e),
            )

    def _build_message_body(self, request: IMSendRequest) -> dict[str, Any]:
        """Build Feishu API message body."""
        body: dict[str, Any] = {
            "receive_id": request.target_id,
            "msg_type": request.message_type.value,
        }

        content = request.content

        if request.message_type == MessageType.TEXT:
            body["content"] = json.dumps({"text": content})
        elif request.message_type == MessageType.MARKDOWN:
            # Feishu uses "interactive" instead of "markdown"
            body["msg_type"] = "interactive"
            body["content"] = json.dumps({
                "config": {"wide_screen_mode": True},
                "elements": [{
                    "tag": "markdown",
                    "content": content,
                }],
                "header": {
                    "title": {"tag": "plain_text", "content": "FDE AI Assistant"},
                },
            })
        elif request.message_type == MessageType.IMAGE:
            body["msg_type"] = "image"
            image_key = request.attachments[0].url if request.attachments else content
            body["content"] = json.dumps({"image_key": image_key})
        elif request.message_type == MessageType.CARD:
            body["msg_type"] = "interactive"
            body["content"] = json.dumps({
                "header": {
                    "title": {"tag": "plain_text", "content": content[:128]},
                },
                "elements": [],
            })
        elif request.message_type == MessageType.FILE:
            body["msg_type"] = "file"
            file_key = request.attachments[0].url if request.attachments else content
            body["content"] = json.dumps({"file_key": file_key})
        else:
            body["msg_type"] = "text"
            body["content"] = json.dumps({"text": content})

        return body

    # ══════════════════════════════════════════════════════════════
    # Receive (Event Callback)
    # ══════════════════════════════════════════════════════════════

    async def receive(self, raw_payload: dict[str, Any]) -> IMMessage:
        """Parse Feishu event callback into unified IMMessage.

        Feishu sends events with envelope: {"schema": "2.0", "header": {...}, "event": {...}}
        """
        self._call_count_receive += 1

        # Extract event from envelope
        event = raw_payload.get("event", raw_payload)
        header: dict[str, str] = raw_payload.get("header", {})

        event_type = event.get("type", "message")
        msg_id = header.get("event_id", event.get("event_id", self._generate_message_id()))

        # Handle message events
        if event_type == "message":
            return self._parse_message_event(event, msg_id, raw_payload)

        # Handle other events (user added, app opened, etc.)
        return IMMessage(
            message_id=msg_id,
            platform=Platform.FEISHU,
            direction=MessageDirection.INBOUND,
            message_type=MessageType.EVENT,
            sender=IMSender(
                user_id=header.get("user_id", event.get("operator", {}).get("open_id", "unknown")),
                display_name="",
                platform=Platform.FEISHU,
            ),
            content=IMContent(
                body=json.dumps(event),
                metadata={"event_type": event_type},
            ),
            raw_payload=raw_payload,
        )

    def _parse_message_event(self, event: dict[str, Any], msg_id: str, raw_payload: dict[str, Any]) -> IMMessage:
        """Parse a Feishu message event."""
        sender_info = event.get("sender", {}).get("sender_id", {})
        user_id = (
            sender_info.get("open_id", "")
            or sender_info.get("user_id", "")
            or event.get("sender", {}).get("sender_open_id", "unknown")
        )

        msg_info = event.get("message", event)
        msg_type = msg_info.get("message_type", "text")
        content_json = msg_info.get("content", "{}")

        # Parse content JSON
        try:
            content_obj = json.loads(content_json) if isinstance(content_json, str) else content_json
        except (json.JSONDecodeError, TypeError):
            content_obj = {"text": str(content_json)}

        text_content = content_obj.get("text", "")
        if not text_content:
            # Try post (rich text) format
            post_content = content_obj.get("post", {})
            if post_content:
                paragraphs = post_content.get("zh_cn", {}).get("content", [])
                text_content = "\n".join(
                    " ".join(e.get("text", "") for e in p if isinstance(e, dict))
                    for p in paragraphs
                    if isinstance(p, list)
                )

        # Map Feishu msg_type to FDE
        type_mapping: dict[str, MessageType] = {
            "text": MessageType.TEXT,
            "image": MessageType.IMAGE,
            "file": MessageType.FILE,
            "post": MessageType.MARKDOWN,
            "interactive": MessageType.CARD,
            "audio": MessageType.TEXT,
        }
        mapped_type = type_mapping.get(msg_type, MessageType.TEXT)

        # Attachments
        attachments: list[IMAttachment] = []
        if msg_type == "image" and content_obj.get("image_key"):
            attachments.append(
                IMAttachment(
                    name=f"image_{msg_id}",
                    url=content_obj["image_key"],
                    content_type="image/jpeg",
                )
            )

        # Extract chat info
        group_id = event.get("chat_id") or msg_info.get("chat_id")

        return IMMessage(
            message_id=msg_id,
            platform=Platform.FEISHU,
            direction=MessageDirection.INBOUND,
            message_type=mapped_type,
            sender=IMSender(
                user_id=user_id,
                display_name=event.get("sender", {}).get("sender_name", ""),
                platform=Platform.FEISHU,
                group_id=group_id,
            ),
            content=IMContent(
                body=text_content,
                attachments=attachments,
                metadata={
                    "feishu_msg_type": msg_type,
                    "root_id": msg_info.get("root_id", ""),
                    "parent_id": msg_info.get("parent_id", ""),
                },
            ),
            raw_payload=raw_payload,
        )

    # ══════════════════════════════════════════════════════════════
    # Session Management
    # ══════════════════════════════════════════════════════════════

    async def get_session(self, session_id: str) -> IMSession | None:
        return self._sessions.get(session_id)

    async def save_session(self, session: IMSession) -> None:
        self._sessions[session.session_id] = session

    # ══════════════════════════════════════════════════════════════
    # Event Verification
    # ══════════════════════════════════════════════════════════════

    def verify_challenge(self, challenge: str) -> str | None:
        """Verify Feishu event subscription challenge and return challenge token.

        Returns:
            The challenge string if verification passes, None otherwise.
        """
        verify_token = os.environ.get("FEISHU_VERIFICATION_TOKEN", "")
        if not verify_token:
            logger.warning("FEISHU_VERIFICATION_TOKEN not set, accepting challenge")
            return challenge

        return _verify_event_challenge(verify_token, challenge)

    # ══════════════════════════════════════════════════════════════
    # Properties
    # ══════════════════════════════════════════════════════════════

    @property
    def is_configured(self) -> bool:
        return bool(self._app_id and self._app_secret)

    @property
    def call_count_send(self) -> int:
        return self._call_count_send

    @property
    def call_count_receive(self) -> int:
        return self._call_count_receive

    @property
    def session_count(self) -> int:
        return len(self._sessions)


# ══════════════════════════════════════════════════════════════════
# Factory
# ══════════════════════════════════════════════════════════════════


def create_feishu_adapter(
    http_client: httpx.AsyncClient | None = None,
) -> FeishuAdapter:
    """Create a Feishu adapter from environment variables."""
    adapter = FeishuAdapter(http_client=http_client)
    if not adapter.is_configured:
        logger.warning(
            "Feishu adapter created but not fully configured. "
            "Set FEISHU_APP_ID, FEISHU_APP_SECRET."
        )
    return adapter


# Need json at module level for _build_message_body
import json  # noqa: E402
