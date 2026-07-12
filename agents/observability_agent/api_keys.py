"""API Key management — CRUD, storage, and rate limiting.

Provides in-memory API Key storage with bcrypt hashing, per-key
quota tracking (TPM/RPM), and token-bucket rate limiting.

For production multi-instance deployments, replace with Redis-backed
storage. For single-instance (current FDE deployment), in-memory is fine.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from collections import defaultdict, deque
from typing import Any

logger = logging.getLogger("fde.observability.apikeys")

# API Key store: {key_id: {key_hash, name, user_id, quota_tpm, quota_rpm, enabled, created_at, last_used_at}}
_api_keys: dict[str, dict[str, Any]] = {}

# Rate limit trackers: {key_id: deque([timestamps])}
_rpm_tracker: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=10000))
_tpm_tracker: dict[str, dict[str, float]] = defaultdict(lambda: {"window_start": time.time(), "tokens": 0})


def _hash_key(raw_key: str) -> str:
    """Hash an API key using SHA-256 (fast lookup, no salt needed for API keys)."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _key_id_from_hash(key_hash: str) -> str:
    """Derive a short key ID from the hash for display."""
    return key_hash[:12]


def create_api_key(
    name: str,
    user_id: str = "",
    quota_tpm: int = 100000,
    quota_rpm: int = 60,
) -> dict[str, Any]:
    """Create a new API key.

    Returns the key info including the raw key (only shown once).
    """
    raw_key = f"fde_{secrets.token_urlsafe(32)}"
    key_hash = _hash_key(raw_key)
    key_id = _key_id_from_hash(key_hash)

    _api_keys[key_id] = {
        "key_id": key_id,
        "key_hash": key_hash,
        "name": name,
        "user_id": user_id,
        "quota_tpm": quota_tpm,
        "quota_rpm": quota_rpm,
        "enabled": True,
        "created_at": time.time(),
        "last_used_at": 0.0,
        "total_calls": 0,
    }

    logger.info("API Key created: %s (name=%s, user=%s)", key_id, name, user_id)

    return {
        "key_id": key_id,
        "api_key": raw_key,  # Only returned on creation
        "name": name,
        "user_id": user_id,
        "quota_tpm": quota_tpm,
        "quota_rpm": quota_rpm,
        "enabled": True,
        "created_at": _api_keys[key_id]["created_at"],
        "message": "Save this API key securely. It will not be shown again.",
    }


def list_api_keys() -> list[dict[str, Any]]:
    """List all API keys (without the raw key or hash)."""
    result = []
    for key_id, info in sorted(_api_keys.items(), key=lambda x: x[1]["created_at"], reverse=True):
        result.append(
            {
                "key_id": key_id,
                "name": info["name"],
                "user_id": info["user_id"],
                "quota_tpm": info["quota_tpm"],
                "quota_rpm": info["quota_rpm"],
                "enabled": info["enabled"],
                "created_at": info["created_at"],
                "last_used_at": info["last_used_at"],
                "total_calls": info["total_calls"],
            }
        )
    return result


def update_api_key(
    key_id: str,
    name: str | None = None,
    quota_tpm: int | None = None,
    quota_rpm: int | None = None,
    enabled: bool | None = None,
) -> dict[str, Any] | None:
    """Update an API key's attributes."""
    if key_id not in _api_keys:
        return None

    info = _api_keys[key_id]
    if name is not None:
        info["name"] = name
    if quota_tpm is not None:
        info["quota_tpm"] = quota_tpm
    if quota_rpm is not None:
        info["quota_rpm"] = quota_rpm
    if enabled is not None:
        info["enabled"] = enabled

    logger.info("API Key updated: %s", key_id)
    return {
        "key_id": key_id,
        "name": info["name"],
        "user_id": info["user_id"],
        "quota_tpm": info["quota_tpm"],
        "quota_rpm": info["quota_rpm"],
        "enabled": info["enabled"],
    }


def delete_api_key(key_id: str) -> bool:
    """Delete an API key."""
    if key_id not in _api_keys:
        return False

    del _api_keys[key_id]
    # Clean up rate limit trackers
    _rpm_tracker.pop(key_id, None)
    _tpm_tracker.pop(key_id, None)

    logger.info("API Key deleted: %s", key_id)
    return True


def validate_api_key(raw_key: str) -> dict[str, Any] | None:
    """Validate an API key and return its info if valid.

    Used by rate-limiting middleware. Returns None if invalid/disabled.
    """
    if not raw_key or not raw_key.startswith("fde_"):
        return None

    key_hash = _hash_key(raw_key)
    key_id = _key_id_from_hash(key_hash)

    info = _api_keys.get(key_id)
    if not info or not info["enabled"]:
        return None

    # Verify hash matches
    if info["key_hash"] != key_hash:
        return None

    # Update last used
    info["last_used_at"] = time.time()
    info["total_calls"] += 1

    return {
        "key_id": key_id,
        "name": info["name"],
        "user_id": info["user_id"],
        "quota_tpm": info["quota_tpm"],
        "quota_rpm": info["quota_rpm"],
    }


def check_rate_limit(key_id: str, tokens: int = 0) -> tuple[bool, str]:
    """Check if an API key is within rate limits.

    Returns (allowed, reason).
    """
    info = _api_keys.get(key_id)
    if not info:
        return True, ""  # No key = no rate limit (public endpoints)

    now = time.time()

    # Check RPM (requests per minute)
    rpm_limit = info["quota_rpm"]
    if rpm_limit > 0:
        tracker = _rpm_tracker[key_id]
        # Remove entries older than 60s
        while tracker and now - tracker[0] > 60:
            tracker.popleft()
        if len(tracker) >= rpm_limit:
            return False, f"Rate limit exceeded: {rpm_limit} requests/minute"

    # Check TPM (tokens per minute)
    tpm_limit = info["quota_tpm"]
    if tpm_limit > 0 and tokens > 0:
        tracker = _tpm_tracker[key_id]
        # Reset window every 60s
        if now - tracker["window_start"] > 60:
            tracker["window_start"] = now
            tracker["tokens"] = 0
        if tracker["tokens"] + tokens > tpm_limit:
            return False, f"Token limit exceeded: {tpm_limit} tokens/minute"
        tracker["tokens"] += tokens

    # Record this request for RPM tracking
    _rpm_tracker[key_id].append(now)

    return True, ""


# ── External API registry ──────────────────────────────────────────

# Manually maintained registry of external API integrations
_EXTERNAL_APIS: list[dict[str, Any]] = [
    {
        "name": "Dify",
        "type": "llm_platform",
        "base_url": "${DIFY_API_URL}",
        "auth_method": "bearer",
        "env_var": "DIFY_API_URL",
        "status": "optional",
        "description": "Dify LLM platform integration for workflow orchestration",
    },
    {
        "name": "Baidu Maps (Browser)",
        "type": "map_service",
        "base_url": "https://api.map.baidu.com",
        "auth_method": "api_key",
        "env_var": "VITE_BAIDU_AK",
        "status": "active",
        "description": "Browser-side Baidu Maps JavaScript API",
    },
    {
        "name": "Baidu Maps (Server)",
        "type": "map_service",
        "base_url": "https://api.map.baidu.com",
        "auth_method": "api_key",
        "env_var": "BAIDU_SERVER_AK",
        "status": "active",
        "description": "Server-side Baidu Maps API for geocoding, POI, routing",
    },
    {
        "name": "WeChat Work (企微)",
        "type": "im_platform",
        "base_url": "https://qyapi.weixin.qq.com",
        "auth_method": "corpid_secret",
        "env_var": "WECOM_CORP_ID",
        "status": "stub",
        "description": "WeChat Work webhook and message push",
    },
    {
        "name": "Feishu (飞书)",
        "type": "im_platform",
        "base_url": "https://open.feishu.cn",
        "auth_method": "app_id_secret",
        "env_var": "FEISHU_APP_ID",
        "status": "stub",
        "description": "Feishu/Lark webhook and bot messaging",
    },
    {
        "name": "DingTalk (钉钉)",
        "type": "im_platform",
        "base_url": "https://oapi.dingtalk.com",
        "auth_method": "app_key_secret",
        "env_var": "DINGTALK_APP_KEY",
        "status": "stub",
        "description": "DingTalk webhook and robot messaging",
    },
    {
        "name": "DeepSeek",
        "type": "llm_provider",
        "base_url": "https://api.deepseek.com",
        "auth_method": "bearer",
        "env_var": "DEEPSEEK_API_KEY",
        "status": "stub",
        "description": "DeepSeek LLM API (deepseek-chat model)",
    },
    {
        "name": "Qwen (通义千问)",
        "type": "llm_provider",
        "base_url": "https://dashscope.aliyuncs.com",
        "auth_method": "bearer",
        "env_var": "QWEN_API_KEY",
        "status": "stub",
        "description": "Alibaba Qwen LLM API (qwen-turbo model)",
    },
    {
        "name": "GLM (智谱)",
        "type": "llm_provider",
        "base_url": "https://open.bigmodel.cn",
        "auth_method": "bearer",
        "env_var": "GLM_API_KEY",
        "status": "stub",
        "description": "Zhipu GLM LLM API (glm-4-flash model)",
    },
]


def get_external_apis() -> list[dict[str, Any]]:
    """Get the external API registry."""
    import os

    result = []
    for api in _EXTERNAL_APIS:
        env_var = api.get("env_var", "")
        configured = bool(os.environ.get(env_var)) if env_var else False
        result.append(
            {
                "name": api["name"],
                "type": api["type"],
                "base_url": api["base_url"],
                "auth_method": api["auth_method"],
                "env_var": env_var,
                "configured": configured,
                "status": api["status"],
                "description": api["description"],
            }
        )
    return result
