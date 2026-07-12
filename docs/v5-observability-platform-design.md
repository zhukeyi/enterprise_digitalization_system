# FDE 全系统运行监测平台 — 完备设计方案

> **定位**：将 RAG 切片可观测性扩展为覆盖全平台的统一监测模块，对标 Langfuse + Portkey + Grafana 三层架构，适配 FDE 的企业落地七步法场景。
>
> **研究方法**：2025–2026 GitHub/开发者社区企业级 AI 可观测性动向调研 + FDE 代码基础设施审计（未改动任何文件）。

---

## 一、评审：原 RAG 切片方案的不足

上一版方案（`docs/v5-rag-observability-research.md`）聚焦 RAG 切片/向量化可视化，方向正确但存在三个盲区：

1. **孤岛思维**：只解决了 RAG 一个模块的可观测性，但 FDE 有 14 个 Agent 模块、65+ 个 API 端点、4 个模型适配器、Qdrant/Postgres/Dify 等多个依赖——RAG 切片问题可能根因在 token 路由选错了模型，也可能根因在 Qdrant 延迟突增，需要跨模块关联才能定位。
2. **未利用已有基础设施**：审计发现 FDE 已有 `metrics.py`（自实现 Prometheus 指标）、`trace.py`（contextvars + PII 脱敏）、`otel_backend.py`（OTLP + Langfuse）、`logging.py`（JSONFormatter）、Grafana dashboard JSON（8 面板）、Prometheus alert rules（6 条）——但 **setup_metrics、setup_structured_logging、OTelBackend 全部未在 main.py 中调用**。上一版方案没提到这些已有件。
3. **缺少企业级治理维度**：社区共识（Portkey 1600+ LLM 网关、LiteLLM、Datadog LLM Obs）强调的"统一翻译官+交警+会计"模式——成本归因、API Key 生命周期管理、模型降级策略、合规审计——在上一版中完全缺失。

**结论**：原方案作为 RAG 模块的子集是对的，但应升级为全平台可观测性体系的一个有机组成部分。

---

## 二、社区动向：2026 企业级 AI 可观测性架构共识

### 2.1 三层架构（业界已收敛）

| 层 | 职责 | 标杆产品 | FDE 对应 |
|---|---|---|---|
| **Layer 1: LLM 追踪与评估** | 捕获 prompt/completion/tool calls、多步链路 trace、在线/离线 eval | Langfuse（OSS, 自托管）、LangSmith、Arize Phoenix | OTelBackend + Langfuse（已有骨架，未启用） |
| **Layer 2: 网关与成本** | 代理层捕获 usage/latency/cost、路由/failover/限流 | Portkey、Helicone、LiteLLM | router_agent（已有 4 适配器 + failover，无 token 计数） |
| **Layer 3: 基础设施 APM** | 确定性系统指标、日志、分布式追踪 | Datadog、Grafana+Tempo+Loki+Prometheus | Grafana dashboard JSON（已有 8 面板，未部署） |

**粘合层 = OpenTelemetry**：所有层通过 OTel GenAI 语义约定关联，一次 trace 讲完整故事。

### 2.2 五大企业模式（MELT 框架）

社区文章 "AI Agent Observability: The MELT Framework (2026)" 提出的 5 个必做模式：

| 模式 | 含义 | FDE 适配 |
|---|---|---|
| **Cost Canary** | 按 agent/部门设成本预算，超限自动降级模型 | router_agent 已有 cost_per_1k_tokens 字段，需接入实际计数 + 预算告警 |
| **Drift Detector** | 每周对比 agent 输出分布，无 prompt 变更但行为漂移则告警 | 需新增：记录每次 LLM 调用的 model/prompt_hash/output_embedding |
| **Compliance Checkpoint** | 每次触碰 PII/财务数据自动记录审计 trail | governance_agent 已有审计中间件，需补可视化 |
| **Human Escalation Tracker** | 追踪 agent→人工移交的触发原因和人工决策 | 防呆5步已有决策记录，需接入监测面板 |
| **Multi-Agent Debugger** | 多 agent 失败时 30 秒内生成完整 trace 可视化 | LangGraph Supervisor + 10 Workers 已有结构，需接入 OTel span |

### 2.3 中国开发者社区的关键洞察

- **"给 AI 装一个电表"**（掘金 7618846325320777780）：好的中台不是"再造一个 OpenAI"，而是做模型世界的"统一翻译官+交警+会计"。
- **"AI 推理网关可观测性四类指标"**（cloudnative-tech.com）：入口体验（QPS/错误率/首 token 延迟）、模型消耗（token/上下文长度）、后端资源（GPU/队列/实例健康）、治理结果（限流/降级/灰度/回滚次数）。
- **五层分层架构**（CSDN 161573588）：入口协同层→AI 应用层→观测采集层→中央平台层→控制治理层。层间职责边界比层数更重要。

---

## 三、FDE 基础设施审计：已有 vs 缺失

### 3.1 已有但未接通（"管道断了"——最高 ROI 修复）

| 组件 | 位置 | 状态 | 修复方式 |
|---|---|---|---|
| Prometheus metrics | `shared/sdk/metrics.py` | **未在 main.py 调用 setup_metrics** | main.py 加一行 `setup_metrics(app)` |
| 结构化日志 | `shared/sdk/logging.py` | **未在 main.py 调用 setup_structured_logging** | main.py 启动时调用 |
| OTel/Langfuse | `shared/sdk/otel_backend.py` | **默认关闭，未与 trace.py 打通** | 设 `FDE_OTEL_ENABLED=1` + 在 LLM 调用处 emit_llm_call |
| Grafana dashboard | `deploy/grafana/dashboards/fde-platform.json` | **8 面板 JSON 已写好，但 compose 中被注释** | 取消注释，部署 Grafana 容器 |
| Prometheus alerts | `deploy/prometheus/alerts.yml` | **6 条告警规则已写好，但 Prometheus 容器被注释** | 取消注释，部署 Prometheus |
| Loki 日志 | `deploy/loki/loki-config.yml` | **配置已写好，3 天保留，未部署** | 取消注释，部署 Loki |
| dify_bridge / im_agent router | 各自目录 | **未在 main.py 注册** | `app.include_router(...)` |
| `@traced` 装饰器 | `shared/sdk/decorators.py` | **存在但仅打日志，未生成 OTel span** | 与 otel_backend 打通 |

### 3.2 完全缺失（需新建）

| 缺口 | 影响 |
|---|---|
| token 真实计数 + 成本追踪 | 3 个 Stub 适配器未实现，total_tokens 恒 0 |
| `/health` 不检查依赖 | Qdrant/Postgres/Dify 宕机时 /health 仍 200 |
| 无 `/healthz` `/readyz` `/livez` 分离 | K8s/systemd 无法正确判断就绪状态 |
| 无 API Key 管理控制台 | Key 分散在 env，无生命周期管理 |
| 无应用层限流（仅 nginx） | 无法 per-user/per-key 配额 |
| 无异步任务重试/死信队列 | worker 异常即 failed，无指数退避 |
| 无平台监测前端 | 所有 portal 无系统健康/服务状态/Trace 视图 |
| 无 RAG 切片检视/维护 | 零读接口，零维护界面 |
| 无模型成本归因报表 | 无法回答"今天花了多少钱、哪个 agent 花的" |

---

## 四、设计方案：FDE Observability Platform

### 4.0 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                    FDE Observability Portal                      │
│                   (frontend/observability-portal/)               │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐│
│  │Over- ││Token ││ API  ││Service││ RAG ││Trace ││Audit ││
│  │view  ││Router││ Mgmt ││Health ││Inspector││Viewer││ Trail ││
│  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘│
└───────────────────┬─────────────────────────────────────────────┘
                    │ FastAPI
┌───────────────────┴─────────────────────────────────────────────┐
│              observability_agent (新建后端模块)                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐│
│  │ Metrics  ││ Token    ││ API      ││ Health   ││ RAG    ││
│  │ Collector ││ Cost    ││ Registry ││ Monitor  ││ Inspector││
│  │          ││ Tracker  ││          ││          ││        ││
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘│
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                         │
│  │ Trace    ││ Alert    ││ Audit    │                         │
│  │ Store    ││ Engine   ││ Logger   │                         │
│  └──────────┘ └──────────┘ └──────────┘                         │
└──────┬──────────────┬──────────────┬──────────────┬─────────────┘
       │              │              │              │
  ┌────▼────┐  ┌─────▼─────┐  ┌────▼────┐  ┌────▼────────┐
  │Prometheus│  │  Grafana  │  │  Loki   │  │ Langfuse    │
  │ (metrics)│  │ (dashboards)│(logs)   │  │ (LLM traces)│
  └──────────┘  └───────────┘  └─────────┘  └─────────────┘
```

### 4.1 模块拆分（7 个子模块）

#### 4.1.1 Overview Dashboard — 平台总览
**对标**：Datadog Overview、Grafana Home Dashboard

- 平台健康分（绿/黄/红）：基于各组件探活 + 错误率 + 延迟 P95 综合评分
- 4 维实时 KPI：请求 QPS、错误率、P95 延迟、活跃 token 消耗/小时
- 24 小时时间线：系统事件标注（部署、告警、降级）
- 14 个 Agent 模块状态卡片：每个显示在线/离线、最近调用时间、错误率
- 组件连通性矩阵：Qdrant / Postgres / Dify / nginx / embedding model

**后端**：
- `GET /api/observability/overview` — 聚合健康分 + KPI + 事件线
- `GET /api/observability/components` — 组件级连通性 + 延迟

**前端**：`OverviewView.vue` — 健康分大圆环 + 4 KPI 卡 + 时间线 + 组件矩阵

#### 4.1.2 Token Router Monitor — token 动态路由监控
**对标**：Portkey、LiteLLM、Helicone

- 模型路由策略可视化：当前 YAML 配置热重载状态、规则命中分布
- Token 用量大盘：按 模型/用户/Agent模块/时段 四维下钻
- 成本归因报表：每次调用记 model/prompt_tokens/completion_tokens/cost_usd，按维度聚合
- Failover 事件流：超时/重试/降级记录
- **Cost Canary**：按 agent 设日预算阈值，超限自动降级 + 告警

**后端**：
- `GET /api/observability/tokens/usage` — 用量统计（支持 group_by=model|user|agent|hour）
- `GET /api/observability/tokens/cost` — 成本报表（日/周/月）
- `GET /api/observability/tokens/routing` — 路由规则命中分布
- `GET /api/observability/tokens/failover` — failover 事件
- `POST /api/observability/tokens/budget` — 设置 agent 预算
- 数据写入：在 4 个 model adapter 的 `complete()` 返回后，emit `token_usage` 事件（Counter + 日志 + OTel span attribute）

**前端**：`TokenRouterView.vue` — 路由策略面板 + 用量堆叠面积图 + 成本柱状图 + Failover 事件流

**关键修复**：
1. 3 个 Stub 适配器补真实实现（或至少 Mock 返回合理 token 数）
2. `emit_llm_call` 在每次 LLM 调用后执行（目前 OTelBackend.emit_llm_call 存在但从未调用）
3. token 用量持久化到 SQLite/Postgres（新增 `token_usage_log` 表）

#### 4.1.3 API Management — 内外部 API 接口管理
**对标**：Kong、Portkey、Spring Cloud Gateway

- **端点注册表**：自动扫描所有 FastAPI router，生成端点目录（path/method/description/所属模块/认证要求/限流配置）
- **调用统计**：每个端点的 QPS / P95 延迟 / 错误率 / 调用趋势
- **外部 API 管理**：Dify bridge / 百度地图 / IM 适配器 / 数据采集源的统一注册、Key 管理、调用日志
- **限流配置**：应用层 per-user / per-key 配额（补充 nginx 层的粗粒度限流）
- **API Key 生命周期**：申请 → 分发 → 配额 → 启用/停用 → 黑名单

**后端**：
- `GET /api/observability/api/endpoints` — 自动扫描所有注册 router
- `GET /api/observability/api/stats/{path}` — 单端点调用统计
- `GET /api/observability/api/external` — 外部 API 注册表
- `POST /api/observability/api/keys` — API Key CRUD
- `PUT /api/observability/api/keys/{id}/quota` — 配额设置
- 中间件：`APIMetricsMiddleware` — 拦截所有请求，记录 path/method/status/latency/user_id

**前端**：`ApiManagementView.vue` — 端点目录表 + 调用趋势图 + 外部 API 卡片 + Key 管理表

**关键修复**：
1. dify_bridge router 和 im_agent webhook router 注册到 main.py
2. 统一 API 版本前缀（`/api/v1/` 或至少文档标注）
3. 应用层限流中间件（基于 token bucket，per-user）

#### 4.1.4 Service Health — 平台各组件服务状态监控
**对标**：Kubernetes liveness/readiness probes、Datadog Service Map

- **三级探活**：
  - `/healthz` — 进程存活（systemd 用）
  - `/readyz` — 依赖就绪（Qdrant + Postgres/SQLite + embedding model 可加载）
  - `/livez` — 实时存活（最近 30 秒无 5xx 风暴）
- **组件健康矩阵**：
  - Qdrant：ping + collection 状态 + 向量数
  - Postgres/SQLite：连接 + 表存在性 + 行数
  - Dify：HTTP ping + tenant_id 校验
  - Embedding Model：模型加载状态 + 维度 + 后端类型
  - nginx：反代可达性
- **服务地图**：14 个 Agent 模块的依赖关系图 + 实时状态着色
- **自动重启**：systemd unit + restart on failure

**后端**：
- `GET /healthz` — 200/503
- `GET /readyz` — 依赖检查（并行探活，3s 超时）
- `GET /livez` — 最近错误率检查
- `GET /api/observability/health/components` — 组件级详细状态
- `GET /api/observability/health/service-map` — 模块依赖关系

**前端**：`ServiceHealthView.vue` — 组件健康矩阵 + 服务地图拓扑图 + 历史可用率折线

**关键修复**：
1. `/health` 升级为真实依赖检查（当前仅返回模型列表）
2. systemd unit 文件（当前仅 docker-compose，但服务器实际用 systemd）
3. Prometheus/Grafana/Loki 容器取消注释，部署启用

#### 4.1.5 RAG Inspector — RAG 切片/向量化可视化与维护
**对标**：FastGPT 知识库管理、raglens、rag-tui

（此模块即原 T0+T1 方案，纳入统一平台）

- **文档列表**：按 doc_type/source/时间筛选，显示 chunk 数/向量维度/嵌入模型/状态
- **Chunk 检视**：按 doc_id 浏览所有切片，显示原文/parent_text/切片方式/block_kind/向量预览
- **检索回放**：输入 query → 展示召回 chunks + 向量相似度 + rerank 分数 + query rewrite 结果
- **引用维护**：对 chunk 标记"有误/修改/删除"（FastGPT 核心卖点）
- **文档管理**：删除文档（Qdrant+Postgres+FTS 级联）+ 重建索引

**后端**：
- `GET /api/observability/rag/docs` — 文档列表
- `GET /api/observability/rag/docs/{id}/chunks` — chunk 列表
- `GET /api/observability/rag/chunks/{id}` — chunk 详情（含向量预览）
- `DELETE /api/observability/rag/docs/{id}` — 级联删除
- `POST /api/observability/rag/docs/{id}/reindex` — 重建索引
- `POST /api/observability/rag/debug/retrieve` — 检索回放

**前端**：`RagInspectorView.vue` — 文档表 + chunk 详情抽屉 + 检索回放面板

**关键修复**：
1. Postgres `document_chunks.metadata_json` / `parent_chunk_id` 实际落库
2. embedding env 拼写 bug（`FDE_RAG_EMBEDING_MODEL` → `FDE_RAG_EMBEDDING_MODEL`）
3. 统一两套 chunker（rag_agent/chunking.py 和 ingestion_agent/chunking.py）

#### 4.1.6 Trace Viewer — 全链路追踪
**对标**：Langfuse、Arize Phoenix、Jaeger/Tempo

- **Trace 列表**：按时间/服务/错误率/延迟筛选
- **Trace 详情**：Span 树（请求→路由→RAG→LLM→后处理），每个 span 显示耗时/输入/输出/属性
- **LLM 专属 span**：prompt/completion/retrieved_context/eval_score（GenAI 语义约定）
- **多 Agent 调试**：LangGraph Supervisor → Worker 的决策树 + 工具调用链
- **Drift 检测**：每周对比输出分布，无 prompt 变更但行为漂移则标红

**后端**：
- `GET /api/observability/traces` — trace 列表（分页 + 过滤）
- `GET /api/observability/traces/{id}` — trace 详情（span 树）
- `GET /api/observability/traces/stats` — 统计（P50/P95/P99、错误率、热路径）
- 数据源：OTel OTLP → 本地 SQLite（简化版，无需 Jaeger/Tempo 容器）

**前端**：`TraceViewerView.vue` — trace 列表 + span 树瀑布图 + LLM 调用详情

**关键修复**：
1. `@traced` 装饰器与 `OTelBackend` 打通（当前仅打日志）
2. 在 LLM 调用处 `emit_llm_call` 记录 prompt/completion/token（当前从未调用）
3. LangGraph 节点加 OTel span（LangGraph 原生支持 `langgraph.trace`）

#### 4.1.7 Audit Trail — 合规审计与治理
**对标**：Datadog Audit Trail、EU AI Act 合规日志

- **操作日志**：所有写操作（删除文档/重建索引/修改配置/API Key 变更/模型切换）
- **PII 访问记录**：触碰 PII/财务数据的 agent 决策链
- **人工移交追踪**：防呆5步的决策记录 + 人工最终裁决
- **合规报告导出**：按时间段导出审计日志（JSON/CSV）

**后端**：
- `GET /api/observability/audit/logs` — 审计日志列表
- `GET /api/observability/audit/export` — 导出
- 数据写入：复用 governance_agent 审计中间件 + 新增 `audit_log` 表

**前端**：`AuditTrailView.vue` — 日志表 + 过滤 + 导出按钮

---

## 五、实施路线图

### Phase 0: 管道接通（1–2 天）— 最高 ROI

**零新建代码，只接通已有组件。**

| # | 任务 | 文件 | 工作量 |
|---|---|---|---|
| 0.1 | main.py 调用 `setup_metrics(app)` | `router_agent/main.py` | 1 行 |
| 0.2 | main.py 调用 `setup_structured_logging()` | 同上 | 3 行 |
| 0.3 | 注册 dify_bridge + im_agent router | 同上 | 4 行 |
| 0.4 | 设 `FDE_OTEL_ENABLED=1` 环境变量 | systemd env | 配置 |
| 0.5 | 取消 Prometheus/Grafana/Loki compose 注释 | docker-compose | 配置 |
| 0.6 | 修 embedding env 拼写 bug | `embeddings.py:332` | 1 行 |

**效果**：`/metrics` 端点上线、结构化 JSON 日志进入 Loki、Grafana 8 面板可用、OTel trace 开始导出。

### Phase 1: 健康检查 + 监测前端骨架（3–4 天）

| # | 任务 |
|---|---|
| 1.1 | `/healthz` `/readyz` `/livez` 三级探活（含 Qdrant/Postgres/Dify/Embedding 检查） |
| 1.2 | 新建 `agents/observability_agent/` 后端骨架（router + models + collector） |
| 1.3 | 新建 `frontend/observability-portal/`（Vue3+Vite+ECharts，base `/obs/`） |
| 1.4 | OverviewView + ServiceHealthView 两个页面 |
| 1.5 | APIMetricsMiddleware（拦截所有请求记 path/status/latency） |
| 1.6 | 部署验证 + nginx `/obs/` location |

### Phase 2: Token 路由 + API 管理（4–5 天）

| # | 任务 |
|---|---|
| 2.1 | Model adapter 补 token 计数（Mock 返回合理值，Stub 接口定义好） |
| 2.2 | `emit_llm_call` 在每次 LLM 调用后执行 |
| 2.3 | `token_usage_log` 表 + 用量/成本聚合 API |
| 2.4 | Cost Canary：agent 日预算 + 超限降级 |
| 2.5 | API 端点自动扫描 + 外部 API 注册表 |
| 2.6 | API Key CRUD + per-key 配额 |
| 2.7 | TokenRouterView + ApiManagementView 前端 |

### Phase 3: RAG Inspector + Trace Viewer（4–5 天）

| # | 任务 |
|---|---|
| 3.1 | RAG 只读 API（docs/chunks/chunk详情） |
| 3.2 | RAG 维护 API（删除/重建/检索回放） |
| 3.3 | Postgres metadata_json / parent_chunk_id 落库修复 |
| 3.4 | `@traced` 与 OTelBackend 打通 |
| 3.5 | LangGraph 节点加 OTel span |
| 3.6 | trace 存储（SQLite 简化版）+ 查询 API |
| 3.7 | RagInspectorView + TraceViewerView 前端 |

### Phase 4: 审计 + 告警闭环（2–3 天）

| # | 任务 |
|---|---|
| 4.1 | `audit_log` 表 + 写入（复用 governance 中间件） |
| 4.2 | 审计查询/导出 API |
| 4.3 | Prometheus alert rules 启用 + 告警通知（webhook → IM） |
| 4.4 | Drift 检测定时任务（每日对比输出分布） |
| 4.5 | AuditTrailView 前端 |

### 总工期

| Phase | 工期 | 累计 |
|---|---|---|
| Phase 0 管道接通 | 1–2 天 | 2 天 |
| Phase 1 健康+前端骨架 | 3–4 天 | 6 天 |
| Phase 2 Token+API | 4–5 天 | 11 天 |
| Phase 3 RAG+Trace | 4–5 天 | 16 天 |
| Phase 4 审计+告警 | 2–3 天 | 19 天 |

**约 3–4 周**，Phase 0+1 即可达到"黑盒变玻璃盒"（约 1.5 周）。

---

## 六、技术决策

### 6.1 后端

- **新建 `agents/observability_agent/`**，与其他 14 个 Agent 平级，router 注册到 main.py
- 数据存储：优先 SQLite（与现有 MVS 一致），Postgres 可用时切换
- 新增表：`token_usage_log`、`audit_log`、`trace_spans`（简化版，无需 Jaeger）
- 复用已有：`shared/sdk/metrics.py`、`trace.py`、`otel_backend.py`、`logging.py`
- Prometheus 指标复用已有 Counter/Histogram/Gauge，新增 `fde_token_usage_total`、`fde_cost_usd_total`、`fde_component_health`

### 6.2 前端

- **新建 `frontend/observability-portal/`**，Vue3 + Vite + ECharts，base `/obs/`
- 暗色主题（运维场景惯例，与 intelligence-portal 一致）
- 7 个 View，侧栏导航
- 复用 `BaseChart.vue` 组件（portal 已封装）

### 6.3 部署

- systemd 环境变量新增：`FDE_OTEL_ENABLED=1`、`FDE_OTEL_ENDPOINT=http://localhost:4318`
- docker-compose 取消注释 Prometheus + Grafana + Loki（仅监控栈，不影响核心服务）
- nginx 新增 `/obs/` location（alias frontend/observability-portal/dist）
- systemd `fde-backend.service` 加 `Restart=on-failure` + `RestartSec=5`

### 6.4 不做的

- **不做全功能 LLM 网关**（Portkey 式 1600+ 模型代理）：FDE 只接 4 个模型，router_agent 够用
- **不做 K8s 探针**：FDE 跑在单机 systemd，不需要 K8s liveness/readiness
- **不做 Jaeger/Tempo 分布式追踪后端**：单服务用 SQLite 存 trace 即可，OTel 导出给 Langfuse 做深度分析
- **不做实时流式监控**（WebSocket 推送）：轮询 30s 刷新足够，降低复杂度

---

## 七、与 V5 七步法的关系

| 七步法 | 监测覆盖 |
|---|---|
| ① 基础 | Service Health 监控所有底层组件 |
| ② 交付（Dashboard） | Overview Dashboard 补充系统级视角 |
| ③ 培训 | Audit Trail 记录培训认证操作 |
| ④ 情报 | API Management 管理数据采集源 |
| ⑤ 营销 | Token Router 追踪营销文案生成成本 |
| ⑥ 裁员 | Audit Trail + Human Escalation 追踪防呆决策 |
| ⑦ 定价 | Token Router 监控 RL 训练 token 消耗 |

监测平台是七步法的**横切关注点**（cross-cutting concern），不是第八步。

---

## 八、验收标准

| 维度 | 验收项 |
|---|---|
| `/metrics` | 返回 Prometheus 格式指标，含 fde_token_usage_total 等 |
| `/healthz` | 进程存活返回 200 |
| `/readyz` | Qdrant+DB+Embedding 全通返回 200，任一不通返回 503 + 详情 |
| Overview | 平台健康分 + 4 KPI + 14 模块状态 + 组件矩阵可见 |
| Token Router | 每次调用记 model/token/cost，按 4 维聚合可查 |
| API Mgmt | 65+ 端点自动列出 + 调用统计 + Key 管理 |
| RAG Inspector | 可浏览任意文档的 chunks + 检索回放 + 删除/重建 |
| Trace Viewer | 单次请求的完整 span 树可见 |
| Audit Trail | 所有写操作有审计记录，可导出 |
| Grafana | 8 面板 dashboard 可访问，数据实时更新 |
| 告警 | Prometheus 6 条规则生效，超限触发通知 |

---

*设计日期：2026-07-12 ｜ 参考标杆：Langfuse、Portkey、LiteLLM、Datadog LLM Obs、Arize Phoenix、FastGPT、raglens、rag-tui、RAGTrace、Helicone ｜ FDE 代码审计范围：`agents/`、`shared/sdk/`、`deploy/`、`frontend/`*
