"""查询缓存抽象（P3b C4 → Redis）。

默认**内存 LRU**（零依赖、测试友好）；生产可切 **Redis**（``CACHE_BACKEND=redis``，
懒加载 ``redis`` SDK）。Redis 连不上时**自动降级为内存**，避免缓存故障拖垮主链路。

结果缓存用于 ``QueryService.ask``：相同 (query, top_k, doc_type) 直接命中缓存，
降低向量检索 + 重排开销（计划 C4）。
"""

from __future__ import annotations

import abc
import json
import os
import time
from collections import OrderedDict
from typing import Any

DEFAULT_TTL = int(os.getenv("QUERY_CACHE_TTL", "300"))


class Cache(abc.ABC):
    """缓存抽象：查询结果等 JSON 安全对象的读写。"""

    @abc.abstractmethod
    async def get(self, key: str) -> Any | None:
        """命中返回原值，未命中返回 None。"""

    @abc.abstractmethod
    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """写入（ttl 秒，None 用默认）。"""

    @abc.abstractmethod
    async def delete(self, key: str) -> None:
        """删除单个 key。"""

    @abc.abstractmethod
    async def clear(self) -> None:
        """清空全部。"""


class MemoryCache(Cache):
    """进程内 LRU 缓存（带 TTL）。"""

    def __init__(self, maxsize: int = 512, default_ttl: int = DEFAULT_TTL) -> None:
        self._store: OrderedDict[str, Any] = OrderedDict()
        self._expires: dict[str, float] = {}
        self._maxsize = maxsize
        self._default_ttl = default_ttl

    async def get(self, key: str) -> Any | None:
        if key not in self._store:
            return None
        exp = self._expires.get(key)
        if exp is not None and exp <= time.monotonic():
            self._store.pop(key, None)
            self._expires.pop(key, None)
            return None
        self._store.move_to_end(key)
        return self._store[key]

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        self._store.pop(key, None)
        self._store[key] = value
        self._store.move_to_end(key)
        t = ttl if ttl is not None else self._default_ttl
        if t is not None and t >= 0:
            self._expires[key] = time.monotonic() + t
        while len(self._store) > self._maxsize:
            old, _ = self._store.popitem(last=False)
            self._expires.pop(old, None)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)
        self._expires.pop(key, None)

    async def clear(self) -> None:
        self._store.clear()
        self._expires.clear()


class RedisCache(Cache):
    """Redis 缓存（懒加载 ``redis`` SDK，连不上自动降级）。

    降级后会话期间退化为进程内 LRU，避免反复重试 Redis。
    """

    def __init__(self, url: str | None = None, default_ttl: int = DEFAULT_TTL) -> None:
        self._url = url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._default_ttl = default_ttl
        self._client: Any | None = None
        self._degraded = False
        self._fallback = MemoryCache(default_ttl=default_ttl)

    def _get_client(self) -> Any:
        if self._client is None:
            from redis import asyncio as aioredis  # 懒加载

            self._client = aioredis.from_url(self._url, decode_responses=False)
        return self._client

    async def get(self, key: str) -> Any | None:
        if self._degraded:
            return await self._fallback.get(key)
        try:
            raw = await self._get_client().get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            self._degraded = True
            return await self._fallback.get(key)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        if self._degraded:
            await self._fallback.set(key, value, ttl)
            return
        try:
            t = ttl if ttl is not None else self._default_ttl
            await self._get_client().set(
                key, json.dumps(value, ensure_ascii=False), ex=t
            )
        except Exception:
            self._degraded = True
            await self._fallback.set(key, value, ttl)

    async def delete(self, key: str) -> None:
        if self._degraded:
            await self._fallback.delete(key)
            return
        try:
            await self._get_client().delete(key)
        except Exception:
            self._degraded = True

    async def clear(self) -> None:
        if self._degraded:
            await self._fallback.clear()
            return
        try:
            await self._get_client().flushdb()
        except Exception:
            self._degraded = True


_cache_singleton: Cache | None = None


def get_cache() -> Cache:
    """按环境变量返回缓存后端（单例）。

    * ``CACHE_BACKEND=redis`` 且 ``redis`` 已安装 → RedisCache
    * 否则 → MemoryCache（含 Redis 不可用时自动降级）
    """
    global _cache_singleton
    if _cache_singleton is not None:
        return _cache_singleton

    backend = os.getenv("CACHE_BACKEND", "memory").lower()
    if backend == "redis":
        try:
            import redis  # noqa: F401  # 校验可导入

            _cache_singleton = RedisCache()
        except ImportError:
            _cache_singleton = MemoryCache()
    else:
        _cache_singleton = MemoryCache()
    return _cache_singleton


def reset_cache_singleton() -> None:
    """清空单例（测试隔离用）。"""
    global _cache_singleton
    _cache_singleton = None


__all__ = [
    "Cache",
    "MemoryCache",
    "RedisCache",
    "get_cache",
    "reset_cache_singleton",
]
