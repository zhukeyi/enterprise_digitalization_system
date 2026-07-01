"""Prompt registry functions."""

from __future__ import annotations

from typing import Any

from shared.prompts.templates import _prompts

__all__ = ["get_prompt", "list_prompts", "register_prompt"]


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
