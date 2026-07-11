# FDE AI Platform — 用户手册 v4

> 版本：v4.0 | 日期：2026-07-11 | 覆盖阶段：P2a → P6a

---

## 1. 系统概览

FDE AI Platform 是企业数字化转型的智能数据底座，提供从**数据接入 → 解析归一 → 向量检索 → RAG 问答**的完整链路。

### 核心能力

| 能力 | 说明 | 阶段 |
|------|------|------|
| 多格式文件入库 | Excel/CSV/PDF/DOCX/PPTX → 自动解析归一化 | P2a/P2b |
| 语义检索问答 | 自然语言查询 → 向量检索 → LLM 合成答案 | P2a |
| 重排 + 改写 | 词汇 F1 融合重排 + 实体归一改写 (MRR 0.30→1.00) | P3 |
| 数据底座 | 幂等去重 + FTS5 全文索引 + 对象存储 + 结果缓存 | P3b |
| 量化嵌入 | ONNX INT8 (24MB, ~287MB 进程) vs PyTorch (~620MB) | P4 |
| 异步入库 | 后台 worker 处理，API 即刻返回 (status API 轮询) | P6a |

### 部署拓扑

```
                    ┌──────────┐
                    │  Nginx   │ :8443 (systemd, not docker)
                    └────┬─────┘
          ┌──────────────┼──────────────┐
     /fde/          /fde-api/          /portal/          /
  MapAI dist        FastAPI:8000      Portal dist      Dify
  (archived)        (fde-backend)                      :80/443
```

---

## 2. 部署指南

### 2.1 环境要求

- **OS**: Ubuntu 22.04+ (ARM64)
- **Python**: 3.11+
- **内存**: ≥2GB (ONNX 模式 ~300MB)
- **依赖服务**: Qdrant (Docker, :6333), MinIO (可选)

### 2.2 初始化

```bash
# 1. Clone
git clone git@github.com:zhukeyi/enterprise_digitalization_system.git
cd fde-ai-platform

# 2. 虚拟环境
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 3. 启动（开发模式）
PYTHONPATH=. python -m uvicorn agents.router_agent.main:app --host 0.0.0.0 --port 8000

# 4. 生产部署（systemd）
sudo cp deploy/systemd/fde-backend.service /etc/systemd/system/
sudo systemctl enable --now fde-backend
```

### 2.3 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `sqlite+aiosqlite:///fde_platform.db` | 数据库连接 |
| `FDE_EMBEDDING_BACKEND` | `pytorch` | `onnx` 切换轻量嵌入 |
| `FDE_ONNX_MODEL_PATH` | `~/.cache/fde/bge_model_int8.onnx` | ONNX 模型路径 |
| `FDE_RAG_EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | 嵌入模型 |
| `FDE_CHUNK_MAX_PARENT` | `1200` | 父块最大字符数 |
| `FDE_CHUNK_CHILD_SIZE` | `220` | 子块目标字符数 |
| `FDE_CHUNK_OVERLAP` | `40` | 滑窗重叠字符数 |
| `MINIO_ENDPOINT` | (未设置) | MinIO S3 端点，未设置用本地存储 |
| `REDIS_URL` | (未设置) | Redis 缓存，未设置用内存 LRU |

### 2.4 ONNX 嵌入（推荐，内存减少 54%）

```bash
# 1. 导出模型
PYTHONPATH=. python agents/rag_agent/scripts/export_onnx.py \
  --model BAAI/bge-small-zh-v1.5 \
  --output ~/.cache/fde/bge_model_int8.onnx

# 2. 切换后端
export FDE_EMBEDDING_BACKEND=onnx
# 或在 systemd drop-in 中设置 Environment=FDE_EMBEDDING_BACKEND=onnx
```

---

## 3. API 参考

### 3.1 文件上传（同步）

```http
POST /ingest/upload
Content-Type: multipart/form-data

file: <binary>
doc_type: my_dataset
```

**支持格式**: `.xlsx` `.xlsm` `.csv` `.pdf` `.docx` `.pptx`

**响应**:
```json
{
  "doc_type": "my_dataset",
  "filename": "data.csv",
  "blocks": 1,
  "canonical": 150,
  "chunks": 150,
  "indexed_vectors": 150,
  "raw_id": "uuid",
  "storage_ref": "local://raw/xx/xx.csv",
  "duplicated": false
}
```

### 3.2 文件上传（异步）

```http
POST /ingest/upload/async
Content-Type: multipart/form-data

file: <binary>
doc_type: my_dataset
```

**响应** (200):
```json
{
  "task_id": "uuid",
  "status": "pending",
  "filename": "data.csv",
  "message": "Task queued. Poll GET /ingest/tasks/{task_id} for status."
}
```

### 3.3 任务状态

```http
GET /ingest/tasks/{task_id}
```

**响应**:
```json
{
  "task_id": "uuid",
  "status": "completed",
  "filename": "data.csv",
  "progress_pct": 100,
  "canonical_count": 150,
  "total_chunks": 150,
  "indexed_chunks": 150,
  "error_message": null
}
```

状态流转: `pending` → `processing` → `completed` | `failed`

### 3.4 语义问答

```http
POST /api/data/ask
Content-Type: application/json

{
  "query": "杭州有哪些科技公司",
  "top_k": 5,
  "doc_type": "my_dataset"
}
```

**响应**:
```json
{
  "query": "杭州有哪些科技公司",
  "answer": "根据已上传的数据，找到 3 条相关记录...",
  "count": 3,
  "sources": [...],
  "cached": false
}
```

---

## 4. 数据流水线

### 4.1 解析归一化流程

```
文件上传 → 格式检测(ext) → 解析器(Parser)
  ├─ Excel/CSV → openpyxl (表格行归一)
  ├─ PDF → pdfplumber (段落提取)
  ├─ DOCX → python-docx (段落提取)
  └─ PPTX → python-pptx (文本框提取)

→ 三层归一化 (field_mapping.yaml)
  ├─ L1: identity (不改名)
  ├─ L2: alias (同义词映射: 城市↔city)
  └─ L3: transform (类型转换: 字符串→数值)

→ 父子Chunking → 嵌入向量 (ONNX/PyTorch) → Qdrant + FTS5
```

### 4.2 查询流水线

```
用户查询 → 查询改写 (实体归一 + 同义词扩展 + 停用词移除)
  → 嵌入向量 (extended query)
  → 多路召回 (Qdrant 向量 ≤20 + FTS5 词法)
  → 词汇 F1 融合重排
  → top_k 结果
  → LLM 合成答案 (带来源引用)
```

### 4.3 幂等去重

相同文件重新上传时，系统通过 SHA256 文件哈希检测重复：
- `duplicated: true` — 返回已有 raw_id，不创建新记录
- `canonical: 0` — 不重复入库
- P3b 起文件原始数据存入对象存储 (`storage_ref`)

---

## 5. 配置优化

### 5.1 切片参数调优

根据模型类型调整分块参数：

| 模型 | MAX_PARENT | CHILD_SIZE | OVERLAP | 建议场景 |
|------|-----------|-----------|---------|----------|
| BGE-small-zh (512) | 800 | 150 | 30 | 短文档 |
| BGE-base-zh (768) | 1200 | 220 | 40 | 通用 (默认) |
| BGE-M3 (1024) | 1600 | 300 | 50 | 长文档 |

环境变量: `FDE_CHUNK_MAX_PARENT`, `FDE_CHUNK_CHILD_SIZE`, `FDE_CHUNK_OVERLAP`

### 5.2 内存优化

| 后端 | 进程内存 | 模型大小 |
|------|---------|---------|
| PyTorch (BGE-M3) | ~620MB | ~400MB |
| ONNX INT8 (BGE-small) | ~287MB | 24MB |
| ONNX INT8 + Worker | ~336MB | 24MB |

推荐生产环境使用 ONNX 后端。

---

## 6. 故障排查

### 后端启动失败

```bash
# 查看日志
sudo journalctl -u fde-backend -n 50 --no-pager

# 常见问题:
# - DATABASE_URL 无效 → 检查 fde-db.conf
# - Qdrant 不可达 → 确认 Docker 容器运行
# - ONNX 模型缺失 → 运行 export_onnx.py 导出
```

### 上传返回 400

- 检查文件扩展名 (仅支持 .xlsx .xlsm .csv .pdf .docx .pptx)
- 文件是否为空
- 文件大小 ≤ 20MB

### 异步任务卡在 pending

```bash
# 1. 确认 worker 已启动
sudo journalctl -u fde-backend | grep IngestWorker

# 2. 检查任务状态
curl -sk https://host:8443/fde-api/ingest/tasks/{task_id}

# 3. 查看错误信息
# 状态为 failed 时，error_message 字段含错误详情
```

### 查询无结果

- 确认 doc_type 参数匹配上传时使用的值
- 确认文件已成功入库 (canonical > 0)
- 尝试同步上传 (`/ingest/upload`) 排除 worker 问题

---

## 7. 性能指标

| 指标 | 数值 |
|------|------|
| 嵌入维度 | 512 (BGE-small ONNX) |
| 向量召回候选 | ≤20 |
| 重排延迟 | <1ms (词法) |
| 查询缓存 TTL | 300s (内存 LRU) |
| Worker 并发 | 3 |
| 嵌入批次 | 32 |
| MRR (组件级) | 1.000 (P3 评测) |

---

## 8. 参考文档

| 文档 | 说明 |
|------|------|
| `docs/master-delivery-plan.md` | V4 主计划（全阶段） |
| `docs/data-infra-runbook.md` | 数据底座运维 (P3b) |
| `docs/p2b-runbook.md` | 完整文件入库运维 (P2b) |
| `docs/p2a-mvs-acceptance-report.md` | MVS 核心验收 (P2a) |
| `docs/p3-rag-optimization-report.md` | RAG 优化报告 (P3) |
| `docs/architecture.md` | 系统架构 |