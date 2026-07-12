# FDE Observability Platform — 详细开发计划

> **文档定位**：将 `docs/v5-observability-platform-design.md` 设计方案转化为可执行的软件开发计划。
>
> **软件工程原则**：WBS 任务分解到 0.5–1 天粒度 | 每个任务有明确输入/输出/验收标准 | 依赖关系显式标注 | 测试左移 | 质量门禁 | 风险前置。
>
> **总工期**：19 个工作日（约 4 周），Phase 0–4 五个阶段。

---

## 一、任务分解结构（WBS）

### Phase 0: 管道接通（Day 1–2）— 2 个工作日

> **目标**：零新建代码，接通已有但未调用的可观测性组件。
> **依赖**：无
> **风险**：低（仅改 main.py + 配置）

#### P0-1: main.py 接通 metrics + logging + OTel（0.5 天）

| 项 | 内容 |
|---|---|
| **文件** | `agents/router_agent/main.py` |
| **改动** | ① startup_event 前调用 `setup_structured_logging()`（L184 附近）<br>② startup_event 后调用 `setup_metrics(app)`（L217 已有函数）<br>③ 在 `chat_completions` 端点（L273）response 返回后调用 `get_default_backend().emit_llm_call()`<br>④ 新增 `import` 语句：`from shared.sdk.metrics import setup_metrics`、`from shared.sdk.logging import setup_structured_logging`、`from shared.sdk.otel_backend import get_default_backend` |
| **输入** | 现有 `shared/sdk/metrics.py`（L217 `setup_metrics`）、`shared/sdk/logging.py`（L51 `setup_structured_logging`）、`shared/sdk/otel_backend.py`（L136 `emit_llm_call`） |
| **输出** | `/metrics` 端点返回 Prometheus 格式指标；日志输出 JSON 格式；LLM 调用产生 OTel span |
| **验收** | ① `curl /metrics` 返回 `fde_http_requests_total` 等指标<br>② 日志输出含 `"timestamp":"..."` JSON 格式<br>③ `FDE_OTEL_ENABLED=1` 时 stdout 出现 `llm_call model=... tokens=...` |
| **测试** | `tests/test_phase0_metrics.py`：GET /metrics 200 + 包含 `fde_` 前缀；GET /health 200 且日志为 JSON |

#### P0-2: 注册 dify_bridge + im_agent router（0.25 天）

| 项 | 内容 |
|---|---|
| **文件** | `agents/router_agent/main.py`（L164 后新增） |
| **改动** | 新增两个 try/except include_router 块：<br>`from agents.dify_bridge.router import create_dify_router; app.include_router(create_dify_router())`<br>`from agents.im_agent.webhook_routes import router as im_router; app.include_router(im_router)` |
| **输入** | `agents/dify_bridge/router.py`（L24 `create_dify_router`，prefix `/dify`）、`agents/im_agent/webhook_routes.py`（L22 `router`，prefix `/im/webhook`） |
| **输出** | `/dify/tools/*` 和 `/im/webhook/*` 端点可达 |
| **验收** | `curl /dify/health` 200；`curl /im/webhook/health` 200（或 404 但路由注册无 ImportError） |
| **测试** | `tests/test_phase0_routers.py`：两个 router 路径返回非 404 |

#### P0-3: 修 embedding env 拼写 bug（0.25 天）

| 项 | 内容 |
|---|---|
| **文件** | `agents/rag_agent/embeddings.py` L332 |
| **改动** | `FDE_RAG_EMBEDING_MODEL` → `FDE_RAG_EMBEDDING_MODEL`（加一个 D） |
| **回归** | 搜索全仓库 `FDE_RAG_EMBEDING_MODEL`（无 D）确认无其他引用 |
| **验收** | `FDE_EMBEDDING_BACKEND=onnx FDE_RAG_EMBEDDING_MODEL=xxx` 能正确读取 |
| **测试** | `tests/test_phase0_embedding_env.py`：设 env 后 `get_embedding_model()` 返回正确模型名 |

#### P0-4: 取消 Grafana/Prometheus/Loki compose 注释（0.5 天）

| 项 | 内容 |
|---|---|
| **文件** | `deploy/docker-compose.prod.yml` L257–306 |
| **改动** | 取消 `prometheus`、`grafana` 两个 service 注释；Loki 取消注释（如有） |
| **前置** | 服务器上 `docker compose` 可用；端口 9090(Prometheus)/3000(Grafana)/3100(Loki) 未占用 |
| **验收** | `docker compose up -d prometheus grafana` 成功；`curl localhost:9090/-/healthy` 200；Grafana 3000 可登录 |
| **注意** | 服务器是 ARM 架构，镜像需支持 arm64（prom/prometheus、grafana/grafana 均支持） |

#### P0-5: systemd 环境变量更新 + 重启验证（0.5 天）

| 项 | 内容 |
|---|---|
| **文件** | 服务器 `/etc/systemd/system/fde-backend.service.d/*.conf` |
| **改动** | 新增 env：`FDE_OTEL_ENABLED=1`、`FDE_ENV=production` |
| **验收** | `sudo systemctl restart fde-backend`；`journalctl -u fde-backend -f` 看到 JSON 日志；`curl localhost:8000/metrics` 200 |
| **部署** | scp main.py → `git pull` → restart → 验证 |

**Phase 0 质量门禁**：
```bash
ruff check agents/router_agent/main.py shared/sdk/metrics.py shared/sdk/logging.py
python -m pytest tests/test_phase0_*.py -v
curl -s http://localhost:8000/metrics | grep "fde_"
```

---

### Phase 1: 健康检查 + 监测前端骨架（Day 3–6）— 4 个工作日

> **目标**：三级探活 + observability_agent 后端骨架 + 前端门户 Overview + Service Health
> **依赖**：Phase 0 完成
> **风险**：中（新建模块，需保证不破坏现有 920+ 测试）

#### P1-1: 新建 observability_agent 后端骨架（0.5 天）

| 项 | 内容 |
|---|---|
| **目录** | `agents/observability_agent/` |
| **文件** | `__init__.py`、`router.py`、`models.py`、`collector.py`、`README.md` |
| **router.py** | `APIRouter(prefix="/api/observability", tags=["Observability"])` |
| **models.py** | Pydantic 模型：`ComponentStatus`、`OverviewStats`、`HealthCheckResult` |
| **注册** | `main.py` 新增 `app.include_router(observability_router)` |
| **验收** | `curl /api/observability/health/ping` 200 |

#### P1-2: 三级探活端点（0.5 天）

| 项 | 内容 |
|---|---|
| **文件** | `agents/observability_agent/router.py` |
| **端点** | `GET /healthz` — 进程存活，200<br>`GET /readyz` — 并行探活 Qdrant(ping)+Postgres(SELECT 1)+Embedding(加载检查)，全通 200 否则 503 + 详情<br>`GET /livez` — 最近 60 秒错误率 < 50% 则 200 |
| **输入** | Qdrant client（`agents/ingestion_agent/store.py` 的 `get_vector_store()`）、DB engine（`governance_agent/database/session.py`）、embedding model info |
| **输出** | `HealthCheckResult{ status: "healthy"|"degraded"|"unhealthy", components: [{name, status, latency_ms, detail}], checked_at }` |
| **验收** | Qdrant 关闭时 `/readyz` 返回 503 + `{"components":[{"name":"qdrant","status":"unhealthy"}]}` |
| **测试** | `tests/test_health.py`：mock 各组件，测 healthy/degraded/unhealthy 三种场景 |

#### P1-3: 组件健康状态 API（0.5 天）

| 项 | 内容 |
|---|---|
| **端点** | `GET /api/observability/health/components` — 组件级详细状态<br>`GET /api/observability/health/service-map` — 14 模块依赖关系 |
| **组件** | qdrant、postgres/sqlite、dify、embedding_model、nginx、redis(如无则跳过) |
| **每组件** | name、type、status、latency_ms、version、details（如 Qdrant 向量数、DB 表行数） |
| **验收** | 返回 JSON 含 5+ 组件状态 |

#### P1-4: Overview 聚合 API（0.5 天）

| 项 | 内容 |
|---|---|
| **端点** | `GET /api/observability/overview` |
| **返回** | `health_score`(0-100)、4 KPI(`qps`/`error_rate`/`p95_latency_ms`/`tokens_hour`)、24h 事件线（部署/告警）、14 模块状态卡片 |
| **数据源** | Prometheus metrics（从 `_metrics_registry` 读取）、`/readyz` 结果、日志事件 |
| **验收** | health_score 基于组件状态 + 错误率计算；KPI 非零 |

#### P1-5: APIMetricsMiddleware（0.5 天）

| 项 | 内容 |
|---|---|
| **文件** | `agents/observability_agent/middleware.py` |
| **功能** | 拦截所有请求，记录 path/method/status/latency/user_id 到内存环形缓冲（最近 10000 条） |
| **注意** | 不与 `shared/sdk/metrics.py` 的 `_metrics_middleware` 冲突——前者做 Prometheus 指标，后者做 API 管理用明细 |
| **注册** | `main.py` 中 `app.add_middleware(APIMetricsMiddleware)` |
| **验收** | 调用任意端点后 `GET /api/observability/api/stats` 能查到最近调用 |

#### P1-6: 前端 observability-portal 骨架（0.5 天）

| 项 | 内容 |
|---|---|
| **目录** | `frontend/observability-portal/` |
| **技术栈** | Vue3 + Vite + ECharts 5.6 + Vue Router，base `/obs/` |
| **主题** | 暗色运维主题（参考 intelligence-portal） |
| **文件** | `package.json`、`vite.config.ts`、`src/main.ts`、`src/App.vue`、`src/router/index.ts`、`src/api/client.ts` |
| **路由** | `/obs/` Overview、`/obs/health` ServiceHealth（其余 5 个 view 路由占位） |
| **验收** | `npm run build` 成功；`npm run dev` localhost 可访问 |

#### P1-7: OverviewView + ServiceHealthView 前端（1 天）

| 项 | 内容 |
|---|---|
| **OverviewView.vue** | 健康分大圆环（ECharts gauge）+ 4 KPI 卡 + 24h 事件时间线 + 14 模块状态网格 |
| **ServiceHealthView.vue** | 组件健康矩阵（表格 + 状态色块）+ 服务拓扑图（简易 SVG 节点连线）+ 历史可用率折线 |
| **API client** | `getOverview()`、`getComponents()`、`getServiceMap()` |
| **轮询** | Overview 30s 自动刷新；ServiceHealth 60s |
| **验收** | 页面展示真实数据（非 mock）；组件宕机时色变红 |

**Phase 1 质量门禁**：
```bash
ruff check agents/observability_agent/
python -m pytest tests/test_health.py tests/test_overview.py -v
cd frontend/observability-portal && npm run build
```

---

### Phase 2: Token 路由 + API 管理（Day 7–11）— 5 个工作日

> **目标**：token 真实计数 + 成本归因 + API 端点管理 + Key 生命周期
> **依赖**：Phase 1 完成
> **风险**：中高（改动 model adapter 可能影响路由链）

#### P2-1: Token 用量数据模型 + 持久化（0.5 天）

| 项 | 内容 |
|---|---|
| **文件** | `agents/observability_agent/models.py`（扩展）、`agents/observability_agent/database.py`（新建） |
| **表** | `token_usage_log`：id, timestamp, trace_id, model, prompt_tokens, completion_tokens, total_tokens, cost_usd, agent_module, user_id, latency_ms |
| **ORM** | SQLAlchemy 2.0 async，复用 `governance_agent/database/session.py` 的 engine |
| **迁移** | `alembic revision --autogenerate -m "add token_usage_log"` |
| **验收** | 表创建成功；插入一条记录可查询 |

#### P2-2: Model adapter 补 token 计数（1 天）

| 项 | 内容 |
|---|---|
| **文件** | `agents/router_agent/adapters/mock.py`（或 `base.py`） |
| **改动** | Mock adapter 的 `complete()` 返回合理的 `total_tokens`（按 messages 字符数估算：`sum(len(m.content)//4 for m in messages)`） |
| **Stub 适配器** | DeepSeek/Qwen/GLM 的 Stub 定义 `complete()` 接口签名，返回 `Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0)` + `NotImplementedError` 的优雅降级 |
| **emit_llm_call** | 在 `main.py` L308（response 返回前）调用 `get_default_backend().emit_llm_call(trace_id, response.model, usage.prompt_tokens, usage.completion_tokens, elapsed)` |
| **同时写入** | `token_usage_log` 表插入记录 |
| **验收** | 发送 `/v1/chat/completions` 后 DB 有记录；`/metrics` 出现 `fde_token_usage_total` |
| **测试** | `tests/test_token_tracking.py`：发送请求 → 查 DB → 验证字段 |

#### P2-3: Token 用量/成本聚合 API（0.5 天）

| 项 | 内容 |
|---|---|
| **端点** | `GET /api/observability/tokens/usage?group_by=model|user|agent|hour&start=...&end=...`<br>`GET /api/observability/tokens/cost?period=daily|weekly|monthly`<br>`GET /api/observability/tokens/routing` — 路由规则命中分布<br>`GET /api/observability/tokens/failover` — failover 事件 |
| **聚合** | SQL GROUP BY + SUM，numpy 兜底（无 pandas） |
| **验收** | 按 model 聚合返回各模型 token 数 + 成本 |

#### P2-4: Cost Canary — agent 预算 + 超限降级（0.5 天）

| 项 | 内容 |
|---|---|
| **文件** | `agents/observability_agent/budget.py`（新建） |
| **功能** | 按 agent_module 设日预算（USD）；每小时检查；超限 → 路由策略降级（如 GPT-4o → GPT-4o-mini） |
| **端点** | `POST /api/observability/tokens/budget` — 设置预算<br>`GET /api/observability/tokens/budget` — 查询预算 + 当前消耗 |
| **告警** | 超限 80% 时 logger.warning；超限 100% 时触发降级 + 事件记录 |
| **验收** | 设预算 $0.01 → 发送若干请求 → 确认降级事件触发 |

#### P2-5: API 端点自动扫描 + 外部 API 注册（0.5 天）

| 项 | 内容 |
|---|---|
| **端点扫描** | 遍历 `app.routes`，提取 path/method/summary/所属模块（从 router prefix 推断） |
| **端点** | `GET /api/observability/api/endpoints` — 全部端点目录<br>`GET /api/observability/api/stats/{path}` — 单端点 QPS/P95/错误率 |
| **外部 API** | `GET /api/observability/api/external` — Dify/BaiduMap/IM 适配器注册表（手动维护 YAML 或代码内枚举） |
| **验收** | 返回 65+ 端点列表 |

#### P2-6: API Key CRUD + 应用层限流（1 天）

| 项 | 内容 |
|---|---|
| **表** | `api_keys`：id, key_hash, name, user_id, quota_tpm, quota_rpm, enabled, created_at, last_used_at |
| **端点** | `POST/GET/PUT/DELETE /api/observability/api/keys` |
| **限流中间件** | Token bucket per-key，在 `APIMetricsMiddleware` 中检查；超限返回 429 |
| **注意** | Key 生成用 `secrets.token_urlsafe(32)`；存储用 bcrypt hash（复用 `shared/utils/hashing.py`） |
| **验收** | 创建 Key → 用 Key 调用 API → 超限 429 |

#### P2-7: TokenRouterView + ApiManagementView 前端（1 天）

| 项 | 内容 |
|---|---|
| **TokenRouterView.vue** | 路由策略面板（YAML 配置只读展示）+ 用量堆叠面积图（按模型）+ 成本柱状图（日维度）+ Failover 事件流 + 预算设置卡 |
| **ApiManagementView.vue** | 端点目录表（可搜索/过滤）+ 调用趋势图 + 外部 API 卡片 + Key 管理表（创建/停用/配额） |
| **验收** | 数据从真实 API 加载；图表正确渲染 |

**Phase 2 质量门禁**：
```bash
ruff check agents/observability_agent/ agents/router_agent/adapters/
python -m pytest tests/test_token_tracking.py tests/test_api_keys.py tests/test_budget.py -v
cd frontend/observability-portal && npm run build
```

---

### Phase 3: RAG Inspector + Trace Viewer（Day 12–16）— 5 个工作日

> **目标**：RAG 切片检视/维护/检索回放 + 全链路 trace 存储/可视化
> **依赖**：Phase 1 完成（Phase 2 可并行）
> **风险**：中（需修 Postgres metadata 落库，有数据迁移风险）

#### P3-1: Postgres metadata_json / parent_chunk_id 落库修复（0.5 天）

| 项 | 内容 |
|---|---|
| **文件** | `agents/ingestion_agent/pipeline.py` L432–440, L487–495 |
| **改动** | 写入 `document_chunks` 时补填 `parent_chunk_id`（从 Qdrant payload 的 `block_kind` 推导）和 `metadata_json`（含 `chunking_strategy`/`chunk_size`/`overlap`/`embedding_model`/`embedding_dim`） |
| **迁移** | Alembic 迁移：对已有数据回填 `metadata_json` 为 `{}`（不回填历史，只保证新数据） |
| **验收** | 上传新文档 → 查 Postgres `document_chunks` → `metadata_json` 非空 |
| **测试** | `tests/test_chunk_metadata.py`：ingest 后查 DB 验证字段 |

#### P3-2: RAG 只读查询 API（0.5 天）

| 项 | 内容 |
|---|---|
| **端点** | `GET /api/observability/rag/docs?page=1&page_size=20&doc_type=...&source=...`<br>`GET /api/observability/rag/docs/{doc_id}/chunks`<br>`GET /api/observability/rag/chunks/{chunk_id}` |
| **数据源** | Postgres `document_chunks` + `canonical_documents` + Qdrant payload |
| **返回** | 文档列表（含 chunk_count/embedding_model/status）；chunk 详情（text/parent_text/metadata/向量预览前 10 维） |
| **验收** | 返回真实数据 |

#### P3-3: RAG 维护 API — 删除 + 重建（0.5 天）

| 项 | 内容 |
|---|---|
| **端点** | `DELETE /api/observability/rag/docs/{doc_id}` — 级联删除 Qdrant points + Postgres rows + FTS 索引<br>`POST /api/observability/rag/docs/{doc_id}/reindex` — 重新切片+嵌入+入库 |
| **防呆** | DELETE 需请求体 `{"confirm": "DELETE"}` 二次确认；返回影响行数 |
| **审计** | 操作写入 `audit_log`（Phase 4 表，此处先写日志） |
| **验收** | 删除后 Qdrant 和 Postgres 中该 doc 的数据全清 |

#### P3-4: RAG 检索回放 API（0.5 天）

| 项 | 内容 |
|---|---|
| **端点** | `POST /api/observability/rag/debug/retrieve` — body: `{"query": "...", "top_k": 10}` |
| **流程** | 复用 `rag_agent` 的 HybridSearch + QueryRewrite + Reranker |
| **返回** | `{"rewritten_query": "...", "chunks": [{id, text, score, rerank_score, source, doc_id}], "latency_ms": ...}` |
| **验收** | 输入已知 query → 返回 chunks 且有分数 |

#### P3-5: Trace 存储 + 查询 API（1 天）

| 项 | 内容 |
|---|---|
| **表** | `trace_spans`：id, trace_id, span_id, parent_span_id, name, start_time, end_time, duration_ms, status, attributes_json, span_type(http/llm/rag/tool) |
| **写入** | 改造 `shared/sdk/decorators.py` 的 `@traced`：除 `_log_trace` 外，同时调用 `get_default_backend().emit_span()` + 写入 `trace_spans` 表 |
| **LangGraph** | 在 orchestrator 的每个 Worker 调用前后加 `@traced("worker_name")` |
| **端点** | `GET /api/observability/traces?page=1&service=...&status=error&min_duration_ms=...`<br>`GET /api/observability/traces/{trace_id}` — 返回 span 树<br>`GET /api/observability/traces/stats` — P50/P95/P99 + 错误率 + 热路径 |
| **验收** | 发送请求 → 查 trace → 返回完整 span 树（http → routing → llm） |

#### P3-6: RagInspectorView + TraceViewerView 前端（1.5 天）

| 项 | 内容 |
|---|---|
| **RagInspectorView.vue** | 文档表（左侧）+ chunk 详情抽屉（右侧：原文/parent_text/metadata/向量预览）+ 检索回放面板（底部：query 输入 + 结果列表 + 分数高亮）+ 删除/重建按钮（防呆确认弹窗） |
| **TraceViewerView.vue** | trace 列表表（可过滤）+ span 树瀑布图（ECharts 自定义图或 Gantt 式条形图）+ LLM span 详情（prompt/completion/token） |
| **验收** | 检索回放展示真实 chunks + 分数；trace 瀑布图展示 span 层级 |

#### P3-7: 统一两套 chunker（0.5 天）

| 项 | 内容 |
|---|---|
| **文件** | `agents/rag_agent/chunking.py` + `agents/ingestion_agent/chunking.py` |
| **改动** | ingestion 的 `build_text_chunks`/`build_table_chunks` 改为调用 rag_agent 的 `ChunkerFactory.create("parent_child")`；保留 rag_agent 的 FixedSize/Semantic/Recursive 作为可选策略 |
| **注意** | 不改变现有切片行为（parent-child 仍为默认），只是统一入口 |
| **验收** | 现有 ingestion 测试全过 |

**Phase 3 质量门禁**：
```bash
ruff check agents/observability_agent/ agents/ingestion_agent/pipeline.py
python -m pytest tests/test_chunk_metadata.py tests/test_rag_inspector.py tests/test_trace_spans.py -v
python -m pytest agents/ingestion_agent/tests/ -v  # 回归
cd frontend/observability-portal && npm run build
```

---

### Phase 4: 审计 + 告警闭环（Day 17–19）— 3 个工作日

> **目标**：审计日志 + Prometheus 告警 + Drift 检测 + 全平台集成验证
> **依赖**：Phase 1–3 完成
> **风险**：低（主要是配置 + 集成）

#### P4-1: audit_log 表 + 写入（0.5 天）

| 项 | 内容 |
|---|---|
| **表** | `audit_log`：id, timestamp, user_id, action, target_type, target_id, detail_json, ip_address, trace_id |
| **写入点** | RAG 删除/重建（P3-3）、API Key CRUD（P2-6）、预算变更（P2-4）、模型切换 |
| **中间件** | 复用 `governance_agent/middleware` 审计能力，或新增 `AuditMiddleware` 拦截 DELETE/POST 写操作 |
| **验收** | 执行删除文档 → 查 audit_log 有记录 |

#### P4-2: 审计查询/导出 API（0.5 天）

| 项 | 内容 |
|---|---|
| **端点** | `GET /api/observability/audit/logs?page=1&action=...&start=...&end=...`<br>`GET /api/observability/audit/export?format=json|csv` |
| **验收** | 导出 JSON/CSV 文件下载成功 |

#### P4-3: Prometheus 告警规则启用 + 通知（0.5 天）

| 项 | 内容 |
|---|---|
| **文件** | `deploy/prometheus/alerts.yml`（已有 6 条规则） |
| **通知** | Alertmanager webhook → IM 适配器（企微/飞书）或 email；简化版：Prometheus alert → webhook → `POST /im/webhook/internal-alert` |
| **验收** | 手动触发高错误率 → 告警规则命中 → 通知发送 |

#### P4-4: Drift 检测定时任务（0.5 天）

| 项 | 内容 |
|---|---|
| **文件** | `agents/observability_agent/drift_detector.py`（新建） |
| **功能** | 每日凌晨 2:00 对比最近 7 天 vs 前 7 天的 LLM 输出分布（按 model/prompt_hash 分组，统计 avg_tokens/avg_latency/error_rate）；变化 > 20% 且无 prompt 变更 → 标记 drift |
| **调度** | APScheduler 或 asyncio 定时任务（在 startup_event 中启动） |
| **验收** | 手动修改数据 → 触发检测 → 事件记录 |

#### P4-5: AuditTrailView 前端（0.5 天）

| 项 | 内容 |
|---|---|
| **AuditTrailView.vue** | 审计日志表（时间/用户/操作/目标/详情）+ 过滤器（action/时间范围）+ 导出按钮 |
| **验收** | 展示真实审计记录 + 导出功能可用 |

#### P4-6: 全平台集成验证 + nginx 部署（0.5 天）

| 项 | 内容 |
|---|---|
| **nginx** | 新增 `/obs/` location（alias `frontend/observability-portal/dist` + SPA fallback） |
| **hub 导航** | `frontend/hub/` 新增"运行监测"卡片链接到 `/obs/` |
| **E2E 验证** | ① 7 个前端页面全可达 ② 7 个后端 API 全 200 ③ Grafana dashboard 数据实时 ④ Prometheus 告警规则加载 ⑤ 删除文档→审计有记录 ⑥ 检索回放返回 chunks |
| **systemd** | `fde-backend.service` 加 `Restart=on-failure` + `RestartSec=5` |

**Phase 4 质量门禁**：
```bash
ruff check agents/observability_agent/
python -m pytest tests/test_audit.py tests/test_drift.py -v
python -m pytest tests/ -v --tb=short  # 全量回归
cd frontend/observability-portal && npm run build
# 部署后验证
curl -s https://217.142.246.70:8443/obs/ | head -5
curl -s https://217.142.246.70:8443/fde-api/api/observability/overview | python -m json.tool
curl -s https://217.142.246.70:8443/fde-api/readyz | python -m json.tool
```

---

## 二、依赖关系图

```
P0-1 ─┬─→ P0-5
P0-2 ─┘
P0-3 ──→ (独立，无下游依赖)
P0-4 ──→ (独立，部署用)

P0-1 ──→ P1-1 ──→ P1-2 ──→ P1-3 ──→ P1-4
                ──→ P1-5
P1-6 ──→ P1-7 (需要 P1-3/P1-4 API)

P1-1 ──→ P2-1 ──→ P2-2 ──→ P2-3 ──→ P2-4
                ──→ P2-5
                ──→ P2-6
P2-7 (前端，依赖 P2-3/P2-5/P2-6 API)

P1-1 ──→ P3-1 ──→ P3-2 ──→ P3-3
                ──→ P3-4 (依赖现有 rag_agent)
        ──→ P3-5 (独立 trace)
        ──→ P3-7 (独立 chunker 统一)
P3-6 (前端，依赖 P3-2/P3-3/P3-4/P3-5 API)

P2-4 + P3-3 + P3-5 ──→ P4-1 ──→ P4-2
P0-4 ──→ P4-3
P3-5 ──→ P4-4
P4-2 ──→ P4-5 (前端)
P1-7 + P2-7 + P3-6 + P4-5 ──→ P4-6 (集成验证)
```

**关键路径**：P0-1 → P1-1 → P1-2 → P1-3 → P1-4 → P1-7 → P2-1 → P2-2 → P2-3 → P2-7 → P4-6

**可并行**：Phase 2 和 Phase 3 的后端任务可并行（不同子模块）；前端任务需等对应后端 API。

---

## 三、测试策略

### 3.1 测试金字塔

| 层级 | 占比 | 工具 | 覆盖 |
|---|---|---|---|
| **单元测试** | 70% | pytest + pytest-asyncio | 每个后端函数/端点 |
| **集成测试** | 20% | pytest + httpx AsyncClient | API → DB → Qdrant 全链路 |
| **E2E 验收** | 10% | 手动 curl + 前端浏览器 | 部署后全链路验证 |

### 3.2 测试用例清单

| 文件 | 用例数 | 覆盖任务 |
|---|---|---|
| `test_phase0_metrics.py` | 3 | P0-1 |
| `test_phase0_routers.py` | 2 | P0-2 |
| `test_phase0_embedding_env.py` | 2 | P0-3 |
| `test_health.py` | 5 | P1-2 |
| `test_overview.py` | 3 | P1-4 |
| `test_api_middleware.py` | 3 | P1-5 |
| `test_token_tracking.py` | 4 | P2-2 |
| `test_token_aggregation.py` | 3 | P2-3 |
| `test_budget.py` | 3 | P2-4 |
| `test_api_endpoints_scan.py` | 2 | P2-5 |
| `test_api_keys.py` | 5 | P2-6 |
| `test_chunk_metadata.py` | 3 | P3-1 |
| `test_rag_inspector.py` | 5 | P3-2/P3-3/P3-4 |
| `test_trace_spans.py` | 4 | P3-5 |
| `test_audit.py` | 3 | P4-1/P4-2 |
| `test_drift.py` | 2 | P4-4 |
| **合计** | **~56 新增** | |

### 3.3 回归策略

- 每个 Phase 结束运行全量 `pytest tests/ -v`（现有 920+ 测试不可回归）
- Phase 3 的 P3-1（Postgres 落库修改）和 P3-7（chunker 统一）需重点回归 `agents/ingestion_agent/tests/`
- Phase 0 的 P0-1（main.py 改动）需回归 `agents/router_agent/tests/`

### 3.4 质量门禁（每 Phase 必过）

```bash
# 1. Lint
ruff check agents/observability_agent/ shared/sdk/
# 2. Type check (mypy strict 已有配置)
mypy agents/observability_agent/ --strict
# 3. Tests
python -m pytest tests/test_phase*.py -v --cov=agents/observability_agent --cov-report=term-missing
# 4. Frontend build
cd frontend/observability-portal && npm run build
# 5. 全量回归（Phase 结束时）
python -m pytest tests/ -v --tb=short
```

---

## 四、分支与提交策略

### 4.1 分支模型（Trunk-Based）

- 主分支 `main`，短生命周期 feature 分支
- 每个 Phase 一个 feature 分支：`feature/observability-phase0` → PR → merge
- 每个 Task 一个 commit（Conventional Commits）：
  - `feat(observability): P0-1 接通 metrics + logging + OTel`
  - `fix(rag): P0-3 修 embedding env 拼写 EMBEDING→EMBEDDING`
  - `feat(observability): P1-2 三级探活 healthz/readyz/livez`

### 4.2 PR 检查清单

- [ ] ruff check 通过
- [ ] mypy strict 通过
- [ ] 新增测试全过
- [ ] 全量回归无失败
- [ ] 前端 build 成功
- [ ] 验收标准已手动验证

---

## 五、部署计划

| Phase | 部署内容 | 停机时间 |
|---|---|---|
| Phase 0 | main.py + systemd env + docker compose 取消注释 | 后端重启 ~5s |
| Phase 1 | observability_agent 后端 + observability-portal 前端 + nginx /obs/ | 后端重启 ~5s |
| Phase 2 | 后端增量 + 前端增量 | 后端重启 ~5s |
| Phase 3 | 后端增量 + 前端增量 + Alembic 迁移 | 后端重启 ~10s |
| Phase 4 | 后端增量 + 前端增量 + Prometheus alertmanager | 后端重启 ~5s |

**部署步骤**（每 Phase 通用）：
1. `git pull` 服务器代码
2. Alembic 迁移（如有）
3. `sudo systemctl restart fde-backend`
4. 前端 `npm run build` → tar → scp → 解包
5. `sudo systemctl reload nginx`
6. curl 验证

---

## 六、风险管理

| # | 风险 | 概率 | 影响 | 缓解措施 |
|---|---|---|---|---|
| R1 | P0-1 改 main.py 导致路由 Agent 启动失败 | 低 | 高 | try/except 包裹新代码；本地 `pytest` 后再部署 |
| R2 | P2-2 改 adapter 影响现有路由链 | 中 | 高 | Mock adapter 改动最小化；Stub 不实现 complete() 只加签名 |
| R3 | P3-1 Postgres 迁移失败丢数据 | 低 | 高 | Alembic 迁移只加列不删数据；先备份 |
| R4 | P3-7 统一 chunker 改变切片行为 | 中 | 中 | 保持 parent-child 为默认；现有测试全过才算 |
| R5 | 服务器 ARM 架构镜像不兼容 | 低 | 低 | Prometheus/Grafana 官方支持 arm64；提前验证 |
| R6 | Grafana/Prometheus 占用服务器资源 | 中 | 低 | 服务器 11G 内存/96G 磁盘；限制 Prometheus 保留 7 天 |
| R7 | 前端 7 个 view 工期超预期 | 中 | 中 | 先做核心 4 个（Overview/Health/RAG/Trace），其余 3 个可迭代 |

---

## 七、验收标准总表

| ID | 验收项 | 对应任务 |
|---|---|---|
| V0-1 | `curl /metrics` 返回 `fde_` 前缀指标 | P0-1 |
| V0-2 | 日志输出 JSON 格式 | P0-1 |
| V0-3 | `FDE_OTEL_ENABLED=1` 时 stdout 有 `llm_call` | P0-1 |
| V0-4 | `/dify/tools/*` 和 `/im/webhook/*` 路由可达 | P0-2 |
| V0-5 | `FDE_RAG_EMBEDDING_MODEL` env 正确读取 | P0-3 |
| V0-6 | Grafana 3000 可登录 + 8 面板有数据 | P0-4 |
| V1-1 | `/healthz` 返回 200 | P1-2 |
| V1-2 | Qdrant 关闭时 `/readyz` 返回 503 + 详情 | P1-2 |
| V1-3 | `/api/observability/overview` 返回健康分 + KPI | P1-4 |
| V1-4 | `/obs/` 前端可达 + Overview 页展示数据 | P1-7 |
| V1-5 | ServiceHealth 页展示组件矩阵 + 拓扑图 | P1-7 |
| V2-1 | 发送 chat 请求后 DB 有 token_usage_log 记录 | P2-2 |
| V2-2 | 按 model 聚合返回各模型 token 数 + 成本 | P2-3 |
| V2-3 | 超预算触发降级事件 | P2-4 |
| V2-4 | API 端点目录返回 65+ 条目 | P2-5 |
| V2-5 | API Key 创建后可用 + 超限 429 | P2-6 |
| V2-6 | TokenRouter + ApiMgmt 前端展示真实数据 | P2-7 |
| V3-1 | 上传文档后 Postgres metadata_json 非空 | P3-1 |
| V3-2 | 文档列表 + chunk 详情 API 返回真实数据 | P3-2 |
| V3-3 | 删除文档后 Qdrant + Postgres 全清 | P3-3 |
| V3-4 | 检索回放返回 chunks + 分数 | P3-4 |
| V3-5 | trace 查询返回完整 span 树 | P3-5 |
| V3-6 | RagInspector + TraceViewer 前端可用 | P3-6 |
| V4-1 | 删除操作后 audit_log 有记录 | P4-1 |
| V4-2 | 审计日志导出 JSON/CSV 成功 | P4-2 |
| V4-3 | Prometheus 告警规则触发通知 | P4-3 |
| V4-4 | Drift 检测识别输出分布变化 | P4-4 |
| V4-5 | AuditTrail 前端展示记录 + 导出 | P4-5 |
| V4-6 | `/obs/` 7 个页面全可达 + hub 导航卡片 | P4-6 |
| V4-7 | 全量回归 920+ 测试无失败 | P4-6 |

---

## 八、工期甘特图

```
Day  1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16 17 18 19
     ├──Phase 0──┤
                 ├───Phase 1───┤
                               ├────Phase 2────┤
                                     ├────Phase 3────┤
                                                   ├──Phase 4──┤
     ┌─────────────可并行──────────────┐
     │ P2 后端  │  P3 后端              │
     └─────────────────────────────────┘
```

- **Phase 0**: Day 1–2（2 天）
- **Phase 1**: Day 3–6（4 天）
- **Phase 2**: Day 7–11（5 天，P3 后端可从 Day 8 并行）
- **Phase 3**: Day 8–16（5 天实际工作，2 天与 Phase 2 并行）
- **Phase 4**: Day 17–19（3 天）
- **总计**: 19 个工作日（约 4 周）

---

*计划日期：2026-07-12 ｜ 基于设计文档：docs/v5-observability-platform-design.md ｜ 代码审计范围：agents/、shared/sdk/、deploy/、frontend/*
