# 数据底座 Runbook（P3b）

> 版本：v1.0 | 部署方言：SQLite（生产） | 生效日期：2026-07-11

## 1. 模块概览

| 模块 | 文件 | 职责 |
|------|------|------|
| 对象存储抽象 | `agents/ingestion_agent/storage.py` | MinIO /本地/内存三种后端，原始文件字节外置，DB 只存元数据 |
| RawDocument 幂等 | `agents/ingestion_agent/database/models.py` L51-53 | `content_hash`（sha256）+ `storage_ref` 列，阻止重复入库幽灵文档 |
| FTS5 全文索引 | `agents/ingestion_agent/fts.py` | SQLite FTS5 虚拟表（Postgres GIN 等价），ASCII MATCH + CJK LIKE 兜底 |
| 启动迁移 | `agents/ingestion_agent/migration.py` | 幂等 ALTER（旧库升级）+ CREATE VIRTUAL TABLE IF NOT EXISTS |
| 查询缓存 | `agents/ingestion_agent/cache.py` | 内存 LRU（默认）/ Redis（`CACHE_BACKEND=redis`），降级兜底 |
| 管线集成 | `agents/ingestion_agent/pipeline.py` | ingest_file/ingest_excel 接入存储+幂等+FTS |


## 2. 环境变量

### 对象存储

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `STORAGE_BACKEND` | （自动检测） | `minio` / `local` / `memory` |
| `MINIO_ENDPOINT` | `10.0.0.159:9000` | MinIO 地址 |
| `MINIO_ACCESS_KEY` | （空） | MinIO AK |
| `MINIO_SECRET_KEY` | （空） | MinIO SK |
| `MINIO_BUCKET` | `fde-raw` | Bucket 名 |
| `MINIO_SECURE` | `false` | 是否 HTTPS |
| `STORAGE_LOCAL_ROOT` | `<module>/.storage-tmp` | 本地后端根目录 |

### 查询缓存

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CACHE_BACKEND` | `memory` | `memory` / `redis` |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接串 |
| `QUERY_CACHE_TTL` | `300` | 缓存过期时间（秒） |

### 自动检测逻辑
- `STORAGE_BACKEND` 未设置 且 `MINIO_ENDPOINT` 存在 → **MinIO**
- 两者都未设置 → **LocalStorage**（`STORAGE_LOCAL_ROOT` 目录）


## 3. 关键行为

### 3.1 上传幂等（无幽灵）

1. 上传文件 → `compute_file_hash(data)` 计算 sha256
2. 查 `raw_documents.content_hash`：若已存在 → 返回 `{"duplicated": True, "raw_id": "..."}`, **不创建新行**
3. 相同原始字节永远只有 1 条 RawDocument + N 条 CanonicalDocument（N=上一次解析结果）
4. `ingest_rows` 也支持 `file_hash` 参数（Excel 路径）

### 3.2 大文件外置

- 上传的文件字节 → 对象存储（MinIO / 本地），DB 的 `raw_payload` 仅存元数据（filename、blocks 等）
- `raw_documents.storage_ref` 记录引用（如 `minio://fde-raw/raw/ab/cdef.../filename`）
- 通过 `storage.get(storage_ref)` 可按需取回原始字节

### 3.3 FTS 词法召回

- 每次创建 CanonicalDocument 时自动写入 `canonical_fts` FTS5 表
- 查询时：ASCII 词走 `MATCH`（精确），CJK / 子串走 `LIKE` 兜底
- FTS 索引失败**不阻断入库**（静默跳过，日志 debug）

### 3.4 缓存

- `QueryService.ask` 结果按 `sha256(query|top_k|doc_type)` 缓存
- 默认 300s TTL，内存 LRU 512 条
- Redis 连不上自动降级为内存


## 4. 启动顺序

```
init_database()                     # create_all 表
  └─ migrate_schema(get_engine())  # ALTER 新列 + 创建 canonical_fts（幂等）
```

已在 `agents/router_agent/main.py:startup_event` 中集成。


## 5. 常见操作

### 5.1 生产启用 MinIO

```bash
export STORAGE_BACKEND=minio
export MINIO_ENDPOINT=10.0.0.159:9000
export MINIO_ACCESS_KEY=...
export MINIO_SECRET_KEY=...
```

### 5.2 生产启用 Redis 缓存

```bash
export CACHE_BACKEND=redis
export REDIS_URL=redis://10.0.0.15:6379/0
```

### 5.3 验证幂等

```bash
# 上传同一文件两次，第二次返回 duplicated=True
curl -X POST https://host/fde-api/ingest/upload \
  -F "file=@test.csv" -F "doc_type=sales"
```

### 5.4 检查 FTS 表

```bash
sqlite3 fde_platform.db "SELECT name FROM sqlite_master WHERE type='table' AND name='canonical_fts'"
sqlite3 fde_platform.db "SELECT count(*) FROM canonical_fts"
```


## 6. 故障处理

| 症状 | 排查 | 修复 |
|------|------|------|
| 上传成功但 RawDocument 无 content_hash | DB 是旧库未迁移 | 重启服务（启动时执行 `migrate_schema`） |
| FTS 查询无结果 | `canonical_fts` 表缺失 | 同上一行，或手动 `CREATE VIRTUAL TABLE` |
| MinIO 不可用仍能上传 | 自动降级为 LocalStorage | 检查 `MINIO_ENDPOINT` / 网络 |
| Redis 不可用 | 缓存自动降级为内存 | 检查 `REDIS_URL` / 网络 |