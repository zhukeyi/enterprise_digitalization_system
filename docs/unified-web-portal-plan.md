# FDE 统一 Web 门户 — 设计与开发计划

> 将分散的模块（A/D/E/F/G/H/J）集成为一个统一 BS 入口：一个网站、左侧菜单、多页面切换。

---

## 一、用户七个问题逐一回答

### A：智能路由网关 — 需要什么 Web 界面？

**现状**：`agents/router_agent/main.py` 已有 3 个 HTTP 端点（`/health`、`/v1/models`、`/v1/chat/completions`），但没有任何前端页面。

**需要做的界面**：

| 页面 | 功能 |
|------|------|
| 模型列表 | 展示可用模型（名称/提供商/计费方式/状态），可启用/停用 |
| 路由规则配置 | 按模型名称→适配器映射，按请求特征自动分流 |
| 调用统计面板 | 各模型调用次数、成功率、平均延迟、成本统计（按天/按模型） |
| Fallback 日志 | 查看自动故障转移链的触发记录 |

### D：IM 消息枢纽 — 怎么用？要不要界面？

**现状**：`agents/im_agent/` 有 3 个平台适配器（企微/飞书/钉钉），webhook 端点已写（`webhook_routes.py`）但**未挂载到 FastAPI app**。目前无法直接使用。

**怎么用**：

1. 把 `webhook_routes.py` 注册到主应用
2. 在各 IM 平台后台配置 webhook URL 指向 `https://你的域名/fde-api/im/webhook/wecom`
3. 用户在企业微信/飞书/钉钉里 @机器人 提问 → webhook 收到回调 → FDE Supervisor 处理 → 适配器把回答推回 IM 群

**需要做的界面**：

| 页面 | 功能 |
|------|------|
| 平台连接管理 | 展示企微/飞书/钉钉三平台连接状态（已连接/未连接） |
| Webhook 地址展示 | 展示各平台的 webhook URL，方便复制 |
| 消息日志 | 查看经 IM 进来的消息历史和响应记录 |
| 连接配置 | 配置各平台的 AppID/Secret/Token 等凭证 |

### E：桌面客户端 SDK — 是不是没做完？

**现状**：
- Python SDK（`models.py` + `auth.py` + `tests`）：**已完成**，包含 DesktopAuthManager、JWT 登录/刷新、16 个数据模型
- Tauri 桌面壳（`src-tauri/`）：**骨架阶段**，有 Vue 组件（FloatingWindow/LoginForm/ChatInput）但未构建、未打包

**结论**：Python SDK 能用，但 Tauri 桌面应用还不能打包发布。本计划**聚焦 Web 门户**，E 的界面需求由门户的 Web 页面覆盖（桌面客户端登录后也是调后端 API），桌面壳延后。

### F：数据情报 — 需要什么 Web 界面？

**现状**：`agents/data_agent/` 有完整的采集/清洗/ETL/报告/调度流水线，但全部通过 ToolRegistry 注册为工具（无独立 HTTP 端点），无前端页面。

**需要做的界面**：

| 页面 | 功能 |
|------|------|
| 数据源管理 | 添加/编辑 Web/RSS/API 数据源，配置采集频率 |
| 采集任务面板 | 手动触发/暂停/查看采集任务状态和日志 |
| 数据清洗规则 | 配置去重规则、字段映射、PII 脱敏策略 |
| 数据质量报告 | 查看清洗前后的数据质量评分 |
| 下游数据预览 | 浏览已入库的结构化数据（表格+JSONB 预览） |

### G：智能分析 — 是不是已经集成到 MapAI 了？

**现状**：G（`agents/analysis_agent/`）有 NL2SQL 引擎 + 安全校验 + 执行器，但**全部通过 ToolRegistry 注册为工具**。MapAI（模块L）是一个独立的地图空间分析模块（地理相关性 + AI 解读 + 图表），它**不包含**模块 G 的 NL2SQL 能力。

**结论**：G 和 L 是两个独立模块，G 的 NL2SQL 还没有任何前端页面。MapAI（L）已做前端。

**需要做的界面**（G 独立页面）：

| 页面 | 功能 |
|------|------|
| 数据库 Schema 浏览器 | 以树形展示所有表和列（复用 schema_extractor） |
| 自然语言查询框 | 输入自然语言 → 展示生成的 SQL + 执行结果表格 |
| SQL 编辑面板 | 直接写 SQL（自动安全校验），查看执行结果 |
| 查询图表可视化 | 结果以柱状/折线/饼图展示（复用 ECharts） |
| 查询历史 | 保存和回看历史查询 |

### H：治理与可观测 — 审计链路的 Web 界面

**现状**：
- DecisionChainLog 写入逻辑完整（`decision_log.py`）
- AuditLog 有 ORM 表结构但**无写入逻辑、无查询 API**
- **没有查询审计/决策链的任何 HTTP 端点**
- TracingMiddleware 生成 trace_id 但无 OTel 导出

**需要做的界面**：

| 页面 | 功能 |
|------|------|
| 决策链路追踪 | 按 trace_id / 用户 / 时间查看完整决策链（Supervisor 计划 → 各 Worker 执行 → 最终回答），可视化时间线 |
| 审计日志列表 | 按用户/操作类型/时间/IP 搜索所有审计事件 |
| 权限管理 | 用户列表、角色管理（RBAC）、资源级权限配置（ABAC） |
| 系统监控面板 | 调用量/成功率/延迟/P50/P99/错误率（对接 Prometheus metrics） |
| API Key 管理 | 创建/查看/吊销 API Key |

### J：人力资源 — 需要什么 Web 界面？

**现状**：`agents/hr_agent/` 有 6 个工具（画像/匹配/风险评估/冗余分析/裁员模拟/组织健康），全部通过 ToolRegistry 注册。有完整的 Mock 数据适配器。无前端。

**需要做的界面**：

| 页面 | 功能 |
|------|------|
| 员工画像搜索 | 按姓名/部门/技能搜索，展示员工综合画像 |
| 人岗匹配器 | 选岗位 → 查看候选人匹配度排名 |
| 风险评估 | 查看离职/绩效/合规等多维风险评估结果 |
| 组织健康仪表盘 | 部门级健康度指标（流失率/配置比/技能梯队） |
| 裁员模拟（防呆） | 选部门+人数 → 5 步防呆校验 → 模拟结果 |

---

## 二、统一 BS 入口设计方案

### 架构概览

```
┌──────────────────────────────────────────────────┐
│              FDE 统一 Web 门户                     │
│  ┌─────────┐  ┌─────────┐  ┌──────────────────┐  │
│  │ 左侧菜单  │  │ 顶栏     │  │  内容区（router-   │  │
│  │ 8 个导航  │  │ 用户/头像 │  │  view）          │  │
│  └─────────┘  └─────────┘  └──────────────────┘  │
│                                                    │
│  技术栈: Vue 3 + Vue Router + Pinia + 组件库       │
│  部署: 新前端项目 frontend/portal/                  │
│  访问: https://域名:8443/portal/                    │
└──────────────────────────────────────────────────┘
```

### 导航菜单设计（8 个一级菜单）

| # | 菜单名 | 路由 | 对应模块 | 说明 |
|---|--------|------|---------|------|
| 1 | **MapAI** | `/portal/map` | L（已有） | 地图空间分析（复用现有 MapAI 前端，iframe 嵌入或直接挂载） |
| 2 | **智能分析** | `/portal/analysis` | G（新建） | NL2SQL + Schema 浏览 + 图表 |
| 3 | **数据情报** | `/portal/data` | F（新建） | 数据源管理 + 采集任务 + 质量报告 |
| 4 | **AI 路由** | `/portal/router` | A（新建） | 模型管理 + 路由规则 + 调用统计 |
| 5 | **人力资源** | `/portal/hr` | J（新建） | 员工画像 + 匹配 + 风险 + 裁员模拟 |
| 6 | **消息枢纽** | `/portal/im` | D（新建） | IM 平台连接 + Webhook 配置 + 消息日志 |
| 7 | **审计与治理** | `/portal/governance` | H（新建） | 决策链路追踪 + 审计日志 + 权限管理 |
| 8 | **系统监控** | `/portal/monitor` | H（新建） | 调用量/延迟/成功率看板（Prometheus 数据） |

### 技术选型

| 层 | 选型 | 原因 |
|----|------|------|
| 前端框架 | Vue 3 + TypeScript | 与现有 MapAI 统一技术栈 |
| 路由 | Vue Router 4 | 多页面导航 |
| 状态管理 | Pinia（每个页面一个 store） | 轻量，MapAI 已用 |
| UI 组件库 | **Naive UI**（推荐）或 Element Plus | 企业后台管理风格组件（表格/表单/日期选择器/图表） |
| 图表 | ECharts 5（已在 MapAI 中复用） | 一致性 |
| 构建工具 | Vite（新项目 `frontend/portal/`） | 与 MapAI 相同 |
| API 基础 | 共享 `src/api/` 模块 | 封装的 fetch 封装（JWT 头注入） |
| 部署 | Vite build → dist → nginx 静态文件 | 同 MapAI 部署流程 |

### 项目结构

```
frontend/portal/
├── package.json
├── vite.config.ts          # base: '/portal/'
├── tsconfig.json
├── index.html
├── src/
│   ├── main.ts              # Vue app 入口
│   ├── App.vue              # 整体布局（侧栏 + 顶栏 + router-view）
│   ├── router/
│   │   └── index.ts         # 8 条路由
│   ├── stores/
│   │   ├── auth.ts          # 登录态（JWT token 管理）
│   │   └── ...              # 各页面独立 store
│   ├── api/
│   │   └── client.ts        # 封装 fetch（自动加 JWT、base URL、错误处理）
│   ├── views/               # 页面级组件
│   │   ├── MapAI.vue        # iframe 嵌入现有 MapAI
│   │   ├── Analysis.vue     # 智能分析
│   │   ├── DataIntel.vue    # 数据情报
│   │   ├── RouterMgmt.vue   # AI 路由管理
│   │   ├── HRDashboard.vue  # 人力资源
│   │   ├── IMMgmt.vue       # 消息枢纽
│   │   ├── Governance.vue   # 审计与治理
│   │   └── Monitor.vue      # 系统监控
│   ├── components/          # 可复用组件
│   │   ├── layout/          # Sidebar, Topbar
│   │   └── shared/          # DataTable, StatCard, etc.
│   └── style.css            # 全局样式
```

### 后端待补齐 API（✅=已有 ⭐=需新增）

| 模块 | 已有 | 需新增 |
|------|------|--------|
| A 路由网关 | `GET /health` `GET /v1/models` | ⭐ 新增 `GET/POST /api/router/rules` `GET /api/router/stats` |
| D 消息枢纽 | webhook 端点（已写未挂载） | ⭐ 挂载 webhook 路由 + 新增 `GET/POST /api/im/connections` `GET /api/im/logs` |
| E 桌面客户端 | Python SDK 完整 | 不需要 Web API（SDK 直接调后端） |
| F 数据情报 | 无 HTTP 端点 | ⭐ 新增 `GET/POST /api/data/sources` `GET/POST /api/data/tasks` `GET /api/data/quality` |
| G 智能分析 | 无 HTTP 端点 | ⭐ 新增 `POST /api/analysis/nl2sql` `GET /api/analysis/schema` `GET /api/analysis/history` |
| H 治理审计 | 7 个 auth 端点 + DecisionLog 写入 | ⭐ 新增 `GET /api/governance/decisions` `GET /api/governance/audit-logs` `GET/POST /api/governance/permissions` `GET /api/governance/stats` |
| J 人力资源 | 无 HTTP 端点 | ⭐ 新增 `POST /api/hr/profile` `POST /api/hr/match` `POST /api/hr/risk` `POST /api/hr/layoff` `GET /api/hr/org-health` |
| 监控 | 无 | ⭐ 在已有 `/metrics` (Prometheus) 上加查询前端 |

> **新增 API 设计原则**：每个模块的新增 API 都直接调用现有的 Worker/Tool 函数（如 `profiling.py` 的 `build_employee_profile()`），不做重复实现，只加一层薄的 HTTP 包装。

**示例** — F（数据情报）的新增端点映射到现有代码：

```python
# agents/data_agent/routes.py (新增文件)
from fastapi import APIRouter
from agents.data_agent.pipeline import run_pipeline
from agents.data_agent.models import DataSourceConfig

router = APIRouter(prefix="/api/data")

@router.post("/sources")
async def add_source(config: DataSourceConfig):
    # 直接调用已有的 pipeline 逻辑
    ...
```

---

## 三、开发计划（分阶段）

### 阶段 0：基础设施（3 天）

| 任务 | 内容 |
|------|------|
| 0.1 | 创建 `frontend/portal/` 项目骨架（Vue 3 + Vite + Vue Router + Pinia + Naive UI） |
| 0.2 | 实现 App.vue 整体布局：左侧菜单 + 顶栏（用户信息/退出） + `<router-view>` |
| 0.3 | API 客户端封装（`api/client.ts`：fetch + JWT 自动注入 + 错误统一处理） |
| 0.4 | 登录页面（复用现有 `/auth/login` 端点），JWT 存储到 localStorage |
| 0.5 | 路由守卫：未登录 → 跳转登录页 |

### 阶段 1：已有能力快速上线（5 天）

优先做**后端已有 API 而不需要新增后端接口**的页面：

| 任务 | 内容 | 后端依赖 |
|------|------|---------|
| 1.1 | **MapAI 嵌入页** | views/MapAI.vue：`<iframe>` 嵌入现有 MapAI（`/fde/`） | 无（已有） |
| 1.2 | **AI 路由管理页** | views/RouterMgmt.vue：模型列表（GET /v1/models）+ 调用统计 | ⭐ 新增 `/api/router/stats` |
| 1.3 | **审计与治理页（决策链追踪）** | views/Governance.vue：按 trace_id 查 DecisionChainLog，时间线展示 | ⭐ 新增 `/api/governance/decisions` |
| 1.4 | **系统监控页** | views/Monitor.vue：Prometheus 数据嵌入（调用量/延迟/成功率） | 挂载 Grafana iframe 或直读 Prometheus API |

### 阶段 2：后端补齐 API + 前端对接（12 天）

| 任务 | 模块 | 内容 |
|------|------|------|
| 2.1 | **F 数据情报** | 新增 `agents/data_agent/routes.py`（4 个端点），前端 DataIntel.vue 完整页面（数据源管理/采集任务/质量报告/数据预览） |
| 2.2 | **G 智能分析** | 新增 `agents/analysis_agent/routes.py`（4 个端点），前端 Analysis.vue（Schema 浏览器/NL 查询框/SQL 编辑器/图表结果/历史） |
| 2.3 | **J 人力资源** | 新增 `agents/hr_agent/routes.py`（5 个端点），前端 HRDashboard.vue（员工画像搜索/人岗匹配/风险评估/组织健康/裁员模拟） |
| 2.4 | **D 消息枢纽** | 将 `webhook_routes.py` 挂载到主 app；新增连接管理端点；前端 IMMgmt.vue（平台连接状态/webhook地址/消息日志） |
| 2.5 | **H 治理补全** | 补 AuditLog 写入 + 查询端点；权限管理页面（用户/角色/ABAC 配置） |

### 阶段 3：权限与打磨（4 天）

| 任务 | 内容 |
|------|------|
| 3.1 | 各页面套用 RBAC 权限控制（不同角色看到不同菜单/功能） |
| 3.2 | 响应式适配（移动端和窄屏在 12.9 英寸 iPad 上可用） |
| 3.3 | 统一错误处理/加载状态/空数据占位符 |
| 3.4 | 部署配置：nginx 添加 `/portal/` 路由，指向新前端 dist |

### 阶段 4：部署与文档（2 天）

| 任务 | 内容 |
|------|------|
| 4.1 | `frontend/portal/` 构建、打包、部署到服务器 |
| 4.2 | 编写用户使用手册 |
| 4.3 | 整体验收测试 |

---

## 四、总结：总工期与依赖

| 阶段 | 天数 | 依赖 |
|------|------|------|
| 阶段 0：基础设施 | 3d | 无 |
| 阶段 1：已有能力上线 | 5d | 阶段 0 |
| 阶段 2：后端补齐 + 前端 | 12d | 阶段 0（部分可与阶段 1 并行） |
| 阶段 3：权限与打磨 | 4d | 阶段 1+2 |
| 阶段 4：部署与文档 | 2d | 阶段 3 |
| **合计** | **26d** | |

> 阶段 1 与阶段 2 在完成阶段 0 后可部分并行（不同人做不同页面）。如果 solo，约 26 人天（5 周）。

### 与现有 MapAI 前端的共存关系

- MapAI 前端（`frontend/map-ai/`）**保持不变，继续独立维护**
- 新门户（`frontend/portal/`）通过 iframe 嵌入 MapAI
- 两套前端共享同一后端 API（JWT 认证互通）
- 构建和部署流程相同（`npm build → tar → scp → nginx`）

### 部署后的 nginx 路由

```
/fde/       → MapAI 独立应用（保持现有）
/portal/    → 新门户前端（新增）
/fde-api/   → 后端 API（共享）
/           → Dify（保持现有）
```