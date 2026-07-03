"""IM Agent Webhook Routes — FastAPI callback endpoints.

Provides unified webhook endpoints for all IM platforms:
- GET  /im/webhook/{platform}  → URL verification (echostr / challenge)
- POST /im/webhook/{platform}  → Message callback receipt

Platforms: wecom, feishu, dingtalk
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from agents.im_agent.adapters import AdapterRegistry
from agents.im_agent.adapters.wecom_adapter import WeComAdapter

logger = logging.getLogger("fde.im.webhook")

router = APIRouter(prefix="/im/webhook", tags=["IM Webhooks"])

# Global registry reference (set during app startup)
_registry: AdapterRegistry | None = None


def get_registry() -> AdapterRegistry:
    """Get the global adapter registry.

    Returns a default registry if not explicitly configured.
    """
    global _registry
    if _registry is None:
        from agents.im_agent.adapters import (
            WeComStubAdapter,
        )

        _registry = AdapterRegistry()
        # Override stubs with real adapters if available
        try:
            _registry.register(Platform.WECOM, WeComAdapter())
        except Exception:
            _registry.register(Platform.WECOM, WeComStubAdapter())

    return _registry


# Import Platform at module level
from agents.im_agent.models import Platform  # noqa: E402

# ══════════════════════════════════════════════════════════════════
# Webhook Endpoints
# ══════════════════════════════════════════════════════════════════


@router.get("/{platform}")
async def verify_webhook_url(
    platform: str,
    msg_signature: str = Query(default=""),
    timestamp: str = Query(default=""),
    nonce: str = Query(default=""),
    echostr: str = Query(default=""),
) -> str:
    """Verify IM platform callback URL (GET request).

    Each platform uses different verification schemes:
    - WeCom: msg_signature + timestamp + nonce + echostr → decrypt echostr
    - Feishu: type=url_verification + token → return challenge
    - DingTalk: register callback in DingTalk admin console (no GET verify)

    Returns:
        The verification token/challenge string.
    """
    if platform not in ("wecom", "feishu", "dingtalk"):
        raise HTTPException(status_code=404, detail=f"Unknown platform: {platform}")

    # WeCom URL verification
    if platform == "wecom":
        registry = get_registry()
        try:
            adapter = registry.get(Platform.WECOM)
        except KeyError:
            raise HTTPException(status_code=500, detail="WeCom adapter not registered")

        if isinstance(adapter, WeComAdapter):
            result = adapter.verify_url(msg_signature, timestamp, nonce, echostr)
            if result is not None:
                return result
            raise HTTPException(status_code=403, detail="WeCom signature verification failed")

        # Stub adapter: echo back
        return echostr or "ok"

    # Feishu URL verification
    if platform == "feishu":
        # Feishu sends: POST with {"type": "url_verification", "token": "xxx"}
        # But GET is sometimes used for simple health checks
        # Return the echostr or challenge
        return echostr or "ok"

    # DingTalk: no GET verification needed
    return "ok"


@router.post("/{platform}")
async def receive_callback(
    platform: str,
    request: Request,
) -> dict[str, str]:
    """Receive IM platform message callback (POST request).

    Accepts:
    - WeCom: XML callback body (parsed by framework)
    - Feishu: JSON event body
    - DingTalk: JSON webhook body

    Returns:
        {"status": "ok"} or {"status": "error", "detail": "..."}
    """
    if platform not in ("wecom", "feishu", "dingtalk"):
        raise HTTPException(status_code=404, detail=f"Unknown platform: {platform}")

    try:
        registry = get_registry()
        plat_enum = Platform(platform)
        adapter = registry.get(plat_enum)

        # Parse raw payload
        raw_payload: dict[str, Any]
        content_type = request.headers.get("content-type", "")

        if "json" in content_type:
            json_data: Any = await request.json()
            raw_payload = dict(json_data)
        elif "xml" in content_type or "text/xml" in content_type:
            body = await request.body()
            logger.warning("XML body received for %s (len=%d), using raw parse", platform, len(body))
            raw_payload = {"raw_xml": body.decode("utf-8", errors="replace"), "platform": platform}
        else:
            # Try JSON first, then raw
            body = await request.body()
            try:
                json_data = await request.json()
                raw_payload = dict(json_data)
            except Exception:
                raw_payload = {"raw_body": body.decode("utf-8", errors="replace"), "platform": platform}

        # Process through adapter
        message = await adapter.receive(raw_payload)

        logger.info(
            "Received %s message: msg_id=%s from=%s type=%s",
            platform,
            message.message_id,
            message.sender.user_id,
            message.message_type.value,
        )

        return {"status": "ok", "message_id": message.message_id}

    except KeyError:
        raise HTTPException(status_code=500, detail=f"{platform} adapter not registered")
    except Exception as e:
        logger.exception("Failed to process %s callback: %s", platform, e)
        return {"status": "error", "detail": str(e)}
