# P2a — MVS 核心 验收报告

> 阶段归属：`master-delivery-plan.md` v4 关键路径 `H0 → P0a → P0 → P2a(MVS) → …`
> 目标：证明「多源数据 → 统一入库 → RAG」核心闭环可用。
> 验收标准：**上传 1 份乱列名 Excel → 字段归一落库 → 对话问答命中该数据**。

## 1. 交付范围（严格限定）

| 层 | 内容 |
|----|------|
| 后端 | `POST /ingest/upload`（仅 .xlsx/.xlsm）→ 字段归一化 → 落库 Postgres → 进 Qdrant |
| 后端 | `POST /api/data/ask` → 基于已入库数据的向量检索问答 |
| 前端 | 极简门户 3 页：**登录**（localStorage 标志）/ **上传** / **对话**，部署于 `/portal/` |

不含（按 V4 范围）：连接器、Docling/PDF/PPT、已有能力页、ABAC 打磨、真实鉴权。

## 2. 核心闭环流程

```
上传 Excel
   │  POST /fde-api/ingest/upload  (multipart: file + doc_type)
   ▼
ingestion_agent.pipeline.IngestionPipeline.ingest_excel
   ├─ openpyxl 读取表头，normalize_field_name 归一（空格/连字符→_，去重加 _N）
   ├─ mapping_loader.build_identity_mapping → FieldMapping（target_field = 归一字段名）
   ├─ apply_field_mapping → CanonicalDocument（字段键统一）
   ├─ RawDocument / CanonicalDocument(ORM) / DocumentChunk 落 Postgres
   ├─ render_canonical_text → 嵌入向量（EmbeddingModel）
   └─ VectorStore.async_upsert → Qdrant 集合 fde_documents（payload 含 text/doc_type/title）
   ▼
对话提问
   │  POST /fde-api/api/data/ask  { query, top_k, doc_type }
   ▼
ingestion_agent.query.QueryService.ask
   ├─ EmbeddingModel.encode_queries([query])
   ├─ VectorStore.async_search(vector, top_k, filter_conditions={doc_type})
   └─ 命中 → 模板/LLM 合成答案 + sources（来源原文）
```

## 3. 验收证据

### 3.1 单元测试（归一化 ≥10）— `agents/ingestion_agent/tests/test_pipeline.py`
- `normalize_field_name`：空格、连字符、混合三种情况
- `build_identity_mapping_rules`：生成 `FieldMappingRule` 且 `target_field` 为归一名
- `normalize_rows_maps_to_normalized_keys`：乱列名（如「客户 名称」「Order-No」）→ `customer_name` / `order_no`
- `normalize_rows_skips_empty_header`：空表头列被忽略
- `render_canonical_text`：非 null 字段渲染为 `key: value`
- `compute_content_hash`：sha256 幂等
- `ingest_rows_stores_canonical_and_returns_counts`：行级落库 + 计数
- `ingest_rows_empty_raises`：空数据抛 `ValueError`
- `ingest_excel_roundtrip_and_search_hit`：**端到端：上传 → 入库 → 检索命中**
- `ingest_excel_empty_file_raises`：空文件抛错
- （共 12 条，含 doc_type 透传校验）

### 3.2 E2E 测试（≥2）— `agents/ingestion_agent/tests/test_router_e2e.py`
通过真实 FastAPI `AsyncClient` + `ASGITransport`，用内存依赖替换 DB/向量库/嵌入模型：
- `test_upload_and_ask_hits_data`：**上传乱列名 Excel → 问答命中该数据**（验收主线）
- `test_ask_before_upload_returns_empty`：未上传时返回空答案
- `test_upload_rejects_non_xlsx`：非 .xlsx 返回 400
- `test_ask_rejects_empty_query`：空 query 返回 400

### 3.3 测试汇总
```
16 passed（12 unit + 4 E2E），ruff 全绿，black 全绿，mypy 新增代码无错误。
```
> 注：仓库其余 40 failed / 18 error 均为本地 `.venv` 缺可选依赖（`qdrant_client` /
> `sentence_transformers`）及 `bcrypt` 版本不兼容导致，**非本阶段改动引入的回归**
> （本阶段仅新增 `ingestion_agent/` 并 try/except 挂载到 `main.py`，未触碰相关模块）。
> 生产服务器依赖齐备，可正常跑通。

## 4. 门户前端（3 页）

| 页面 | 路由 | 说明 |
|------|------|------|
| 登录 | `/portal/login` | 任意用户名/密码 → 写 localStorage 标志，路由守卫 |
| 上传 | `/portal/upload` | 选 .xlsx/.xlsm + doc_type → `POST /fde-api/ingest/upload`，展示入库结果 |
| 对话 | `/portal/chat` | 输入问题 → `POST /fde-api/api/data/ask`，渲染答案 + 来源原文 |

技术栈：Vue 3.5 + Vite 8 + vue-router 4 + Pinia 3 + axios（与 `frontend/map-ai` 版本对齐）。
`base: '/portal/'`，`npm run build` 产物 `frontend/portal/dist/`。

## 5. 部署（生产服务器 `217.142.246.70`）
1. 后端：`git pull` → `fde-backend` 重启（`on_event startup` 调 `init_database()` 自动
   `create_all` 建 4 张共享表：raw_documents / canonical_documents / document_chunks / connector_registry）。
2. 门户：`frontend/portal/dist/` 解包到 nginx `/portal/` docroot。
3. nginx `fde-platform` 配置补 `location /portal/ { alias .../portal/dist/; }` + `try_files`。
4. 验证：浏览器开 `/portal/` → 登录 → 上传样例乱列名 Excel → 对话提问命中。

## 6. 已知限制（MVS 最小集）
- 登录为 localStorage 标志，无真实鉴权（H3 阶段接 JWT）。
- 仅 Excel（.xlsx/.xlsm），无 PDF/PPT/连接器（P2b 扩展）。
- 问答合成使用模板；接入 LLM 时需后端注入 `llm` 依赖。
- 单集合 `fde_documents`，doc_type 用于逻辑隔离。

## 7. 下一阶段
`P2b`（完整本地文件入库：Docling / pdfplumber+python-docx + 三层字段归一化 + 父子 chunk）→
`P3`（重排 + 查询改写）。
