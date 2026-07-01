"""FDE Platform — shared prompt templates.

Prompts are versioned and organized by agent/use-case.
Avoid hardcoding prompts in agent code — reference from here.
"""

from __future__ import annotations

from shared.prompts.registry import get_prompt, list_prompts, register_prompt
from shared.prompts.templates import (
    SYSTEM_ANTI_FOOLPROOF,
    SYSTEM_RAG,
    SYSTEM_ROUTER,
    _prompts,
)

__all__ = [
    "SYSTEM_ANTI_FOOLPROOF",
    "SYSTEM_RAG",
    "SYSTEM_ROUTER",
    "_prompts",
    "get_prompt",
    "list_prompts",
    "register_prompt",
]
