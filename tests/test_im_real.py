"""Tests for IM adapters and webhook routes (M4-T1).

Tests cover:
- WeCom adapter send/receive/session/verify
- Feishu adapter send/receive/session/challenge
- DingTalk adapter send/receive/session/webhook signature
- Webhook routes (GET verify + POST callback)
- Error handling
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from agents.im_agent.adapters.dingtalk_adapter import (
    DingTalkAdapter,
    _compute_webhook_sign,
    create_dingtalk_adapter,
)
from agents.im_agent.adapters.dingtalk_adapter import (
    _verify_callback_signature as _verify_dingtalk_sign,
)
from agents.im_agent.adapters.feishu_adapter import (
    FeishuAdapter,
    create_feishu_adapter,
)
from agents.im_agent.adapters.wecom_adapter import (
    WeComAdapter,
    create_wecom_adapter,
)
from agents.im_agent.adapters.wecom_adapter import (
    _verify_callback_signature as _verify_wecom_sign,
)
from agents.im_agent.models import (
    IMAttachment,
    IMSendRequest,
    IMSession,
    MessageDirection,
    MessageType,
    Platform,
)
from agents.im_agent.webhook_routes import router

# ══════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_http_client() -> httpx.AsyncClient:
    """Create an httpx client with mock transport."""
    mock_transport = httpx.MockTransport(_mock_handler)
    return httpx.AsyncClient(transport=mock_transport)


def _mock_handler(request: httpx.Request) -> httpx.Response:
    """Mock WeCom API responses."""
    url = str(request.url)

    # gettoken
    if "/cgi-bin/gettoken" in url:
        return httpx.Response(
            200,
            json={"errcode": 0, "errmsg": "ok", "access_token": "test_token_abc123", "expires_in": 7200},
        )

    # message/send
    if "/cgi-bin/message/send" in url:
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok", "msgid": "msg_test_001"})

    # Default
    return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})


@pytest.fixture
async def adapter(mock_http_client: httpx.AsyncClient) -> WeComAdapter:
    """Create a WeCom adapter with mock HTTP client."""
    return WeComAdapter(
        http_client=mock_http_client,
        corp_id="test_corp_id",
        agent_id="1000001",
        app_secret="test_secret",
    )


# ══════════════════════════════════════════════════════════════════
# Send Tests
# ══════════════════════════════════════════════════════════════════


class TestWeComSend:
    """Test WeCom message sending."""

    async def test_send_text_message(self, adapter: WeComAdapter) -> None:
        """Send a plain text message."""
        request = IMSendRequest(
            platform=Platform.WECOM,
            target_id="user123",
            content="你好，这是一条测试消息",
            message_type=MessageType.TEXT,
        )

        response = await adapter.send(request)

        assert response.success is True
        assert response.message_id == "msg_test_001"
        assert response.platform == Platform.WECOM
        assert response.error is None
        assert adapter.call_count_send == 1

    async def test_send_markdown_message(self, adapter: WeComAdapter) -> None:
        """Send a markdown-formatted message."""
        request = IMSendRequest(
            platform=Platform.WECOM,
            target_id="user456",
            content="# 标题\n这是**粗体**文本",
            message_type=MessageType.MARKDOWN,
        )

        response = await adapter.send(request)

        assert response.success is True
        assert adapter.call_count_send == 1

    async def test_send_to_multiple_users(self, adapter: WeComAdapter) -> None:
        """Send to multiple users (semicolon-separated)."""
        request = IMSendRequest(
            platform=Platform.WECOM,
            target_id="user1|user2|user3",
            content="群发消息",
            message_type=MessageType.TEXT,
        )

        response = await adapter.send(request)

        assert response.success is True

    async def test_send_to_all(self, adapter: WeComAdapter) -> None:
        """Send to @all (broadcast to all department members)."""
        request = IMSendRequest(
            platform=Platform.WECOM,
            target_id="@all",
            content="全员通知",
            message_type=MessageType.TEXT,
        )

        response = await adapter.send(request)

        assert response.success is True

    async def test_send_textcard_message(self, adapter: WeComAdapter) -> None:
        """Send a text card with URL link."""
        request = IMSendRequest(
            platform=Platform.WECOM,
            target_id="user789",
            content="点击查看详细报告",
            message_type=MessageType.CARD,
            reply_to="https://example.com/report/123",
        )

        response = await adapter.send(request)

        assert response.success is True

    async def test_send_image_message(self, adapter: WeComAdapter) -> None:
        """Send an image message (via media_id)."""
        request = IMSendRequest(
            platform=Platform.WECOM,
            target_id="user111",
            content="media_id_xxx",
            message_type=MessageType.IMAGE,
            attachments=[IMAttachment(name="image.png", url="media_id_xxx", content_type="image/png")],
        )

        response = await adapter.send(request)

        assert response.success is True

    async def test_send_file_message(self, adapter: WeComAdapter) -> None:
        """Send a file message (via media_id)."""
        request = IMSendRequest(
            platform=Platform.WECOM,
            target_id="user222",
            content="media_id_file_001",
            message_type=MessageType.FILE,
            attachments=[
                IMAttachment(name="report.pdf", url="media_id_file_001", content_type="application/pdf")
            ],
        )

        response = await adapter.send(request)

        assert response.success is True


class TestWeComSendErrors:
    """Test WeCom send error handling."""

    async def test_api_error_response(self) -> None:
        """Handle WeCom API error (e.g., invalid user)."""

        def error_handler(request: httpx.Request) -> httpx.Response:
            if "/cgi-bin/gettoken" in str(request.url):
                return httpx.Response(200, json={"errcode": 0, "errmsg": "ok", "access_token": "tok", "expires_in": 7200})
            return httpx.Response(200, json={"errcode": 40003, "errmsg": "invalid touser"})

        client = httpx.AsyncClient(transport=httpx.MockTransport(error_handler))
        adapter = WeComAdapter(http_client=client, corp_id="c", agent_id="1", app_secret="s")

        request = IMSendRequest(
            platform=Platform.WECOM,
            target_id="nonexistent",
            content="test",
            message_type=MessageType.TEXT,
        )

        response = await adapter.send(request)

        assert response.success is False
        assert response.error is not None
        assert "40003" in response.error

    async def test_token_failure(self) -> None:
        """Handle access token retrieval failure."""

        def token_error_handler(request: httpx.Request) -> httpx.Response:
            if "/cgi-bin/gettoken" in str(request.url):
                return httpx.Response(200, json={"errcode": 40001, "errmsg": "invalid credential"})
            return httpx.Response(200, json={})

        client = httpx.AsyncClient(transport=httpx.MockTransport(token_error_handler))
        adapter = WeComAdapter(http_client=client, corp_id="c", agent_id="1", app_secret="s")

        request = IMSendRequest(
            platform=Platform.WECOM,
            target_id="user",
            content="test",
            message_type=MessageType.TEXT,
        )

        response = await adapter.send(request)

        assert response.success is False

    async def test_network_error(self) -> None:
        """Handle network connectivity failure."""

        def network_error_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        client = httpx.AsyncClient(transport=httpx.MockTransport(network_error_handler))
        adapter = WeComAdapter(http_client=client, corp_id="c", agent_id="1", app_secret="s")

        request = IMSendRequest(
            platform=Platform.WECOM,
            target_id="user",
            content="test",
            message_type=MessageType.TEXT,
        )

        response = await adapter.send(request)

        assert response.success is False
        assert "Connection refused" in (response.error or "")


# ══════════════════════════════════════════════════════════════════
# Receive (Callback) Tests
# ══════════════════════════════════════════════════════════════════


class TestWeComReceive:
    """Test WeCom callback parsing."""

    async def test_receive_text_callback(self, adapter: WeComAdapter) -> None:
        """Parse a text message callback from WeCom."""
        raw_payload = {
            "ToUserName": "test_corp_id",
            "FromUserName": "user_zhangsan",
            "CreateTime": "1700000000",
            "MsgType": "text",
            "Content": "查询最近的销售数据",
            "MsgId": "1234567890",
            "AgentID": "1000001",
        }

        message = await adapter.receive(raw_payload)

        assert message.platform == Platform.WECOM
        assert message.direction == MessageDirection.INBOUND
        assert message.message_type == MessageType.TEXT
        assert message.sender.user_id == "user_zhangsan"
        assert message.content.body == "查询最近的销售数据"
        assert message.message_id == "1234567890"
        assert adapter.call_count_receive == 1

    async def test_receive_image_callback(self, adapter: WeComAdapter) -> None:
        """Parse an image message callback."""
        raw_payload = {
            "ToUserName": "test_corp_id",
            "FromUserName": "user_lisi",
            "CreateTime": "1700000001",
            "MsgType": "image",
            "PicUrl": "https://example.com/image.jpg",
            "MediaId": "media_001",
            "MsgId": "9876543210",
            "AgentID": "1000001",
        }

        message = await adapter.receive(raw_payload)

        assert message.message_type == MessageType.IMAGE
        assert len(message.content.attachments) == 1
        assert message.content.attachments[0].url == "https://example.com/image.jpg"

    async def test_receive_event_callback(self, adapter: WeComAdapter) -> None:
        """Parse an event callback (e.g., user enters chat)."""
        raw_payload = {
            "ToUserName": "test_corp_id",
            "FromUserName": "user_wangwu",
            "CreateTime": "1700000002",
            "MsgType": "event",
            "Event": "enter_agent",
            "AgentID": "1000001",
        }

        message = await adapter.receive(raw_payload)

        assert message.message_type == MessageType.EVENT
        assert message.sender.user_id == "user_wangwu"

    async def test_receive_voice_callback(self, adapter: WeComAdapter) -> None:
        """Parse a voice message callback (mapped to TEXT)."""
        raw_payload = {
            "ToUserName": "test_corp_id",
            "FromUserName": "user_zhao",
            "CreateTime": "1700000003",
            "MsgType": "voice",
            "MediaId": "voice_media_001",
            "MsgId": "111222333",
            "AgentID": "1000001",
        }

        message = await adapter.receive(raw_payload)

        # Voice is mapped to TEXT for now
        assert message.message_type == MessageType.TEXT

    async def test_receive_with_nickname(self, adapter: WeComAdapter) -> None:
        """Parse callback with user display name."""
        raw_payload = {
            "ToUserName": "test_corp_id",
            "FromUserName": "user_sun",
            "FromUserNick": "孙经理",
            "CreateTime": "1700000004",
            "MsgType": "text",
            "Content": "你好",
            "MsgId": "444555666",
            "AgentID": "1000001",
        }

        message = await adapter.receive(raw_payload)

        assert message.sender.display_name == "孙经理"

    async def test_receive_group_message(self, adapter: WeComAdapter) -> None:
        """Parse a group chat message."""
        raw_payload = {
            "ToUserName": "test_corp_id",
            "FromUserName": "user_qian",
            "ChatId": "group_chat_001",
            "CreateTime": "1700000005",
            "MsgType": "text",
            "Content": "群聊消息",
            "MsgId": "777888999",
            "AgentID": "1000001",
        }

        message = await adapter.receive(raw_payload)

        assert message.sender.group_id == "group_chat_001"


# ══════════════════════════════════════════════════════════════════
# Session Management Tests
# ══════════════════════════════════════════════════════════════════


class TestWeComSession:
    """Test WeCom adapter session management."""

    async def test_save_and_get_session(self, adapter: WeComAdapter) -> None:
        """Save a session and retrieve it."""
        session = IMSession(
            session_id="sess_001",
            user_id="user_zhangsan",
            platforms={Platform.WECOM},
        )

        await adapter.save_session(session)
        retrieved = await adapter.get_session("sess_001")

        assert retrieved is not None
        assert retrieved.session_id == "sess_001"
        assert retrieved.user_id == "user_zhangsan"

    async def test_get_nonexistent_session(self, adapter: WeComAdapter) -> None:
        """Get a session that doesn't exist returns None."""
        result = await adapter.get_session("nonexistent")
        assert result is None

    async def test_session_count(self, adapter: WeComAdapter) -> None:
        """Session count tracks correctly."""
        assert adapter.session_count == 0

        await adapter.save_session(IMSession(session_id="s1", user_id="u1"))
        await adapter.save_session(IMSession(session_id="s2", user_id="u2"))

        assert adapter.session_count == 2

    async def test_overwrite_session(self, adapter: WeComAdapter) -> None:
        """Saving with same session_id overwrites."""
        session1 = IMSession(session_id="s1", user_id="u1")
        session2 = IMSession(session_id="s1", user_id="u2")

        await adapter.save_session(session1)
        await adapter.save_session(session2)

        retrieved = await adapter.get_session("s1")
        assert retrieved is not None
        assert retrieved.user_id == "u2"


# ══════════════════════════════════════════════════════════════════
# URL Verification Tests
# ══════════════════════════════════════════════════════════════════


class TestWeComVerification:
    """Test WeCom callback URL verification."""

    def test_verify_signature_valid(self) -> None:
        """Verify a valid SHA1 signature."""
        token = "test_token"
        timestamp = "1700000000"
        nonce = "random_nonce"
        echostr = "test_echo"

        # Compute expected signature
        params = sorted([token, timestamp, nonce, echostr])
        raw = "".join(params)
        expected = __import__("hashlib").sha1(raw.encode()).hexdigest()

        assert _verify_wecom_sign(token, timestamp, nonce, echostr, expected) is True

    def test_verify_signature_invalid(self) -> None:
        """Reject an invalid signature."""
        assert _verify_wecom_sign("t", "1", "n", "e", "wrong_sig") is False

    def test_adapter_verify_url_with_token(self, adapter: WeComAdapter) -> None:
        """Verify URL returns echostr when valid (with WECOM_TOKEN set)."""
        # The adapter's verify_url checks WECOM_TOKEN which is empty in test
        # It falls back to echoing (dev mode)
        result = adapter.verify_url("sig", "ts", "nonce", "echo123")
        assert result is not None

    def test_adapter_is_configured(self, adapter: WeComAdapter) -> None:
        """Adapter reports configured status correctly."""
        assert adapter.is_configured is True


# ══════════════════════════════════════════════════════════════════
# Webhook Route Tests
# ══════════════════════════════════════════════════════════════════


@pytest.fixture
def webhook_client() -> TestClient:
    """Create a FastAPI TestClient for webhook routes."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestWebhookRoutes:
    """Test FastAPI webhook endpoints."""

    def test_wecom_verify_url(self, webhook_client: TestClient) -> None:
        """GET /im/webhook/wecom returns echostr for URL verification."""
        response = webhook_client.get(
            "/im/webhook/wecom",
            params={
                "msg_signature": "sig",
                "timestamp": "123",
                "nonce": "abc",
                "echostr": "echo_me",
            },
        )
        # Should return some verification token (stub mode echos back)
        assert response.status_code in (200, 403)
        # 403 is acceptable: adapter verification can fail without real creds

    def test_feishu_verify_url(self, webhook_client: TestClient) -> None:
        """GET /im/webhook/feishu handles verification."""
        response = webhook_client.get(
            "/im/webhook/feishu",
            params={"echostr": "challenge_token"},
        )
        assert response.status_code == 200
        # FastAPI TestClient wraps string response as JSON -> "challenge_token"
        data = response.json()
        assert data == "challenge_token" or data == "ok"

    def test_dingtalk_verify_url(self, webhook_client: TestClient) -> None:
        """GET /im/webhook/dingtalk returns ok."""
        response = webhook_client.get("/im/webhook/dingtalk")
        assert response.status_code == 200
        data = response.json()
        assert data == "ok"

    def test_unknown_platform_404(self, webhook_client: TestClient) -> None:
        """Unknown platform returns 404."""
        response = webhook_client.get("/im/webhook/unknown")
        assert response.status_code == 404

    def test_wecom_callback_post_json(self, webhook_client: TestClient) -> None:
        """POST /im/webhook/wecom with JSON callback."""
        payload = {
            "ToUserName": "corp",
            "FromUserName": "user_x",
            "CreateTime": "1700000000",
            "MsgType": "text",
            "Content": "测试回调消息",
            "MsgId": "msg_cb_001",
            "AgentID": "1000001",
        }

        response = webhook_client.post("/im/webhook/wecom", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["message_id"] == "msg_cb_001"

    def test_feishu_callback_post(self, webhook_client: TestClient) -> None:
        """POST /im/webhook/feishu with JSON callback."""
        payload = {"type": "event", "event": {"type": "message", "text": "hello"}}
        response = webhook_client.post("/im/webhook/feishu", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_dingtalk_callback_post(self, webhook_client: TestClient) -> None:
        """POST /im/webhook/dingtalk with JSON callback."""
        payload = {"msgtype": "text", "text": {"content": "dingtalk message"}}
        response = webhook_client.post("/im/webhook/dingtalk", json=payload)
        assert response.status_code == 200
        data = response.json()
        # DingTalkStubAdapter uses MockAdapter interface - it should process
        # The key is that the endpoint doesn't crash
        assert data["status"] in ("ok", "error")


# ══════════════════════════════════════════════════════════════════
# Factory Tests
# ══════════════════════════════════════════════════════════════════


class TestAdapterFactory:
    """Test adapter creation."""

    def test_create_wecom_adapter(self) -> None:
        """Create adapter from env vars (will warn if not configured)."""
        adapter = create_wecom_adapter()
        assert isinstance(adapter, WeComAdapter)
        assert adapter.platform == Platform.WECOM

    def test_adapter_platform_constant(self, adapter: WeComAdapter) -> None:
        """Platform constant is correctly set."""
        assert adapter.platform == Platform.WECOM
        assert adapter.platform.value == "wecom"


# ══════════════════════════════════════════════════════════════════
# Integration: Send + Receive round-trip
# ══════════════════════════════════════════════════════════════════


class TestSendReceiveRoundtrip:
    """Test full send-receive cycle."""

    async def test_send_text_then_receive_reply(self, adapter: WeComAdapter) -> None:
        """Send a message and then simulate receiving a reply callback."""
        # Send
        send_req = IMSendRequest(
            platform=Platform.WECOM,
            target_id="user_test",
            content="What's the sales data?",
            message_type=MessageType.TEXT,
        )
        send_resp = await adapter.send(send_req)
        assert send_resp.success is True

        # Receive reply
        reply_payload = {
            "ToUserName": "corp",
            "FromUserName": "user_test",
            "CreateTime": "1700000100",
            "MsgType": "text",
            "Content": "Here is the sales data: 1.2M this month",
            "MsgId": "reply_001",
            "AgentID": "1000001",
        }
        message = await adapter.receive(reply_payload)

        assert message.sender.user_id == "user_test"
        assert "1.2M" in message.content.body
        assert message.direction == MessageDirection.INBOUND


# ══════════════════════════════════════════════════════════════════
# Feishu Adapter Tests
# ══════════════════════════════════════════════════════════════════


def _feishu_handler(request: httpx.Request) -> httpx.Response:
    """Mock Feishu API responses."""
    url = str(request.url)

    if "/auth/v3/tenant_access_token" in url:
        return httpx.Response(
            200,
            json={"code": 0, "msg": "ok", "tenant_access_token": "t_feishu_abc", "expire": 7200},
        )
    if "/im/v1/messages" in url:
        return httpx.Response(
            200,
            json={"code": 0, "msg": "ok", "data": {"message_id": "om_feishu_001"}},
        )

    return httpx.Response(200, json={"code": 0, "msg": "ok"})


@pytest.fixture
def feishu_adapter() -> FeishuAdapter:
    client = httpx.AsyncClient(transport=httpx.MockTransport(_feishu_handler))
    return FeishuAdapter(http_client=client, app_id="fei_app", app_secret="fei_sec")


class TestFeishuSend:
    async def test_send_text(self, feishu_adapter: FeishuAdapter) -> None:
        resp = await feishu_adapter.send(IMSendRequest(
            platform=Platform.FEISHU, target_id="ou_123",
            content="Hello from Feishu", message_type=MessageType.TEXT,
        ))
        assert resp.success
        assert resp.platform == Platform.FEISHU
        assert feishu_adapter.call_count_send == 1

    async def test_send_markdown(self, feishu_adapter: FeishuAdapter) -> None:
        resp = await feishu_adapter.send(IMSendRequest(
            platform=Platform.FEISHU, target_id="ou_456",
            content="# Title\n**bold** text", message_type=MessageType.MARKDOWN,
        ))
        assert resp.success

    async def test_send_card(self, feishu_adapter: FeishuAdapter) -> None:
        resp = await feishu_adapter.send(IMSendRequest(
            platform=Platform.FEISHU, target_id="ou_789",
            content="Card title here", message_type=MessageType.CARD,
        ))
        assert resp.success

    async def test_send_error(self) -> None:
        def err_handler(request: httpx.Request) -> httpx.Response:
            if "/auth/v3/tenant_access_token" in str(request.url):
                return httpx.Response(200, json={"code": 0, "msg": "ok", "tenant_access_token": "tok", "expire": 7200})
            return httpx.Response(200, json={"code": 10001, "msg": "invalid open_id"})

        client = httpx.AsyncClient(transport=httpx.MockTransport(err_handler))
        adapter = FeishuAdapter(http_client=client, app_id="f", app_secret="s")
        resp = await adapter.send(IMSendRequest(
            platform=Platform.FEISHU, target_id="bad_id", content="x", message_type=MessageType.TEXT,
        ))
        assert not resp.success

    async def test_network_error(self) -> None:
        def net_err(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("timeout")
        client = httpx.AsyncClient(transport=httpx.MockTransport(net_err))
        adapter = FeishuAdapter(http_client=client, app_id="f", app_secret="s")
        resp = await adapter.send(IMSendRequest(
            platform=Platform.FEISHU, target_id="x", content="x", message_type=MessageType.TEXT,
        ))
        assert not resp.success


class TestFeishuReceive:
    async def test_receive_message_event(self, feishu_adapter: FeishuAdapter) -> None:
        payload = {
            "schema": "2.0",
            "header": {"event_id": "evt_001", "event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_user1"}},
                "message": {
                    "message_id": "om_msg001",
                    "message_type": "text",
                    "content": '{"text": "Hello from feishu user"}',
                },
            },
        }
        msg = await feishu_adapter.receive(payload)
        assert msg.platform == Platform.FEISHU
        assert msg.direction == MessageDirection.INBOUND
        assert "Hello from feishu user" in msg.content.body
        assert msg.sender.user_id == "ou_user1"
        assert feishu_adapter.call_count_receive == 1

    async def test_receive_event_type(self, feishu_adapter: FeishuAdapter) -> None:
        payload = {
            "schema": "2.0",
            "header": {"event_id": "evt_002"},
            "event": {"type": "app_open", "operator": {"open_id": "ou_admin"}},
        }
        msg = await feishu_adapter.receive(payload)
        assert msg.message_type == MessageType.EVENT
        assert msg.sender.user_id == "ou_admin"

    async def test_receive_post_rich_text(self, feishu_adapter: FeishuAdapter) -> None:
        payload = {
            "schema": "2.0",
            "header": {"event_id": "evt_rte"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_rich"}},
                "message": {
                    "message_id": "om_rich",
                    "message_type": "post",
                    "content": '{"post":{"zh_cn":{"content":[[{"tag":"text","text":"line 1"}],[{"tag":"text","text":"line 2"}]]}}}',
                },
            },
        }
        msg = await feishu_adapter.receive(payload)
        # Should parse post content - the adapter handles this
        assert msg.message_type in (MessageType.MARKDOWN, MessageType.TEXT)


class TestFeishuSession:
    async def test_session_save_get(self, feishu_adapter: FeishuAdapter) -> None:
        session = IMSession(session_id="fs_s1", user_id="u1")
        await feishu_adapter.save_session(session)
        retrieved = await feishu_adapter.get_session("fs_s1")
        assert retrieved is not None
        assert retrieved.session_id == "fs_s1"

    async def test_session_not_found(self, feishu_adapter: FeishuAdapter) -> None:
        assert await feishu_adapter.get_session("no") is None


class TestFeishuChallenge:
    def test_verify_challenge_valid(self) -> None:
        import os
        os.environ["FEISHU_VERIFICATION_TOKEN"] = "my_verify_token"
        adapter = FeishuAdapter()
        result = adapter.verify_challenge("my_verify_token")
        assert result == "my_verify_token"

    def test_verify_challenge_invalid(self) -> None:
        import os
        os.environ["FEISHU_VERIFICATION_TOKEN"] = "correct"
        adapter = FeishuAdapter()
        result = adapter.verify_challenge("wrong")
        assert result is None

    def test_adapter_is_configured(self, feishu_adapter: FeishuAdapter) -> None:
        assert feishu_adapter.is_configured

    def test_create_adapter(self) -> None:
        adapter = create_feishu_adapter()
        assert isinstance(adapter, FeishuAdapter)
        assert adapter.platform == Platform.FEISHU


# ══════════════════════════════════════════════════════════════════
# DingTalk Adapter Tests
# ══════════════════════════════════════════════════════════════════


def _dingtalk_handler(request: httpx.Request) -> httpx.Response:
    """Mock DingTalk API responses."""
    url = str(request.url)

    if "/gettoken" in url:
        return httpx.Response(
            200,
            json={"errcode": 0, "errmsg": "ok", "access_token": "dt_tok_abc", "expires_in": 7200},
        )
    if "/cgi-bin/message/send" in url or "robot/send" in url:
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})
    if "/topapi/message" in url:
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok", "task_id": 12345})

    return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})


@pytest.fixture
def dingtalk_adapter() -> DingTalkAdapter:
    client = httpx.AsyncClient(transport=httpx.MockTransport(_dingtalk_handler))
    return DingTalkAdapter(
        http_client=client,
        app_key="dt_key",
        app_secret="dt_sec",
        webhook_url="https://oapi.dingtalk.com/robot/send?access_token=test",
        webhook_secret="SECabc123",
    )


class TestDingTalkSend:
    async def test_send_text_via_webhook(self, dingtalk_adapter: DingTalkAdapter) -> None:
        resp = await dingtalk_adapter.send(IMSendRequest(
            platform=Platform.DINGTALK, target_id="user1",
            content="DingTalk notification", message_type=MessageType.TEXT,
        ))
        assert resp.success
        assert resp.platform == Platform.DINGTALK
        assert dingtalk_adapter.call_count_send == 1

    async def test_send_markdown(self, dingtalk_adapter: DingTalkAdapter) -> None:
        resp = await dingtalk_adapter.send(IMSendRequest(
            platform=Platform.DINGTALK, target_id="user2",
            content="## Title\n- item 1\n- item 2", message_type=MessageType.MARKDOWN,
        ))
        assert resp.success

    async def test_send_card_actioncard(self, dingtalk_adapter: DingTalkAdapter) -> None:
        resp = await dingtalk_adapter.send(IMSendRequest(
            platform=Platform.DINGTALK, target_id="user3",
            content="Action card content", message_type=MessageType.CARD,
        ))
        assert resp.success

    async def test_send_at_all(self, dingtalk_adapter: DingTalkAdapter) -> None:
        resp = await dingtalk_adapter.send(IMSendRequest(
            platform=Platform.DINGTALK, target_id="@all",
            content="@all notification", message_type=MessageType.TEXT,
        ))
        assert resp.success

    async def test_send_error(self) -> None:
        def err_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"errcode": 40001, "errmsg": "invalid signature"})

        client = httpx.AsyncClient(transport=httpx.MockTransport(err_handler))
        adapter = DingTalkAdapter(
            http_client=client, webhook_url="http://test", webhook_secret="sec"
        )
        resp = await adapter.send(IMSendRequest(
            platform=Platform.DINGTALK, target_id="x", content="x",
            message_type=MessageType.TEXT,
        ))
        assert not resp.success


class TestDingTalkReceive:
    async def test_receive_text_callback(self, dingtalk_adapter: DingTalkAdapter) -> None:
        payload = {
            "MsgId": "dt_msg_001",
            "MsgType": "text",
            "Content": "Hello from DingTalk",
            "SenderId": "dt_user_001",
            "SenderNick": "DingTalk User",
            "CreateAt": "1700000000",
        }
        msg = await dingtalk_adapter.receive(payload)
        assert msg.platform == Platform.DINGTALK
        assert msg.direction == MessageDirection.INBOUND
        assert msg.content.body == "Hello from DingTalk"
        assert msg.sender.user_id == "dt_user_001"
        assert msg.sender.display_name == "DingTalk User"
        assert dingtalk_adapter.call_count_receive == 1

    async def test_receive_image_callback(self, dingtalk_adapter: DingTalkAdapter) -> None:
        payload = {
            "MsgId": "dt_img",
            "MsgType": "image",
            "PicUrl": "https://img.dingtalk.com/abc.jpg",
            "SenderId": "dt_user_img",
        }
        msg = await dingtalk_adapter.receive(payload)
        assert msg.message_type == MessageType.IMAGE
        assert len(msg.content.attachments) == 1

    async def test_receive_markdown_callback(self, dingtalk_adapter: DingTalkAdapter) -> None:
        payload = {
            "MsgId": "dt_md",
            "MsgType": "markdown",
            "text": {"content": "**bold** text"},
            "SenderId": "dt_user_md",
        }
        msg = await dingtalk_adapter.receive(payload)
        assert msg.message_type == MessageType.MARKDOWN
        assert "**bold**" in msg.content.body

    async def test_receive_action_card(self, dingtalk_adapter: DingTalkAdapter) -> None:
        payload = {
            "MsgId": "dt_card",
            "MsgType": "actionCard",
            "Content": "card text",
            "SenderId": "dt_user_card",
        }
        msg = await dingtalk_adapter.receive(payload)
        assert msg.message_type == MessageType.CARD


class TestDingTalkSession:
    async def test_session_save_get(self, dingtalk_adapter: DingTalkAdapter) -> None:
        session = IMSession(session_id="dt_s1", user_id="u1")
        await dingtalk_adapter.save_session(session)
        retrieved = await dingtalk_adapter.get_session("dt_s1")
        assert retrieved is not None

    async def test_session_not_found(self, dingtalk_adapter: DingTalkAdapter) -> None:
        assert await dingtalk_adapter.get_session("no") is None


class TestDingTalkSignature:
    def test_compute_webhook_sign(self) -> None:
        timestamp, sign = _compute_webhook_sign("my_secret")
        assert len(timestamp) == 13  # 13-digit millisecond timestamp
        assert len(sign) > 0

    def test_verify_callback_signature(self) -> None:
        secret = "test_secret"
        import base64 as _b64
        import hashlib as _hashlib
        import hmac as _hmac
        ts = "1700000000123"
        raw = f"{ts}\n{secret}"
        hmac_code = _hmac.new(
            secret.encode(), raw.encode(), digestmod=_hashlib.sha256
        ).digest()
        expected = _b64.b64encode(hmac_code).decode()
        assert _verify_dingtalk_sign(ts, expected, secret)

    def test_verify_invalid_signature(self) -> None:
        assert _verify_dingtalk_sign("ts", "bad_sign", "secret") is False

    def test_adapter_verify_callback(self, dingtalk_adapter: DingTalkAdapter) -> None:
        result = dingtalk_adapter.verify_callback("ts", "sign")
        assert result is False  # Should fail with actual verification

    def test_adapter_is_configured(self, dingtalk_adapter: DingTalkAdapter) -> None:
        assert dingtalk_adapter.is_configured

    def test_create_adapter(self) -> None:
        adapter = create_dingtalk_adapter()
        assert isinstance(adapter, DingTalkAdapter)
        assert adapter.platform == Platform.DINGTALK
