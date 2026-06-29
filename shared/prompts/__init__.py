"""FDE Platform — shared prompt templates.

Prompts are versioned and organized by agent/use-case.
Avoid hardcoding prompts in agent code — reference from here.
"""

from __future__ import annotations

from typing import Any

# ── System Prompts ─────────────────────────────────────────────────


SYSTEM_ROUTER = """You are the FDE intelligent routing engine.
Analyze the user's request and determine:
1. Complexity level: simple, medium, complex
2. Sensitivity: public, internal, confidential
3. Best model to handle: cost-optimized vs performance-optimized
4. Whether RAG retrieval is needed

Respond in JSON format with routing decision."""

SYSTEM_RAG = """You are the FDE knowledge retrieval engine.
Given a user query and retrieved document chunks, synthesize a comprehensive answer.
- Cite sources when possible (document name, chunk ID)
- Mark unanswerable questions clearly
- Never fabricate information from outside the provided context"""

SYSTEM_ANTI_FOOLPROOF = """You are the FDE anti-foolproof guardian.
Before executing any user action, verify:
1. Is the action reversible?
2. Has the user been warned about irreversible operations?
3. Does the action affect other users or system components?
4. Is the user about to delete/modify something they might not intend to?

If any check fails, block the action and explain why in plain, non-technical language.
Assume the user is NOT a technical expert — use simple words."""


# ── Prompt Registry ────────────────────────────────────────────────

_prompts: dict[str, str] = {
    "system.router": SYSTEM_ROUTER,
    "system.rag": SYSTEM_RAG,
    "system.anti_foolproof": SYSTEM_ANTI_FOOLPROOF,
}


def get_prompt(name: str, **kwargs: Any) -> str:
    """Retrieve a prompt template by name, with optional formatting.

    Args:
        name: Prompt identifier (e.g., 'system.router').
        **kwargs: Variables to format into the template.

    Returns:
        Formatted prompt string.
    """
    template = _prompts.get(name, "")
    if kwargs:
        return template.format(**kwargs)
    return template


def register_prompt(name: str, template: str) -> None:
    """Register a new prompt template.

    Args:
        name: Unique prompt identifier.
        template: Prompt template string.
    """
    _prompts[name] = template


def list_prompts() -> list[str]:
    """List all registered prompt names."""
    return sorted(_prompts.keys())
