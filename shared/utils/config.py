"""Config loading helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

__all__ = ["load_config"]


def load_config(path: str | Path, env_prefix: str = "FDE_") -> dict[str, Any]:
    """Load configuration from JSON/YAML file, overridden by env vars.

    Args:
        path: Path to config file.
        env_prefix: Environment variables with this prefix override file values.

    Returns:
        Merged configuration dictionary.
    """
    config: dict[str, Any] = {}
    path_obj = Path(path)

    if path_obj.suffix in (".json",) and path_obj.exists():
        config = json.loads(path_obj.read_text(encoding="utf-8"))

    # Override with env vars
    for key, value in os.environ.items():
        if key.startswith(env_prefix):
            config_key = key[len(env_prefix) :].lower()
            config[config_key] = value

    return config
