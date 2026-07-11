# FDE 数据底座 + RAG 性能提升 · 整体落地路线图

> 本文把三份子方案（《rag-performance-improvement-plan.md》《data-ingestion-layer-plan.md》《multi-source-database-plan.md》）串成一份可执行的落地路线图，明确依赖、优先级、周次排期与最小可演示切片。
>
> 现状基线：ARM 2C/11G 单机、Postgres（系统库）、Qdrant（向量，457 点 green）、Redis/MinIO 尚未建；logistics_agent 是 Java 连接器平台（独立仓库）。
>
> **v2 修订（2026-07-11 自评审后）**：根据评估意见调整了人天估算、新增前置 spike、提前 ABAC 包裹、补充降级方案。总工期从 52d → 68d。

---

## 1. 目标与原则

| 目标 | 说明 |
|------|------|
| **即插即用** | ① 本地多源文件（docx/pptx/pdf/xlsx/txt）一键入库；② 任意 Java 连接器（用友/金蝶/视频…）加一个 `/manifest` 即被 FDE 自动识别、注册成可问答工具。 |
| **统一落库** | A、B 两套入口走同一条 IngestionPipeline，落同一套表（raw / canonical / chunks），进同一个 Qdrant，复用同一份 `field_mapping.yaml`。 |
| **检索质量可量化** | 每一步优化都过评测闭环（recall@k / MRR），不靠拍脑袋。 |
| **不污染生产** | 新表/新集合独立命名空间；连接器先 mock/yonyou 跑通再接真实系统；基准用 `rag_bench_*` 隔离集合。 |
| **每阶段可降级** | 技术假设未达预期时有 Plan B，不做"做完才验收"。 |

**优先级铁律**：先定契约（schema）→ 先打通最小切片证明即插即用 → 再扩广度（本地文件）→ 再提深度（重排/量化）→ 最后规模化（分布/异步/GPU）。

---

## 2. 工作流全景与依赖

```
                 ┌─────────────────────────────────────────────┐
                 │  Phase 0  契约与 Schema 定型（不写业务，只定约） │
                 │  ConnectorManifest / CanonicalDocument /      │
                 │  field_mapping.yaml / 4张SQL表 + Alembic       │
                 └─────────────────────────────────────────────┘
                    │                │                │
        ┌───────────┴──┐    ┌────────┴────────┐   ┌────┴──────────┐
        │ Work2-B      │    │ Work2-A         │   │ Work3 数据底座 │
        │ 连接器接入   │    │ 本地文件入库    │   │ (建库/扩展)    │
        │ /manifest+   │    │ Docling+归一化  │   │ Postgres+MinIO │
        │ connector_   │    │ +切片→DB+Qdrant │   │ +Redis+Qdrant  │
        │ agent骨架    │    │                 │   │ 量化/分区      │
        │ +ABAC基础包裹│    │                 │   │                │
        └──────┬───────┘    └────────┬────────┘   └────┬──────────┘
               │                    │                 │
               └─────────┬──────────┴─────────────────┘
                         ▼
                 ┌─────────────────────────────────────────────┐
                 │  Work1 RAG 性能提升（质量+延迟）              │
                 │  T0 快赢 → T1 重排 → T2 量化 → T3 改写       │
                 │  → T4 切片结构 → T5 GPU 推理微服务           │
                 └─────────────────────────────────────────────┘
                         │
                         ▼
                 ┌─────────────────────────────────────────────┐
                 │  Phase 6 规模化 + 加固（分布/异步/鉴权/可观测）│
                 └─────────────────────────────────────────────┘
```

**依赖要点**
- Phase 0 schema 是 A、B、Work3 的共同前置——**必须先定**，否则各自建表会分裂。
- Work 1 的 T0（嵌入换 ONNX / 缓存 / RRF）**不依赖**任何新表，可最早并行启动。
- Work 1 的 T1（重排）需要"已有候选 chunk 产出"，所以排在 Work2-A/B 入库之后。
- Work 1 的 T2（Qdrant 量化）与 Work3 的 Qdrant 扩展强耦合，合并实施。
- Work 2-B 需要 logistics 仓库先加 `/manifest`（跨仓库改造，需你授权 push）。
- **[v2 新增]** P0.5 Spike（Docling ARM + Reranker ARM）在 P1 期间并行执行，结论决定 P2/P3 技术选型，不阻塞 P1。

---

## 3. 阶段划分与排期（甘特式）

> 人天按**单人专注投入**估算（参考你 M4 的 solo 模式）。标注 `‖` 的表示若有人手可并行。
> **[v2]** 人天已含 30% 缓冲，更贴近 solo 实际。

| 阶段 | 内容 | 关联工作 | 人天 | 周次 | 依赖 |
|------|------|----------|------|------|------|
| **P0** | 契约与 Schema 定型：①`ConnectorManifest` v1 规格（企业族+视频族对齐） ②`CanonicalDocument` 模型 ③`field_mapping.yaml` schema（与 logistics FieldMappingConfig 对齐） ④SQL 4 表 + Alembic 迁移 ⑤评测集（50 查询+ground truth） | 全部前置 | **6** | W1 | — |
| **P0.5** | **[v2 新增] 前置技术 Spike**（与 P1 并行）：① Docling 在 ARM 2C 上解析 PDF/DOCX/XLSX 的延迟与内存（0.5d） ② BGE-Reranker-v2-M3 / FlashRank 在 ARM 上的单对延迟（0.5d）。结论决定 P2 解析器选型与 P3 重排策略 | P2, P3 前置 | **1** | W1-2 ‖ | — |
| **P1** | **最小可演示切片**：logistics 加 `/manifest` 端点（Java 改造）；FDE `connector_agent` 骨架（registry/adapter/tools）注册 yonyou/mock→canonical→DB→Qdrant→Supervisor 工具；**[v2] ABAC 基础包裹**（auth_filter + DecisionChainLog）；端到端跑通 | Work2-B, Work1-T0 | **8** | W1-3 | P0 |
| **P1b** | Work1 T0 快赢：嵌入换 ONNXRuntime、语义缓存（Redis/内存）、RRF 权重调优、评测闭环脚本 | Work1 | 3 | W1-2 ‖ | — |
| **P2** | Work2-A 本地文件入库：Docling 接入（**[v2] 若 P0.5 spike 不通过则回退现有 parser + pdfplumber/python-docx**） + 三层字段归一化 + 清洗复用 + 表格父子 chunk + 落 DB+Qdrant | Work2-A | **9** | W3-4 | P0, P0.5 |
| **P3** | Work1 T1 重排：新增 `reranker.py`（**[v2] 选型由 P0.5 spike 决定**：ARM 达标→BGE-Reranker-v2-M3；不达标→FlashRank 或延后到 P6 上 GPU）；T3 查询改写（HyDE/Multi-Query） | Work1 | **7** | W4-5 ‖ | P2 有产出 |
| **P3b** | Work3 数据底座补全：MinIO 二进制存储、Redis（缓存/队列）、Postgres GIN(JSONB) 索引、content_hash 幂等 | Work3 | 4 | W4-5 ‖ | P0 |
| **P4** | Work1 T2 量化：Qdrant Scalar/Binary + Matryoshka；T4 切片结构（句窗/父子/RAPTOR 初版）。**[v2] Plan B：量化掉精度→保留 FP32 + 仅做 payload 索引优化** | Work1, Work3 | 5 | W6-7 | P3, P3b |
| **P5** | Work2-B 扩展：discovery.py 移植为 Python 扫描工具；视频族契约对齐；连接器高级 ABAC 策略（动态权限、字段级脱敏） | Work2-B | **5** | W6-7 ‖ | P1 |
| **P6** | 规模化与加固：异步 ingestion worker + 批量嵌入、Qdrant 分布式/分区、Postgres 读写分离、GPU 推理微服务（解耦 bge-m3+reranker）、outbox 一致性、可观测/安全审计 | Work1-T5, Work3 | 8 | W8-10 | P4, P5 |
| **P7** | 文档 + 演示 + 复盘：用户手册、即插即用接入示例、压测复测、Roadmap 验收 | 全部 | **5** | W10-11 | 全部 |

**合计 ≈ 68 人天（约 12-13 周，单人连续）**；若 P0.5/P1b/P3/P3b/P5 并行，关键路径约 9-10 周。

> **[v2] 与 v1 的差异**：P0 4→6d（契约定型不能赶）；P1 6→8d（含跨仓库 Java 改造+ABAC 基础包裹）；P2 8→9d（含 Docling 回退方案预留）；P3 6→7d（含 spike 结论分支）；P7 3→5d（文档+演示+复盘需充分）；新增 P0.5 spike 1d。总计 52→68d（含 30% 缓冲）。

---

## 4. 关键路径 & 最小可演示切片（MDS）

**关键路径**：`P0 schema` → `P1 连接器切片` + `P2 本地文件` → `P3 重排` → `P6 规模化`。

**最小可演示切片（MDS，仅 P0+P1，≈14 人天）即可证明整个愿景**：
- logistics 侧：加一个 `/manifest` REST 端点（返回能力、实体、字段映射引用）。
- FDE 侧：`connector_agent` 注册该连接器 → 拉取订单/库存 → 归一为 `CanonicalDocument` → 落 Postgres + 进 Qdrant → 注册成 `ToolDefinition` → 在对话里问"用友上个月销售额"能答。
- **[v2]** ABAC 基础包裹：连接器工具调用经 `auth_filter` 权限校验 + `DecisionChainLog` 留痕，mock 阶段就包上，不裸奔。
- **演示价值**：把"即插即用"从 PPT 变成可点的事实；且这条链路复用了现有 `ToolRegistry`/`VectorStore`/`EmbeddingModel`，不写重依赖。

> 落地建议：**先只做 MDS（P0+P1）**，跑通后再决定是否继续 P2 往下。这样风险最低、反馈最快。

---

## 5. 各阶段交付物与验收标准

| 阶段 | 交付物 | 验收 |
|------|--------|------|
| P0 | `docs/connector-manifest-spec.md`、`models/canonical.py`、4 张表 migration、评测集 JSON | 表可迁移、评测脚本能跑出 baseline（MRR/recall@k） |
| **P0.5** | **[v2]** Spike 报告：Docling ARM 延迟/内存数据 + reranker ARM 单对延迟数据 + P2/P3 选型结论 | 有明确"可行/不可行/需降级"结论 |
| P1 | logistics `/manifest` PR；FDE `connector_agent/` 模块；ABAC 基础包裹；端到端 demo | 对话中能基于 yonyou/mock 数据正确回答≥3 类问题；调用链有决策日志 |
| P1b | `embeddings_onnx.py`、`cache.py`、评测对比报告 | 查询嵌入 30ms→≤10ms；MRR 不降 |
| P2 | `ingest_agent/` + `field_mapping.yaml` + Docling adapter（或回退方案） + 归一化引擎 | 乱列名 Excel、docx、pdf 各 1 样例端到端入库；字段统一 |
| P3 | `reranker.py`（选型由 spike 决定）、改写模块、对比报告 | MRR 0.30→≥0.50（基准集）；ARM 下单次检索仍<50ms（限候选）；**[v2] 不达标则走降级路径** |
| P3b | MinIO/Redis 封装、GIN 索引、幂等 | 大文件二进制可存取；重复 ingest 不产生幽灵 |
| P4 | 量化配置、切片结构改造、报告 | Qdrant 内存↓≥4x、检索延迟↓；质量持平；**[v2] 不达标→保留 FP32 + payload 索引优化** |
| P5 | 扫描工具、视频契约、高级 ABAC 策略 | 新连接器免改 FDE 代码即接入；字段级脱敏生效 |
| P6 | 异步 worker、分布 Qdrant、GPU 微服务、一致性、可观测 | 千级文档 ingest 不阻塞 API；bge-m3+reranker 延迟达标 |
| P7 | 手册、示例、复盘 | 第三方按文档 30 分钟内接一个新连接器 |

---

## 6. 风险与应对

| 风险 | 影响 | 应对 | **[v2] 降级方案** |
|------|------|------|-------------------|
| ARM 2C 跑重排/大模型过慢 | P3/P6 质量杠杆失效 | P0.5 spike 前置验证；重排限候选≤20；最终上 GPU 微服务（P6） | spike 不达标→P3 用 FlashRank 轻量重排或延后到 P6 上 GPU |
| logistics 仓库跨仓改造需你授权 push | P1 阻塞 | 先用本地 fork + mock 验证，再提 PR | mock-only 快速版先跑通 FDE 侧，logistics 改造延后 |
| **Docling 在 ARM 上偏重** | P2 解析慢/OOM | **[v2] P0.5 spike 前置验证**；仅文档解析走 Docling，表格/轻量走现有 parser | spike 不达标→回退 `pdfplumber`+`python-docx`+`openpyxl` 组合（功能弱但轻量） |
| 字段映射覆盖不全 | 连接器/Excel 字段漏映射 | `custom_fields` JSONB 兜底不丢数据；SchemaInference + 人工复核缓存 | 不兜底——漏映射数据进 custom_fields 原样保留 |
| **Qdrant 量化丢精度** | P4 召回降 | 先 Scalar 再 Binary，评测闭环把关；MATRYOSHKA 截断维度 | **[v2] 不达标→保留 FP32 + 仅做 payload 索引优化** |
| **连接器无鉴权暴露** | 安全 | **[v2] ABAC 基础包裹提到 P1**（mock 阶段就包上）；连接器侧补 token | 不裸奔——mock 阶段 auth_filter + DecisionChainLog 就位 |
| **[v2] solo 模式工期偏差** | 排期不准 | 人天含 30% 缓冲；P0.5 spike 提前暴露技术风险 | 阶段间设"检查点"，不达标暂停调整而非硬推 |

---

## 7. 资源与角色（solo 模式下由你一人按阶段推进）

- **架构/契约**（P0）：定标准，最关键，错则全返工。**[v2] 给足 6 天，不赶。**
- **[v2] 技术验证**（P0.5）：0.5d Docling ARM + 0.5d Reranker ARM，结论决定 P2/P3 走哪条路。
- **后端（FDE Python）**：connector_agent、ingest_agent、reranker、DB 封装。
- **Java 侧（logistics）**：/manifest、字段映射 schema 对齐、安全边界——需你或 Java owner 配合。**[v2] 若 Java 环境不熟，先 mock-only 跑通 FDE 侧。**
- **基础设施**：docker-compose 增量、Qdrant/MinIO/Redis、GPU 微服务。
- **安全**（**[v2] 提前**）：ABAC 基础包裹从 P1 开始，高级策略在 P5。
- **质量**：始终由评测闭环（P0 建的评测集）把关每一步。**[v2] 每阶段设检查点，不达标走降级方案或暂停调整。**

---

## 8. 下一步建议（立即可做，不污染生产）

1. **批准 MDS（P0+P1）** 作为第一里程碑。
2. 我可立即产出 **P0 交付物**：`ConnectorManifest` 规格文档 + `canonical.py` 模型 + 4 张表 Alembic migration + 评测集脚本（纯新增文件，不改现有逻辑）。
3. **[v2] P0 期间并行跑 P0.5 spike**：Docling ARM 安装试解析 + reranker ARM 延迟测试（各 0.5d），结论写进 spike 报告。
4. 随后做 **P1**：logistics 加 `/manifest`（先本地 fork 验证）+ FDE `connector_agent` 骨架连通 mock + ABAC 基础包裹。

确认后我从 P0 开始实现。

---

## 附：v1 → v2 修订记录（2026-07-11 自评审）

| 修订项 | v1 | v2 | 原因 |
|--------|----|----|------|
| P0 人天 | 4d | 6d | 契约定型要同时覆盖企业族+视频族+对齐 logistics FieldMappingConfig，4d 不够 |
| P1 人天 | 6d | 8d | 含跨仓库 Java 改造（/manifest）+ ABAC 基础包裹 |
| P1 内容 | 无 ABAC | +ABAC 基础包裹 | mock 阶段不裸奔，安全从第一天起 |
| P0.5 spike | 无 | 新增 1d | Docling ARM + Reranker ARM 前置验证，避免 P2/P3 开工后技术翻车 |
| P2 人天 | 8d | 9d | 含 Docling 回退方案预留时间 |
| P2 依赖 | P0 | P0 + P0.5 | 解析器选型取决于 spike 结论 |
| P3 人天 | 6d | 7d | 含 spike 结论分支（选 BGE vs FlashRank vs 延后） |
| P5 内容 | 含 ABAC 包裹 | ABAC 移到 P1，P5 只留高级策略 | 基础安全不等到 W6 |
| P4 降级 | 无 | 量化不达标→保留 FP32 + payload 索引优化 | 不硬推量化 |
| P7 人天 | 3d | 5d | 文档+演示+复盘 3d 不够 |
| 总工期 | 52d / 10 周 | 68d / 12-13 周 | 含 30% 缓冲 + spike + 降级预留 |
