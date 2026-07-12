# FDE 平台开源集成与产品化开发方案（v1.0）

> **文档定位**：由原《开源项目优化路线图》+《战略评审》合并升级为完备开发方案。
> **核心修正**：单纯堆叠横向 OSS 不构成产品策略。本方案以"横向 OSS 强化（抬底线）+ 纵向产品化补齐（打包装/多租户/培训/差异化）"双线推进，把 FDE 从"可演示"推进到"可商业化交付的产品"。
> **生成时间**：2026-07-13　**状态**：已评审，待启动

---

## 一、背景与基线

### 1.1 现状基线

| 维度 | 现状 |
| :--- | :--- |
| 交付进度 | V4 工程底座 ✅；V5 七步法 ✅（审计 ~95%）；全系统运行监测平台 ✅ |
| 规模 | 16 后端智能体 + 9 前端门户，全量测试 1227 个 |
| 部署 | 单台 Oracle ARM（**2C/11G/96G**），systemd + nginx，自签证书；FDE 后端 + Dify + Qdrant 同机 |
| 约束 | 无 Postgres（SQLite 兜底）；pricing/marketing 被 numpy-only 约束；无 K8s |
| 商业定位（V5 说明书） | 基础版 1-3（基建+交付+培训）一次性交付费；增值模块 4-7（情报/营销/裁员/定价）按年订阅；全家桶折扣 |

### 1.2 商业目标

对照 `docs/v5-enterprise-delivery-plan.md`：从"AI 平台"到"可交付的商业产品"。本方案的目标是补齐"可商业化交付"的最后差距——集中在**打包部署、多租户计费、培训交付物、基础设施可信度**四点，而非再堆功能。

### 1.3 战略评审结论（对本方案的修正）

1. **OSS 方向合适但非充分**：横向 OSS（网关/采集/解析/观测）抬高底线可信度，但 V5 卖点是纵向垂直模块；OSS 应隐形于其后做基础设施。
2. **资源硬约束**：现 2C/11G 单机已偏紧，无法再承载 crawl4ai(Playwright/Chromium)+Langfuse(ClickHouse) 全套。必须取舍或升配/分机。
3. **产品化缺口（OSS 未覆盖）**：一键部署、多租户隔离、配置驱动、升级路径、客户 onboarding——这些决定"能否打包为产品"的程度高于 OSS 选型。
4. **差异化护城河 = 垂直模块**（裁员防呆 5 步 / GEO 营销 / 动态定价 RL），不可被标准 OSS 同质化稀释。
5. **唯一"工程质量+商业使能"双赢项 = LiteLLM**：虚拟 Key + 按租户预算直接承载年订阅计费，最高优先。

---

## 二、目标架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                    客户租户（年订阅单元）                              │
│   基础版(①②③)              增值模块(④⑤⑥⑦ 任选)                       │
└──────────────┬───────────────────────────────────────────────────────┘
               │ HTTPS
┌──────────────▼───────────────────────────────────────────────────────┐
│  nginx 网关 (8443)  +  Docker Compose 一键部署                         │
│   /fde-api/ /obs/ /portal/ /hr/ /pricing/ /marketing/ /intel/ /hub/   │
└──────────────┬───────────────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────────────┐
│  LiteLLM 网关 (统一 100+ 模型 / 虚拟 Key / 按租户成本预算 / fallback)  │
│   ← 多租户隔离与计费基座；替代 router_agent 自研 4 适配器              │
│   callback → Langfuse 观测                                             │
└──────┬───────────────┬───────────────────────┬────────────────────────┘
       │               │                       │
┌──────▼──────┐  ┌──────▼────────┐  ┌──────────▼──────────┐
│ FDE 后端     │  │ 采集层(可拆    │  │ 观测层              │
│ LangGraph    │  │  worker 机)   │  │ Langfuse+ClickHouse │
│ 16 Agents    │  │ RSSHub        │  │ (P3，需升配)        │
│ +Docling     │  │ crawl4ai      │  │ 现内存环缓冲(单机)   │
│ +Vanna       │  │ changedetect  │  │                     │
└──────────────┘  └───────────────┘  └─────────────────────┘
```

**设计原则**

- **OSS 隐形化**：客户感知的是垂直模块门户，LiteLLM/crawl4ai/Docling 不可见。
- **租户隔离靠 LiteLLM 虚拟 Key**：每租户一 Key，绑定模型白名单 + 预算 + 限流。
- **采集层可拆**：Chromium 类重负载放独立 worker 机，保护主机。
- **观测可降级**：单机用内存环缓冲，多机/企业版用 Langfuse 持久化。

---

## 三、WBS 总览（7 阶段）

| 阶段 | 名称 | 主线 | 优先级 | 工作量 | 依赖 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **P0** | LiteLLM 网关统一 + 多租户基座 | 横向/商业使能 | 🔴 最高 | 8d | — |
| **P0** | 一键打包部署（Docker Compose + 升级路径） | 产品化 | 🔴 最高 | 6d | — |
| **P1** | 情报源扩展（RSSHub + crawl4ai worker） | 横向 | 🟠 高 | 7d | P0 |
| **P1** | 培训交付物补齐 | 产品化/审计缺口 | 🟠 高 | 8d | — |
| **P2** | RAG 解析升级（Docling） | 横向 | 🟡 中 | 5d | P0 |
| **P2** | 分析层升级（Vanna） | 横向 | 🟡 中 | 5d | P0 |
| **P3** | 观测持久化（Langfuse） | 横向 | 🟢 低（需升配） | 6d | 升配 |

> 关键路径：P0(LiteLLM) → P1(情报) → P2(RAG) → P3(观测)；P0(打包) 与 P1(培训) 可并行。

---

## 四、各阶段详细任务

### P0-A：LiteLLM 网关统一 + 多租户基座（8d）

**目标**：用 LiteLLM 替代 router_agent 自研 4 适配器，并建立按租户的 Key/预算/计费基座。

| 任务 | 改动点 | 输入 | 输出/验收 | 工作量 |
| :--- | :--- | :--- | :--- | :--- |
| L-1 LiteLLM 部署 | `deploy/litellm/config.yaml`、docker-compose | 模型清单 | 容器 :4000 起，OpenAI 兼容接口通 | 1d |
| L-2 适配器迁移 | `router_agent/adapters/*` → LiteLLM config | 现有 4 适配器 | chat/embedding 经 LiteLLM 透传，响应格式一致 | 2d |
| L-3 token/cost 对接 | `observability_agent/token_tracker.py` | LiteLLM spend callback | token_tracker 改读 LiteLLM cost，预算/降级逻辑保留 | 1d |
| L-4 多租户虚拟 Key | LiteLLM virtual keys + budget | V5 租户模型 | 每租户 Key + 模型白名单 + 预算 + 限流；超额触发降级 | 2d |
| L-5 回归与防呆 | `tests/` | 现有 router/observability 测试 | 全量回归通过；新增 LiteLLM 集成测试 | 1.5d |
| L-6 文档 | `docs/` | — | 网关迁移说明 + 租户配置手册 | 0.5d |

**风险**：侵入 router 核心链路（R1，高影响）。**缓解**：保留原适配器作 fallback 适配层，灰度切换；L-5 全量回归门禁。

### P0-B：一键打包部署（6d）

**目标**：客户买回 30 分钟跑起来；具备升级路径。

| 任务 | 改动点 | 输出/验收 | 工作量 |
| :--- | :--- | :--- | :--- |
| D-1 主 Compose | `deploy/docker-compose.prod.yml` | FDE 后端 + Qdrant + LiteLLM + nginx + 前端 dist 一键起 | 2d |
| D-2 环境配置化 | `.env.example` 拆分 base/tenant | 行业/租户配置驱动，无硬编码 | 1d |
| D-3 数据卷与持久化 | volumes + 备份脚本 | Qdrant/SQLite/LiteLLM DB 卷挂载 + 备份/恢复 | 1d |
| D-4 升级路径 | `scripts/upgrade.sh` | 版本滚动升级，不丢数据 | 1d |
| D-5 安装文档 | `docs/deployment/` | 30 分钟安装指南 + 故障排查 | 1d |

**验收**：干净主机执行 `docker compose up` → 全部门户 200，可创建租户并跑通一次 RAG 问答。

### P1-A：情报源扩展（7d）

**目标**：data_agent 源覆盖 +10x、提取质量质变。**注意资源约束**：crawl4ai 的 Chromium 必须评估或拆 worker 机。

| 任务 | 改动点 | 输出/验收 | 工作量 |
| :--- | :--- | :--- | :--- |
| I-1 RSSHub 自托管 | `deploy/` 加 RSSHub 容器 | RSSHub 起，data_agent `RSSScraper` 订阅 1000+ 路由 | 1d |
| I-2 crawl4ai Scraper | `data_agent/scrapers/crawl4ai_scraper.py` 注册 `ScraperRegistry` | 新增 SourceType 或复用 WEB；输出 LLM-ready Markdown | 2d |
| I-3 资源评估/拆机 | Chromium 内存压测；必要时拆 crawl worker | 主机内存安全（≤70%）；或 worker 机方案 | 1d |
| I-4 情报门户适配 | `intelligence-portal` SourceView | RSSHub/crawl4ai 源可管理、可预览 | 1.5d |
| I-5 测试 | `data_agent/tests/` | crawl4ai/rsshub 集成测试 + 回归 | 1d |
| I-6 文档 | `docs/` | 源扩展配置手册 | 0.5d |

**风险**：Chromium 吃内存（R2）。**缓解**：I-3 先压测，超阈则拆 worker 机，绝不拖垮主服务。

### P1-B：培训交付物补齐（8d，审计 ❌ 缺口）

**目标**：补齐说明书③要求的视频/题库/PPT/手册，使③达可交付。

| 任务 | 输出/验收 | 工作量 |
| :--- | :--- | :--- |
| T-1 用户手册（V5 专用） | `docs/training/manual.md` 三级（操作员/分析师/架构师） | 2d |
| T-2 题库（30-50 题） | `docs/training/exam-bank.md` 含答案与实操题 | 2d |
| T-3 视频（5-10 个） | 录屏 3-5 分钟/个 | 3d |
| T-4 PPT + 考证流程 | 培训 PPT + 认证发放流程 | 1d |

### P2-A：RAG 解析升级 Docling（5d）

| 任务 | 输出/验收 | 工作量 |
| :--- | :--- | :--- |
| R-1 Docling 集成 | `ingestion_agent` 解析层接 `DocumentConverter`，输出 Markdown 入 chunking | 2d |
| R-2 表格/布局回归 | 对比 PyPDF vs Docling，表格准确率验证 | 1.5d |
| R-3 测试 + 文档 | 解析测试 + 手册 | 1.5d |

### P2-B：分析层升级 Vanna（5d）

| 任务 | 输出/验收 | 工作量 |
| :--- | :--- | :--- |
| A-1 Vanna 集成 | `analysis_agent` NL2SQL 包裹 Vanna；向量库复用 Qdrant；LLM 经 LiteLLM | 2d |
| A-2 训练数据 | DDL/表结构/历史 SQL 向量化入库 | 1.5d |
| A-3 测试 + 文档 | NL2SQL 准确率测试 + 手册 | 1.5d |

### P3：观测持久化 Langfuse（6d，需升配）

| 任务 | 输出/验收 | 工作量 |
| :--- | :--- | :--- |
| O-1 升配评估 | ClickHouse 资源测算，决定升配/多机 | 1d |
| O-2 Langfuse 部署 | Docker/K8s，ClickHouse 后端 | 2d |
| O-3 LiteLLM callback 接入 | LLM 调用自动上报 Langfuse | 1d |
| O-4 observability_agent 对接 | 前端可选接 Langfuse UI；保留现内存方案作降级 | 1.5d |
| O-5 测试 + 文档 | 端到端追踪验证 + 手册 | 0.5d |

---

## 五、多租户与计费设计

V5 商业模式 = 年订阅，要求租户隔离。**LiteLLM 虚拟 Key 承载此层**：

```
租户(Tenant) ──┬── LiteLLM Virtual Key（模型白名单 + 预算 + RPM/TPM 限流）
               ├── 绑定增值模块授权（情报/营销/裁员/定价 开关）
               ├── 用量/成本记入租户账单（LiteLLM spend → 计费表）
               └── 超预算 → Cost Canary 降级（observability_agent budget 复用）
```

| 订阅层 | 模型权限 | 预算 | 模块授权 |
| :--- | :--- | :--- | :--- |
| 基础版 | 经济模型（mock/小模型） | 低 | ①②③ |
| 增值单模块 | +该模块所需模型 | 中 | +④ 或 ⑤ 或 ⑥ 或 ⑦ |
| 全家桶 | 全模型 | 高 | ①-⑦ |

> 计费表建议复用 observability_agent 的 cost_report，按租户聚合，导出对账。

---

## 六、资源与部署规划

| 形态 | 组件 | 适用 | 说明 |
| :--- | :--- | :--- | :--- |
| **单机版（现机）** | FDE + Dify + Qdrant + LiteLLM + RSSHub | P0/P1-RSSHub | 2C/11G 可承载，监控内存≤70% |
| **两机版** | + 独立 crawl worker（crawl4ai/Chromium） | P1-crawl4ai | 保护主服务，crawl4ai 重负载隔离 |
| **升配/多机版** | + Langfuse + ClickHouse | P3 | ClickHouse 重，需 ≥4C/16G 专用 |

**决策门**：每引入一个 Docker 组件先做内存压测，超 70% 阈值即触发拆机或延后。

---

## 七、风险与缓解

| 风险 | 影响 | 概率 | 缓解 |
| :--- | :--- | :--- | :--- |
| R1 LiteLLM 迁移破坏路由链 | 高 | 中 | 保留原适配器 fallback 层；灰度切换；全量回归门禁 |
| R2 Chromium 拖垮主机 | 高 | 中 | P1-I-3 先压测；超阈拆 worker 机 |
| R3 多组件运维复杂度↑ → 客户 TCO↑ | 中 | 高 | 一键 Compose + 升级脚本；重负载可卸载项文档化 |
| R4 AGPL 组件（FreshRSS/SearXNG）商业分发合规 | 中 | 低 | 仅内部用或法务确认；面向客户用 MIT/Apache 组件 |
| R5 OSS 同质化稀释差异化 | 中 | 中 | OSS 隐形化；护城河押垂直模块，不在网关/采集上做卖点 |
| R6 升配成本 | 中 | 中 | P3 非必需可延后；单机版先行满足多数客户 |

---

## 八、质量门禁与验收

每阶段必须通过：

1. `ruff check` 零告警 → `black` → `mypy --strict`
2. `pytest` 全量通过（基线 1227，新增不得回退）+ 该阶段新增测试
3. 前端 `npm run build` 通过
4. 线上部署后对应端点 200，30 分钟稳定
5. 阶段文档入库

**整体产品化验收**（全部阶段完成）：
- 干净主机 30 分钟一键起；
- 可创建租户、跑通基础版 ①②③ + 至少一个增值模块 ④-⑦；
- LiteLLM 记录该租户成本，可导出对账；
- 培训手册/题库/视频可交付客户。

---

## 九、里程碑与排期

| 里程碑 | 内容 | 累计工作量 |
| :--- | :--- | :--- |
| **M1 网关+打包基座** | P0-A + P0-B 完成 | 14d |
| **M2 情报可信+培训可交付** | P1-A + P1-B 完成 | 29d |
| **M3 RAG+分析质量抬升** | P2-A + P2-B 完成 | 39d |
| **M4 观测持久化（升配后）** | P3 完成 | 45d |

> 单人节奏约 9 周；P0 两项并行可压缩。P3 受升配节奏制约，可独立排期。

---

## 十、许可合规速查

| 组件 | 许可 | 商业分发 | 备注 |
| :--- | :--- | :--- | :--- |
| LiteLLM | MIT | ✅ 安全 | 网关核心 |
| crawl4ai | Apache-2.0 | ✅ 安全 | 采集 |
| RSSHub | MIT | ✅ 安全 | 采集 |
| changedetection.io | Apache-2.0 | ✅ 安全 | 变化监控（P1 备选） |
| Docling | Apache-2.0 | ✅ 安全 | 解析 |
| Vanna | MIT | ✅ 安全 | NL2SQL |
| Langfuse | MIT(core) | ✅ 安全 | 观测 |
| FreshRSS | AGPL-3.0 | ⚠️ 需法务 | 仅内部用 |
| SearXNG | AGPL-3.0 | ⚠️ 需法务 | 仅内部用 |

---

## 十一、与 V5 说明书的关系

- 本方案**不替代** V5 七步法，而是为其**补强基础设施底座 + 补齐产品化包装**。
- V5 纵向模块（④情报/⑤营销/⑥裁员/⑦定价）继续自建，是差异化护城河；本方案的横向 OSS 隐形支撑它们。
- P1-B 培训直接闭合 V5 审计 ❌ 缺口；P0-B 打包直接服务"可交付商业产品"定位。
- 推荐客户交付顺序不变（②→④→⑥→⑤→⑦），本方案在其下做地基。

---

*文档路径：docs/oss-optimization-roadmap.md（已升级为完备开发方案）*
*修订记录：v1.0 2026-07-13 合并路线图+战略评审，新增 WBS/多租户/资源规划/风险/里程碑*
