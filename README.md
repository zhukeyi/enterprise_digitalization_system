# FDE 企业级 AI 平台（enterprise_digitalization_system）

> 以 **LangGraph 多智能体编排** 为核心、**企业 RAG（Qdrant + ONNX 嵌入）** 为知识底座、**Dify** 为应用编排层的可私有化部署企业级 AI 数字化平台。已完成 V4 工程底座与 V5「企业落地七步法」商业化交付，并内置 **全系统运行监测平台**。

- 仓库：`git@github.com:zhukeyi/enterprise_digitalization_system.git`（分支 `main`，Trunk-Based 开发）
- 生产环境：`https://217.142.246.70:8443`（Oracle ARM 实例，自签名证书，systemd + nginx 托管）
- 代码规模：**16 个后端智能体 + 9 个前端门户**，全量测试 **1227 个**
- 商业交付审计达成度：**~95%**（V5 P0/P1/P2 共 10 项缺口已全部闭合）

---

## 一、项目现状（Current Status）

| 阶段 | 内容 | 状态 |
| :--- | :--- | :--- |
| **V4 工程底座** | Monorepo + 统一 API 网关 + LangGraph Supervisor-Worker + 企业 RAG + Dify 集成 + 桌面客户端 + IM 集成 + 评测/CI-CD | ✅ 已完成 |
| **V5 企业落地七步法** | 基础 → 交付（驾驶舱）→ 培训 → 情报 → 营销 → 裁员 → 定价，7 个 Web 门户 + 统一入口 | ✅ 已完成并部署 |
| **全系统运行监测平台** | Overview / Token Router / API 管理 / 服务健康 / RAG 检视 / Trace Viewer / 审计与告警 | ✅ 已完成并部署 |
| **V5 商业审计** | P0（Dify 工具/HR 裁员模拟器/情报 4 视图）+ P1（定价弹性竞品/Dify 工作流/培训交付物）+ P2（多语言/图表组件/测试） | ✅ 10/10 闭合，~95% |

> 设计文档详见 `docs/`：`v5-enterprise-delivery-plan.md`、`v5-audit-report.md`、`v5-observability-platform-design.md`、`v5-observability-dev-plan.md`。

---

## 二、快速访问（已部署门户）

所有前端为 SPA，后端 API 统一前缀 `/fde-api/`。

| 路径 | 门户 | 说明 |
| :--- | :--- | :--- |
| `/` | Dify 工作台 | 可视化工作流编排（独立 Dify 实例，172.18.0.12） |
| `/portal/` | 基础 RAG 门户 | 登录 / 文档上传 / 对话 / 驾驶舱 Dashboard |
| `/hub/` | 七步法统一入口 | 7 步法导航页 + 跨模块跳转 |
| `/intel/` | 情报收集增幅器 | 外部情报采集、趋势、报告、预警（GEO 视角） |
| `/hr/` | HR 智能评估 | 员工画像、人岗匹配、风险评估、裁员模拟器（含防呆 5 步） |
| `/pricing/` | 动态定价引擎 | 需求预测、弹性估计、竞品追踪、What-if 模拟、RL 定价 |
| `/marketing/` | GEO 营销投放 | 可见度追踪、内容 E-E-A-T 优化、广告多变体、ROI 预测 |
| `/obs/` | 全系统运行监测 | 7 个观测子模块的面板与审计/告警 |
| `/training/` | 培训与认证 | 三级认证体系（操作员/分析师/架构师）门户 |

> 自签名证书，浏览器访问时需手动信任。各门户 base path 与路径一致（如 `/obs/`、`/hr/`）。

---

## 三、架构总览

```
                          ┌─────────────────────────────────────────────┐
   浏览器 / 客户端  ─────▶ │  nginx (8443)                                │
                          │   /fde-api/ ─▶ backend:8000                  │
                          │   /obs/ /portal/ /hr/ ... ─▶ static dist     │
                          │   /         ─▶ Dify (172.18.0.12)            │
                          └───────────────────┬─────────────────────────┘
                                              │
                          ┌───────────────────▼─────────────────────────┐
                          │  FastAPI 网关 (router_agent)                 │
                          │   • 多模型适配器 (4) + 故障切换              │
                          │   • API Key 鉴权 + 限速 (auth_middleware)    │
                          │   • 指标/链路中间件 (OpenTelemetry)          │
                          └───────────────────┬─────────────────────────┘
                                              │
                          ┌───────────────────▼─────────────────────────┐
                          │  LangGraph Orchestrator (Supervisor-Worker)  │
                          │   Main Agent 只规划 → 结构化指令 → 后端执行   │
                          │   10 个 Worker：rag/hr/data/analysis/router/ │
                          │   governance/compliance/business/im/map      │
                          └───┬──────┬──────┬──────┬──────┬──────┬───────┘
                              │      │      │      │      │      │
                  ┌───────────┘      │      │      │      │      └───────────┐
                  ▼                  ▼      ▼      ▼      ▼                  ▼
            Qdrant(向量)      PostgreSQL/   Dify    外部API          观测环缓冲        桌面/IM
            +SQLite(元数据)    SQLite      编排    (百度/企微…)     (trace/audit/    适配器
                                                  (LLM网关)          token 环形缓冲)
```

**关键设计原则**

- **LLM 只规划，后端执行**：Main Agent 输出结构化指令（Pydantic），真实工具调用由后端确定性代码执行，杜绝提示词注入导致的越权。
- **权限硬过滤**：权限控制在后端实现，不经过 LLM。
- **防呆设计**：删除/重建索引/裁员提交/危险 SQL 等高风险操作均含确认、影响范围预览、回退机制。
- **本地优先**：PII 与私域数据组件本地部署；评测数据平面在客户侧。

---

## 四、智能体清单（16 个）

| 智能体 | 职责 | 关键能力 |
| :--- | :--- | :--- |
| `router_agent` | FastAPI 网关 | 4 模型适配器、路由策略、故障切换、防呆中间件 |
| `orchestrator` | LangGraph Supervisor | 任务拆解、Worker 调度、冲突裁决、结构化指令路由 |
| `rag_agent` | 企业 RAG 引擎 | Qdrant + HybridSearch + Reranker + QueryRewrite + ONNX 嵌入 |
| `ingestion_agent` | 文档入湖 | 多格式解析、三层归一化、parent-child chunking、入库/查询 |
| `analysis_agent` | 智能分析层 | NL2SQL 引擎（规则 + LLM fallback + MockExecutor）、Dashboard |
| `hr_agent` | HR 智能决策 | 员工画像、胜任力模型、人岗匹配、风险评估、裁员模拟、防呆 5 步 |
| `data_agent` | 数据情报服务 | 多源采集器（RSS/HTTP/API）、清洗、GEO Guard、推送 |
| `pricing_agent` | 动态定价引擎 | 需求预测、弹性估计、竞品追踪、规则/RL 优化、What-if、报告（numpy-only） |
| `marketing_agent` | GEO 营销投放 | 可见度追踪、内容 E-E-A-T 优化、广告多变体/A-B、ROI 预测（numpy-only） |
| `map_agent` | 地图 AI 分析 | 地图分析 API、解释器、langgraph 节点、标记 CRUD |
| `im_agent` | 统一消息枢纽 | IMWorker + 企微/飞书/钉钉适配器 Stub |
| `client_agent` | 桌面 AI 助手 | Desktop Client SDK（16 models、DesktopAuthManager） |
| `dify_bridge` | Dify 集成 | DifyBridge + `/dify/*` 路由 + OpenAPI spec（11 个 x-dify 工具） |
| `compliance_agent` | 合规 Worker | 合规检查节点 |
| `business_agent` | 业务系统 Worker | ERP/WMS/TMS 等业务系统对接 |
| `governance_agent` | 全栈治理 | 认证/权限/监控/审计/防呆组件 |
| `observability_agent` | 运行监测 | Overview/Token Router/API 管理/服务健康/RAG 检视/Trace/审计告警 |

---

## 五、前端门户清单（9 个）

| 门户 | 技术 | base path | 视图 |
| :--- | :--- | :--- | :--- |
| `portal` | Vue3+Vite+ECharts | `/portal/` | Login / Upload / Chat / Dashboard |
| `map-ai` | Vue3+MapboxGL+Tiptap+Pinia | — | 15 组件（已冻结，tag `archive/map-ai-stable`） |
| `intelligence-portal` | Vue3+Vite+ECharts（暗色霓虹） | `/intel/` | Dashboard / Source / Trend / Report / Alert |
| `hr-portal` | Vue3+Vite+ECharts（专业亮色） | `/hr/` | Dashboard / EmployeeList / EmployeeDetail / RedundancySimulator |
| `pricing-portal` | Vue3+Vite+ECharts（金融暗色） | `/pricing/` | Dashboard / Simulator / Strategy / Elasticity / Competitors |
| `marketing-portal` | Vue3+Vite+ECharts（营销科技暗色） | `/marketing/` | GEO Dashboard / Content Studio / Ad Manager / ROI Dashboard |
| `hub` | Vue3+Vite（纯静态） | `/hub/` | 七步法导航页（7 卡 + Dify 外链） |
| `training-portal` | Vue3+Vite（纯静态） | `/training/` | 培养目标 / 课程模块 / 认证路径 / 资料中心 |
| `observability-portal` | Vue3+Vite+ECharts（暗色） | `/obs/` | Overview / TokenRouter / ApiManagement / ServiceHealth / RagInspector / TraceViewer / AuditTrail+Alerts |

> 统一约定：所有门户 ECharts 固定 **5.6.0**；API `BASE` 指向 `/fde-api/api/<module>`。

---

## 六、V5 企业落地七步法

按「基础 → 交付 → 培训 → 情报 → 营销 → 裁员 → 定价」顺序交付，门户经 `/hub/` 统一串联：

1. **① 基础（信息化基建）**：V4 成果 —— 网关、RAG、LangGraph、Dify、门户。
2. **② 交付（驾驶舱）**：`/portal/dashboard` 统计文档量、切片数、类型分布、入库趋势。
3. **③ 培训（信息化培训班 + 考证）**：`/training/` 轻量门户 + `docs/training/manual.md`（三级手册）+ `docs/training/exam-bank.md`（17 题题库）。*视频课程待录制。*
4. **④ 情报（外部情报收集增幅器）**：`/intel/` 5 视图 + `data_agent` 采集/清洗/推送。
5. **⑤ 营销（GEO 投放）**：`/marketing/` + `marketing_agent`（numpy-only），可见度/内容/广告/ROI。
6. **⑥ 裁员（HR 模块 Web）**：`/hr/` + `hr_agent`，含裁员模拟器与防呆 5 步。
7. **⑦ 定价（动态定价引擎）**：`/pricing/` + `pricing_agent`（numpy-only，RL 策略梯度），需求/弹性/竞品/模拟。

> Dify 集成：`docs/fde-dify-openapi.yaml` v5.0.0 含 **11 个 x-dify 工具**；`docs/dify-workflows/` 提供 5 个可导入 DSL。

---

## 七、全系统运行监测平台（Observability）

对标业界三层架构 **Langfuse（LLM 追踪）+ Portkey/LiteLLM（网关成本）+ Datrafana（基础设施 APM）**，以 OpenTelemetry 为粘合层；落地五大企业模式：**Cost Canary / Drift Detector / Compliance Checkpoint / Human Escalation Tracker / Multi-Agent Debugger**。

**7 个子模块**

| 子模块 | 能力 |
| :--- | :--- |
| Overview Dashboard | 平台总览指标聚合 |
| Token Router Monitor | 用量/成本/路由分布、Cost Canary 日预算（80% 预警 / 100% 超限 + 模型降级） |
| API Management | API Key CRUD（SHA-256）+ token-bucket 限速 + 外部 API 注册表（9 个） |
| Service Health | 三级探活 `/healthz` `/readyz` `/livez` + 组件健康 |
| RAG Inspector | 切片浏览/向量预览/重索引/删除/检索回放（DB 不可用时优雅降级） |
| Trace Viewer | span 瀑布图 + P50/P95/P99 + error_rate + hot-paths |
| Audit Trail + Alerting | 审计日志（CSV 导出）+ 4 默认告警规则 + 漂移检测（滚动基线 ≥50% 变化标记） |

**部署要点**

- 单实例采用 **内存环形缓冲**（trace 20k / audit 50k / token 50k），避免引入 Alembic 迁移；如需重启后历史可追溯可升级为 SQLite/Postgres 持久化。
- 测试：observability 65 + router 集成覆盖，共 **71 个**专项测试，ruff 零告警。
- 设计文档：`docs/v5-observability-platform-design.md`、`docs/v5-observability-dev-plan.md`（5 Phase × 27 Task）。

---

## 八、技术栈（实际落地）

| 层级 | 组件 | 选型 / 说明 |
| :--- | :--- | :--- |
| 后端框架 | Python 3.11+ / FastAPI | 统一 API 风格，异步 |
| 多智能体编排 | LangGraph | Supervisor-Worker，结构化指令路由 |
| RAG 向量库 | Qdrant | 元数据过滤；Docker 容器 :6333 |
| RAG 嵌入 | BGE ONNX INT8（24MB） | `FDE_EMBEDDING_BACKEND=onnx`，`BAAI/bge-small-zh-v1.5` |
| 元数据底座 | PostgreSQL / SQLite 兜底 | 服务器未装 Postgres，MVS 用 SQLite（`DATABASE_URL` 注入） |
| 应用编排 | Dify | 独立实例，注册为 Custom Tool（`fde_data_tool`） |
| 前端 | Vue 3 + Vite + ECharts 5.6 | 多主题暗/亮色门户；map-ai 用 Mapbox GL + Tiptap |
| 科学计算 | numpy-only（pricing/marketing） | 服务器无 pandas/xgboost/prophet；RL 用策略梯度/PPO 风格 |
| 认证 | bcrypt（4.0–5.0） | `FDE_ENABLE_AUTH` 开关（默认关闭） |
| 观测 | 内存环缓冲 + Prometheus/Grafana | docker-compose 可选启用 |
| 部署 | systemd + nginx + Docker | 单台 Oracle ARM（2C/11G/96G），非 K8s |
| 代码质量 | ruff → black → mypy(strict) | Conventional Commits；pytest + coverage |

> **与原 v2.0 规划的主要偏差**（见附录）：RAGFlow → Qdrant + 自研解析/检索；Kubernetes → 单主机 systemd；pandas/scipy → 部分 agent numpy-only。偏差源于服务器资源约束与交付节奏，功能等价或更强。

---

## 九、本地开发

```bash
# 1. 后端（Python 3.11+）
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # 按需填写模型/百度地图 AK/数据库等
pytest                         # 全量 1227 个测试

# 2. 前端（以某个门户为例，Node 20+）
cd frontend/observability-portal
npm install && npm run dev     # 默认 http://localhost:5173，base /obs/

# 3. 启动后端
uvicorn router_agent.main:app --host 0.0.0.0 --port 8000
```

关键环境变量：`.env.example` 含 `FDE_RAG_EMBEDING_MODEL`（注意拼写，历史遗留）、`FDE_EMBEDDING_BACKEND`、`BAIDU_SERVER_AK` / `VITE_BAIDU_AK`、`FDE_ENABLE_AUTH`、`DATABASE_URL`。

---

## 十、部署（生产）

部署拓扑（宿主机 systemd nginx，端口 8443）：

```
/            → Dify (172.18.0.12)
/fde-api/     → proxy_pass 127.0.0.1:8000   (FastAPI 后端)
/portal/ /obs/ /hr/ /pricing/ /marketing/ /intel/ /hub/ /training/
             → alias 各 frontend/dist (SPA fallback → index.html)
```

标准发布流程：

```bash
# 后端
git push origin main
ssh -i ~/ssh/arm.key ubuntu@217.142.246.70 \
  "cd ~/fde-ai-platform && git pull && sudo systemctl restart fde-backend"

# 前端（示例：observability-portal）
cd frontend/observability-portal && npm run build
tar czf obs.tar.gz -C dist .
scp -i ~/ssh/arm.key obs.tar.gz ubuntu@217.142.246.70:~/fde-ai-platform/frontend/observability-portal/
ssh -i ~/ssh/arm.key ubuntu@217.142.246.70 \
  "cd ~/fde-ai-platform/frontend/observability-portal && rm -rf dist && mkdir dist && tar xzf obs.tar.gz -C dist && sudo nginx -t && sudo systemctl reload nginx"
```

> 服务单元：`fde-backend.service`（WorkingDirectory `/home/ubuntu/fde-ai-platform`，venv `/home/ubuntu/fde-ai-platform/venv`）。Prometheus 告警规则见 `deploy/prometheus/alerts.yml`。

---

## 十一、测试与质量门禁

- **全量测试**：`pytest` 收集 **1227 个**用例（含 observability 专项 71 个）。
- **质量门禁**：`ruff check`（零告警）→ `black` → `mypy --strict` → `pytest` + coverage。
- **CI/CD**：`.github/` 流水线 + Makefile 封装常用命令（见 `Makefile`）。
- **评测**：合规场景强制溯源引用（相似度低于阈值直接拒答）；结构化指令解析成功率 100%。

---

## 十二、文档索引

| 文档 | 内容 |
| :--- | :--- |
| `docs/v5-enterprise-delivery-plan.md` | V5 七步法交付计划 |
| `docs/v5-audit-report.md` | V5 商业交付审计（达成度 ~95%） |
| `docs/v5-observability-platform-design.md` | 运行监测平台设计（三层架构 + 企业模式） |
| `docs/v5-observability-dev-plan.md` | 运行监测平台开发计划（5 Phase × 27 Task） |
| `docs/v5-rag-observability-research.md` | RAG 切片可观测性调研（对标 FastGPT） |
| `docs/fde-dify-openapi.yaml` | Dify 集成 OpenAPI（v5.0.0，11 个工具） |
| `docs/dify-workflows/` | 5 个可导入 DSL |
| `docs/training/manual.md` `docs/training/exam-bank.md` | 培训手册 + 题库 |
| `docs/retrospective-v4.md` | V4 复盘报告 |
| `AGENTS.md` | 智能体协作约定 |

---

## 附录：原始 v2.0 规划背景（历史参考）

> 以下为项目早期（v2.0）的总体规划，作为历史背景保留。**部分内容已被实际落地方案替代**（见第八节偏差说明），以本文前述「现状 / 架构 / 智能体 / 技术栈」为准。

### A. 规划模块列表（11 大模块，A–L）

| 编号 | 模块 | 部署形态 | 规划人天 |
| :--- | :--- | :--- | :--- |
| A | 智能路由网关 | 云端 SaaS | 37 |
| B | 企业 RAG 引擎 | 本地部署 | 53 |
| C | Dify 应用编排层 | 本地部署 | 20 |
| D | 统一消息枢纽 | 本地部署 | 27 |
| E | 桌面 AI 助手 | 本地安装 | 25 |
| F | 数据情报服务 | 云端 SaaS | 39 |
| G | 智能分析层 | 本地/云混合 | 26 |
| H | 全栈治理与可观测性 | 全平台贯穿 | 40 |
| I | 实施工具包 | — | 16 |
| J | 人力资源智能决策层 | 本地部署 | 51 |
| K | LangGraph 多智能体编排层 | 本地部署 | 35 |
| L | 地图 AI 分析模块 | 本地/云混合 | 42 |
| | **合计** | | **411（约 20.5 人月，含缓冲 ~27 人月）** |

### B. 子 Agent 职责矩阵（规划版，12 个）

| 子 Agent | 负责模块 | 核心任务数 |
| :--- | :--- | :--- |
| Orchestrator | 任务拆解/调度/集成测试/部署 | 跨全部 |
| Router Agent | 智能路由网关（A） | 4 |
| RAG Agent | RAG 引擎（B） | 10 |
| Dify Agent | 应用编排（C） | 6 |
| IM Agent | 统一消息枢纽（D） | 5 |
| Client Agent | 桌面 AI 助手（E） | 4 |
| Data Agent | 数据情报（F） | 6 |
| Analysis Agent | 智能分析（G） | 5 |
| Governance Agent | 全栈治理（H） | 9 |
| HR Agent | 人力资源决策（J） | 10 |
| LangGraph Agent | 编排层（K） | 10 |
| Map Agent | 地图 AI 分析（L） | 12 |

> 实际落地后新增 `ingestion_agent`、`pricing_agent`、`marketing_agent`、`observability_agent`、`dify_bridge`、`compliance_agent`、`business_agent`，共 **16 个**智能体。

### C. 里程碑（规划版，4 阶段 / 9 个月）

| 阶段 | 时间 | 核心任务 |
| :--- | :--- | :--- |
| M1 地基 | 第 1–3 月 | 基础设施 + RAG + Dify + LangGraph 框架 |
| M2 触点+智能体 | 第 4–5 月 | IM + 桌面客户端 + 合规/业务 Agent + 权限硬过滤 |
| M3 大脑+数据+地图 | 第 6–7 月 | 数据分析 + 数据情报 + HR 核心 + 地图 AI 分析 |
| M4 交付 | 第 8–9 月 | 裁员评估 + 防呆组件 + 全景看板 + 实施工具包 |

### D. 防呆机制清单（已落地）

文档删除（数量+影响范围+二次确认）、索引重建（输入 `CONFIRM`+预计耗时）、权限批量修改（diff 预览）、模型切换（影响提示+二次确认）、机器人开关（影响提示）、危险 SQL 拦截（无 WHERE 拦截）、数据导出（超阈值审批）、角色删除（关联用户数+二次确认）、**裁员方案提交（四步：预览→影响评估→合规检查→最终确认）**、结构化指令解析失败（fallback 自动触发）、地图分析提交（空实体校验/语音降级/权限校验）。

### E. 核心决策点

| 决策点 | 选择 | 理由 |
| :--- | :--- | :--- |
| RAG 底座 | Qdrant + 自研（规划为 RAGFlow） | 解析/检索可控，资源占用低 |
| 应用编排 | Dify | 可视化工作流、多模型网关 |
| 多智能体 | LangGraph Supervisor-Worker | 状态驱动、可中断恢复 |
| 输出控制 | `with_structured_output()` | 格式 100% 可解析 |
| 工具调用 | 后端代码执行 | LLM 只规划，防幻觉 |
| 权限控制 | 后端硬过滤 + 元数据注入 | 物理隔离，防注入 |
| 部署 | 单主机 systemd（规划为 K8s） | 资源约束下的务实选择 |

### F. 资源汇总（规划版）

开发周期 9 个月（4 里程碑）｜总工作量 ~411 人天（含缓冲 ~535）｜推荐团队 9 人（后端 4 / 前端 3 / 运维 1 / PM 1）｜子 Agent 16 个｜前端门户 9 个｜核心任务 79+ 个。

---

*最后更新：2026-07-13 — 补齐 V4/V5/Observability 实际交付状态与部署信息。*
