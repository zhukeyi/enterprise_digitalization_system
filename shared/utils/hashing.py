"""Content hashing helpers."""

from __future__ import annotations

import hashlib

__all__ = ["hash_content"]


def hash_content(content: str, algorithm: str = "sha256") -> str:
    """Hash a string for deduplication."""
    h = hashlib.new(algorithm)
    h.update(content.encode("utf-8"))
    return h.hexdigest()
