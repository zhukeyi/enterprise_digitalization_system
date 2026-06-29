# v2.0 开发计划对比分析 & 推进路线图

> 对比：已完成 M1 (v1.0 计划) vs v2.0 完整整合版计划

## 一、已完成模块 → v2.0 映射

| 已完成 (v1.0 M1) | 映射到 v2.0 | 状态 | 备注 |
|:---|:---|:---|:---|
| Router Agent (网关+4适配器+路由+故障切换) | **M1-T3** 统一API网关 | ✅ 完成 | 与v2.0基本一致 |
| RAG Agent (Vector Store + Parser + Chunking + Embeddings + Hybrid Search) | **M1-T4 部分** RAGFlow 需要替换自建部分 | ⚠️ 部分 | RAGFlow 将替换自建文档解析/检索 |
| RAG Agent 自建 Qdrant 向量存储 | 保留，RAGFlow 底层可用 | ✅ 保留 | Qdrant v1.13.2 已运行 |
| Tests + CI/CD + Lint | M1-T1 / T8 | ✅ 完成 | — |
| 防呆中间件 (含中文关键词) | M1-T7 防呆组件基础 | ✅ 提前完成 | — |
| 服务器部署 (217.142.246.70) | 测试环境 | ✅ 运行中 | — |
| GitHub 仓库 | 代码管理 | ✅ | enterprise_digitalization_system |

## 二、v2.0 新增模块 & 已构建能力的差距

```
v2.0 总工作量: 411人天 (~20.5人月)
已 完 成 工 作:  ~45人天 (M1 Router + RAG + 防呆)
剩 余 工 作 量:  ~366人天 (~18人月)
```

### 关键差距分析

| v2.0 模块 | 变化 | 策略 |
|:---|:---|:---|
| **B - RAGFlow 引擎** | 自建 RAG → RAGFlow 底座 (53d) | 保留 Qdrant, 对接 RAGFlow 文档解析 + GraphRAG |
| **C - Dify 编排** | 全新 (20d) | 新增工作流可视化编排 |
| **K - LangGraph 多智能体** | LLM 规划 → 结构化指令路由 (35d) | Main Agent 只规划, 后端代码执行工具 |
| **L - 地图 AI 分析** | **全新** (42d) | 最复杂的全新模块, Mapbox + ECharts + ASR + 相关性计算 |
| **J - HR 决策层** | 之前仅规划 (51d) | 员工画像/人岗匹配/风险评估/裁员 |
| **D - IM 消息枢纽** | 待开发 (27d) | 企微/飞书/钉钉 |
| **E - 桌面助手** | 待开发 (25d) | Tauri 客户端 |
| **F - 数据情报** | 待开发 (39d) | 全球数据采集 |
| **G - 智能分析** | 待开发 (26d) | NL2SQL / Dashboard |
| **H - 治理** | 部分完成 (40d) | 防呆已完成, 缺认证/权限/审计 |
| **I - 实施工具** | 待开发 (16d) | Helm Charts / 部署工具 |

## 三、推进路线图 (重新排序 M1~M4)

基于「已完成的工作 + 新增模块」, 建议按以下顺序推进:

### 阶段 1: 补全 v2.0 M1 剩余 (~30人天)

已有 M1-T3 (router) 和部分 M1-T4 (rag) 完成, 需补:

| 优先级 | 任务 | 人天 | 说明 |
|:---|:---|:--|:---|
| 🔴 P0 | **LangGraph 框架搭建** (M1-T6) | 13 | Supervisor-Worker 模式, 全局 State, Main Agent 提示词 |
| 🟡 P1 | **RAGFlow 部署与对接** (M1-T4) | 26 | 替换自建文档解析, 保留 Qdrant/QCloud, 企业连接器 |
| 🟡 P1 | **Dify 部署 + RAGFlow 接入** (M1-T5) | 5 | 可视化工作流, 可作为后续 Agent 编排的后备 |
| 🟢 P2 | **可观测底座** (M1-T2) | 6 | Prometheus + Grafana + Langfuse |
| 🟢 P2 | **端到端集成测试** (M1-T8) | 3 | — |

### 阶段 2: M2 触点+智能体 (~65人天)

| 任务 | 人天 | 依赖 |
|:---|:--|:---|
| 统一认证+权限引擎 | 8 | LangGraph |
| 权限过滤检索中间件 | 8 | RAGFlow |
| **IM 消息枢纽** (企微/飞书/钉钉) | 15 | 认证 |
| **桌面 AI 助手** (Tauri) | 15 | 认证 |
| LangGraph 子 Agent Worker | 6 | M1 LangGraph |
| 冲突裁决 + Response Generator | 5 | Worker |
| Dify 工具节点集成 | 5 | Dify |

### 阶段 3: M3 数据+HR+地图 (~138人天)

| 优先级 | 模块 | 人天 |
|:---|:---|:--|
| 🔴 | **地图 AI 分析** (M3-T8~T12) | 42 |
| 🟡 | HR 决策层 (M3-T5) | 33 |
| 🟡 | 数据情报 (M3-T1/T2) | 26 |
| 🟡 | 智能分析 NL2SQL (M3-T3/T4) | 20 |
| 🟢 | LangGraph Worker 扩展 | 6 |
| 🟢 | 评测体系 | 8 |
| 🟢 | 集成测试 | 3 |

### 阶段 4: M4 交付 (~52人天)

交付与收尾工作, 裁掉/部署/文档/验收。

## 四、新增模块 L — 地图 AI 分析 详细拆解 (42天)

这是 v2.0 最复杂的全新模块, 需要 12 个子任务:

```
前端 (20d)                    后端 (14d)                基础设施 (8d)
 ┌─────────────────┐           ┌─────────────────┐      ┌─────────────────┐
 │ L1 全局状态 (2d) │           │ L11 API路由 (2d)│      │ L7 ASR集成 (2d) │
 │ L2 地图+按钮(3d) │           │ L12 数据获取(3d)│      │ L15 Celery  (2d) │
 │ L3 弹窗+按钮(2d) │           │ L13 相关性计算(3d)│    │ L16 WebSocket(2d) │
 │ L4 下钻+按钮(2d) │  ───────→ │ L14 AI解读  (2d)│      │ L21 防呆     (3d) │
 │ L5 收纳盒   (5d) │           │ L10 分析提交(2d)│      └─────────────────┘
 │ L6 拖拽排序 (2d) │           └─────────────────┘
 │ L8 语音输入 (2d) │
 │ L9 代词消解 (1d) │
 │ L17 热力图   (3d) │
 │ L18 散点矩阵 (2d) │
 │ L19 地图联动 (2d) │
 │ L20 结果看板 (3d) │
 └─────────────────┘
```

**关键技术挑战:**
- 代词指代消解: 语音输入 → 检测代词 → 查 AnalysisContext → 替换
- 时间序列对齐: 不同数据源粒度不同, 需重采样
- 地图联动: ECharts 图表 ↔ Mapbox 地图双向交互

## 五、LangGraph 多智能体设计 (35天)

这是架构的核心变化。旧架构中 LLM 直接调用工具, v2.0 改为 **LLM 只规划, 后端执行**。

```
用户请求
  ↓
Main Agent (Supervisor)
  ├─ 理解意图, 拆解子任务
  ├─ 输出 StructuredInstruction (JSON, pydantic)
  └─ 后端代码解析指令, 路由到 Worker
       ├─ Router Agent (已有)
       ├─ RAG Agent (已有, 需对接 RAGFlow)
       ├─ Map Agent (全新)
       ├─ HR Agent (全新)
       ├─ Data Agent (全新)
       └─ IM Agent (全新)
```

**Workflow 节点:**
1. `parse_intent` → 意图分类
2. `plan_tasks` → 拆解为 SubAgentTask[]
3. `execute_tasks` → 并行/串行执行 (后端代码)
4. `detect_conflicts` → 冲突检测
5. `resolve_conflicts` → 裁决
6. `generate_response` → 生成最终回复

## 六、下步行动建议

基于「最小可行迭代」原则, 优先推进:

### 立即开始 (本周)
1. **LangGraph 框架搭建 (M1-T6, 13d)** — 架构基础
   - 定义 `EnterpriseAgentState`
   - 实现 `StructuredInstruction` Pydantic Model
   - Supervisor 提示词模板
   - 基础 StateGraph 流程

2. **地图 AI 分析前端骨架 (L1~L4, 9d)** — 并行启动
   - Redux/Pinia 全局状态管理
   - 地图 Marker "+" 按钮
   - 弹窗/下钻信息框实体标记

### 第 2-3 周
3. **RAGFlow 部署与迁移** (M1-T4, 26d)
4. **Dify 部署** (M1-T5, 5d)
5. **地图分析后端 (L10~L14, 14d)**

### 第 4+ 周
6. HR 决策层 (J, 51d)
7. IM 消息枢纽 (D, 27d)
8. 其余模块按 M2→M3→M4 顺序

## 七、架构变化总结

| 维度 | v1.0 (已完成) | v2.0 (新计划) |
|:---|:---|:---|
| **RAG 引擎** | 自建文档解析 + Qdrant | RAGFlow + Qdrant |
| **应用编排** | 无 | Dify 可视化工作流 |
| **多智能体** | Router 单层路由 | LangGraph Supervisor-Worker |
| **LLM 角色** | 直接调用工具 | 只规划, 后端执行 |
| **新增模块** | — | 地图 AI (L), HR (J), IM (D), 桌面 (E), 数据 (F), 分析 (G) |
| **团队** | 1人 | 9人 (推荐) |
| **周期** | ~1月 (M1) | 9月 (M1~M4) |