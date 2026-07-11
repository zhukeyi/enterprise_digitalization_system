# 多维数据输入与清洗模块 — 设计方案（Unified Ingestion & Cleaning Module）

> 目标：把企业环境中散落的 **Word / PPT / PDF / Excel / TXT（及 CSV/MD/HTML）** 文件，
> 经过"解析 → 字段归一化 → 清洗 → 落库 → 切片 → 向量化"统一管线，
> 统一收集进数据库，并直接支撑现有 RAG 检索。
> 解决核心痛点：**同一批文件字段命名/结构不一致，无法统一入库**。

---

## 1. 现状盘点（FDE 已有什么）

| 能力 | 现状 | 位置 | 评价 |
|------|------|------|------|
| 文件解析 | `ParserFactory` + 6 个解析器（PDF/DOCX/XLSX/PPTX/MD/TXT） | `rag_agent/document_parser.py` | **朴素**：PDF 用 PyMuPDF `get_text()`（丢表格/版面）；DOCX 只拼段落（丢表格）；XLSX 拍平成 TSV（丢列语义） |
| 切片 | `FixedSize / Semantic / Recursive` 三种 | `rag_agent/chunking.py` | **可用**，且支持父子 chunk 元数据 |
| 向量化+入库 | `parse→chunk→embed(BGE)→Qdrant` + BM25 重建 | `rag_agent/integration.py` (`_rag_ingest_sync`) | **可用**，但只吃本地文件路径，无采集/归一化/落库环节 |
| 清洗 | 去重/标准化/PII 脱敏/GEO 评估/质量评分 | `data_agent/cleaning.py` | **只服务 web/rss/api 源**，内存存储，无文件源、无字段映射 |
| 数据库 | Postgres：users/api_keys/audit_logs/decision_chain_logs/knowledge_bases | `shared/models/schema.sql` | **无 documents / chunks 表**；governance_agent 已有 SQLAlchemy 会话模式可复用 |
| 向量库 | Qdrant（已运行，`fde_knowledge` 集合） | — | 复用，point ID 用 `uuid5(chunk_id)` 派生（已对齐 BM25） |

**结论**：零件基本齐全，但缺三块拼图——**① 文件采集入口**、**② 字段归一化/模式映射（解决"字段不一致"）**、**③ 文档/切片持久化落库**。本模块=把现有零件编排成端到端管线 + 补齐这三块。

---

## 2. 成熟方案调研与选型

| 方案 | 定位 | 格式覆盖 | 质量/速度 | 自托管 | 适配结论 |
|------|------|---------|----------|--------|---------|
| **Docling**（IBM → LF AI & Data，42k★） | 结构化解析工具包 | PDF/DOCX/PPTX/XLSX/HTML/图 | 表格 97.9% 准确率；CPU 可跑；**结构/层级保留好** | ✅ 完全本地 | **主解析器首选**：敏感数据不出域，中文企业文档友好 |
| Unstructured.io | 全能 ETL 平台 | 20+ 格式 | OCR 强但本地慢（51–141s/页） | ⚠️ 本地重 | 可作兜底，非首选 |
| LlamaParse | 表格专才（LlamaCloud） | 主要 PDF | 最快（~6s）但**依赖云端 API** | ❌ | 敏感数据不适用，排除 |
| MinerU | 公式/学术 PDF | PDF/Word/PPT | 公式最强 | ✅ | 仅作公式型 PDF 的可选后端 |
| **LlamaIndex IngestionPipeline** | **架构范式** | — | — | — | **直接借鉴其 "Transformation 链 + 节点缓存 + 入库" 模式** |
| Dify / RAGFlow | 端到端 KB 系统 | 多 | 开箱即用 UI | ✅（已部署 Dify） | 可用作"临时快速通道"，但数据不在 FDE 库内、难与 ABAC/审计/审计链集成 |

**选型决策**：
- **解析层**：以 **Docling** 为结构化主解析器（PDF/DOCX/PPTX/XLSX），保留现有轻量解析器作 txt/md/csv/email 与降级兜底；公式型 PDF 预留 MinerU 适配器。
- **编排范式**：借鉴 **LlamaIndex IngestionPipeline** —— 把"解析/归一化/切片/向量化"做成可插拔 Transformation，节点+转换按哈希缓存（增量重跑省时）。
- **不引入 Dify/RAGFlow 作主路径**：本模块是 FDE 自有资产，需与 governance（RBAC/ABAC）、audit_logs、decision_chain_logs 打通；Dify 仅作可选快速预览通道。

---

## 3. 目标架构（分层）

```
┌──────────────────────────────────────────────────────────────────┐
│ 采集层 Acquisition                                                │
│  /ingest/upload (multipart/zip/目录) · 监听文件夹 · SourceType.FILE │
└───────────────┬──────────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────────┐
│ 解析层 Parsing（ParserRegistry 适配器）                            │
│  DoclingParser(PDF/DOCX/PPTX/XLSX) ──fallback──► 现有轻量解析器     │
│  输出: RawDocument{ text, tables[], headings[], images[], metadata }│
└───────────────┬──────────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────────┐
│ ★ 归一化层 Normalization（本模块核心，解决"字段不一致"）            │
│  CanonicalDocument 标准模型                                        │
│  FieldMapper: 声明式映射(YAML) 列名别名词典/正则/类型强转          │
│  SchemaInference: 未知表头→LLM/规则推断映射，按 source_system 缓存 │
└───────────────┬──────────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────────┐
│ 清洗层 Cleaning（复用 data_agent.CleaningPipeline）                │
│  去重(content hash) · PII 脱敏 · GEO 评估 · 质量评分 · 丢弃低质    │
└───────────────┬──────────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────────┐
│ 落库层 Storage（Postgres，新增 3 张表，见 §4）                     │
│  raw_documents · canonical_documents · document_chunks             │
└───────────────┬──────────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────────┐
│ 切片层 Chunking（复用 rag_agent.chunking）                         │
│  recursive/semantic/fixed + Docling HybridChunker；表格→父/子 chunk │
└───────────────┬──────────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────────┐
│ 向量化层 Embedding（复用 EmbeddingModel + VectorStore → Qdrant）    │
│  chunk_id → uuid5 → Qdrant point；重建 BM25；权限标签随 payload   │
└──────────────────────────────────────────────────────────────────┘
```

编排器：`IngestionPipeline.run(job)` 串联上述阶段，带 **per-doc 状态、幂等（内容哈希去重）、异步、进度回调**。

---

## 4. 数据模型（Canonical Schema + DB 表）

### 4.1 标准文档模型 `CanonicalDocument`（新增 `agents/ingest_agent/models.py`）
```python
class CanonicalDocument(BaseModel):
    doc_id: str                      # uuid
    title: str                      # 归一化标题
    doc_type: str                   # pdf/docx/pptx/xlsx/txt/...
    author: str | None
    created_at: datetime | None     # 强转为 UTC（兼容 "2024/1/1"、"2024-01-01" 等多种格式）
    source_system: str | None       # 来源系统/业务域（用于映射缓存与权限）
    language: str = "zh"
    tags: list[str] = []
    full_text: str                  # 清洗后正文
    structured: dict                # {tables:[...], headings:[...], images:[...]}
    custom_fields: dict             # 无法映射到标准字段的余下列 → JSONB 保留，不丢数据
    content_hash: str               # 去重用
```

### 4.2 Postgres 新增表（`shared/models/schema.sql` 追加）
```sql
CREATE TABLE raw_documents (         -- 原始文件/引用，便于重解析
    id UUID PRIMARY KEY,
    filename VARCHAR(512), mime VARCHAR(128),
    storage_ref TEXT,               -- 本地/对象存储路径或 blob
    content_hash VARCHAR(64) UNIQUE,-- 幂等去重
    size_bytes BIGINT, uploaded_by UUID,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE canonical_documents (   -- 归一化后的统一记录
    id UUID PRIMARY KEY,
    raw_id UUID REFERENCES raw_documents(id),
    title TEXT, doc_type VARCHAR(32), author TEXT,
    created_at TIMESTAMPTZ, source_system VARCHAR(128),
    language VARCHAR(8), tags JSONB,
    full_text TEXT, structured JSONB, custom_fields JSONB,
    quality_score REAL, pii_masked BOOLEAN,
    created_at_ts TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE document_chunks (       -- 切片，关联 Qdrant
    id UUID PRIMARY KEY,             -- = uuid5(chunk_id)
    doc_id UUID REFERENCES canonical_documents(id),
    chunk_index INT, strategy VARCHAR(32),
    content TEXT, metadata JSONB,
    embedding_id UUID,               -- 对应 Qdrant point id
    parent_chunk_id UUID NULL        -- 表格父 chunk 自引用
);
CREATE INDEX idx_chunk_doc ON document_chunks(doc_id);
```

> 切片内容仍进 Qdrant 做语义检索；Postgres 存结构化/可审计/权限相关字段。两者用 `embedding_id` 关联。

---

## 5. 字段不一致的统一方案（模块灵魂）

企业里同一业务域的 Excel/CSV 列名千奇百怪（"客户名称/客户名/顾客/Customer"），本模块用**三层映射**解决：

1. **声明式映射（YAML，人工/一次性配置）** —— `field_mapping.yaml`
   ```yaml
   source_system: "sales_crm"
   rules:
     - from: ["客户名称","客户名","顾客","Customer"]   # 别名词典
       to: subject
     - from: ["日期","时间","dt"]
       to: created_at
       coerce: date            # 归一为 ISO8601
     - from: ["金额","price","amt"]
       to: amount
       coerce: float
   ```
   `FieldMapper` 按别名匹配 + 正则 + 类型强转（日期/数字/枚举）。

2. **Schema Inference（未知表头自动推断）** —— 首次遇到未配置 source_system 时：
   - 先用**规则启发式**（列名包含"日期/时间"→date；含"金额/价格/¥/$"→float；含"名/name"→subject 等）；
   - 规则置信度低时调 **LLM 提议映射**（零幻觉：仅输出 from→to 映射，不编造数据）；
   - 推断结果**写回 `field_mapping.yaml` 并按 source_system 缓存**，下次同源自动套用，人工可复核修正。

3. **兜底保留**：任何无法映射的列，原样落入 `custom_fields` JSONB，**绝不丢数据**；并在质量报告里提示"N 个字段未归一化"。

> 这样：无论上游 Excel 列名怎么变，落库后都是统一 `subject/created_at/amount/...`，下游 RAG、分析、看板都能直接消费。

---

## 6. 关键流程（IngestionPipeline 阶段）

```
acquire(file) → parse() → normalize()(FieldMapper/SchemaInference)
  → clean()(复用 CleaningPipeline) → persist_raw() → persist_canonical()
  → chunk()(含表格父/子策略) → embed() → upsert_qdrant() → rebuild_bm25()
  → persist_chunks() → update_job_status()
```
- **幂等**：`content_hash` 命中则跳过（或增量更新）。
- **异步 + 进度**：`IngestionJob` 表记录每个文件状态（pending/parsing/normalized/cleaned/stored/chunked/done/error）+ 进度百分比，前端可轮询。
- **复用清单**：`ParserFactory`、`chunk_documents`、`EmbeddingModel`、`VectorStore`、`_CHUNK_ID_NAMESPACE` 派生逻辑、`CleaningPipeline`、`auth_filter` 全部直接复用，不重写。

---

## 7. 与现有模块的对齐

| 现有模块 | 如何对接 |
|---------|---------|
| `rag_agent/document_parser.py` | 新增 `DoclingParser`，注册进 `ParserFactory`；旧解析器保留为 fallback |
| `rag_agent/chunking.py` | 直接复用；新增 `TableParentChildChunker`（表格摘要为子 chunk，原表为父） |
| `rag_agent/integration.py` | 新管线调用其 `_rag_ingest_sync` 的切片/向量化逻辑（抽成 `embed_and_store()` 函数复用） |
| `data_agent/cleaning.py` | `CleaningPipeline` 改为接受 `CanonicalDocument`，复用去重/PII/GEO/质量 |
| `governance_agent/database` | 复用 SQLAlchemy session；切片 payload 带 `source_system`/权限标签，search 时走现有 `auth_filter` |
| `shared/models/schema.sql` | 追加 raw/canonical/chunks 三表 |

---

## 8. 实施分阶段（建议）

- **阶段 0 — 接入与模型**：`ingest_agent/` 骨架 + `CanonicalDocument`/`IngestionJob` 模型 + `field_mapping.yaml` 机制（1–2 天）
- **阶段 1 — 解析升级**：集成 Docling，新增 `DoclingParser` + fallback；保留现有解析器（2–3 天）
- **阶段 2 — 归一化引擎**：`FieldMapper`（别名/正则/强转）+ `SchemaInference`（规则+LLM 缓存）（3–4 天）
- **阶段 3 — 落库**：Postgres 三表 + `IngestionPipeline` 编排 + 幂等/进度（2–3 天）
- **阶段 4 — 切片与向量化闭环**：表格父/子 chunk + 复用 embed/upsert/BM25 + `persist_chunks`（2 天）
- **阶段 5 — API 与前端**：`/ingest/upload`、`/ingest/jobs` 轮询、前端上传页 + 字段映射可视编辑（3–4 天）
- **阶段 6 — 测试与验证**：混合格式 + 乱列名 Excel 端到端用例，recall@k/MRR 回归（2 天）

---

## 9. 风险与权衡

- **Docling 在 2 核 ARM 上偏重**：PDF 解析较慢 → ① 仅对复杂 PDF 走 Docling，txt/md/csv 走轻量解析器；②  ingestion 设计为后台异步批量，不阻塞查询；③ 后续可换更强机型或加 GPU。
- **LLM 推断映射的零幻觉**：只让 LLM 输出"列名→标准字段"映射，不碰业务数据；结果需人工复核缓存。
- **大 Excel 拍平丢失语义**：改为"逐 sheet 保留表头 + 行级记录 + 表格父/子 chunk"，既入库又可检索。
- **与 Dify 知识库的定位**：Dify 继续作"快速预览/小文件"通道；本模块是 FDE 主知识资产库，二者集合可隔离（不同 Qdrant collection）。

---

## 10. 验证方案

- 构造 20 份混合文件（含 5 份"列名乱起"的 Excel：同一业务域用 3 套不同列名），跑通端到端；
- 断言：落库后 `canonical_documents` 字段统一；乱列名 Excel 的"客户名称/顾客/Customer"全部映射到 `subject`；
- RAG 检索 recall@5 / MRR 不低于当前基线（参考 `rag-deployment-verification-and-perf.md`）；
- `content_hash` 重复上传幂等；PII 脱敏生效；权限过滤生效。
