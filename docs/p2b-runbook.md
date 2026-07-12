# P2b 运行手册 — 完整本地文件入库

> 关联主计划：V4 master delivery plan（P2b 行：「完整本地文件入库 — Docling（spike 不通过则回退 pdfplumber+python-docx）+ 三层字段归一化扩展 + 表格父子 chunk → DB+Qdrant」）
> 代码提交：`3cbc9ea`（已 push origin/main）
> 部署验证：2026-07-11 生产环境（https://217.142.246.70:8443）

## 1. 交付范围

| 模块 | 文件 | 职责 |
|------|------|------|
| 多格式解析 | `agents/ingestion_agent/parsers.py` | Excel/CSV/PDF/DOCX/PPTX → `ParsedDocument(Block[Text/Heading/Table])` |
| 三层归一化 | `agents/ingestion_agent/normalization.py` | L1 表头别名 → L2 类型强转 → L3 实体去重 |
| 父子 chunk | `agents/ingestion_agent/chunking.py` | 表格：父=整表文本，子=每行；文本：父=段落组，子=滑窗 |
| 入库管线 | `agents/ingestion_agent/pipeline.py` | `ingest_file()`：解析→RawDocument→规范化→CanonicalDocument→父子chunk→Qdrant |
| 路由 | `agents/ingestion_agent/router.py` | `POST /ingest/upload` 多扩展名 + 20MB/类型守卫；`POST /api/data/ask` |
| 检索 | `agents/ingestion_agent/query.py` | 检索优先用 `parent_text` 携带父上下文 |

**设计决策（与 V4 计划一致）**：Docling spike 在 ARM（~1.5G torch）下不通过，已按回退路径采用 `pdfplumber + python-docx + openpyxl + python-pptx`。CSV 走 `ingest_file` 的 TABLE 分支；Excel 仍走 P2a 的 `ingest_excel`（零配置 identity 路径，保持向后兼容）。

## 2. 支持格式与约束

| 扩展名 | 解析器 | 归一化 | chunk 方式 |
|--------|--------|--------|-----------|
| `.xlsx` `.xlsm` | openpyxl（多 sheet） | 是（别名+L2+L3） | ingest_excel：父=整行，子=整行 |
| `.csv` | csv（无 header 推断，首行即表头） | 是 | 表格父/子 chunk |
| `.pdf` | pdfplumber（文本段 + 表格） | 文本块：normalize_text_block；表格块：normalize_table_rows | 文本滑窗 / 表格父-子 |
| `.docx` | python-docx（段落+表格） | 同上 | 文本滑窗 / 表格父-子 |
| `.pptx` | python-pptx（每页文本+表格） | 同上 | 文本滑窗 / 表格父-子 |

- 上传上限 `MAX_UPLOAD_BYTES = 20 * 1024 * 1024`（20MB），超限返回 413。
- 不支持的扩展名返回 400（提示允许列表）。
- 空文件返回 400。

## 3. 三层归一化细节

1. **L1 表头别名**（`DEFAULT_ALIASES`）：中文/杂乱表头 → 规范英文字段，如 `客户名称→customer_name`、`订单号→order_no`、`所在城市→city`、`合同金额→contract_amount`。大小写不敏感，未命中则保留原表头。
2. **L2 类型强转**（`_coerce_value`）：剥离 `¥`/`,`/空格 → `float`；日期 → ISO；编码类字段 `upper`。
3. **L3 实体去重**：按 `content_hash` 对同文件内重复行去重；`DEFAULT_ENTITY_MAP`（如 `上海市→上海`）统一实体表述。

> 扩展映射：修改 `normalization.py` 中的 `DEFAULT_ALIASES` / `DEFAULT_ENTITY_MAP`，或在调用 `normalize_table_rows` 时传入自定义 `aliases` / `entity_map`。

## 4. 端点

所有路径经 nginx `/fde-api/` 前缀代理到后端 `127.0.0.1:8000`（去前缀）。

### 4.1 上传
```
POST /fde-api/ingest/upload
Content-Type: multipart/form-data
file: <二进制文件>
doc_type: <可选，默认 "file_upload">
```
响应示例（CSV）：
```json
{"doc_type":"csv_sample","source_ref":"local://sample.csv","filename":"sample.csv",
 "blocks":1,"canonical":3,"chunks":3,"indexed_vectors":3,"raw_id":"58d526e0-..."}
```

### 4.2 问答
```
POST /fde-api/api/data/ask
Content-Type: application/json
{"query":"杭州的客户","top_k":5,"doc_type":null}
```
返回 `answer` + `sources[]`，每条 source 含 `text`（子 chunk）、`parent_text`（父 chunk 上下文）、`canonical`（规范化字段）、`block_kind`、`title`。

## 5. 部署步骤（新服务器 / 重新部署）

```bash
# 1. 拉取代码
cd /home/ubuntu/fde-ai-platform && git pull --ff-only origin main

# 2. 安装 P2b 解析依赖（venv 路径固定为 /home/ubuntu/fde-ai-platform/venv）
venv/bin/pip install pdfplumber python-docx python-pptx openpyxl

# 3. 重启后端（systemd drop-in 已注入 DATABASE_URL=sqlite + BAIDU_SERVER_AK）
sudo systemctl restart fde-backend
sudo systemctl is-active fde-backend   # 应返回 active
```

> ⚠️ 依赖清单：`pdfplumber`（P2b 新增，最易遗漏）、`python-docx`、`python-pptx`、`openpyxl`（P2a 已装）。
> 嵌入模型为服务端 env `FDE_RAG_EMBEDDING_MODEL`（实际 `BAAI/bge-small-zh-v1.5`），首次请求懒加载约 20–40s。

## 6. 验收结果（生产环境，2026-07-11）

端到端上传 → 入库 → 检索问答，四种格式全部通过：

| 格式 | doc_type | blocks/canonical/chunks/vectors | 问答验证 |
|------|----------|----------------------------------|----------|
| Excel(.xlsx) | xlsx_sample | 2/2/2/2 | "杭州的客户" → **杭州科技** ✅ |
| CSV | csv_sample | 1/3/3/3 | "杭州的客户" → **阿里巴巴(杭州)**，parent_text 携带整表 ✅ |
| DOCX | docx_sample | 4/4/4/4 | "阿里巴巴总部在哪里" → **总部位于杭州** ✅ |
| PDF | pdf_sample | 1/1/1/1 | "杭州是哪个省的省会" → **浙江省会** ✅ |

单元测试：ingestion 套件 **39 passed**（P2a 16 + P2b 23：解析 5 + 归一化 7 + chunk 3 + 入库 3 + 路由 E2E 4）。
代码质量：P2b 新增/改动文件 ruff clean / black clean / mypy clean（10 个遗留 mypy 错误在 governance/rag 旧模块，与 P2b 无关）。

## 7. 已知限制 / 后续（H2b 等）

- **PDF 表格**：`pdfplumber` 能抽表格，但复杂跨页/合并单元格表格归一等价为文本块处理，不保证单元格级精确；生产级表格抽取待 H2b 增强。
- **magic-bytes 校验**：当前仅按扩展名 + 大小守卫，H2b 会补 magic-bytes 校验防伪装上传。
- **数据库**：生产仍用 SQLite 兜底（`fde-db.conf` drop-in）；正式环境应装 Postgres（默认 `DATABASE_URL=postgresql+asyncpg`）。
- **重复入库**：`content_hash` 仅去重同文件内行；跨文件/跨次上传同内容会重复，待 H2b 全局去重。
- **PPTX/DOCX 表格**：已支持，但未在本文档单独跑验收样例（逻辑与 PDF/CSV 表格分支一致）。

## 8. 清理验收样例数据

验收时写入的样例数据 doc_type 为 `*_sample`（csv_sample / docx_sample / pdf_sample / xlsx_sample），可在 SQLite `fde_platform.db` 的 `canonical_documents`/`document_chunks`/`raw_documents` 及 Qdrant 集合 `fde_documents` 中按 `doc_type`/`raw_id` 过滤删除。如需彻底重置：删除 `fde_platform.db` 并重建 Qdrant 集合 `fde_documents`。
