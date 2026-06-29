"""
Pytest configuration for FDE AI Platform.

Provides shared fixtures and markers used across all agent test suites.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import httpx


@pytest.fixture(scope="function")
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provide an async HTTPX client for testing FastAPI endpoints.

    Usage:
        async def test_health(async_client):
            response = await async_client.get("/health")
            assert response.status_code == 200
    """
    import httpx

    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture(scope="session")
def test_project_root() -> str:
    """Return the absolute path to the project root."""
    from pathlib import Path

    return str(Path(__file__).resolve().parent)
