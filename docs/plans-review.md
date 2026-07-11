# FDE 开发计划 · 整合评审报告

> 评审对象（按时间）：
> 1. `rag-deployment-verification-and-perf.md`（RAG 部署验证 + 性能基准，已落地）
> 2. `rag-performance-improvement-plan.md`（RAG 性能提升，T0–T5）
> 3. `ingestion-cleaning-module-plan.md`（多维数据输入与清洗，A 本地文件）
> 4. `logistics-connector-integration-analysis.md`（Java 连接器接入分析，B）
> 5. `data-ingestion-layer-plan.md`（A+B 统一入库）
> 6. `multi-source-database-plan.md`（多源数据库选型/搭建/扩展）
> 7. `implementation-roadmap.md`（总路线图 v2，串起 2/3/4/5/6）
> 8. `unified-web-portal-plan.md`（统一 Web 门户，8 菜单）
> 9. `system-architecture-diagram.html`（架构图，可视化交付）
>
> 评审日期：2026-07-11

---

## 1. 总体结论

**打分（单项）**：各子方案技术选型合理、有评测闭环、有降级方案，质量 **B+ ~ A-**。

**致命问题（Program 层面）**：这些计划是**孤岛**，没有整合为统一 Program。

| 维度 | 评价 |
|------|------|
| 技术选型 | ✅ 优秀。Docling / Qdrant / Postgres+JSONB / Naive UI 等选择都有依据、有降级路径。 |
| 评测闭环 | ✅ 好。roadmap P0 建 50 条评测集贯穿 RAG 优化；但**只覆盖 RAG**，门户/连接器无验收基准。 |
| 降级方案 | ✅ 好。roadmap v2 已补量化/解析器/重排降级。 |
| **跨计划一致性** | ❌ **差**。门户计划与总路线图互不引用；表结构/API 强耦合却各自排期。 |
| **缺口覆盖** | ⚠️ 中。本地文件入库 UI、连接器管理 UI、MapAI 地图 bug 三处缺失。 |
| 排期可行性 | ⚠️ 中。门户 26d 偏乐观（参考 roadmap 自身 52→68 的教训）；总程序被低估。 |

---

## 2. 一致性问题清单（跨计划矛盾）

| # | 问题 | 涉及文档 | 影响 | 严重度 |
|---|------|---------|------|--------|
| **C1** | **门户计划完全不在总路线图里** | `unified-web-portal-plan` vs `implementation-roadmap` | 总工期漏算 **26 人天**；资源排期冲突；两份计划都假设 solo 但无统一调度 | 🔴 高 |
| **C2** | 门户的 F/G/J/H/D 后端 API 依赖 `canonical_documents` / `connector_registry` 表，但门户计划**未声明对 ingestion/db 计划的依赖** | `unified-web-portal` vs `data-ingestion-layer` §4 / `multi-source-database` §4 | 若先建门户，「数据预览」「连接器问答」页无表可查，变成空壳 | 🔴 高 |
| **C3** | 契约文档命名不一致：roadmap 写 `docs/connector-manifest-spec.md`，ingestion/connector 计划写 `docs/connector-contract.md` | `implementation-roadmap` P0 vs `data-ingestion-layer` §6 | 交付物命名漂移，P0 验收找不到文件 | ⚠️ 中 |
| **C4** | Redis 时序矛盾：T0 语义缓存（W1-2）早于 Redis 建设（P3b W4-5） | `rag-performance` T0 / `implementation-roadmap` P1b vs `multi-source-database` P3b | 虽 roadmap 注「Redis/内存」缓解，但门户缓存策略未对齐统一 | ⚠️ 中 |
| **C5** | 门户「数据情报」只覆盖 web/RSS/API，**未覆盖本地文件上传 `/ingest/upload`** | `unified-web-portal` 菜单3 vs `data-ingestion-layer` §2.2 | 本地 Word/PPT/PDF/Excel 入库**没有 UI 入口**，用户无法操作（这正是你最初的需求 A） | 🔴 高 |
| **C6** | 连接器即插即用，但**门户 8 菜单里没有「连接器管理」页** | `implementation-roadmap` connector_registry vs `unified-web-portal` 菜单 | 无法在界面注册/查看/健康检查连接器，违背「即插即用」可演示性 | ⚠️ 中 |

---

## 3. 缺口清单（Gaps）

| # | 缺口 | 说明 | 建议归属 |
|---|------|------|---------|
| **G1** | 本地文档入库 UI | `/ingest/upload` 端点设计在 ingestion 计划，但门户无对应菜单/页面。要么新增菜单「知识库/文档入库」，要么并入「数据情报」 | 门户计划新增 |
| **G2** | 连接器管理 UI | 注册连接器、查看 manifest、健康检查、字段映射可视化 —— 应独立页面或并入「数据情报」 | 门户计划新增 |
| **G3** | **MapAI 地图加载 bug 未纳入任何计划** | 你已报告「右侧悬浮窗改动后地图加载不了」，此 bug 在两份前端相关计划（portal 嵌入 MapAI、架构图）中都未提及。门户通过 iframe 嵌入 MapAI，bug 会一并带进门户 | 独立 hotfix，插入 P0 前 |
| **G4** | 门户与数据底座「数据预览」语义未对齐 | 门户 F 要「浏览已入库结构化数据」= 读 `canonical_documents`；ingestion 计划的预览是独立 API。需统一一个预览端点 | 门户 + ingestion 对齐 |
| **G5** | 连接器/RAG 无独立评测基准 | roadmap P0 评测集只覆盖 RAG 检索质量；连接器接入、门户交互无验收基准 | 各计划补 |

---

## 4. 排期与可行性

### 4.1 被低估的总程序规模
- 总路线图 v2：**68 人天（12-13 周）**
- 门户计划：**26 人天（5 周）** —— 但 solo 模式下 8 个全栈模块（前端+后端 API+权限+部署），参考 roadmap 自身「52→68（+30%）」的教训，**门户也应 +30% → ~34 人天**。
- **真实总程序 ≈ 68 + 34 ≈ 102 人天（约 20 周）**，而非任何一个计划单独宣称的数字。

### 4.2 两份计划都假设 solo，但无「联合演示」节点
- roadmap 有 MDS（连接器→canonical→Qdrant→RAG 对话问答）。
- 门户有阶段1（MapAI 嵌入 + 路由统计 + 治理时间线 + 监控）。
- **但缺一个横跨「门户 + 数据 + 连接器」的垂直切片**：用户在门户上传一份 Excel → 看到入库 → 在对话里问答命中。这个 MVS（Minimum Viable Slice）才是真正证明整盘愿景的节点，目前不存在。

### 4.3 优先级冲突风险
- roadmap 主张「先定契约 P0 → 连接器切片 P1 → 本地文件 P2」。
- 门户主张「先做门户骨架 + 已有能力快速上线」。
- 若两者并行且无协调，门户阶段1 的「数据情报/治理」页可能早于底层表存在，变成空壳；或门户做完发现数据底座接口对不上，返工。

---

## 5. 整合建议（如何变成统一 Program）

### 5.1 把门户纳入总路线图
在 `implementation-roadmap.md` 中新增一个并行轨道 **Phase 门户**，并明确它与数据底座的依赖：

```
P0 契约/Schema (6d)
  ├─ P0.5 Spike (1d)
  ├─ P1 连接器切片 (8d) ──────────┐
  ├─ P2 本地文件入库 (9d) ─────────┤
  │                                ▼
  ├─ P1b RAG T0 (3d)      Phase 门户（新增）
  ├─ P3 重排 (7d)           ├─ 门户P0 骨架 (3d)
  ├─ P3b 数据底座 (4d) ───►├─ 门户P1 已有能力 (5d)
  ├─ P4 量化 (5d)           ├─ 门户P2 后端补齐+前端 (12d→~16d)
  ├─ P5 连接器扩展 (5d)     └─ 门户P3 权限打磨 (4d→~5d)
  └─ P6 规模化 (8d)
```

**关键依赖标注**：门户 P2 的「数据情报预览 / 连接器问答」必须等 ingestion P0+P2（表存在）才能真实跑通。

### 5.2 定义统一垂直切片 MVS（替代各自 MDS）
> 用户登录门户 → 上传一份乱列名 Excel（或注册一个 yonyou 连接器）→ 在门户「数据情报」页看到入库记录 → 在对话/分析页提问命中该数据。

这条切片横跨：门户（UI）+ ingestion（P0/P2）+ connector（P1）+ RAG（T0 已就位）。**它比 roadmap 的 MDS（仅后端对话问答）更接近最终用户价值**，建议作为第一里程碑。

### 5.3 命名与契约统一
- 契约文档统一命名为 **`docs/connector-contract.md`**（以 ingestion 计划为准，roadmap P0 同步修改）。
- `canonical_documents` / `document_chunks` / `raw_documents` / `connector_registry` 四表为**全 Program 共享 SoR**，任何计划的表变更必须回到 `multi-source-database-plan.md` §4 单一事实源。

### 5.4 补两个缺失 UI（G1/G2）
门户菜单建议从 8 个扩到 **10 个**（或把这两个并入「数据情报」）：
- **知识库 / 文档入库**：上传 docx/pptx/pdf/xlsx/txt → 进度 → 落库预览（对应 ingestion A）
- **连接器管理**：注册/健康/字段映射查看（对应 connector_registry）

### 5.5 MapAI 地图 bug 列为 P0 前 hotfix（G3）
门户用 iframe 嵌入 MapAI，地图 bug 会污染门户。建议在动门户之前先修（独立小任务，约 0.5–1d）。

---

## 6. 具体修订行动清单

| 行动 | 落点文档 | 内容 |
|------|---------|------|
| A1 | `implementation-roadmap.md` | 新增「Phase 门户」轨道，标注与 P0/P2 的依赖；总工期改为 ~102d |
| A2 | `unified-web-portal-plan.md` | 菜单扩到 10 个（加文档入库、连接器管理）；排期 +30% 缓冲（26→34d）；显式声明依赖 ingestion/db 计划 |
| A3 | `unified-web-portal-plan.md` | 阶段2 的 F/G/J/H/D 后端 API 注明「需 canonical_documents / connector_registry 表已建」 |
| A4 | `implementation-roadmap.md` / `data-ingestion-layer.md` | 契约文档名统一为 `connector-contract.md` |
| A5 | 新建 | 定义 MVS（门户+数据+连接器垂直切片）作为第一里程碑，替换/补充 roadmap 的 MDS |
| A6 | 新建 hotfix 任务 | MapAI 地图加载 bug 修复（P0 前，0.5–1d） |
| A7 | `unified-web-portal-plan.md` | 系统监控页明确依赖 M4 的 Prometheus/Grafana 已部署 |

---

## 7. 一句话总结

**计划们各自能打，但还没「组队」。** 最该立刻做的是：把门户计划并回总路线图（A1/A2）、补两个缺失 UI（A4）、修掉 MapAI 地图 bug（A6）、并定义一个横跨门户+数据+连接器的垂直切片 MVS（A5）——这比任何单份计划的精细度提升都更能降低整体交付风险。
