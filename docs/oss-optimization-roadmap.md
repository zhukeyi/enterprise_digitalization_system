# FDE 平台开源项目优化路线图

> 目标：以成熟开源项目逐模块强化现有系统，遵循"先补数据入口质量（最高 ROI），再做智能层，最后增强层"的优先级。所有候选均核实许可、星数与适配度。

生成时间：2026-07-13

---

## 〇、架构总览：开源项目如何拼装

```
                         ┌──────────────────────────────────────────────┐
   采集层（情报/RAG 入口） │  RSSHub(1000+源)  crawl4ai(LLM-ready 提取)     │
                         │  changedetection.io(变化监控)  FreshRSS(骨干) │
                         └───────────────┬──────────────────────────────┘
                                         │ webhook / API
                         ┌───────────────▼──────────────────────────────┐
   网关层                │  LiteLLM (统一 100+ 模型 OpenAI 接口/Key/成本) │
                         │  ↕ 取代 router_agent 自研 4 适配器            │
                         └───────────────┬──────────────────────────────┘
                                         │
                ┌────────────────────────┼─────────────────────────┐
                ▼                        ▼                         ▼
   ┌────────────────────┐   ┌─────────────────────┐   ┌────────────────────┐
   │ data_agent(情报)   │   │ ingestion_agent     │   │ analysis_agent     │
   │ + GEO Guard        │   │ + Docling(解析升级) │   │ + Vanna(NL2SQL升级)│
   └────────────────────┘   └─────────────────────┘   └────────────────────┘
                │                        │                         │
                └────────────┬───────────┴─────────────────────────┘
                             ▼
                ┌────────────────────────────────┐
   观测层        │ Langfuse (经 LiteLLM callback) │  ← 升级 observability_agent
                │ ClickHouse 后端 / OTel 原生    │     (现内存环缓冲单实例够用)
                └────────────────────────────────┘
```

**核心洞察**：LiteLLM 是粘合枢纽——统一模型接口、经 callback 自动喂 Langfuse 观测、与 observability_agent 的 token_tracker/cost 对齐；crawl4ai/RSSHub 喂 data_agent；Docling 喂 ingestion_agent；Vanna 升级 analysis_agent。生态自洽，无需重复造轮子。

---

## 一、情报模块（data_agent + intelligence-portal）—— 第一步

### 1.1 现状评估（已读代码）

`data_agent` 是完整 ETL：`BaseScraper` 抽象 → `HTTPScraper/RSSScraper/APIScraper` → `pipeline` 清洗 → `geo_guard`（GEO 污染/AI 生成/提示注入检测）→ `push_service`。设计扎实。

**短板**：
- `HTTPScraper` 用 stdlib `HTMLParser` 解析，仅抓 `article/.post/.item` 类标签，无 JS 渲染、无反爬、无结构化提取——复杂页面几乎抓不到东西。
- RSS 采集依赖源站原生 RSS；微博/知乎/B站/公众号等中文社交生态无 RSS，等于覆盖盲区。
- 无"变化监控"能力（跨次 diff、调度、状态），竞品页/价格变化只能靠定时全量重抓。
- 无统一 RSS 骨干，源管理偏弱。

### 1.2 changedetection.io + data_agent 方案评估

**结论：方向正确、是好的增量，但不是该模块最高杠杆项。**

- ✅ 补的正是 data_agent 缺的：状态化变化 diff + 调度 + 80+ 通知（含钉钉/企微，贴合 IM 栈）+ REST API。Flask+SQLite+Docker 轻量，契合单主机。
- ✅ Webhook out → data_agent 新增一个 ingest webhook 端点 → 进 `pipeline` → `intel` Alert 视图。契约干净，改动小。
- ⚠️ 增加一个需运维的组件（主机已跑 FDE 后端 + Dify + Qdrant + nginx）。
- ⚠️ 与 crawl4ai 职责需划清：changedetection.io = "X 何时变了"；crawl4ai = "X 的干净内容是什么"。互补非冗余。
- ⚠️ 仅当"竞品/价格/网页变化监控"是真实业务需求时才上；否则属过度建设。

### 1.3 情报模块优化分层（推荐顺序）

| 优先级 | 项目 | 许可/热度 | 作用 | 集成方式 |
| :--- | :--- | :--- | :--- | :--- |
| **P0** | **RSSHub** | MIT / 30k★ | 1000+ 路由，把微博/知乎/B站/公众号/Twitter/Reddit 等无 RSS 站点变 RSS | 自托管实例，data_agent 的 `RSSScraper` 直接订阅 RSSHub 路由 URL |
| **P0** | **crawl4ai** | Apache-2.0 / 67k★ | LLM-ready Markdown 提取、Playwright JS 渲染、反爬、结构化抽取 | 新增 `Crawl4AIScraper` 注册到 `ScraperRegistry`，替代/补强 `HTTPScraper` |
| **P1** | **changedetection.io** | Apache-2.0 / 28k★ | 竞品页/价格/内容变化监控 + 80 通知 | Webhook → data_agent 新增 `/api/intelligence/ingest` 端点 |
| **P2** | **FreshRSS** / **Miniflux** | AGPL / Apache | RSS 聚合骨干（OPML/调度/过滤/扩展） | 作 RSS 后端，data_agent 经其 REST API 取条目 |
| **P3** | **SearXNG** | AGPL-3.0 | 元搜索，广谱 web 采集 | JSON API 作为 API 源接入 `APIScraper` |

> 第一步只做 P0：RSSHub + crawl4ai。这两项直接解决"源覆盖盲区"和"提取质量差"两个根因，性价比远高于先上 changedetection.io。

---

## 二、网关模块（router_agent）—— 第二步（全系统最高杠杆）

| 项 | 内容 |
| :--- | :--- |
| 项目 | **LiteLLM**（BerriAI/litellm） |
| 许可/热度 | MIT / 18k★ / Docker 拉取 2.4 亿 |
| 现状 | router_agent 自研 4 模型适配器 + MockAdapter，token 计数靠估算，成本/路由/fallback 自建 |
| LiteLLM 提供 | 100+ 提供商统一 OpenAI 接口、虚拟 Key、按项目/用户成本追踪、自动 fallback/重试/负载均衡、guardrails、缓存 |
| 适配点 | **可替代自研 4 适配器**；observability_agent 的 token_tracker/budget 直接对接 LiteLLM 的成本追踪 |
| 风险 | 侵入 router_agent 核心链路，需充分回归测试；但 LiteLLM 兼容 OpenAI 客户端，业务侧改动小 |
| 部署 | Docker，`:4000` 端口，`config.yaml` 配模型列表 |

**为何是全系统最高杠杆**：网关是所有 LLM 调用咽喉。统一后，新增模型从"写适配器+改计费+改 fallback"变成"改一行 config"，且天然对接 Langfuse 观测。

---

## 三、解析与 RAG 模块（ingestion_agent + rag_agent）—— 第三步

| 优先级 | 项目 | 许可/热度 | 作用 | 集成方式 |
| :--- | :--- | :--- | :--- | :--- |
| **P0** | **Docling**（IBM） | Apache-2.0 / 15k★ | PDF/DOCX/PPTX 表格/布局/方程结构化解析，表格准确率 93.6% | ingestion_agent 解析层接 Docling `DocumentConverter`，输出 Markdown 入 chunking |
| P1 | **LightRAG** / **GraphRAG** | Apache/MIT | 关系型检索（实体关系图），补纯向量检索短板 | rag_agent 增 graph 检索分支，与 HybridSearch 并行召回 |
| P1 | **bge-reranker-v2-m3** | MIT | 比现 reranker 更强 | 替换 rag_agent reranker 模型 |

> 解析是 RAG 质量天花板——"解析错了，下游全是垃圾"。Docling 是当前最强免费 OSS 布局解析器，且与现有 ONNX 嵌入流程正交。

---

## 四、分析模块（analysis_agent）—— 第四步

| 项 | 内容 |
| :--- | :--- |
| 项目 | **Vanna**（vanna-ai/vanna） |
| 许可/热度 | MIT / 13.5k★ |
| 现状 | analysis_agent = 规则引擎 + LLM fallback + MockExecutor，无自学习、无 schema 向量化 |
| Vanna 提供 | RAG-for-SQL：把 DDL/表结构/历史 SQL/文档向量化检索作上下文；自学习（成功 SQL 自动入库）；支持 Qdrant/Chroma；SQL 本地执行不出数据 |
| 适配点 | 替换/包裹 analysis_agent 的 NL2SQL 引擎；向量库复用现有 Qdrant；LLM 经 LiteLLM |
| 风险 | 低——analysis_agent 已隔离为独立 Worker，替换内部实现不影响编排 |

---

## 五、观测模块（observability_agent）—— 第五步（按需）

| 项 | 内容 |
| :--- | :--- |
| 项目 | **Langfuse** |
| 许可/热度 | MIT（核心）/ 22k★ / 自托管 Docker/K8s |
| 现状 | observability_agent 用内存环缓冲（trace 20k/audit 50k/token 50k），单实例够用，重启丢历史 |
| Langfuse 提供 | 持久化 LLM 追踪/成本/评测/Prompt 管理；ClickHouse 后端；OTel 原生；100+ 集成（含 Dify/LiteLLM） |
| 适配点 | **不替换** observability_agent，而是经 LiteLLM callback 自动上报；observability_agent 前端可继续用，或对接 Langfuse UI |
| 何时上 | 当需要跨重启历史追溯、多实例、或 LLM-as-judge 评测时。当前单实例内存方案可继续用 |
| 风险 | ClickHouse 较重，单主机资源需评估（可先用 Docker 小规模） |

---

## 六、其余模块增强（第六步及以后）

| 模块 | 候选 | 适配点 | 优先级 |
| :--- | :--- | :--- | :--- |
| marketing_agent（GEO） | **SearXNG** + crawl4ai | GEO 可见度追踪（搜索排名）+ 内容研究素材抓取 | 中 |
| map_agent（地图） | **deck.gl** / **kepler.gl** | 更强地理可视化（现模块已冻结，待重启评估） | 低 |
| pricing_agent（定价） | statsmodels（若放宽 numpy-only）/ Optuna | 时序预测增强、超参优化 | 低（受服务器约束） |
| im_agent（IM） | — | 已有 3 适配器 Stub，按业务推进即可 | 按需 |
| client_agent（桌面） | — | Tauri 客户端已成形 | — |
| governance/compliance/business | — | Worker 性质，随编排增强自然受益 | — |

---

## 七、落地优先级与节奏建议

| 阶段 | 模块 | 动作 | 预期收益 |
| :--- | :--- | :--- | :--- |
| **Phase 1** | 情报 | RSSHub + crawl4ai 接入 data_agent | 源覆盖 +10x，提取质量质变 |
| **Phase 2** | 网关 | LiteLLM 替代自研适配器 | 模型扩展成本从天级降到分钟级，成本追踪自动化 |
| **Phase 3** | RAG | Docling 接入 ingestion_agent | 文档（尤其表格）解析准确率大幅提升 |
| **Phase 4** | 分析 | Vanna 升级 analysis_agent | NL2SQL 准确率与自学习闭环 |
| **Phase 5** | 观测 | Langfuse（按需） | 持久化追踪 + 评测闭环 |
| **Phase 6** | 增强 | SearXNG/deck.gl 等 | GEO/地图能力增强 |

### 决策原则

1. **先入口后智能**：采集/解析/网关质量决定一切下游上限，优先补。
2. **单主机资源约束**：每引入一个 Docker 组件评估内存（现 11G）；RSSHub/crawl4ai/changedetection.io/LiteLLM 都较轻，Langfuse(ClickHouse)最重，放最后。
3. **许可合规**：AGPL 项目（FreshRSS/SearXNG）若做商业分发需法务确认；MIT/Apache 无虞。
4. **不重复造轮子**：LiteLLM/Vanna/Docling 都是各自领域事实标准，自研替代是负 ROI。

---

## 附录：候选项目速查表

| 项目 | 模块 | 许可 | Stars | 一句话 |
| :--- | :--- | :--- | :--- | :--- |
| RSSHub | 情报 | MIT | 30k+ | 万物皆可 RSS，1000+ 路由 |
| crawl4ai | 情报/RAG | Apache-2.0 | 67k | LLM-ready 爬虫，#1 trending |
| changedetection.io | 情报 | Apache-2.0 | 28k | 网页变化监控 + 80 通知 |
| FreshRSS | 情报 | AGPL-3.0 | — | 自托管 RSS 骨干 |
| SearXNG | 情报/营销 | AGPL-3.0 | — | 自托管元搜索 |
| LiteLLM | 网关 | MIT | 18k | 100+ 模型统一 OpenAI 网关 |
| Docling | RAG | Apache-2.0 | 15k | IBM 文档布局解析（表格 93.6%） |
| LightRAG | RAG | Apache/MIT | — | 图+向量 RAG |
| Vanna | 分析 | MIT | 13.5k | RAG-for-SQL 自学习 |
| Langfuse | 观测 | MIT(core) | 22k | LLM 工程平台，ClickHouse+OTel |
| deck.gl | 地图 | MIT | — | 地理可视化 |
