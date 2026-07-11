"""P3b 缓存抽象测试（内存 LRU / Redis 降级）。"""

from __future__ import annotations

import pytest

from agents.ingestion_agent.cache import (
    MemoryCache,
    RedisCache,
    get_cache,
    reset_cache_singleton,
)


@pytest.mark.asyncio
async def test_memory_cache_set_get() -> None:
    c = MemoryCache()
    await c.set("k", {"a": 1})
    assert await c.get("k") == {"a": 1}


@pytest.mark.asyncio
async def test_memory_cache_ttl_expiry() -> None:
    c = MemoryCache(default_ttl=0)
    await c.set("k", 1, ttl=0)
    assert await c.get("k") is None


@pytest.mark.asyncio
async def test_memory_cache_lru_eviction() -> None:
    c = MemoryCache(maxsize=2)
    await c.set("a", 1)
    await c.set("b", 2)
    await c.set("c", 3)
    assert await c.get("a") is None  # 最旧被淘汰
    assert await c.get("c") == 3


@pytest.mark.asyncio
async def test_memory_cache_delete_clear() -> None:
    c = MemoryCache()
    await c.set("a", 1)
    await c.delete("a")
    assert await c.get("a") is None
    await c.set("b", 2)
    await c.clear()
    assert await c.get("b") is None


def test_get_cache_factory_memory(monkeypatch) -> None:
    monkeypatch.setenv("CACHE_BACKEND", "memory")
    reset_cache_singleton()
    assert isinstance(get_cache(), MemoryCache)


@pytest.mark.asyncio
async def test_redis_cache_degrades_without_server() -> None:
    """连不上 Redis 时优雅降级为内存，不抛错。"""
    c = RedisCache(url="redis://127.0.0.1:1/0")  # 不可达端口
    await c.set("k", 1)
    assert await c.get("k") == 1  # 降级后由内存兜底
