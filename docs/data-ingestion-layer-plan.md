# 数据输入层方案（A 本地文件 + B 连接器 Agent）— 统一入库

> 目标：把**两类异构数据源**——(A) 本地 Word/PPT/PDF/Excel/TXT 文件、(B) Java 连接器平台（logistics_agent）里的业务系统数据（用友/金蝶/海康…）——**统一收集、归一化、清洗、入库、切片、向量化**，让它们走同一条管线、落同一套表，下游 RAG/分析/看板直接消费。
>
> 复用：`ingestion-cleaning-module-plan.md`（A 部分）、`logistics-connector-integration-analysis.md`（B 部分）。本文聚焦**统一架构 + 入库落地**。

---

## 1. 核心设计思想：一个漏斗，两套入口

```
                    ┌──────────────── 统一入管管线 (IngestionPipeline) ────────────────┐
                    │ 归一化(Normalize) → 清洗(Clean) → 落库(Storage) → 切片(Chunk) → 向量化(Vector) │
                    └───────────────┬───────────────────────┬───────────────────────────┘
                                    │                        │
                ┌───────────────────┴────┐          ┌──────────┴──────────────────────┐
                │ A. 本地文件入口         │          │ B. 连接器 Agent 入口 (Python↔Java) │
                │ /ingest/upload (zip/目录)│         │ connector_agent 拉 Java REST      │
                │ ParserFactory(Docling…) │         │ → 归一 → 作为数据源入库            │
                └────────────────────────┘          └───────────────────────────────────┘
                                    两者都产出 CanonicalDocument → 同一套 3 张表 → Qdrant
```

**关键结论**：无论数据来自"一份散乱的 Excel"还是"用友的一批订单 JSON"，经过归一化后都是同一种 `CanonicalDocument`，落同一套库表，切片进同一个 Qdrant 集合。这就是"字段不一致"问题的统一解法。

---

## 2. A 部分：本地文件对接入库

### 2.1 流程（复用 ingestion 计划 §3/§6）
```
acquire(file) → parse(Docling/轻量) → normalize(FieldMapper/SchemaInference)
  → clean(去重/PII/GEO/质量) → persist_raw → persist_canonical
  → chunk(含表格父/子) → embed → upsert_qdrant → rebuild_bm25 → persist_chunks
```
- **解析器**：Docling 主解析（PDF/DOCX/PPTX/XLSX，表格 97.9% 准），现有轻量解析器作 txt/md/csv 与兜底；公式 PDF 预留 MinIO+MinerU。
- **字段归一化（灵魂）**：`field_mapping.yaml` 声明式别名/正则/类型强转 + `SchemaInference`（未知表头规则+LLM 推断，按 `source_system` 缓存）；映射不上的列落 `custom_fields` JSONB，**绝不丢数据**。
- **落库表**：`raw_documents` / `canonical_documents` / `document_chunks`（见 §4）。

### 2.2 关键实现点
- 新增 `agents/ingest_agent/`：`models.py`(CanonicalDocument/IngestionJob)、`parsers.py`、`normalizer.py`、`pipeline.py`。
- 复用：`ParserFactory`、`chunk_documents`、`EmbeddingModel`、`VectorStore`、`_CHUNK_ID_NAMESPACE` 派生、`CleaningPipeline`、`auth_filter` —— **不重写**。
- API：`POST /ingest/upload`、`GET /ingest/jobs/{id}`（轮询进度）、`GET /ingest/field-mappings`（可视化编辑）。

---

## 3. B 部分：Python(FDE) 对接 Java(logistics_agent) 连接器

### 3.1 对接方式（服务间 HTTP，不合并代码）
- Java 连接器是独立 REST 服务（如 `connector-yonyou:8091`），FDE 用 `httpx` 消费，**不共享进程**。
- 唯一耦合点 = **连接器契约**（manifest + 标准路径 + 响应信封），详见下方。

### 3.2 连接器契约（让两边即插即用，最小改动）
1. **`GET /manifest` 端点（Java 侧 M2，最关键）**：返回
   ```json
   { "system_key":"yonyou", "category":"enterprise",
     "entities":["order","inventory","shipment"],
     "operations":["list","get","create","subscribe"],
     "auth":"none|bearer", "version":"1.0", "base_path":"/api/v1" }
   ```
   FDE 注册时只传 `base_url`，自己拉 manifest 推断能力 → **免硬编码端口/路径**。
2. **稳定 base path**：所有连接器统一前缀（如 `/api/v1/connector/{entity}`）。
3. **响应信封**：复用 Java 侧已有 `ApiResponse<T>`。

> 这一步把 logistics_agent 从"半自动（deploy-tool 里硬编码端口表）"变成"真·即插即用"。

### 3.3 FDE 侧 `connector_agent` 包（复用现有 `ToolRegistry` 接缝）
```
agents/connector_agent/
  models.py      # ConnectorManifest, CanonicalEntity(订单/库存/设备…)
  registry.py    # ConnectorRegistry: system_key → ConnectorAdapter
  adapter.py     # ConnectorAdapter(httpx): 拉 manifest / 拼路径 / 归一 / 套 field_mapping
  tools.py       # 把已注册连接器动态注册成 ToolDefinition → ToolRegistry
  discovery.py   # 移植 deploy-tool 的 discovery.py 为纯 Python 扫描工具（可选）
```

**`adapter.py` 核心逻辑（入库关键）：**
```python
class ConnectorAdapter:
    async def pull(self, entity: str, params: dict) -> list[CanonicalDocument]:
        # 1. 调 Java REST（按 manifest 拼路径）
        resp = await self.http.get(f"{self.base}/api/v1/connector/{entity}", params=params)
        rows = resp.json()["data"]
        # 2. 套用共享 field_mapping（Java 的 FieldMappingConfig 与 FDE 同 schema）
        normalized = [self.field_mapper.apply(row, source_system=self.system_key) for row in rows]
        # 3. 包装成 CanonicalDocument，source_ref 标记来源
        return [
            CanonicalDocument(
                doc_id=uuid5(ns, f"{self.system_key}:{entity}:{r['id']}"),
                title=f"{self.system_key}/{entity}/{r.get('id')}",
                doc_type="connector_" + entity,
                source_system=self.system_key,
                full_text=self._to_text(r),          # 行 → 可读文本（供切片/检索）
                structured={"record": r},            # 原始结构化
                custom_fields={...未映射字段},
                content_hash=sha256(str(r).encode()),
            )
            for r in normalized
        ]
```
- `full_text` 由结构化记录拼成自然语言句（如"订单 ORD-123，客户甲公司，金额￥5000，状态已发货"），这样连接器数据**既能结构化查询，又能进 RAG 语义检索**。
- `source_ref = f"connector://{system_key}/{entity}"` 写入 `raw_documents.storage_ref`，与文件来源区分。

### 3.4 注册与治理
- `POST /connectors/register`（`base_url` + `system_key` + 凭据）→ 拉 manifest → 建 adapter → 注册 `ToolDefinition`（如 `connector_yonyou_get_orders`）。
- Supervisor 加"业务系统查询"路由 → "查用友华东仓库存"命中对应工具，无需改 Supervisor 代码（manifest 驱动）。
- **治理**：读操作经 `auth_filter`(ABAC) + `DecisionChainLog` 留痕；写操作（`createOrder`）标 `is_dangerous=True` 走防呆二次确认（补 Java 侧缺失的治理层）。

---

## 4. 统一落库表（A 与 B 共用）

> 在 `shared/models/schema.sql` 追加，**A、B 两套入口落同一套表**，用 `source_system` / `doc_type` 区分。

```sql
CREATE TABLE raw_documents (           -- 原始引用（文件或连接器）
    id UUID PRIMARY KEY,
    filename VARCHAR(512),             -- 连接器可为 NULL
    mime VARCHAR(128),
    storage_ref TEXT,                  -- 文件: 对象存储路径; 连接器: connector://system/entity
    content_hash VARCHAR(64) UNIQUE,   -- 幂等去重（同一条订单重复拉取跳过）
    size_bytes BIGINT,
    uploaded_by UUID,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE canonical_documents (     -- 归一化后的统一记录（A/B 同构）
    id UUID PRIMARY KEY,
    raw_id UUID REFERENCES raw_documents(id),
    title TEXT,
    doc_type VARCHAR(32),              -- pdf/docx/xlsx/connector_order/connector_inventory...
    author TEXT,
    created_at TIMESTAMPTZ,
    source_system VARCHAR(128),        -- A: 业务域/文件名; B: yonyou/kingdee/hikvision
    language VARCHAR(8),
    tags JSONB,
    full_text TEXT,                    -- B: 由记录拼成的自然语言
    structured JSONB,                  -- B: {record: {...}}; A: {tables/headings}
    custom_fields JSONB,               -- 未映射字段，绝不丢
    quality_score REAL,
    pii_masked BOOLEAN,
    created_at_ts TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE document_chunks (         -- 切片（关联 Qdrant）
    id UUID PRIMARY KEY,               -- = uuid5(chunk_id)
    doc_id UUID REFERENCES canonical_documents(id),
    chunk_index INT,
    strategy VARCHAR(32),
    content TEXT,
    metadata JSONB,
    embedding_id UUID,                 -- 对应 Qdrant point id
    parent_chunk_id UUID NULL          -- 表格/父子 chunk 自引用
);
CREATE INDEX idx_chunk_doc ON document_chunks(doc_id);
CREATE INDEX idx_canonical_source ON canonical_documents(source_system);
```

**入库路径对比：**
| 步骤 | A 本地文件 | B 连接器 |
|------|-----------|---------|
| acquire | `/ingest/upload` 文件 | `adapter.pull()` 拉 JSON |
| raw | 文件存 MinIO，`storage_ref=minio://...` | `storage_ref=connector://system/entity` |
| normalize | `FieldMapper`(Excel 列名别名) | `FieldMapper`(厂商字段别名，与 Java 同 schema) |
| canonical | `full_text`=清洗后正文 | `full_text`=记录拼自然语言 |
| chunk→vector | 同 | 同（一个订单往往 1 chunk） |
| RAG | 同 | 同（"用友 ORD-123"可语义命中） |

---

## 5. 字段映射对齐（A 与 B 统一一份 YAML）

- logistics_agent 的 `FieldMappingConfig` 与 FDE ingestion 的 `field_mapping.yaml` **是同一思想两种实现**，统一为一份 schema：`{from:[别名...], to:标准字段, coerce:类型}` + 兜底 `custom_fields`。
- Java 侧 `@ConfigurationProperties` 读、Python 侧 pydantic 读，**两边共享同一份规范**。
- logistics 的 `OrderModel/InventoryModel/...` 直接充当 FDE `CanonicalEntity` 的初始字段定义，省去重设计。

---

## 6. 实施分阶段（与之前节奏一致：先骨架，再打通）

| 阶段 | 范围 | 产出 |
|------|------|------|
| **P0 契约定型** | 定义 `ConnectorManifest` + 标准路径 + 信封；统一 `field_mapping.yaml` schema | `docs/connector-contract.md` |
| **P1 入库骨架** | `ingest_agent` 三表 + `CanonicalDocument` + `IngestionPipeline`（先支持文件 A） | A 端到端入库 |
| **P1 连接器骨架** | logistics 一个连接器加 `/manifest`；FDE `connector_agent` 注册 1 个 yonyou/mock 为 ToolDefinition | B 最小打通 |
| **P2 连接器入库** | `adapter.pull()` → canonical → chunk → Qdrant；验证"用友订单可被 RAG 问答" | A/B 同库同检索 |
| **P3 治理+扩展** | ABAC 包裹、discovery 移植、视频族接入、字段映射可视编辑 | 完整能力 |

**建议从 P0 + P1（两端各取最小切片）先打通**：logistics 加 `/manifest`，FDE `connector_agent` 能注册它并把它暴露成可问答工具，且连接器数据落进与文件相同的 `canonical_documents` 表。这一步不依赖重依赖、不污染生产。

---

## 7. 风险与注意

1. **语言边界不可逆**：Java↔Python 只能 HTTP，契约即唯一契约，版本向后兼容。
2. **视频流不进 RAG**：海康/大华 RTSP/HLS 是二进制流，作为"工具/流地址"暴露给看板，不进 ingestion（避免污染文档型 RAG）。
3. **连接器凭证安全**：`app_key/secret` 由 FDE 密钥管理注入，绝不下发前端；FDE 代理时再带租户上下文。
4. **连接器数据量大**：订单/库存可能百万行 → 入库走**增量/分页拉取 + 异步 worker**，且只把"需检索/需审计"的字段进 `full_text`，原始大 JSON 存 `structured` 不切片。
5. **契约漂移**：Java 改了 manifest/path，FDE 适配器拉不到就标 DOWN，不影响其他连接器。
