# 多源数据 — 数据库选型 / 搭建 / 扩展方案

> 背景：我们要同时存**三类异构数据**——(1) 结构化业务数据（连接器进来的订单/库存/设备）、(2) 半/非结构化文档（Word/PDF/Excel 解析后的正文与表格）、(3) 向量（切片 embedding）。外加原始二进制（大文件）、审计/决策链等元数据。本文给出选型、搭建、扩展方案。

---

## 1. 数据分类与各自的"最优存储"

| 数据类型 | 例子 | 访问模式 | 最优存储 | 理由 |
|---------|------|---------|---------|------|
| **结构化业务数据** | 订单/库存/设备 JSON（连接器） | 按字段过滤、聚合、联表、事务 | **PostgreSQL** | ACID、JSONB 容错、已用（governance SQLAlchemy）、强生态 |
| **半/非结构化文档** | 归一化正文、表格、自定义字段 | 按文档/字段检索、全文、灵活 schema | **PostgreSQL + JSONB** | 同一库内，关系+灵活一体；JSONB GIN 支持半结构查询 |
| **向量** | 切片 embedding（512/1024d） | ANN 近邻、按 payload 过滤 | **Qdrant**（已运行） | 专为向量；量化、过滤、分布式成熟 |
| **原始二进制** | 大 PDF/Office/连接器附件 | 整文件读、偶尔取 | **MinIO（S3 兼容）** | 对象存储便宜、解耦大 blob 与行库；ARM 二进制可用 |
| **全文/关键词检索（大规模）** | BM25 千万级 | 倒排、分词 | **OpenSearch**（可选）或 pgvector | 当前 457 块内存 BM25 够；百万+ 时下移 OpenSearch |
| **缓存 / 队列 / 会话** | 语义缓存、ingest 任务队列 | KV、低延迟、TTL | **Redis** | 标配；语义缓存 + 异步 worker 队列 |

> **核心原则：多语种持久化（Polyglot Persistence）**——每类数据用最合适的引擎，但**以 Postgres 为"系统记录（SoR）"**，其他引擎通过 `doc_id` / `embedding_id` 外键关联，保证一致性与可审计。

---

## 2. 选型决策（为什么不"一个库搞定"）

| 候选 | 结论 | 理由 |
|------|------|------|
| 只用 Postgres（+pgvector） | **主库用，向量暂不强行内迁** | pgvector 在 ~千万向量内很香（运维简单、事务一致）；但 Qdrant 已跑且在用，且量化/分布式更成熟。**保留 Qdrant 作向量专库**，Postgres 存元数据。若未来想"一库到底"，可平滑把向量迁 pgvector（ID 已对齐）。 |
| 只用 MongoDB | ❌ | 无原生向量 ANN、事务弱、中文企业场景运维成本高；JSONB 已覆盖其灵活优势 |
| 只用 Elastic/OpenSearch | ❌ | 擅检索不擅事务；业务数据的事务/联表弱；作为"BM25 规模化补充"而非主库 |
| Qdrant 当主库 | ❌ | 向量库，不存业务关系数据 |
| **Postgres + Qdrant + MinIO + Redis（推荐）** | ✅ | 各司其职，均已 ARM 可跑，运维边界清晰 |

---

## 3. 目标拓扑（当前 → 目标）

```
当前已运行：
  Postgres(governance)  Qdrant(fde_knowledge)  Dify  nginx8443
                         ↑ 已用

目标新增：
  + MinIO       (raw_documents.storage_ref 指向的对象存储)
  + Redis       (语义缓存 + ingest 异步队列 + 会话)
  + OpenSearch  (可选，BM25 规模化；当前内存 BM25 暂不急着上)
  + (Postgres) 追加 raw/canonical/chunks/connector 表 + pgvector 扩展(预留)
```

**数据流向：**
```
文件/连接器 → ingest_agent/connector_agent
   → 原始 blob → MinIO (storage_ref)
   → canonical_documents (Postgres, JSONB)
   → document_chunks (Postgres) ──embedding_id──► Qdrant (向量)
   → 语义缓存 → Redis
   → 大规模 BM25(可选) → OpenSearch
```

---

## 4. 搭建步骤（docker-compose 增量）

在现有 `docker-compose`（或新增 `docker-compose.data.yml`）追加：

```yaml
services:
  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_PASSWORD}
    volumes: ["minio_data:/data"]
    ports: ["9000:9000"]

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes: ["redis_data:/data"]

  # 可选：BM25 规模化
  opensearch:
    image: opensearch-project/opensearch:2
    environment: { "discovery.type": "single-node", "OPENSEARCH_INITIAL_ADMIN_PASSWORD": "${OS_PWD}" }
    volumes: ["os_data:/usr/share/opensearch/data"]

  # Postgres 追加扩展（已有实例执行一次）
  # CREATE EXTENSION IF NOT EXISTS vector;   -- pgvector，预留向量内迁
  # CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- 模糊/全文辅助
```

**Postgres 建表（追加到 `shared/models/schema.sql`）：**
- `raw_documents` / `canonical_documents` / `document_chunks`（见 `data-ingestion-layer-plan.md` §4）
- 连接器元数据表 `connector_registry`（system_key, base_url, manifest JSON, health, last_sync）
- 索引：`idx_canonical_source`、`GIN(idx_canonical_structured)`（JSONB 半结构查询）、`idx_chunk_doc`

**迁移工具**：用 Alembic（或现有 SQLAlchemy `Base.metadata.create_all`）管理版本，保证多环境一致。

**接入代码**：
- `minio_client.py`：`fde_minio` 单例（put/get，返回 `minio://bucket/key`）。
- `redis_client.py`：语义缓存（TTL）+ ARQ/Celery 异步队列（ingest 任务）。
- `canonical_repo.py`：封装 `canonical_documents` / `document_chunks` 的增删查 + 与 Qdrant 的 ID 对齐（`embedding_id = uuid5(chunk_id)`）。

---

## 5. 扩展性设计（从千级到亿级）

### 5.1 垂直扩展（先吃满单机）
- **嵌入/重排独立 GPU 机**：ARM 查询节点只做检索，重推理放 GPU 微服务（与 RAG 性能方案 T1/T5 一致）。
- **Postgres 升配**：更多内存让 `canonical_documents` 热数据留缓冲；JSONB GIN 索引驻内存。

### 5.2 Postgres（关系+JSONB）扩展
| 手段 | 做法 |
|------|------|
| **连接池** | pgbouncer，避免 worker 数 × 查询打爆连接 |
| **读写分离** | 1 主 N 从，读多写少（RAG 检索/看板读从库） |
| **分区** | `document_chunks` 按 `doc_id` 哈希或时间范围分区，单表不膨胀 |
| **JSONB 索引** | `GIN` 索引支持 `custom_fields`/`structured` 内字段查询 |
| **归档** | 冷文档（N 月未访问）迁历史表/列存（如 TimescaleDB/Citus） |

### 5.3 Qdrant（向量）扩展
| 手段 | 做法 |
|------|------|
| **量化** | Scalar（int8，4x）起步，语料大后 Binary（32x）+ oversampling+rescore（见 RAG 方案 T2） |
| **Payload 索引** | 对 `source_system`/`doc_type` 建索引，过滤检索不掉速 |
| **分布式** | 单节点 → 集群分片（`shard_number`）+ 副本，水平扩到亿级向量 |
| **快照/备份** | 定期 `snapshot` 到 MinIO，灾备 |

### 5.4 MinIO（二进制）扩展
- 多盘/多节点 erasure coding；桶级配额；冷热分层（S3 lifecycle 到低成本存储）。

### 5.5 管线扩展（ ingestion 是 CPU 重活）
- **异步 worker 队列**（Redis + ARQ/Celery）：上传/拉取 → 排队 → 解析/嵌入在 worker 池跑，不阻塞 API。
- **批量嵌入**（`embed_batch` 已支持）压满 GPU；连接器增量分页拉取，避免一次性百万行。
- **幂等**：`content_hash` 去重，重跑安全；连接器用 `(system_key, entity, id)` 作幂等键。

### 5.6 一致性边界
- **系统记录 = Postgres**。Qdrant/MinIO/OpenSearch 都是"派生索引"，由 `doc_id`/`embedding_id` 关联。
- 文档删除/更新：删 Postgres 行 → 同步删 Qdrant point（`delete_points`）+ 失效 Redis 缓存 + 重建受影响 BM25 段。
- 用 **outbox / 事件表** 保证"删一行"触发多引擎清理，避免幽灵向量。

---

## 6. 当前已具备 vs 待建

| 项 | 状态 | 行动 |
|----|------|------|
| Postgres（governance 表） | ✅ 已用 | 追加 raw/canonical/chunks/connector 表 |
| Qdrant（fde_knowledge） | ✅ 已运行 | 加量化配置 + payload 索引 |
| Dify | ✅ 已部署 | 仅作快速预览通道，不冲突 |
| MinIO | ❌ 待建 | docker-compose 加，接 `minio_client` |
| Redis | ❌ 待建 | 语义缓存 + 异步队列 |
| OpenSearch | ⚠️ 可选 | 百万+ chunk 时再上 BM25 规模化 |
| pgvector 扩展 | ⚠️ 预留 | 若想"一库到底"再开 |

---

## 7. 风险与注意

1. **不要把向量硬塞进 Postgres 当主路径**（当前规模 Qdrant 更好）；pgvector 是"未来可选内迁"，不是现在必做。
2. **JSONB 不是万能**：高频过滤/聚合字段应提为标准列（`source_system`/`doc_type`/`created_at`），只把"真灵活"部分放 `custom_fields`，否则 GIN 索引也救不了慢查询。
3. **多引擎一致性是运维难点**：必须靠 `doc_id` 关联 + 事件驱动清理，否则会出现"Postgres 没了但 Qdrant 还有"的幽灵数据。
4. **MinIO 必须设访问策略**：原始文件可能含敏感信息，桶级 IAM + 服务端加密；FDE 代理访问，凭证不下发前端。
5. **ARM 资源有限**：MinIO/Redis 极轻，可同机；OpenSearch 较重，真需要再单独机器。
