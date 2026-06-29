"""Smoke tests for project structure and basic assertions."""

from __future__ import annotations

from pathlib import Path


def test_project_root_exists(test_project_root: str) -> None:
    """Verify the project root directory is accessible."""
    root = Path(test_project_root)
    assert root.is_dir()
    assert (root / "pyproject.toml").is_file()
    assert (root / "README.md").is_file()


def test_python_packages_importable() -> None:
    """Verify all core packages can be imported."""
    import agents.orchestrator
    import agents.rag_agent
    import agents.router_agent
    import shared

    assert shared
    assert agents.orchestrator
    assert agents.router_agent
    assert agents.rag_agent


def test_venv_runtime() -> None:
    """Verify we're running inside the project virtual environment."""
    import sys

    assert ".venv" in sys.executable or ".workbuddy" in sys.prefix

    py_version = sys.version_info
    assert py_version >= (
        3,
        11,
    ), f"Requires Python 3.11+, got {py_version.major}.{py_version.minor}"
