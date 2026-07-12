"""Router Agent — model adapters."""

from agents.router_agent.adapters.base import (
    AdapterError,
    BaseAdapter,
    MockAdapter,
    ModelRegistry,
)
from agents.router_agent.adapters.litellm_adapter import (
    LiteLLMAdapter,
    LiteLLMAdapterError,
    build_litellm_adapter,
)

__all__ = [
    "AdapterError",
    "BaseAdapter",
    "LiteLLMAdapter",
    "LiteLLMAdapterError",
    "MockAdapter",
    "ModelRegistry",
    "build_litellm_adapter",
]
