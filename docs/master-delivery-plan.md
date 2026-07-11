# FDE Platform 统一交付主计划（Master Plan v4）

> **本文档是唯一排期事实源（SoR for scheduling）。** 整合自：
> - `implementation-roadmap.md`（v2，数据底座 + RAG 性能）
> - `unified-web-portal-plan.md`（统一 Web 门户，8→10 菜单）
> - `plans-review.md`（整合评审 C1–C6 / G1–G5 / A1–A7）
> - `master-plan-review.md`（**工程评审 P0-1~P0-3 / P1-1~P1-5 / P2-1~P2-6 → F1–F13**）
>
> v4 日期：2026-07-11。v3→v4 变更见文末附录。

---

## 0. 为什么要重构（两轮评审结论）

### 第一轮（整合评审）：子计划是孤岛
各子计划单项 B+~A-，但门户计划不在路线图里、契约命名漂移、Redis 时序矛盾、缺本地文件/连接器管理 UI、MapAI 地图 bug 未纳入。→ v3 已修（C1–C6/G1–G5/A1–A7）。

### 第二轮（工程评审）：战略好但工程纪律缺
v3 战略层 A-，但工程纪律层有 3 个致命缺口：

| 级别 | 问题 | v4 修复 |
|------|------|---------|
| **P0-1** | 测试策略完全缺失，800+ 测试传统断裂 | F1：P0 新增测试规约；每阶段 ≥80% 覆盖 + CI 门禁 |
| **P0-2** | 单机 11G 资源容量未评估 | F2：P0 新增资源容量评估表；P6 拆 P6a(单机)/P6b(需扩容移出) |
| **P0-3** | MVS 名不副实（38d 不是 minimum） | F3：定义真 MVS ≤10d；原 MVS 降级为 Milestone 1 |
| P1-1 | 计划写 Alembic 但项目无 Alembic | F4：P0a 引入 Alembic + baseline + downgrade |
| P1-2 | 文件上传安全零字 | F5：H2b 加上传安全子任务 |
| P1-3 | 跨仓库契约无版本化 | F6：contract 加 schema_version + 向后兼容 |
| P1-4 | CI 未纳入门禁 | F7：每阶段 CI 全绿 stage gate；H1 更新 ci.yml |
| P1-5 | P6 规模化单机做不到 | F2：P6 拆 P6a/P6b |
| P2-1 | 文档 P7 集中补写 | F8：文档分阶段增量 |
| P2-2 | solo/团队排期混用 | F9：排期分两列 |
| P2-3 | H2b 两菜单依赖不同却打包 | F10：连接器管理移 H2 |
| P2-4 | 无 stage gate | F11：每阶段设门禁 |
| P2-5 | 可观测性接入不完整 | F12：新端点 trace_id + 前端错误上报 |
| P2-6 | 凭证存储未规范 | F13：P0 加凭证存储规范 |

---

## 1. 统一愿景与原则

| 原则 | 说明 |
|------|------|
| **即插即用** | ① 本地多源文件一键入库；② 任意 Java 连接器加 `/manifest` 即被 FDE 自动注册成可问答工具。 |
| **统一落库** | A（本地文件）+ B（连接器）走同一条 IngestionPipeline，落同一套表，进同一个 Qdrant。 |
| **统一入口** | 所有模块从一个 Web 门户的多个菜单访问，共享登录态与权限。 |
| **检索质量可量化** | 每步优化过评测闭环（recall@k / MRR）。 |
| **测试先行**（F1） | 每阶段新增代码测试覆盖率 **≥80%**；CI 全绿方可进入下一阶段。 |
| **容量约束**（F2） | 新增服务前先做资源容量评估；单机做不到的明确标「需扩容」。 |
| **契约版本化**（F6） | 跨仓库契约含 `schema_version`，向后兼容，破坏性变更双端同步。 |
| **不污染生产** | 新表/集合独立命名空间；连接器先 mock；基准用隔离集合。 |
| **每阶段可降级 + 有门禁**（F11） | 技术假设有 Plan B；阶段结束设 stage gate，不通过则暂停。 |
| **先定约后写码** | 契约/schema 是全局前置。 |

---

## 2. 共享事实源（SoR）

### 2.1 四张共享表（定义在 `multi-source-database-plan.md` §4）
- `raw_documents` — 原始抽取
- `canonical_documents` — 归一后标准实体（连接器数据 `storage_ref=connector://...`）
- `document_chunks` — 切片（含父子关系）
- `connector_registry` — 连接器注册/健康/字段映射引用

> 表变更必须回到 `multi-source-database-plan.md` §4，禁止各自建表。

### 2.2 契约文档（F4/F6）
- **`docs/connector-contract.md`**：ConnectorManifest v1 规格 + CanonicalDocument 模型 + field_mapping.yaml schema。
- **版本化**（F6）：manifest 含 `schema_version`（semver）；FDE 按 semver 向后兼容；破坏性变更需 FDE + logistics 双端同步发布。FDE 收到未知版本时优雅降级 + 告警。
- **凭证存储规范**（F13）：连接器/IM 的 AppID/Secret/Token 用 Postgres pgcrypto 加密列存储，**不明文**；或接外部 secret manager。

### 2.3 数据预览统一端点
门户「数据情报」与 ingestion 预览共用 `GET /api/data/preview`（读 `canonical_documents`）。

---

## 3. 模块清单与现状（速查）

| 编号 | 模块 | 后端现状 | 需 Web 页 | 门户菜单 |
|------|------|----------|-----------|----------|
| A | 智能路由网关 | 3 端点 | 需 | 菜单 6 |
| D | IM 消息枢纽 | webhook 已写未挂载 | 需 | 菜单 8 |
| E | 桌面客户端 SDK | Python SDK 完成；Tauri 壳骨架 | Web 覆盖 | — |
| F | 数据情报 | 经 ToolRegistry，无 HTTP | 需 | 菜单 3 |
| G | 智能分析 | NL2SQL 经 ToolRegistry | 需 | 菜单 2 |
| H | 治理与可观测 | DecisionChainLog 写入完整；AuditLog 有表无写入无 API | 需 | 菜单 9、10 |
| J | 人力资源 | 6 工具经 ToolRegistry | 需 | 菜单 7 |
| L | MapAI | 完整前端 | iframe | 菜单 1 |
| B | 连接器（Java） | 每厂商独立 REST | 需 | 菜单 5 |
| 数据底座 | Postgres+Qdrant 已跑；MinIO/Redis 待建 | — | — |

---

## 4. 里程碑（F3 重构）

### 4.1 MVS（Minimum Viable Slice，≤10 人天，第一里程碑）
> v3 的 38d「MVS」名不副实。v4 定义**真 MVS**——最小成本验证最大不确定性。

**用户故事**：登录门户 → 上传一份乱列名 Excel → 在对话页提问 → **命中该数据**。

**范围（严格限定）**：
- 门户只做 **3 页面**：登录 + 文件上传 + 对话（不做 10 菜单骨架、不做权限打磨）
- 后端只做：`/ingest/upload`（Excel only）+ 字段归一化 + 入库 Postgres + 进 Qdrant + RAG 查询
- **不含**：连接器、Docling/PDF/PPT、已有能力页、ABAC 打磨

**涉及的阶段**：H0 + P0a + P0 + P2a（MVS 核心） = 1+1+6+3 = **11 人天**（接近 10d 目标）

**验收**：上传 1 份乱列名 Excel → 字段归一落库 → 对话问答命中该数据。证明「多源数据→统一入库→RAG」核心闭环。

### 4.2 Milestone 1（M1，原 v3 的 MVS 降级）
> MVS 跑通后扩展为完整「门户 + 数据 + 连接器 + RAG」垂直切片。

涉及 H1（门户完整骨架）→ P1（连接器）→ H2（已有能力+连接器管理）→ P2b（完整文件入库）→ H2b（文档入库页）。验收：MVS 两条路（Excel + 连接器）各跑通。

### 4.3 MDS（连接器即插即用切片，后端里程碑）
仅 P0+P1：logistics 加 `/manifest` → FDE `connector_agent` 注册 → 归一 → 落库 → 进 Qdrant → 注册成 ToolDefinition → 对话能答。

---

## 5. 阶段与轨道（甘特）

> 人天按单人专注估算，含 30% 缓冲。
> **F9**：排期分 solo / 3 人团队两列。`‖` 仅在团队列有意义。
> **F11**：每阶段结束设 **stage gate**（见 §7），不通过不进入下一阶段。

| 阶段 | 内容 | 轨道 | 人天 | solo 周次 | 团队周次 | 依赖 |
|------|------|------|------|----------|----------|------|
| **H0** | **[G3/F2-前置] MapAI 地图 bug hotfix** | 修复 | 1 | W1 | W1 | — |
| **P0a** | **[F4] 引入 Alembic** + 现有 schema.sql 纳入 baseline migration + downgrade 脚本 | 数据 | 1 | W1 | W1 | — |
| **P0** | 契约与 Schema：`connector-contract.md`（含 F6 版本化）+ `CanonicalDocument` + `field_mapping.yaml` + 4 表 Alembic migration + downgrade + **[F1] 测试规约** + **[F2] 资源容量评估表** + **[F13] 凭证存储规范** + 评测集（50 查询 + 连接器/门户 smoke） | 数据 | 6 | W1-2 | W1-2 | P0a |
| **P0.5** | Spike：Docling ARM + Reranker ARM（结论定 P2b/P3 选型） | 数据 | 1 | W2 ‖ | W2 ‖ | — |
| **H1** | 门户骨架：Vue3+Vite+Router+Pinia+Naive UI，布局/API 客户端/登录/路由守卫；**[F7] 更新 ci.yml 加前端 lint+build** | 门户 | 3 | W2-3 ‖ | W2 ‖ | P0 |
| **P1** | **[MDS]** logistics `/manifest`（Java，含 F6 schema_version）；FDE `connector_agent`（registry/adapter/tools）注册 yonyou/mock→canonical→DB→Qdrant→Supervisor；ABAC 基础包裹 | 数据/连接器 | 8 | W3-4 | W2-3 | P0 |
| **P1b** | RAG T0：嵌入换 ONNX；语义缓存先用内存 LRU（C4）；RRF 调优；评测闭环 | RAG | 3 | W4 ‖ | W3 ‖ | — |
| **P2a** | **[F3/MVS 核心]** Excel 归一化 + 入库 Postgres + 进 Qdrant + RAG 查询 + 门户上传页/对话页（3 页面极简版） | 数据/门户 | 3 | W4-5 | W3 | P0 |
| **H2** | 门户已有能力页：MapAI iframe、AI 路由统计、治理决策链时间线、系统监控（Grafana iframe）；**[F10] 连接器管理页**（仅依赖 P1，从 H2b 移来） | 门户 | 6 | W5-6 | W4 | H1, P1 |
| **P2b** | **[完整本地文件入库]** Docling（spike 不通过则回退 pdfplumber+python-docx）+ 三层字段归一化扩展 + 表格父子 chunk → DB+Qdrant | 数据 | 6 | W6-7 | W5 | P0, P0.5, P2a |
| **P3b** | 数据底座补全：MinIO（**[F2] 容量评估后决定**）、Redis、Postgres GIN(JSONB)、content_hash 幂等 | 数据 | 4 | W7 ‖ | W5 ‖ | P0 |
| **H2b** | **[F5/F10] 文档入库页**（依赖 P2b）：`/ingest/upload` + 进度 + 落库预览；**[F5] 上传安全**（类型 magic-bytes 校验 + 大小限制 + UUID 路径 + 临时文件 TTL） | 门户 | 3 | W8 | W6 | P2b |
| **P3** | RAG T1 重排（选型由 P0.5 定）+ T3 查询改写 | RAG | 7 | W8-9 | W7 | P2b |
| **H3** | **[C2/A3] 门户后端补齐 + 模块页**（依赖 P0/P1/P2b 表）：F/G/J/D/H 端点+页面；**[F12] 所有新端点注入 trace_id（复用 TracingMiddleware）+ 前端错误上报** | 门户 | 13 | W10-12 | W7-9 | P0,P1,P2b |
| **P4** | RAG T2 量化 + T4 切片结构；不达标→FP32 + payload 索引 | RAG | 5 | W12-13 | W9 | P3,P3b |
| **P5** | 连接器扩展：discovery.py 移植、视频族契约、高级 ABAC | 连接器 | 5 | W13-14 ‖ | W9 ‖ | P1 |
| **H4** | 门户权限打磨：各页 RBAC/ABAC、响应式、错误/空态、nginx `/portal/` 部署 | 门户 | 7 | W14-15 | W10 | H3 |
| **P6a** | **[F2 拆分] 规模化（单机可做）**：异步 ingestion worker + 批量嵌入 + outbox 一致性 + 可观测接入 | 数据/RAG | 4 | W15-16 | W11 | P4 |
| ~~P6b~~ | **[F2 拆分] 需扩容，移出当前周期**：分布式 Qdrant、Postgres 读写分离、GPU 推理微服务 | — | — | Phase 2 | Phase 2 | 需多节点 |
| **P7** | **[F8] 文档整合 + 演示 + 复盘**（各阶段已产出文档增量，此处只整合） | 全部 | 3 | W16 | W12 | 全部 |

**合计 ≈ 97 人天 / solo 约 16-17 周；3 人团队约 12 周。**

> v3→v4 人天变化：102→97。P0a +1d；P2 拆 P2a(3)+P2b(6)=9d（不变）；H2b 6→3d（连接器管理移 H2，H2 5→6d，净不变）；P6 8→P6a 4d（-4d）；P7 5→3d（文档分阶段，-2d）。

### 关键路径
`solo`：H0 → P0a → P0 → P2a(MVS) → P2b → P3 → P4 → P6a → P7
`团队`：数据轨(P0→P1→P2b→P3→P4→P6a) ‖ 门户轨(H1→H2→H3→H4) ‖ RAG 轨(P1b→P3→P4)

---

## 6. 统一门户：10 个菜单

> 访问 `https://域名:8443/portal/`，与 MapAI `/fde/`、后端 `/fde-api/`、Dify `/` 共存。
> 新项目 `frontend/portal/`（Vue3 + TS + Router + Pinia + Naive UI + ECharts）。

| # | 菜单 | 路由 | 模块 | 后端依赖 | 阶段 |
|---|------|------|------|----------|------|
| 1 | MapAI | `/portal/map` | L | 已有 iframe | H2 |
| 2 | 智能分析 | `/portal/analysis` | G | ⭐`/api/analysis/*` | H3 |
| 3 | 数据情报 | `/portal/data` | F | ⭐`/api/data/*` | H3 |
| 4 | 知识库/文档入库 | `/portal/kb` | A(本地) | ⭐`/ingest/upload` + P2b 表 | H2b |
| 5 | 连接器管理 | `/portal/connectors` | B | ⭐`/api/connectors/*` + P1 | **H2**（F10 移来） |
| 6 | AI 路由 | `/portal/router` | A | `/v1/models` + ⭐`/api/router/stats` | H2 |
| 7 | 人力资源 | `/portal/hr` | J | ⭐`/api/hr/*` | H3 |
| 8 | 消息枢纽 | `/portal/im` | D | webhook 挂载 + ⭐`/api/im/*` | H3 |
| 9 | 审计与治理 | `/portal/governance` | H | ⭐`/api/governance/*` | H2/H3 |
| 10 | 系统监控 | `/portal/monitor` | H | Grafana iframe（M4 已部署） | H2 |

**后端新增 API 原则**：薄 HTTP 包装已有 Worker/Tool 函数，不重复实现。**所有新端点自动注入 trace_id**（F12）。

---

## 7. 各阶段交付物、验收与 Stage Gate（F1/F7/F8/F11）

> **每阶段 Stage Gate（F11）**：① CI 全绿（lint+test+typecheck）② 验收标准达成 ③ 评测不降级 ④ 该阶段文档增量已产出。四项全过才进入下一阶段。

| 阶段 | 交付物 | 验收标准 | 测试要求(F1) | 文档增量(F8) |
|------|--------|----------|-------------|-------------|
| H0 | 地图修复 PR | `/fde/` 地图可见可交互 | 现有前端测试不回归 | hotfix 说明 |
| P0a | Alembic 引入 + baseline + downgrade | `alembic upgrade head` 可跑；`downgrade -1` 可回滚 | migration 有测试 | Alembic 使用说明 |
| P0 | contract.md(含版本化) + canonical.py + 4表 migration + **测试规约** + **资源容量评估表** + **凭证存储规范** + 评测集 | 表可迁移；评测脚本跑出 baseline；容量评估有明确结论 | — | contract.md 本身即文档 |
| P0.5 | Spike 报告 | 明确「可行/降级」结论 | — | spike 报告 |
| H1 | 门户骨架 + 登录 + 路由守卫 + **ci.yml 加前端** | 能登录进空壳门户；CI 含前端 lint+build | 骨架组件 ≥1 测试 | 门户开发指南 |
| P1 | logistics `/manifest`(含版本) + connector_agent + ABAC + MDS demo | 对话基于连接器数据答对≥3类；manifest 未知版本优雅降级 | adapter ≥5 单元测试；端到端 ≥1 | 连接器接入手册初稿 |
| P1b | ONNX 嵌入 + 内存缓存 + 评测对比 | 嵌入 30ms→≤10ms；MRR 不降 | 嵌入/缓存 ≥3 测试 | RAG T0 报告 |
| **P2a** | **MVS**：Excel 归一化+入库+问答+3页面 | **上传 Excel→问答命中** | 归一化 ≥10 单元测试；E2E ≥2 | MVS 验收报告 |
| H2 | 4 已有能力页 + 连接器管理页 | 各页数据可见；连接器注册/健康可见 | 各页 ≥1 集成测试 | — |
| P2b | ingest_agent 完整 + Docling/fallback + 父子 chunk | Excel/docx/pdf 各1样例端到端入库 | 归一化扩展 ≥5 测试；解析 ≥3 | 入库运维 runbook |
| P3b | MinIO/Redis 封装 + GIN + 幂等 | 大文件可存；重复 ingest 无幽灵 | 封装 ≥3 测试 | 数据底座 runbook |
| H2b | 文档入库页 + `/ingest/upload` + **上传安全** | 上传进度可见、落库预览；恶意文件被拒 | 上传安全 ≥3 测试（类型/大小/路径） | — |
| P3 | reranker.py + 改写模块 | MRR 0.30→≥0.50；ARM 单次<50ms | 重排/改写 ≥5 测试 | RAG 优化报告 |
| H3 | F/G/J/D/H 端点+5模块页 + **trace_id 注入** + **前端错误上报** | 各页数据真实可读；trace 可查 | 每模块端点 ≥2 集成测试 | API 文档(OpenAPI) |
| P4 | 量化配置 + 切片结构 | 内存↓≥4x；质量持平（否则 FP32） | 量化回归测试 | — |
| P5 | 扫描工具 + 视频契约 + 高级 ABAC | 新连接器免改代码接入 | discovery ≥3 测试 | 连接器接入手册完稿 |
| H4 | RBAC/ABAC 每页 + 响应式 + nginx 部署 | 不同角色菜单不同；iPad 可用 | 权限 ≥3 测试 | 部署 runbook |
| P6a | 异步 worker + 批量嵌入 + outbox + 可观测 | 千级文档 ingest 不阻塞 API | 异步 ≥3 测试 | 规模化 runbook |
| P7 | 手册整合 + 演示 + 复盘 | 第三方 30 分钟接一个新连接器 | 全量回归 | 用户手册+复盘 |

---

## 8. 资源容量评估（F2，P0 产出）

> P0 阶段必须产出此表。以下为预填估算，P0 时用实测数据替换。

| 服务 | 当前占用 | 计划新增 | 峰值 RAM | 能否单机 | 备注 |
|------|----------|----------|----------|----------|------|
| Dify 12 容器 | ~3.5G | — | ~4G | ✅ | 已运行 |
| Qdrant | ~1G | — | ~2G(457→万级) | ✅ | 已运行 |
| Postgres | ~1G | 4 表 | ~1.5G | ✅ | 已运行 |
| fde-backend | ~0.5G | ONNX | ~1.5G | ✅ | 含 ONNX 嵌入 |
| nginx | ~50M | /portal/ | ~50M | ✅ | — |
| Redis | — | 新增 | ~256M | ✅ | 轻量 |
| MinIO | — | 新增 | ~512M | ✅ | 轻量 |
| Docling (torch) | — | 按需加载 | ~1.5G | ⚠️ | spike 验证；可能需按需启停 |
| BGE-Reranker (568M) | — | 按需加载 | ~1.2G | ⚠️ | spike 验证；可能走 P6b GPU |
| **合计** | ~6G | ~5G | **~11.8G** | **⚠️ 临界** | 11G 机器接近上限 |

**结论**：单机可跑 Redis + MinIO + ONNX；**Docling + Reranker 不能同时常驻**，须按需加载或走独立微服务。P6b（分布式/GPU）需扩容。

---

## 9. 风险登记（统一）

| 风险 | 应对 | 降级 |
|------|------|------|
| ARM 跑重排/大模型慢 | P0.5 spike；重排限候选≤20；最终 GPU(P6b) | spike 不达标→FlashRank 或延后 |
| **[F2] 单机 11G 容量临界** | P0 容量评估；Docling/Reranker 按需加载 | 超限→关停非关键服务或扩容 |
| logistics 跨仓需授权 push | 先本地 fork + mock | mock-only 先跑通 FDE 侧 |
| Docling ARM 偏重 | P0.5 spike | 回退 pdfplumber+python-docx+openpyxl |
| 字段映射不全 | custom_fields JSONB 兜底 | 漏映射原样保留 |
| Qdrant 量化丢精度 | 先 Scalar 再 Binary；评测把关 | 保留 FP32 + payload 索引 |
| 连接器无鉴权暴露 | ABAC 基础包裹提到 P1 | mock 阶段 auth_filter 就位 |
| **[F5] 文件上传安全** | magic-bytes 校验+大小限制+UUID 路径+TTL 清理 | 恶意文件拒绝上传 |
| **[F6] 契约版本不兼容** | manifest schema_version + semver 兼容 | 未知版本优雅降级+告警 |
| **[F13] 凭证泄露** | pgcrypto 加密列 / secret manager | 不明文存储 |
| C4 Redis 时序 | T0 用内存 LRU，P3b 后迁 Redis | 门户缓存策略与后端一致 |
| G3 MapAI bug 污染门户 | H0 hotfix 先行 | iframe 前先验证地图正常 |
| solo 工期偏差 | 30% 缓冲 + stage gate | 不达标暂停调整 |
| **[F1] 测试债务** | 每阶段 ≥80% 覆盖 + CI 门禁 | 不达标不进入下一阶段 |

---

## 10. 修复行动落地对照

### 第一轮（整合评审 A1–A7）
| 行动 | 状态 |
|------|------|
| A1 门户并入总路线图 | ✅ §5 Phase 门户轨道 |
| A2 菜单扩 10 + 门户缓冲 | ✅ §6 |
| A3 门户声明表依赖 | ✅ §5 H3/H2b |
| A4 契约命名统一 | ✅ §2.2 |
| A5 MVS 垂直切片 | ✅ §4（v4 进一步修正为 ≤10d） |
| A6 MapAI bug hotfix | ✅ §5 H0 |
| A7 监控页依赖 Prometheus | ✅ §6 菜单10 |

### 第二轮（工程评审 F1–F13）
| 行动 | 落点 | 状态 |
|------|------|------|
| F1 测试规约 + ≥80% 覆盖 + CI 门禁 | §1 原则 + §7 每阶段 | ✅ |
| F2 资源容量评估表 + P6 拆分 | §8 + §5 P6a/P6b | ✅ |
| F3 真 MVS ≤10d | §4.1 | ✅ |
| F4 Alembic 引入 + baseline + downgrade | §5 P0a | ✅ |
| F5 文件上传安全 | §5 H2b + §7 | ✅ |
| F6 契约版本化 + 向后兼容 | §2.2 + §7 P1 验收 | ✅ |
| F7 CI 全绿 stage gate + ci.yml 更新 | §7 + H1 | ✅ |
| F8 文档分阶段增量 | §7 文档增量列 | ✅ |
| F9 solo/团队排期两列 | §5 | ✅ |
| F10 连接器管理移 H2 | §5/§6 | ✅ |
| F11 stage gate 机制 | §7 | ✅ |
| F12 trace_id 注入 + 前端错误上报 | §5 H3 | ✅ |
| F13 凭证存储规范 | §2.2 + §9 | ✅ |

---

## 11. 下一步（立即可做，不污染生产）

1. **H0 hotfix 先行**（1d，独立低风险，解除地图问题）。
2. **P0a 引入 Alembic**（1d，纯新增框架，不改现有表）。
3. **P0 契约+Schema+测试规约+容量评估**（6d，纯新增文件）。
4. P0 期间并行 **P0.5 spike**（各 0.5d）。
5. P0 完成后做 **P2a 真 MVS**（3d，证明核心闭环）。
6. 确认后我从 **H0 + P0a** 开始实现。

---

## 附录：v3 → v4 修订记录

| 修订项 | v3 | v4 | 原因 |
|--------|----|----|------|
| 测试策略 | 无 | **F1**：每阶段 ≥80% 覆盖 + CI 门禁 | P0-1 致命：800+ 测试传统断裂 |
| 资源容量评估 | 无 | **F2**：§8 容量评估表 | P0-2 致命：11G 单机撑不住 |
| MVS 范围 | 38d | **F3**：≤10d（P2a）；原 MVS 降级 M1 | P0-3 致命：38d 不是 minimum |
| Alembic | P0 直接写 | **F4**：新增 P0a 引入框架+baseline | P1-1：项目无 Alembic |
| 文件上传安全 | 无 | **F5**：H2b 加安全子任务 | P1-2：上传入口无防护 |
| 契约版本化 | 无 | **F6**：schema_version + semver | P1-3：跨仓库无版本兼容 |
| CI 门禁 | 无 | **F7**：每阶段 stage gate + ci.yml | P1-4：CI 未纳入计划 |
| 文档 | P7 集中 | **F8**：分阶段增量 | P2-1：集中补写反模式 |
| 排期 | solo 混用 ‖ | **F9**：solo/团队两列 | P2-2：‖ 在 solo 是噪音 |
| H2b 菜单 | 两菜单打包 | **F10**：连接器管理移 H2 | P2-3：依赖不同 |
| Stage gate | 无 | **F11**：每阶段四项门禁 | P2-4：无阶段门禁 |
| 可观测性 | 不完整 | **F12**：trace_id + 前端错误上报 | P2-5：新端点无 trace |
| 凭证存储 | 无 | **F13**：pgcrypto / secret manager | P2-6：不明文 |
| P6 | 8d 含分布式 | 拆 P6a(4d 单机) / P6b(移出) | P1-5：单机做不到分布式 |
| P7 | 5d | 3d（文档分阶段，只整合） | F8 |
| P0a | 无 | 新增 1d | F4 |
| 总人天 | 102 | **97** | P6 -4d, P7 -2d, P0a +1d |
