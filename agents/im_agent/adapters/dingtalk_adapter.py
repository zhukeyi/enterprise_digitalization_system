"""钉钉 (DingTalk) 平台适配器 —— 完整实现.

对接钉钉开放平台:
- 发送: POST robot webhook (sign + timestamp)
- 接收: 回调 Webhook 签名验证 + 消息解析
- 会话: 内存存储

API 文档: https://open.dingtalk.com/document/orgapp/custom-robot-access
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import time
from typing import Any
from urllib.parse import quote_plus

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

logger = logging.getLogger("fde.im.dingtalk")

# ══════════════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════════════


def _get_config(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


DINGTALK_APP_KEY = _get_config("DINGTALK_APP_KEY")
DINGTALK_APP_SECRET = _get_config("DINGTALK_APP_SECRET")
DINGTALK_WEBHOOK_URL = _get_config("DINGTALK_WEBHOOK_URL")
DINGTALK_WEBHOOK_SECRET = _get_config("DINGTALK_WEBHOOK_SECRET")
DINGTALK_API_BASE = _get_config("DINGTALK_API_BASE", "https://oapi.dingtalk.com")

# Access token cache
_token_cache: dict[str, tuple[str, float]] = {}


# ══════════════════════════════════════════════════════════════════
# Access Token Management
# ══════════════════════════════════════════════════════════════════


async def _get_access_token(http_client: httpx.AsyncClient) -> str:
    """Get or refresh DingTalk access_token."""
    cache_key = f"{DINGTALK_APP_KEY}:{DINGTALK_APP_SECRET}"

    if cache_key in _token_cache:
        cached_token, expires_at = _token_cache[cache_key]
        if time.time() < expires_at - 300:
            return cached_token

    url = f"{DINGTALK_API_BASE}/gettoken"
    params = {"appkey": DINGTALK_APP_KEY, "appsecret": DINGTALK_APP_SECRET}

    response = await http_client.get(url, params=params)
    data = response.json()

    if data.get("errcode") != 0:
        raise RuntimeError(
            f"DingTalk gettoken failed: errcode={data.get('errcode')} "
            f"errmsg={data.get('errmsg')}"
        )

    token: str = data["access_token"]
    expires_in = data.get("expires_in", 7200)
    _token_cache[cache_key] = (token, time.time() + expires_in)

    logger.info("DingTalk access_token refreshed, expires in %ds", expires_in)
    return token


# ══════════════════════════════════════════════════════════════════
# Signature Utilities
# ══════════════════════════════════════════════════════════════════


def _compute_webhook_sign(secret: str) -> tuple[str, str]:
    """Compute DingTalk webhook signature.

    Uses HMAC-SHA256 with Base64 encoding.

    Returns:
        (timestamp, sign) tuple.
    """
    timestamp = str(int(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sign = quote_plus(base64.b64encode(hmac_code).decode())
    return timestamp, sign


def _verify_callback_signature(timestamp: str, sign: str, secret: str) -> bool:
    """Verify DingTalk callback signature."""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    expected = base64.b64encode(hmac_code).decode()
    return sign == expected


# ══════════════════════════════════════════════════════════════════
# DingTalk Adapter
# ══════════════════════════════════════════════════════════════════


class DingTalkAdapter(BaseIMAdapter):
    """钉钉应用消息适配器.

    对接钉钉开放平台, 支持:
    - 文本消息发送 (text)
    - Markdown 消息发送 (markdown)
    - 链接消息发送 (link)
    - ActionCard 消息发送
    - Webhook 签名 + 回调验证
    - 会话管理
    """

    platform = Platform.DINGTALK

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        app_key: str | None = None,
        app_secret: str | None = None,
        webhook_url: str | None = None,
        webhook_secret: str | None = None,
    ) -> None:
        self._client = http_client or httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        self._app_key = app_key or DINGTALK_APP_KEY
        self._app_secret = app_secret or DINGTALK_APP_SECRET
        self._webhook_url = webhook_url or DINGTALK_WEBHOOK_URL
        self._webhook_secret = webhook_secret or DINGTALK_WEBHOOK_SECRET
        self._sessions: dict[str, IMSession] = {}
        self._call_count_send: int = 0
        self._call_count_receive: int = 0

    # ══════════════════════════════════════════════════════════════
    # Send
    # ══════════════════════════════════════════════════════════════

    async def send(self, request: IMSendRequest) -> IMSendResponse:
        """Send a message via DingTalk webhook.

        Uses robot webhook URL with signature for group chats,
        or DingTalk API for direct messages.
        """
        self._call_count_send += 1
        start_time = time.time()

        try:
            # Use webhook for simple robot messages
            if self._webhook_url:
                return await self._send_via_webhook(request, start_time)
            else:
                return await self._send_via_api(request, start_time)

        except Exception as e:
            logger.exception("DingTalk send failed: %s", e)
            return IMSendResponse(
                success=False,
                platform=Platform.DINGTALK,
                error=str(e),
            )

    async def _send_via_webhook(
        self, request: IMSendRequest, start_time: float
    ) -> IMSendResponse:
        """Send via DingTalk robot webhook with signature."""
        if not self._webhook_secret:
            return IMSendResponse(
                success=False,
                platform=Platform.DINGTALK,
                error="DINGTALK_WEBHOOK_SECRET not configured",
            )

        timestamp, sign = _compute_webhook_sign(self._webhook_secret)
        url = f"{self._webhook_url}&timestamp={timestamp}&sign={sign}"

        msg_body = self._build_webhook_body(request)

        response = await self._client.post(url, json=msg_body)
        data = response.json()
        latency_ms = int((time.time() - start_time) * 1000)

        if data.get("errcode") == 0:
            return IMSendResponse(
                success=True,
                message_id=self._generate_message_id(),
                platform=Platform.DINGTALK,
                latency_ms=latency_ms,
            )
        else:
            return IMSendResponse(
                success=False,
                platform=Platform.DINGTALK,
                error=f"errcode={data.get('errcode')} errmsg={data.get('errmsg')}",
                latency_ms=latency_ms,
            )

    async def _send_via_api(
        self, request: IMSendRequest, start_time: float
    ) -> IMSendResponse:
        """Send via DingTalk API (corp conversation)."""
        token = await _get_access_token(self._client)

        msg_body = {
            "agent_id": request.target_id,
            "userid_list": request.target_id,
            "msg": self._build_api_msg_body(request),
        }

        url = f"{DINGTALK_API_BASE}/topapi/message/corpconversation/asyncsend_v2"
        params = {"access_token": token}

        response = await self._client.post(url, json=msg_body, params=params)
        data = response.json()
        latency_ms = int((time.time() - start_time) * 1000)

        if data.get("errcode") == 0:
            return IMSendResponse(
                success=True,
                message_id=str(data.get("task_id", self._generate_message_id())),
                platform=Platform.DINGTALK,
                latency_ms=latency_ms,
            )
        else:
            return IMSendResponse(
                success=False,
                platform=Platform.DINGTALK,
                error=f"errcode={data.get('errcode')} errmsg={data.get('errmsg')}",
                latency_ms=latency_ms,
            )

    def _build_webhook_body(self, request: IMSendRequest) -> dict[str, Any]:
        """Build DingTalk webhook message body."""
        body: dict[str, Any] = {"msgtype": request.message_type.value}

        content = request.content

        if request.message_type == MessageType.TEXT:
            body["text"] = {"content": content}
        elif request.message_type == MessageType.MARKDOWN:
            body["markdown"] = {"title": content[:64], "text": content}
        elif request.message_type == MessageType.CARD:
            # ActionCard
            body["msgtype"] = "actionCard"
            body["actionCard"] = {
                "title": content[:128],
                "text": content,
                "btnOrientation": "0",
            }
        else:
            body["msgtype"] = "text"
            body["text"] = {"content": content}

        # @mention support
        if "@all" in request.target_id:
            body["at"] = {"isAtAll": True}
        elif request.target_id and request.target_id not in ("@all", ""):
            body["at"] = {"atMobiles": [request.target_id]}

        return body

    def _build_api_msg_body(self, request: IMSendRequest) -> dict[str, Any]:
        """Build DingTalk API message body."""
        msg: dict[str, str] = {"content": request.content}
        return {"msgtype": "text", "text": msg}

    # ══════════════════════════════════════════════════════════════
    # Receive (Callback)
    # ══════════════════════════════════════════════════════════════

    async def receive(self, raw_payload: dict[str, Any]) -> IMMessage:
        """Parse DingTalk callback/webhook payload."""
        self._call_count_receive += 1

        msg_id = raw_payload.get("MsgId", raw_payload.get("msgId", self._generate_message_id()))
        msg_type = raw_payload.get("MsgType", raw_payload.get("msgtype", "text"))
        content = raw_payload.get("Content", raw_payload.get("text", {}).get("content", ""))
        from_user = raw_payload.get("SenderId", raw_payload.get("senderId", "unknown"))
        from_nick = raw_payload.get("SenderNick", "")

        # Map DingTalk msgtype to FDE
        type_mapping: dict[str, MessageType] = {
            "text": MessageType.TEXT,
            "image": MessageType.IMAGE,
            "file": MessageType.FILE,
            "markdown": MessageType.MARKDOWN,
            "actionCard": MessageType.CARD,
            "link": MessageType.CARD,
        }
        mapped_type = type_mapping.get(msg_type, MessageType.TEXT)

        # Attachments
        attachments: list[IMAttachment] = []
        if msg_type == "image" and raw_payload.get("PicUrl"):
            attachments.append(
                IMAttachment(
                    name=f"image_{msg_id}",
                    url=raw_payload["PicUrl"],
                    content_type="image/jpeg",
                )
            )

        # Session info
        session_id = raw_payload.get("SessionWebhook", "")

        return IMMessage(
            message_id=msg_id,
            platform=Platform.DINGTALK,
            direction=MessageDirection.INBOUND,
            message_type=mapped_type,
            sender=IMSender(
                user_id=from_user,
                display_name=from_nick,
                platform=Platform.DINGTALK,
                group_id=raw_payload.get("ChatId"),
            ),
            content=IMContent(
                body=content,
                attachments=attachments,
                metadata={
                    "dingtalk_msgtype": msg_type,
                    "session_webhook": session_id,
                    "create_at": raw_payload.get("CreateAt", ""),
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
    # Callback Verification
    # ══════════════════════════════════════════════════════════════

    def verify_callback(self, timestamp: str, sign: str) -> bool:
        """Verify DingTalk callback signature."""
        if not self._webhook_secret:
            return True  # No secret = accept all (dev mode)
        return _verify_callback_signature(timestamp, sign, self._webhook_secret)

    # ══════════════════════════════════════════════════════════════
    # Properties
    # ══════════════════════════════════════════════════════════════

    @property
    def is_configured(self) -> bool:
        return bool(self._app_key and self._app_secret) or bool(self._webhook_url and self._webhook_secret)

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


def create_dingtalk_adapter(
    http_client: httpx.AsyncClient | None = None,
) -> DingTalkAdapter:
    """Create a DingTalk adapter from environment variables."""
    adapter = DingTalkAdapter(http_client=http_client)
    if not adapter.is_configured:
        logger.warning(
            "DingTalk adapter created but not fully configured. "
            "Set DINGTALK_APP_KEY/APP_SECRET or DINGTALK_WEBHOOK_URL/SECRET."
        )
    return adapter
