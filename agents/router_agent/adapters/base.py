"""Model adapters — pluggable LLM provider integrations.

Each adapter wraps a specific LLM provider (DeepSeek, Qwen, GLM, etc.)
behind a common interface. New providers are added as plugins without
modifying the router core.

M1-T5: At least 3 adapters (Mock + DeepSeek-stub + Qwen-stub + GLM-stub)
       Mock adapter works without API keys for development.
"""

from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod

from agents.router_agent.models.request import ChatCompletionRequest, Message
from agents.router_agent.models.response import ChatCompletionResponse, Choice, Usage

logger = logging.getLogger("fde.router.adapters")


# ══════════════════════════════════════════════════════════════════
# Base Adapter
# ══════════════════════════════════════════════════════════════════


class BaseAdapter(ABC):
    """Abstract base for model adapters."""

    model_name: str
    provider: str
    cost_per_1k_tokens: float = 0.0
    supports_streaming: bool = True
    max_tokens: int = 4096

    @abstractmethod
    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Execute a completion request. Must be implemented by subclasses."""
        ...

    def health_check(self) -> bool:
        """Check if the adapter is available."""
        return True

    @property
    def full_name(self) -> str:
        return f"{self.provider}/{self.model_name}"


# ══════════════════════════════════════════════════════════════════
# Mock Adapter — works without API keys for development/testing
# ══════════════════════════════════════════════════════════════════


_MOCK_RESPONSES = {
    "hello": "你好！我是 FDE AI 平台的 Mock 适配器。当前没有连接真实模型 API，所有回复均为模拟数据。\n\n"
    "如果你想接入真实模型，请提供 API Key 并在 `.env` 中配置：\n"
    "- DEEPSEEK_API_KEY\n- QWEN_API_KEY\n- GLM_API_KEY",
    "help": "FDE AI 平台支持以下功能：\n"
    "- 📡 智能路由：自动选择最优模型\n"
    "- 🔍 RAG 检索：企业知识库问答\n"
    "- 👥 HR 分析：员工画像与风险评估\n"
    "- 📊 数据分析：NL2SQL 与交互式看板",
    "default": "这是来自 Mock 适配器的回复。你的问题是：\n\n"
    '"{query}"\n\n'
    "🔧 [演示模式] 接入真实 API Key 后可获得实际 AI 回复。",
}


class MockAdapter(BaseAdapter):
    """Mock adapter for development without API keys.

    Always available, returns canned responses matching common queries.
    """

    model_name: str = "mock-v1"
    provider: str = "fde"
    cost_per_1k_tokens: float = 0.0

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Return a mock response based on the last user message."""
        last_msg = _extract_last_user_message(request.messages)
        query_lower = last_msg.lower().strip()

        # Pattern match
        if any(word in query_lower for word in ("你好", "hello", "hi")):
            content = _MOCK_RESPONSES["hello"]
        elif any(word in query_lower for word in ("帮助", "help", "功能")):
            content = _MOCK_RESPONSES["help"]
        else:
            content = _MOCK_RESPONSES["default"].format(query=last_msg)

        # Estimate tokens: ~1 token per 4 chars (English) / 1 token per CJK char
        all_text = " ".join(m.content for m in request.messages)
        prompt_tokens = _estimate_tokens(all_text)
        completion_tokens = _estimate_tokens(content)

        return ChatCompletionResponse(
            id=f"mock-{uuid.uuid4().hex[:8]}",
            created=int(time.time()),
            model=self.full_name,
            choices=[Choice(message=Message(role="assistant", content=content))],
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )


# ══════════════════════════════════════════════════════════════════
# Stub Adapters — skeleton for real provider integrations
# ══════════════════════════════════════════════════════════════════


class DeepSeekStubAdapter(BaseAdapter):
    """Stub for DeepSeek API. Activates when DEEPSEEK_API_KEY is set."""

    model_name: str = "deepseek-chat"
    provider: str = "deepseek"
    cost_per_1k_tokens: float = 0.001
    max_tokens: int = 8192

    def health_check(self) -> bool:
        import os

        return bool(os.environ.get("DEEPSEEK_API_KEY"))

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        raise NotImplementedError("DeepSeek adapter not yet implemented (DEEPSEEK_API_KEY not set)")


class QwenStubAdapter(BaseAdapter):
    """Stub for Qwen (Tongyi) API. Activates when QWEN_API_KEY is set."""

    model_name: str = "qwen-turbo"
    provider: str = "qwen"
    cost_per_1k_tokens: float = 0.0008
    max_tokens: int = 8192

    def health_check(self) -> bool:
        import os

        return bool(os.environ.get("QWEN_API_KEY"))

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        raise NotImplementedError("Qwen adapter not yet implemented (QWEN_API_KEY not set)")


class GlmStubAdapter(BaseAdapter):
    """Stub for GLM (Zhipu) API. Activates when GLM_API_KEY is set."""

    model_name: str = "glm-4-flash"
    provider: str = "zhipu"
    cost_per_1k_tokens: float = 0.0006
    max_tokens: int = 4096

    def health_check(self) -> bool:
        import os

        return bool(os.environ.get("GLM_API_KEY"))

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        raise NotImplementedError("GLM adapter not yet implemented (GLM_API_KEY not set)")


# ══════════════════════════════════════════════════════════════════
# Adapter Registry
# ══════════════════════════════════════════════════════════════════


class ModelRegistry:
    """Central registry for all model adapters.

    Usage:
        registry = ModelRegistry()
        registry.register(MockAdapter())
        adapter = registry.get("fde/mock-v1")
    """

    def __init__(self) -> None:
        self._adapters: dict[str, BaseAdapter] = {}
        self._aliases: dict[str, str] = {}  # alias -> canonical full_name

    def register(self, adapter: BaseAdapter, aliases: list[str] | None = None) -> None:
        """Register an adapter instance.

        ``aliases`` lets an adapter answer to additional model names (used by
        the LiteLLM gray-rollout: one adapter instance answers ``fde-default``,
        ``fde-economy``, ``fde-frontier`` so existing client model names route
        through the proxy without touching calling code).
        """
        self._adapters[adapter.full_name] = adapter
        for alias in aliases or []:
            self._aliases[alias] = adapter.full_name
        logger.debug("Registered adapter: %s (aliases=%s)", adapter.full_name, aliases or [])

    def get(self, name: str) -> BaseAdapter | None:
        """Get adapter by full name, alias, or model name prefix match."""
        if name in self._adapters:
            return self._adapters[name]
        if name in self._aliases:
            return self._adapters[self._aliases[name]]

        # Prefix match (e.g., "deepseek" matches "deepseek/deepseek-chat")
        for full_name, adapter in self._adapters.items():
            if name in full_name or name == adapter.model_name:
                return adapter

        return None

    def list_models(self) -> list[str]:
        """List all registered model names (canonical + aliases)."""
        return list(self._adapters.keys()) + list(self._aliases.keys())

    def get_available(self) -> list[BaseAdapter]:
        """Get all adapters that pass health check (canonical only)."""
        available = []
        for adapter in self._adapters.values():
            try:
                if adapter.health_check():
                    available.append(adapter)
            except Exception:
                pass
        return available

    def discover_adapters(self) -> None:
        """Auto-register all built-in adapters."""
        self.register(MockAdapter())
        self.register(DeepSeekStubAdapter())
        self.register(QwenStubAdapter())
        self.register(GlmStubAdapter())


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════


def _estimate_tokens(text: str) -> int:
    """Estimate token count from text (rough heuristic).

    ~1 token per CJK char, ~1 token per 4 Latin chars.
    """
    if not text:
        return 0
    cjk = sum(1 for c in text if ord(c) > 0x4E00)
    other = len(text) - cjk
    return cjk + max(1, other // 4)


def _extract_last_user_message(messages: list[Message]) -> str:
    """Extract the last user message from the message list."""
    for msg in reversed(messages):
        if msg.role == "user":
            return msg.content
    return ""


class AdapterError(Exception):
    """Raised when an adapter fails to process a request."""

    def __init__(self, adapter_name: str, reason: str) -> None:
        self.adapter_name = adapter_name
        self.reason = reason
        super().__init__(f"Adapter '{adapter_name}' failed: {reason}")
