# V4 主计划复盘报告

> 日期：2026-07-11 | 周期：H0 → P6a (7 阶段, 约 30 人天)

---

## 一、已交付阶段

| 阶段 | 名称 | 关键交付 | 测试数 | 内存 |
|------|------|----------|--------|------|
| H0 | 修复百度地图 + 集成基线 | AK 泄密修复, MapAI 冻存 | — | — |
| P0a | Alembic + 连接器契约 | 迁移框架, CanonicalDocument, 容量评估 | — | — |
| P0 | 核心补丁 (F1-13) | 评测集(50查询), 凭证规范, 测试规约 | — | — |
| P2a | MVS 核心 | Excel 归一化, 入库 Qdrant, RAG 查询, 3 页门户 | 16 | ~620MB |
| P2b | 完整文件入库 | pdfplumber+python-docx+父子chunk+三层归一 | 41 | ~620MB |
| P3 | 重排 + 查询改写 | LexicalReranker + QueryRewriter, MRR 0.30→1.00 | 56 | ~620MB |
| P3b | 数据底座 | MinIO 封装 + FTS5 + 幂等 + Redis 缓存 | 60 | ~620MB |
| P4 | 量化嵌入 | ONNX INT8 + Rust tokenizer + chunk 优化 | 82 | **~287MB** |
| P6a | 异步 Worker | Task Queue + 状态 API + 后台 worker | **91** | ~336MB |

**测试增长**: 16 → 41 → 56 → 60 → 82 → 91 (+469%)
**内存优化**: 620MB → 287MB (-54%)

---

## 二、关键决策回顾

### 2.1 Docling → pdfplumber (P2b)

**决策**: 放弃 Docling (~1.5GB PyTorch)，选用 pdfplumber + python-docx + openpyxl。

**效果**: 无新增 GPU 依赖，ARM CPU 可用，内存可控。

**代价**: 复杂表格解析需手动归一化，PDF 图片内容无法提取。

### 2.2 Postgres GIN → SQLite FTS5 (P3b)

**决策**: 生产用 SQLite（ARM 无 Postgres），以 FTS5 代替 GIN(JSONB)。

**效果**: 零配置部署，FTS5 ASCII MATCH + LIKE 兜底 CJK 可行。

**代价**: 中文全文检索需 LIKE 回退，精度低于 Postgres GIN + jieba。

### 2.3 PyTorch → ONNX INT8 (P4)

**决策**: BGE-small-zh-v1.5 → ONNX INT8 量化 (92MB→24MB) + Rust tokenizer。

**效果**: 进程内存 ↓54% (620MB→287MB)，无量化质量降级。

**关键坑**: transformers tokenizer 导入 torch → 改用 `tokenizers` 库 (Rust, 无 torch)。

### 2.4 Celery/Redis → asyncio.Queue (P6a)

**决策**: 单机 asyncio worker，不引入 Celery/Redis 消息队列。

**效果**: 零额外依赖，任务状态持久化 DB，并发 3。

**代价**: 无分布式，重启丢队列中任务（DB 持久化的任务可恢复）。

---

## 三、测试质量

```
阶段     测试数    覆盖模块
P2a      16      归一化+管道+路由E2E
P2b      41      +解析器(5)+多格式E2E
P3       56      +重排(8)+改写(7)
P3b      60      +storage(7)+cache(6)+fts(3)+幂等(3)
P4       82      +token(5)+切片(6)+ONNX配置(11)
P6a      91      +queue(2)+lifecycle(4)+E2E(3)
```

RUFF clean, no type errors (mypy limited scope).

---

## 四、已知限制 & 技术债务

| 限制 | 影响 | 建议 |
|------|------|------|
| SQLite 非 Postgres | 无并发写入、无真正 GIN | P6b 迁移 Postgres |
| CJK FTS5 LIKE 回退 | 中文检索精度低 | 集成 jieba 分词 |
| 词汇重排缺语义 | "成都腾讯 vs 深圳腾讯" 难区分 | P6b GPU Reranker |
| 查询改写仅规则式 | 无 HyDE/Multi-Query | P6b GPU |
| asyncio.Queue 无持久化 | 重启丢队列 | 升级 Redis task broker |
| 无分布式 Qdrant | 单节点容量上限 | P6b 集群 |
| MinIO 未配置 | 默认本地文件存储 | 补充 MINIO_ENDPOINT |

---

## 五、运维指标

| 指标 | 数值 |
|------|------|
| 生产服务器 | Oracle ARM 2C/11G/96G |
| 当前可用内存 | ~8.5Gi (ONNX 模式) |
| fde-backend 进程 | ~336MB (ONNX + Worker) |
| Qdrant 版本 | 1.13.2 (Docker) |
| 测试框架 | pytest 9.x + pytest-asyncio |
| Linter | ruff (E,W,F,I,N,UP,B,SIM,C4,RUF) |
| CI/CD | GitHub Actions |
| 部署方式 | systemd + rsync |

---

## 六、经验总结

### 做得好的

1. **阶段门禁**: 每阶段 ruff + test + deploy + acceptance 四步，零回滚
2. **ONNX Rust tokenizer**: 关键优化，找到 transformers→torch 瓶颈并解决
3. **幂等去重**: SHA256 文件级去重 + content_hash 行级去重，用户体验好
4. **向后兼容**: 同步/异步上传共存，原 API 不破坏

### 可改进的

1. **文档滞后**: 边开发边写文档，P7 才集中整合 → 建议每阶段即产出 runbook
2. **Chunking 参数**: 默认值适合 BGE-small，切换模型需手动调参
3. **FTS5 中文**: 应引入 jieba 分词替代 LIKE 回退
4. **系统架构图**: 缺失即时更新的架构图，后续应自动化

### 下一步建议

```
优先级:
P0: 补充 MINIO_ENDPOINT 生产配置
P1: FTS5 集成 jieba 中文分词
P2: Redis 替换内存 LRU 缓存
P3: 升级 asyncio.Queue → Redis task broker (持久化)
P4: GPU 语义重排 + HyDE 查询改写
```