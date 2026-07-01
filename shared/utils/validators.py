"""Path and filename validation helpers."""

from __future__ import annotations

from pathlib import Path

__all__ = ["ensure_dir", "safe_filename"]


def ensure_dir(path: str | Path) -> Path:
    """Ensure a directory exists, creating it if necessary."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    import re

    name = re.sub(r"[^\w\s-]", "", name).strip()
    name = re.sub(r"[-\s]+", "_", name)
    return name[:255]
