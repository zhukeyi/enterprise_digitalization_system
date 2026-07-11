"""对象存储抽象（P3b：MinIO / 本地 / 内存）。

把上传的原始文件字节存入对象存储（生产用 MinIO，开发/测试用本地文件系统或
内存），使：

* 关系库 ``raw_payload`` 只保留元数据，原始字节不进 DB（避免大文件撑爆库）；
* 重入库 / 审计 / 重新分块时可按需取回原始字节；
* 与 ``content_hash`` 幂等（详见 pipeline.py）配合，实现「重复 ingest 无幽灵」。

``Minio`` / ``redis`` 等重依赖均**懒加载**，未安装时不影响其它模块导入与测试。
"""

from __future__ import annotations

import abc
import hashlib
import io
import os
from pathlib import Path
from typing import Any

# 内容寻址 key 前缀：raw/<hh>/<hash>/<filename>，保证相同文件落到同一对象（天然幂等）。
RAW_PREFIX = "raw"


def make_storage_key(filename: str, content_hash: str) -> str:
    """内容寻址 key：相同 (filename, hash) 永远落到同一对象。"""
    safe_name = Path(filename).name or "blob"
    return f"{RAW_PREFIX}/{content_hash[:2]}/{content_hash}/{safe_name}"


def _split_ref(ref: str) -> tuple[str, str]:
    """把 ``scheme://rest`` 拆成 (scheme, rest)。"""
    scheme, sep, rest = ref.partition("://")
    return (scheme, rest) if sep else ("", ref)


class ObjectStorage(abc.ABC):
    """对象存储抽象：原始文件字节的落库 / 取回 / 判存。"""

    @abc.abstractmethod
    async def put(self, key: str, data: bytes) -> str:
        """写入字节，返回可回查的 storage_ref（含 scheme，如 ``minio://...``）。"""

    @abc.abstractmethod
    async def get(self, ref: str) -> bytes:
        """按 storage_ref 取回字节。"""

    @abc.abstractmethod
    async def exists(self, ref: str) -> bool:
        """判存。"""

    @abc.abstractmethod
    async def delete(self, ref: str) -> None:
        """删除（按 ref）。"""


class MinIOStorage(ObjectStorage):
    """MinIO / S3 兼容对象存储（懒加载 ``minio`` SDK）。"""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
    ) -> None:
        self._endpoint = endpoint
        self._bucket = bucket
        self._secure = secure
        self._access_key = access_key
        self._secret_key = secret_key
        self._client: Any | None = None

    @classmethod
    def from_env(cls, bucket: str | None = None) -> MinIOStorage:
        """从环境变量构建（生产默认）。"""
        endpoint = os.getenv("MINIO_ENDPOINT", "10.0.0.159:9000")
        access_key = os.getenv("MINIO_ACCESS_KEY", "")
        secret_key = os.getenv("MINIO_SECRET_KEY", "")
        bucket = bucket or os.getenv("MINIO_BUCKET", "fde-raw")
        secure = os.getenv("MINIO_SECURE", "false").lower() in ("1", "true", "yes")
        return cls(endpoint, access_key, secret_key, bucket, secure)

    def _get_client(self) -> Any:
        if self._client is None:
            from minio import Minio  # 懒加载

            self._client = Minio(
                self._endpoint,
                access_key=self._access_key,
                secret_key=self._secret_key,
                secure=self._secure,
            )
        return self._client

    async def put(self, key: str, data: bytes) -> str:
        client = self._get_client()
        try:
            if not client.bucket_exists(self._bucket):
                client.make_bucket(self._bucket)
        except Exception:
            # bucket 已存在或权限问题在 put 时再暴露，这里容错继续
            pass
        client.put_object(self._bucket, key, io.BytesIO(data), length=len(data))
        return f"minio://{self._bucket}/{key}"

    async def get(self, ref: str) -> bytes:
        _scheme, rest = _split_ref(ref)
        bucket, _, key = rest.partition("/")
        bucket = bucket or self._bucket
        resp = self._get_client().get_object(bucket, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    async def exists(self, ref: str) -> bool:
        _scheme, rest = _split_ref(ref)
        bucket, _, key = rest.partition("/")
        bucket = bucket or self._bucket
        try:
            self._get_client().stat_object(bucket, key)
            return True
        except Exception:
            return False

    async def delete(self, ref: str) -> None:
        _scheme, rest = _split_ref(ref)
        bucket, _, key = rest.partition("/")
        bucket = bucket or self._bucket
        self._get_client().remove_object(bucket, key)


class LocalStorage(ObjectStorage):
    """本地文件系统存储（开发 / 测试友好，零重依赖）。"""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # 防目录穿越：只取相对片段
        return self._root.joinpath(*[p for p in Path(key).parts if p not in ("", ".", "..")])

    async def put(self, key: str, data: bytes) -> str:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return f"local://{key}"

    async def get(self, ref: str) -> bytes:
        _scheme, rest = _split_ref(ref)
        return self._path(rest).read_bytes()

    async def exists(self, ref: str) -> bool:
        _scheme, rest = _split_ref(ref)
        return self._path(rest).exists()

    async def delete(self, ref: str) -> None:
        _scheme, rest = _split_ref(ref)
        self._path(rest).unlink(missing_ok=True)


class FakeStorage(ObjectStorage):
    """内存存储（测试用，无需任何 IO）。"""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes) -> str:
        ref = f"memory://{key}"
        self._store[ref] = data
        return ref

    async def get(self, ref: str) -> bytes:
        return self._store[ref]

    async def exists(self, ref: str) -> bool:
        return ref in self._store

    async def delete(self, ref: str) -> None:
        self._store.pop(ref, None)


_storage_singleton: ObjectStorage | None = None


def get_storage() -> ObjectStorage:
    """按环境变量返回存储后端（单例）。

    * ``STORAGE_BACKEND=minio`` → MinIO（需 ``minio`` SDK + MINIO_* 环境变量）
    * ``STORAGE_BACKEND=local`` → 本地目录（``STORAGE_LOCAL_ROOT``，默认系统临时目录）
    * ``STORAGE_BACKEND=memory`` / ``fake`` → 内存
    * 未设置：若 ``MINIO_ENDPOINT`` 存在则 MinIO，否则本地临时目录（零配置默认）
    """
    global _storage_singleton
    if _storage_singleton is not None:
        return _storage_singleton

    backend = os.getenv("STORAGE_BACKEND", "").lower()
    if backend in ("memory", "fake"):
        _storage_singleton = FakeStorage()
    elif backend == "minio":
        _storage_singleton = MinIOStorage.from_env()
    elif backend == "local":
        _storage_singleton = LocalStorage(_local_root())
    elif os.getenv("MINIO_ENDPOINT"):
        _storage_singleton = MinIOStorage.from_env()
    else:
        _storage_singleton = LocalStorage(_local_root())
    return _storage_singleton


def reset_storage_singleton() -> None:
    """清空单例（测试隔离用）。"""
    global _storage_singleton
    _storage_singleton = None


def _local_root() -> str:
    return os.getenv("STORAGE_LOCAL_ROOT") or os.path.join(
        os.path.dirname(__file__), ".storage-tmp"
    )


def compute_file_hash(data: bytes) -> str:
    """文件级内容哈希（sha256，截断 64 字符，与 ``content_hash`` 列宽一致）。"""
    return hashlib.sha256(data).hexdigest()[:64]


__all__ = [
    "FakeStorage",
    "LocalStorage",
    "MinIOStorage",
    "ObjectStorage",
    "compute_file_hash",
    "get_storage",
    "make_storage_key",
    "reset_storage_singleton",
]
