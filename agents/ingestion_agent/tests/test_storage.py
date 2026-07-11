"""P3b 对象存储抽象测试（MinIO / 本地 / 内存）。"""

from __future__ import annotations

import pytest

from agents.ingestion_agent.storage import (
    FakeStorage,
    LocalStorage,
    MinIOStorage,
    compute_file_hash,
    get_storage,
    make_storage_key,
    reset_storage_singleton,
)


@pytest.mark.asyncio
async def test_fake_storage_roundtrip() -> None:
    s = FakeStorage()
    ref = await s.put("a/b.txt", b"hello")
    assert ref.startswith("memory://")
    assert await s.exists(ref)
    assert await s.get(ref) == b"hello"
    await s.delete(ref)
    assert not await s.exists(ref)


@pytest.mark.asyncio
async def test_local_storage_roundtrip(tmp_path) -> None:
    s = LocalStorage(tmp_path)
    ref = await s.put("raw/ab/cd/file.csv", b"data")
    assert ref.startswith("local://")
    assert await s.exists(ref)
    assert await s.get(ref) == b"data"


def test_make_storage_key_content_addressed() -> None:
    k = make_storage_key("f.csv", "deadbeef" * 8)
    assert k.startswith("raw/de/deadbeef")
    assert k.endswith("f.csv")


def test_compute_file_hash_deterministic() -> None:
    assert compute_file_hash(b"x") == compute_file_hash(b"x")
    assert compute_file_hash(b"x") != compute_file_hash(b"y")
    assert len(compute_file_hash(b"x")) == 64


def test_get_storage_factory_memory(monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "memory")
    reset_storage_singleton()
    assert isinstance(get_storage(), FakeStorage)


def test_get_storage_factory_local(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path))
    reset_storage_singleton()
    assert isinstance(get_storage(), LocalStorage)


def test_minio_from_env_defaults(monkeypatch) -> None:
    monkeypatch.setenv("MINIO_BUCKET", "fde-raw")
    s = MinIOStorage.from_env()
    assert s._bucket == "fde-raw"
