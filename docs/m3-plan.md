# M3 详细拆分与执行计划

> 创建时间：2026-07-01  
> 里程碑：M3 — 大脑 + 数据 + 地图（第6-7月）  
> 计划总量：138 人天（含地图模块 42 人天）  
> 前置状态：M1-M2 全部完成，511 tests passed，commit 6a4f36f

---

## 一、M3 总览

| 维度 | 数据 |
|------|------|
| **任务数** | 13 个（M3-T1 ~ M3-T13） |
| **人天** | 138 人天 |
| **涉及 Agent** | Data, Analysis, HR, Map, LangGraph, Governance, Orchestrator |
| **新增 Agent** | 3 个从空壳到完整实现（data_agent, analysis_agent, hr_agent） |
| **现有基础** | map_agent 已有骨架（models.py + engine.py + routes.py + 6 tests），前端已有 Vue3 骨架 |
| **核心交付** | 数据采集 + NL2SQL + HR引擎 + 地图AI分析 + 评测体系 |

### 依赖关系图

```
                    M3-T6 (扩展Worker)
                   /        |          \
          M3-T1 (数据采集)  M3-T5 (HR引擎)  M3-T8~T12 (地图AI)
                   |              |              |
          M3-T2 (报告推送)  M3-T5依赖T6      T8~T12串行
                   |                             |
          M3-T3 (NL2SQL)                    M3-T13 (E2E)
                   |
          M3-T4 (Dashboard)
                   |
          M3-T7 (评测体系) ← 独立，可与任何模块并行
          M3-T13 (E2E) ← 最后执行，依赖全部
```

### 并行开发策略

| 并行组 | 任务 | 可并行原因 |
|--------|------|-----------|
| 组 A | M3-T1+T2 (Data Agent) | 独立模块，与 analysis/hr/map 无文件交叉 |
| 组 B | M3-T3+T4 (Analysis Agent) | 独立模块，依赖 M3-T6 的 Worker 注册 |
| 组 C | M3-T5 (HR Agent) | 独立模块，依赖 M3-T6 的 Worker 注册 |
| 组 D | M3-T8→T12 (Map Agent) | 前后端串行，但与其他组无交叉 |
| 组 E | M3-T7 (评测体系) | 完全独立，可与任何组并行 |
| 串行 | M3-T6 (扩展Worker) | 修改 orchestrator/workers.py，需在 T1/T3/T5 之后 |
| 串行 | M3-T13 (E2E) | 最后执行 |

---

## 二、任务详细拆分

### M3-T1: 多源爬虫 + 全球数据采集 + 清洗管道 + 分析流水线（18 人天）

**所属 Agent**：data_agent  
**前置状态**：空壳（仅 `__init__.py` + `tests/__init__.py`）  
**目标**：实现数据情报采集服务，支持多数据源接入、清洗、结构化输出

#### 子任务拆分

| 子任务 | 内容 | 人天 | 产出文件 |
|--------|------|------|---------|
| T1-1 | 数据源模型 + 采集配置 | 2 | `data_agent/models.py` — SourceConfig, CollectedItem, DataQualityReport |
| T1-2 | Web 爬虫引擎（HTTP + 解析） | 4 | `data_agent/scrapers/` — BaseScraper, HTTPScraper, HTMLParser |
| T1-3 | RSS Feed 采集器 | 2 | `data_agent/scrapers/rss_scraper.py` — feedparser 封装 |
| T1-4 | API 数据源适配器 | 2 | `data_agent/scrapers/api_scraper.py` — REST API 采集 |
| T1-5 | 数据清洗管道 | 3 | `data_agent/cleaning.py` — 去重/标准化/字段映射/PII脱敏 |
| T1-6 | 分析流水线（聚合/统计/趋势） | 3 | `data_agent/pipeline.py` — DataPipeline（extract→transform→load） |
| T1-7 | 工具注册 + 测试 | 2 | `data_agent/integration.py` + `tests/test_data.py` |

#### 技术决策

- 爬虫框架：`httpx`（async HTTP）+ `selectolax`（HTML 解析，比 BS4 快 10x）
- RSS：`feedparser` 库
- 清洗：复用 `shared/utils/validators.py` 的 `safe_filename` + 新增 PII 脱敏
- 输出：Pydantic `CollectedItem` 统一模型，写入 PostgreSQL（复用 governance 的 session）
- 不使用 Scrapy 框架（过重，我们只需轻量采集）

#### 注册工具（注册到 ToolRegistry）

| 工具名 | 参数 | 功能 |
|--------|------|------|
| `data_collect` | source_type, query, max_items | 从指定数据源采集数据 |
| `data_clean` | raw_items | 清洗原始数据（去重/标准化/脱敏） |
| `data_pipeline` | source_config, transform_config | 执行完整 ETL 流水线 |
| `data_quality_report` | dataset_id | 生成数据质量报告 |

---

### M3-T2: 报告模板引擎 + 定制化推送服务（8 人天）

**所属 Agent**：data_agent  
**前置**：M3-T1 完成  
**目标**：基于采集数据生成结构化报告，支持多渠道推送

#### 子任务拆分

| 子任务 | 内容 | 人天 | 产出文件 |
|--------|------|------|---------|
| T2-1 | 报告模板模型 + Jinja2 引擎 | 2 | `data_agent/report_models.py` — ReportTemplate, ReportInstance |
| T2-2 | 模板渲染器（Jinja2 + ECharts 图片） | 2 | `data_agent/report_renderer.py` — Jinja2 + matplotlib 图表 |
| T2-3 | 推送服务（邮件 + IM + Webhook） | 2 | `data_agent/push_service.py` — 复用 im_agent 适配器 |
| T2-4 | 定时任务调度 | 1 | `data_agent/scheduler.py` — APScheduler 轻量调度 |
| T2-5 | 测试 | 1 | `tests/test_report.py` |

#### 技术决策

- 模板引擎：Jinja2（Python 标准，支持复杂模板继承）
- 图表：matplotlib 生成 PNG 嵌入报告（不依赖前端 ECharts）
- 推送：复用 `im_agent/adapters/` 的 Webhook 模式
- 调度：APScheduler（轻量，不引入 Celery，Celery 在 M3-T11 地图模块用）

---

### M3-T3: 数据查询网关 + NL2SQL 引擎（10 人天）

**所属 Agent**：analysis_agent  
**前置状态**：空壳  
**目标**：自然语言转 SQL 查询，支持多数据源

#### 子任务拆分

| 子任务 | 内容 | 人天 | 产出文件 |
|--------|------|------|---------|
| T3-1 | 查询模型 + Schema 元数据 | 2 | `analysis_agent/models.py` — NL2SQLRequest, SQLResult, TableSchema |
| T3-2 | Schema 提取器（从 DB 读取表结构） | 2 | `analysis_agent/schema_extractor.py` — 读取 PostgreSQL information_schema |
| T3-3 | NL2SQL 引擎（规则 + LLM 混合） | 3 | `analysis_agent/nl2sql.py` — 规则优先 + LLM fallback |
| T3-4 | SQL 安全校验器（防呆） | 1 | `analysis_agent/sql_safety.py` — 拦截 DELETE/UPDATE/DROP 无 WHERE |
| T3-5 | 查询执行器 + 结果格式化 | 1 | `analysis_agent/executor.py` — asyncpg 执行 + Pydantic 格式化 |
| T3-6 | 测试 | 1 | `tests/test_analysis.py` |

#### 技术决策

- NL2SQL 策略：**规则优先**（关键词映射表名/字段名）→ **LLM fallback**（复杂查询走路由网关）
- SQL 安全：拦截 `DELETE/UPDATE/DROP/TRUNCATE` 无 WHERE 子句（防呆设计）
- 执行：`asyncpg`（async PostgreSQL driver，复用 governance 的 DB session）
- 只读模式：默认 `READ_ONLY=1`，所有查询走只读事务

#### 注册工具

| 工具名 | 参数 | 功能 |
|--------|------|------|
| `nl2sql` | query, db_schema_id | 自然语言转 SQL 并执行 |
| `sql_execute` | sql, params | 执行预编译 SQL（需安全校验通过） |
| `schema_list` | db_schema_id | 列出可用表和字段 |
| `query_chart_data` | query, chart_type | 查询并返回图表所需格式数据 |

---

### M3-T4: Dashboard + 下钻分析 + 关联分析（10 人天）

**所属 Agent**：analysis_agent  
**前置**：M3-T3 完成  
**目标**：交互式可视化看板，支持下钻和跨维度关联

#### 子任务拆分

| 子任务 | 内容 | 人天 | 产出文件 |
|--------|------|------|---------|
| T4-1 | Dashboard 模型 + 布局配置 | 2 | `analysis_agent/dashboard_models.py` — DashboardConfig, Widget, Filter |
| T4-2 | 下钻分析引擎 | 3 | `analysis_agent/drill_down.py` — DrillDownEngine（层级递进 + 筛选传递） |
| T4-3 | 关联分析引擎 | 2 | `analysis_agent/correlation.py` — 跨表 JOIN 发现 + 统计关联 |
| T4-4 | 数据聚合服务 | 2 | `analysis_agent/aggregation.py` — GroupBy + Pivot + TimeSeries |
| T4-5 | 测试 | 1 | `tests/test_dashboard.py` |

---

### M3-T5: HR 系统对接 + 员工画像 + 人岗匹配 + 风险评估 + 冗余分析（33 人天）

**所属 Agent**：hr_agent  
**前置状态**：空壳（Worker 已存在于 orchestrator）  
**目标**：完整 HR 智能决策引擎

#### 子任务拆分

| 子任务 | 内容 | 人天 | 产出文件 |
|--------|------|------|---------|
| T5-1 | HR 数据模型 + ORM | 3 | `hr_agent/models.py` — Employee, Position, Competency, Performance |
| T5-2 | HR 系统数据源适配器 | 3 | `hr_agent/adapters/` — BaseHRAdapter, MockHRAdapter, WorkdayStub |
| T5-3 | 员工画像引擎 | 4 | `hr_agent/profiling.py` — EmployeeProfiler（技能矩阵 + 绩效趋势 + 稳定性评分） |
| T5-4 | 岗位胜任力模型 | 3 | `hr_agent/competency.py` — CompetencyModel（能力维度 + 权重 + 评分算法） |
| T5-5 | 人岗匹配引擎 | 4 | `hr_agent/matching.py` — PersonJobMatcher（余弦相似度 + 加权评分） |
| T5-6 | 风险评估引擎 | 4 | `hr_agent/risk_assessment.py` — RiskAssessor（离职风险 + 合规风险 + 绩效风险） |
| T5-7 | 冗余分析 + 组织优化建议 | 4 | `hr_agent/redundancy.py` — RedundancyAnalyzer（部门重叠度 + 岗位冗余度） |
| T5-8 | 防呆机制（裁员模拟 5 步校验） | 3 | `hr_agent/foolproof.py` — 复用 AntiFoolproofMiddleware + 裁员专属校验 |
| T5-9 | 工具注册 + Worker 集成 | 2 | `hr_agent/integration.py` — 注册到 ToolRegistry |
| T5-10 | 测试 | 3 | `tests/test_hr.py` — 30+ 测试 |

#### 注册工具

| 工具名 | 参数 | 功能 |
|--------|------|------|
| `hr_employee_profile` | employee_id | 生成员工画像 |
| `hr_person_job_match` | employee_id, position_id | 人岗匹配度评分 |
| `hr_risk_assessment` | employee_id, risk_types | 风险评估 |
| `hr_redundancy_analysis` | department_id | 部门冗余分析 |
| `hr_layoff_simulation` | plan_config | 裁员方案模拟（触发防呆） |
| `hr_org_health` | department_id | 组织健康度报告 |

#### 防呆设计（裁员场景）

```
裁员方案提交 → 5 步校验：
1. 可逆性检查：方案是否可撤销（试用期可撤销，正式员工不可逆）
2. 影响范围：显示影响人数 × 成本 + 法律风险
3. 通俗解释："本方案将影响 XX 部门 N 人，预计节省 M 万元/年"
4. 二次确认：需要输入 "CONFIRM_LAYOFF"
5. 快照：自动生成组织架构快照（可回滚参考）
```

---

### M3-T6: 扩展 Worker（另类数据 + HR）（6 人天）

**所属 Agent**：orchestrator (langgraph)  
**前置**：M3-T1, M3-T3, M3-T5 基本完成  
**目标**：将 data/analysis/hr 三个空壳 Worker 升级为完整实现

#### 子任务拆分

| 子任务 | 内容 | 人天 | 产出文件 |
|--------|------|------|---------|
| T6-1 | DataWorker 完整实现 + 工具注册 | 2 | `orchestrator/langgraph/workers.py` — DataWorker.execute() |
| T6-2 | AnalysisWorker 完整实现 + 工具注册 | 2 | `orchestrator/langgraph/workers.py` — AnalysisWorker.execute() |
| T6-3 | HRWorker 完整实现 + 工具注册 | 1 | `orchestrator/langgraph/workers.py` — HRWorker.execute() |
| T6-4 | Supervisor 路由关键词更新 | 1 | `orchestrator/langgraph/supervisor.py` — _mock_plan 新增 data/analysis/hr 关键词 |

#### 当前状态

- DataWorker / AnalysisWorker / HRWorker 已在 `workers.py` 中有类定义
- 但 `execute()` 未实现（继承 BaseWorker 默认 dispatch）
- 需要注册各 Agent 的工具到 ToolRegistry
- Supervisor `_mock_plan` 已有 data/hr/analysis 的基础关键词路由（M2-T8 修复时添加）

---

### M3-T7: 评测体系（Braintrust + Golden Dataset + Ragas）（8 人天）

**所属 Agent**：governance_agent  
**前置**：无（可与其他模块并行）  
**目标**：建立持续评测能力，CI 门禁集成

#### 子任务拆分

| 子任务 | 内容 | 人天 | 产出文件 |
|--------|------|------|---------|
| T7-1 | Golden Dataset 管理 | 2 | `governance_agent/eval/golden_dataset.py` — JSONL 格式测试集 |
| T7-2 | Ragas 集成（RAG 评测） | 2 | `governance_agent/eval/ragas_eval.py` — faithfulness + relevance + context_recall |
| T7-3 | Promptfoo CI 门禁 | 2 | `governance_agent/eval/promptfoo_runner.py` — CI 集成 |
| T7-4 | 评测报告生成 | 1 | `governance_agent/eval/report.py` — Markdown 评测报告 |
| T7-5 | 测试 | 1 | `tests/test_eval.py` |

#### 技术决策

- Braintrust：数据平面本地，评测 API 可选
- Ragas：本地运行，不依赖外部服务
- Golden Dataset：YAML/JSONL 格式，版本控制
- CI 集成：GitHub Actions 新增 `eval` job（非阻塞，生成报告）

---

### M3-T8: 全局状态管理 + 地图/弹窗/下钻"+"按钮 + UI反馈（7 人天）

**所属 Agent**：map_agent (前端)  
**前置状态**：前端已有 Vue3 + MapboxGL + Pinia 骨架  
**目标**：实现实体标记的完整前端交互

#### 子任务拆分

| 子任务 | 内容 | 人天 | 产出文件 |
|--------|------|------|---------|
| T8-1 | Pinia Store + LocalStorage 持久化 | 2 | `stores/analysis.ts` — markedEntities CRUD + 持久化 |
| T8-2 | 地图 Marker "+" 按钮 | 2 | `components/MapMarkerPlus.vue` — 点击写入 Store，防重复 |
| T8-3 | 监控弹窗/侧边栏 "+" 按钮 | 1 | `components/SidebarPlus.vue` |
| T8-4 | 下钻信息框 "+" 按钮 | 1 | `components/DrillDownPlus.vue` |
| T8-5 | UI 反馈 + 空状态 + Toast 提示 | 1 | `components/EntityToast.vue` |

---

### M3-T9: 分析收纳盒组件 + 拖拽排序 + 语音输入混合框 + 代词提示（10 人天）

**所属 Agent**：map_agent (前端)  
**前置**：M3-T8 完成  
**目标**：全局悬浮分析收纳盒 + 语音/文字混合输入

#### 子任务拆分

| 子任务 | 内容 | 人天 | 产出文件 |
|--------|------|------|---------|
| T9-1 | 分析收纳盒组件（悬浮 + 拖拽 + 最小化） | 4 | `components/AnalysisBox.vue` — 全局浮窗 + entity 卡片 |
| T9-2 | 实体卡片拖拽排序 | 2 | `components/EntityCard.vue` — vuedraggable 集成 |
| T9-3 | 语音 + 文字混合输入框 | 2 | `components/VoiceTextInput.vue` — Web Speech API + 降级 |
| T9-4 | 代词指代消解前端提示 | 1 | `components/PronounHint.vue` — "已选中{实体名}" |
| T9-5 | 分析提交 API + 加载状态 | 1 | `api/analysis.ts` — POST /api/analysis/correlate |

#### 技术决策

- ASR：优先 Web Speech API（浏览器原生，零依赖），降级为手动输入
- 拖拽：`vuedraggable`（Vue3 兼容版）
- 代词消解：前端展示提示，后端做实际替换

---

### M3-T10: 后端分析 API + LangGraph 节点扩展（7 人天）

**所属 Agent**：map_agent (后端)  
**前置**：M3-T9 前端框架完成  
**目标**：后端分析 API + LangGraph 节点扩展

#### 子任务拆分

| 子任务 | 内容 | 人天 | 产出文件 |
|--------|------|------|---------|
| T10-1 | 分析 API 设计 + 路由 | 2 | `map_agent/routes.py` — POST /api/analysis/correlate |
| T10-2 | LangGraph 节点：实体数据获取 | 2 | `map_agent/langgraph_nodes.py` — 从各数据源拉取时间序列 |
| T10-3 | LangGraph 节点：相关性计算 | 1 | 复用 `map_agent/engine.py` SpatialCorrelationEngine |
| T10-4 | LangGraph 节点：AI 解读 | 1 | `map_agent/interpreter.py` — LLM 生成自然语言解读 |
| T10-5 | 测试 | 1 | `tests/test_map_analysis.py` |

#### 当前状态

- `map_agent/engine.py` 已有 SpatialCorrelationEngine（ratio-based heuristic）
- `map_agent/models.py` 已有完整 Pydantic 模型
- `map_agent/routes.py` 已有基础路由
- 需要扩展为 LangGraph 节点 + 真实数据获取 + LLM 解读

---

### M3-T11: 异步任务 Celery + WebSocket 推送 + 防呆设计（7 人天）

**所属 Agent**：map_agent + orchestrator  
**前置**：M3-T10 完成  
**目标**：耗时分析异步化 + 结果实时推送

#### 子任务拆分

| 子任务 | 内容 | 人天 | 产出文件 |
|--------|------|------|---------|
| T11-1 | Celery 异步任务队列 | 2 | `map_agent/tasks.py` — @celery_app.task 分析任务 |
| T11-2 | WebSocket 推送通道 | 2 | `map_agent/websocket.py` — FastAPI WebSocket + 广播 |
| T11-3 | 前端 WebSocket 接收 | 1 | `stores/analysis.ts` — ws.onmessage → 更新状态 |
| T11-4 | 防呆设计（空实体 + 语音失败 + 权限） | 2 | `map_agent/foolproof.py` — 校验中间件 |

---

### M3-T12: 热力图 + 散点矩阵 + 时间序列 + 地图联动 + 结果看板（11 人天）

**所属 Agent**：map_agent (前端)  
**前置**：M3-T11 完成  
**目标**：完整可视化输出

#### 子任务拆分

| 子任务 | 内容 | 人天 | 产出文件 |
|--------|------|------|---------|
| T12-1 | 相关性热力图组件 | 3 | `components/HeatmapChart.vue` — ECharts heatmap |
| T12-2 | 散点矩阵图组件 | 2 | `components/ScatterMatrix.vue` — ECharts scatter |
| T12-3 | 时间序列图组件 | 2 | `components/TimeSeriesChart.vue` — ECharts line |
| T12-4 | 地图联动高亮（flyTo + 图层） | 2 | `components/MapHighlight.vue` — Mapbox flyTo + 高亮 |
| T12-5 | 分析结果看板整合 | 2 | `views/AnalysisResult.vue` — 图表 + AI 解读整合 |

---

### M3-T13: 端到端集成测试（3 人天）

**所属 Agent**：orchestrator  
**前置**：M3-T1~T12 全部完成  
**目标**：M3 全链路 E2E 测试

#### 子任务拆分

| 子任务 | 内容 | 人天 | 产出文件 |
|--------|------|------|---------|
| T13-1 | 多模块协作 E2E（data→analysis→hr） | 1 | `tests/test_m3_e2e.py` |
| T13-2 | 地图分析全链路 E2E（标记→提交→分析→推送） | 1 | `tests/test_map_e2e.py` |
| T13-3 | 质量门禁验证 + 回归 | 1 | 全量 pytest + ruff + mypy + black |

---

## 三、执行顺序与排期

### 推荐执行顺序（4 个 Sprint）

```
Sprint 1 (并行启动 4 组):
├── 组A: M3-T1 (数据采集, 18d) ← 辅助 Agent
├── 组C: M3-T5 (HR引擎, 33d) ← 主 Agent
├── 组E: M3-T7 (评测体系, 8d) ← 辅助 Agent
└── 组D: M3-T8 (地图前端标记, 7d) ← 辅助 Agent

Sprint 2 (Sprint 1 部分完成后启动):
├── 组A: M3-T2 (报告推送, 8d) ← 依赖 T1 完成
├── 组B: M3-T3 (NL2SQL, 10d) ← 可独立启动
├── 组D: M3-T9 (收纳盒+语音, 10d) ← 依赖 T8 完成
└── 组C: M3-T5 继续

Sprint 3:
├── 组B: M3-T4 (Dashboard, 10d) ← 依赖 T3 完成
├── 组D: M3-T10 (后端API, 7d) + T11 (异步推送, 7d) ← 串行
├── M3-T6 (扩展Worker, 6d) ← 依赖 T1/T3/T5 基本完成 ← 主 Agent

Sprint 4 (收尾):
├── 组D: M3-T12 (可视化输出, 11d) ← 依赖 T11 完成
├── M3-T13 (E2E, 3d) ← 依赖全部 ← 主 Agent
```

### 关键路径

```
M3-T5 (HR, 33d) → M3-T6 (Worker, 6d) → M3-T13 (E2E, 3d) = 42d (最长路径)
M3-T8 (7d) → T9 (10d) → T10 (7d) → T11 (7d) → T12 (11d) → T13 (3d) = 45d (地图路径)
```

地图路径是关键路径（45 人天），建议优先启动 M3-T8。

---

## 四、M1-M2 遗留问题在 M3 中的处理

| 遗留问题 | M3 处理方式 | 对应任务 |
|----------|------------|---------|
| 可观测底座仅 30%（M1-T2） | M3-T7 评测体系同时接入 OTel exporter | M3-T7 |
| 3 个 Agent 空壳 | M3-T1/T3/T5 从头实现 | M3-T1/T3/T5 |
| IM 适配器全是 Stub | 不在 M3 范围，M4 对接 | — |
| Tauri 桌面客户端未开始 | 不在 M3 范围，M4 实现 | — |
| docker-compose 仅有 dev | 不在 M3 范围，M4 补充 | — |
| CI 缺 CD | 不在 M3 范围，M4 实现 | — |

---

## 五、质量门禁

每个子任务完成时必须通过：

```bash
make verify          # ruff + black --check + mypy
make test-cov        # pytest + coverage ≥ 模块平均值
```

M3 整体完成时额外要求：
- 总测试数 ≥ 700（当前 511 + M3 新增 ~200）
- 总覆盖率 ≥ 85%
- E2E 测试覆盖 M3 全链路（data→analysis→hr→map）
- 无 P0/P1 类型错误
- 前端 vue-tsc 0 errors

---

## 六、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| scipy 在 ARM 上编译问题 | 中 | T10 相关性计算 | 已有 ratio-based fallback，可降级 |
| NL2SQL 准确率不足 | 中 | T3 用户体验 | 规则优先 + LLM fallback + 用户可编辑 SQL |
| Celery + Redis 部署复杂度 | 低 | T11 异步任务 | 先用 BackgroundTasks 降级，Celery 作为优化 |
| ASR 浏览器兼容性 | 中 | T9 语音输入 | Web Speech API 降级为手动输入 |
| HR 数据源无真实 API | 高 | T5 无法端到端 | MockHRAdapter 提供完整模拟数据 |
| 前端 ECharts + Mapbox 联动复杂 | 中 | T12 可视化 | 分步实现：先独立图表，后联动 |
