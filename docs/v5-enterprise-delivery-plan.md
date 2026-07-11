# FDE V5 — 企业落地七步法 · 商业化交付计划

> **定位**：从"AI 平台"到"可交付的商业产品"
> **核心逻辑**：基础(1) → 交付(2) → 培训(3) → 情报(4) → 营销(5) → 裁员(6) → 定价(7)
> **销售策略**：1-3 是标配（基建+交付+培训），4-7 是增值模块（按需采购）

---

## 一、现有能力盘点

| 步骤 | 需要的能力 | 现状 | 缺口 |
|------|-----------|------|------|
| ① 基础 | Dify + FDE Backend + RAG + 文件入库 + Portal | ✅ 全部就绪 | 无 |
| ② 交付 | 定制 Dify 工作流 + 驾驶舱 + 自定义工具 | ✅ 工具已注册 | 驾驶舱前端待定制 |
| ③ 培训 | 说明书 + 视频 + 考证体系 | ❌ 无 | 全部待做（轻量） |
| ④ 情报 | 外部情报收集 + 炫酷 Web 界面 | ⚠️ 后端已有 data_agent | Web 前端待做 |
| ⑤ 营销 | GEO 投放 + AI 内容优化 | ❌ 无 | 全部待做 |
| ⑥ 裁员 | HR 智能评估 + Web 界面 | ⚠️ 后端已有 hr_agent | Web 前端待做 |
| ⑦ 定价 | 动态定价引擎 + 数据接入 | ❌ 无 | 全部待做 |

### 现有后端能力（已可用于 Dify 工具编排）

**data_agent（情报后端）**：
- 多源爬虫框架（RSS / HTTP / API，YAML 规则配置化）
- 全球数据源采集（新闻/社交媒体/行业论坛/政府数据，中/英/日/韩）
- 数据清洗管道（去重 → 实体识别 → 分类打标 → 结构化）
- 自动分析流水线（摘要/情感分析/趋势识别/关键事件提取）
- 报告模板引擎 + 定制化推送服务
- GeoGuard 地理围栏合规

**hr_agent（裁员后端）**：
- 员工画像（EmployeeProfile）+ 能力模型（CompetencyModel）
- 人岗匹配引擎（PersonJobMatching）
- 风险评估（RiskAssessment）
- 裁员模拟器（RedundancySimulator）+ 防呆 5 步校验
- 支持可逆性检查 + 影响范围 + 通俗解释 + 二次确认 + 快照

---

## 二、七步法详细计划

### 步骤 ① 基础 — 企业信息化基建 ✅ 已完成

**交付物**：
- Dify 平台（工作流编排 + 知识库 + 对话界面）
- FDE Backend（FastAPI + LangGraph 10 Workers）
- RAG 引擎（Qdrant + BGE-M3 + FTS5 混合检索）
- 文件入库（xlsx/csv/pdf/docx/pptx → 解析 → 归一化 → 向量化）
- Portal 门户（上传 + 对话）

**客户感知**：打开浏览器就能用，上传文件就能问

---

### 步骤 ② 交付 — 定制版 Dify 工作流 + 驾驶舱

**已有**：FDE 自定义工具已注册到 Dify（ask_data / upload_file / get_task_status）

**待做**：

| 任务 | 说明 | 工作量 |
|------|------|--------|
| 定制 Dify 工作流模板 | 按客户行业预配 3-5 个工作流（如"合同分析"、"数据问答"、"报告生成"） | 2 天/行业 |
| 驾驶舱前端 | 复用 Portal 框架，增加 Dashboard 看板（ECharts 已有组件） | 5 天 |
| 业务 Skill/Agent 定制 | 按客户需求开发专用工具，注册到 Dify | 2 天/skill |

**驾驶舱设计**：
- 基于 `frontend/portal/` 扩展，新增 DashboardView
- 复用 M3-T12 已有的 5 个 ECharts 组件（TimeSeriesChart / ScatterMatrix / HeatmapChart）
- 布局：顶部 KPI 卡片 + 中间图表区 + 底部数据表

---

### 步骤 ③ 培训 — 信息化培训班 + 考证

**交付物**：

| 材料 | 说明 | 工作量 |
|------|------|--------|
| 用户手册 | Dify 使用 + FDE Portal 使用 + 工具调用说明 | 3 天 |
| 视频教程 | 录屏 5-10 个短视频（每个 3-5 分钟） | 5 天 |
| 考证题库 | 30-50 道选择题 + 实操题 | 3 天 |
| 培训 PPT | 1 天课程 + 0.5 天实操 | 2 天 |

**考证体系**：
- 初级：FDE 平台操作员（会用工具、能跑工作流）
- 中级：FDE 工作流设计师（能编排工作流、能配置工具）
- 高级：FDE AI 架构师（能开发自定义工具、能调优 RAG）

> 这一步后续再细化，当前先出框架。

---

### 步骤 ④ 情报 — 外部情报收集增幅器（增值服务）

**后端**：✅ data_agent 已完成（爬虫 + 清洗 + 分析 + 报告 + 推送）

**前端**：❌ 需要做一个炫酷的 Web 界面

**设计方案**：

```
intelligence-portal/
├── src/
│   ├── views/
│   │   ├── DashboardView.vue      # 情报总览看板（世界地图 + 热力图）
│   │   ├── SourceView.vue          # 数据源管理（CRUD 爬虫规则）
│   │   ├── TrendView.vue           # 趋势分析（时间线 + 关键事件）
│   │   ├── ReportView.vue          # 情报报告（模板渲染 + 导出 PDF）
│   │   └── AlertView.vue           # 预警管理（关键词触发 + 推送配置）
│   ├── components/
│   │   ├── WorldHeatmap.vue        # 全球热力图（MapboxGL 复用）
│   │   ├── TimelineFlow.vue        # 时间线流（垂直滚动动画）
│   │   ├── SentimentGauge.vue      # 情感分析仪表盘
│   │   └── KeywordCloud.vue        # 关键词云（动态权重）
│   └── stores/
│       └── intelligence.ts         # Pinia store
```

**炫酷点**：
- 深色主题 + 霓虹色高亮
- 全球地图热力动画（数据源实时闪烁）
- 情报流时间线（垂直滚动 + 淡入动画）
- 情感分析仪表盘（正向/负向指针）
- AI 摘要卡片（自动生成 + 打字机效果）

**开发计划**：

| 阶段 | 任务 | 工作量 |
|------|------|--------|
| P1 | 基础框架 + 总览看板 + 数据源管理 | 5 天 |
| P2 | 趋势分析 + 情报报告 + 预警管理 | 5 天 |
| P3 | 炫酷动效 + 地图动画 + 打字机 | 3 天 |
| 合计 | | **13 天** |

**技术栈**：Vue3 + MapboxGL（复用 map-ai 经验） + ECharts + TailwindCSS + GSAP（动画）

---

### 步骤 ⑤ 营销 — GEO 投放（增值服务）

**现状**：❌ 无任何模块

**开源方案调研结果**：

| 项目 | 类型 | 说明 | 可用性 |
|------|------|------|--------|
| GEOVisibilityTool | 可见度测量 | 测品牌在 AI 搜索中的可见度，6 模块端到端 | ⭐⭐⭐ 可参考 |
| Toprank | 全栈 GEO+SEO+ADS | Claude Code Skills，3 模块覆盖全周期 | ⭐⭐⭐ 可集成 |
| GEOFlow | 内容生产系统 | GEO/SEO 内容自动化，多模型 + 任务调度 | ⭐⭐ 需适配 |
| Geoify | GEO 优化工具 | 内容优化让 AI 引擎引用，E-E-A-T 评分 | ⭐⭐ CLI 工具 |
| gego | GEO Tracker | 多 LLM 关键词追踪，Go+MongoDB | ⭐⭐ 需改造 |
| AI_Advertisement-Optz_Agent | 广告优化 | FastAPI + 多变体 + 质量评分 + 反馈循环 | ⭐⭐⭐ 可参考 |

**推荐方案**：自建 + 集成 Toprank Skills

**FDE 营销模块架构**：

```
marketing_agent/
├── geo/                    # GEO 生成式引擎优化
│   ├── visibility_tracker.py   # 品牌在 AI 搜索中的可见度追踪
│   ├── content_optimizer.py    # 内容优化（让 AI 引擎引用）
│   └── keyword_strategy.py     # 关键词策略
├── ads/                    # 广告投放优化
│   ├── variant_generator.py    # AI 多变体广告文案生成
│   ├── ab_tester.py            # A/B 测试自动化
│   └── budget_allocator.py     # 跨平台预算智能分配
├── content/                # 内容生产
│   ├── seo_writer.py           # SEO 文章生成
│   ├── geo_writer.py           # GEO 内容生成（结构化投喂）
│   └── multilingual.py         # 多语言文案（Qwen 适配器）
└── analytics/              # 效果分析
    ├── roi_predictor.py        # ROI 预测
    └── performance_tracker.py  # 多平台效果追踪
```

**Web 界面设计**：

```
marketing-portal/
├── views/
│   ├── GEODashboard.vue       # GEO 可见度总览
│   ├── ContentStudio.vue       # 内容生产工作室
│   ├── AdManager.vue           # 广告投放管理
│   └── ROIDashboard.vue        # ROI 看板
```

**开发计划**：

| 阶段 | 任务 | 工作量 |
|------|------|--------|
| P1 | GEO 可见度追踪 + 内容优化引擎 | 8 天 |
| P2 | 广告多变体生成 + A/B 测试 | 5 天 |
| P3 | 营销 Web 界面 | 7 天 |
| P4 | ROI 预测 + 效果分析 | 5 天 |
| 合计 | | **25 天** |

**技术选型**：
- GEO 核心：参考 GEOVisibilityTool 的 probe.py 方法（零依赖）
- 内容生成：复用 FDE 的 LLM 路由网关（4 模型适配器）
- 广告优化：参考 AI_Advertisement-Optz_Agent 的多变体 + 质量评分
- Web：Vue3 + ECharts

---

### 步骤 ⑥ 裁员 — AI 替代能力评估（增值服务）

**后端**：✅ hr_agent 已完成（画像 + 匹配 + 风险 + 裁员模拟 + 防呆 5 步）

**前端**：❌ 需要做 Web 界面

**设计方案**：

```
hr-portal/
├── views/
│   ├── EmployeeProfileView.vue    # 员工画像看板
│   ├── CompetencyMatrixView.vue   # 能力矩阵（热力图）
│   ├── RedundancySimulatorView.vue # 裁员模拟器
│   ├── RiskAssessmentView.vue     # 风险评估看板
│   └── AIReplacementView.vue      # AI 替代评估
├── components/
│   ├── OrgTree.vue                # 组织架构树
│   ├── SkillRadar.vue             # 技能雷达图
│   ├── ReplacementGauge.vue       # AI 替代度仪表盘
│   └── FoolproofDialog.vue        # 防呆确认弹窗（5 步）
```

**核心功能**：
1. **AI 替代评估**：按岗位分析哪些能力可被 AI 替代
   - 输入：岗位描述 + 工作流分析
   - 输出：替代度评分（0-100%）+ 可替代能力清单 + 不可替代能力清单
   - 模型：基于 O*NET 能力模型 + FDE 工具能力映射

2. **裁员模拟器**（已有后端，需前端）：
   - 选择部门/岗位 → 拖拽调整裁员比例
   - 实时计算：节省成本、风险等级、影响范围
   - 防呆 5 步：可逆性 → 影响范围 → 通俗解释 → 二次确认 → 快照

3. **保守评估模式**：
   - 只标注"AI 可以增强"而非"AI 可以替代"的岗位
   - 推荐"人机协作"方案而非直接裁员

**开发计划**：

| 阶段 | 任务 | 工作量 |
|------|------|--------|
| P1 | 员工画像 + 能力矩阵前端 | 5 天 |
| P2 | 裁员模拟器前端 + 防呆弹窗 | 5 天 |
| P3 | AI 替代评估引擎 | 8 天 |
| P4 | 风险评估看板 + 报告导出 | 4 天 |
| 合计 | | **22 天** |

---

### 步骤 ⑦ 定价 — AI 驱动的动态定价（增值服务）

**现状**：❌ 无任何模块

**开源方案调研结果**：

| 项目 | 技术 | 说明 | 可用性 |
|------|------|------|--------|
| PricePilot | XGBoost + PPO + Streamlit | 需求预测 + RL 定价 + 可解释性 | ⭐⭐⭐ 可参考 |
| Smart Dynamic Pricing | Dueling DQN + React + Flask | 仿真环境 + 客户分群 + 竞品 | ⭐⭐⭐ 可参考 |
| Grid Dynamics Pricing Kit | GCP Vertex AI + AutoML | 端到端定价管线，开源 | ⭐⭐ 需 GCP |
| warehouse-pricing-tui | SAC + Textual | 75K 产品 + 库存定价 | ⭐⭐ TUI 非企业 |

**推荐方案**：自建 FDE pricing_agent

**FDE 定价模块架构**：

```
pricing_agent/
├── models.py                    # 定价数据模型
├── demand_forecaster.py         # 需求预测（XGBoost / Prophet）
├── elasticity_estimator.py      # 价格弹性估算
├── competitor_tracker.py        # 竞品价格追踪
├── pricing_optimizer.py         # 定价优化引擎
│   ├── rule_based.py            # 规则引擎（成本加成 / 竞品跟随 / 心理定价）
│   └── rl_based.py              # 强化学习（PPO，参考 PricePilot）
├── data_connector.py            # 数据接入（ERP / POS / 电商 API）
├── report_generator.py          # 定价建议报告
└── routes.py                    # REST API
```

**Web 界面设计**：

```
pricing-portal/
├── views/
│   ├── PricingDashboard.vue     # 定价总览
│   ├── ElasticityView.vue       # 弹性分析看板
│   ├── CompetitorView.vue       # 竞品价格监控
│   ├── SimulatorView.vue        # 定价模拟器（What-if 分析）
│   └── StrategyView.vue         # 定价策略配置
```

**核心功能**：
1. **需求预测**：历史销售数据 + 季节性 + 趋势 → 预测未来需求
2. **弹性估算**：价格变动 → 需求变动 → 弹性系数
3. **定价优化**：
   - 规则引擎：成本加成、竞品跟随、心理定价、阶梯定价
   - RL 引擎：PPO 模型学习最优定价策略（参考 PricePilot）
4. **What-if 模拟**：调整价格 → 预测收入/利润/销量变化
5. **竞品监控**：自动抓取竞品价格（复用 data_agent 爬虫）

**开发计划**：

| 阶段 | 任务 | 工作量 |
|------|------|--------|
| P1 | 数据模型 + 需求预测 + 弹性估算 | 8 天 |
| P2 | 定价优化引擎（规则 + RL） | 8 天 |
| P3 | 竞品监控 + 数据接入 | 5 天 |
| P4 | 定价 Web 界面 | 7 天 |
| P5 | What-if 模拟器 + 报告 | 5 天 |
| 合计 | | **33 天** |

**技术选型**：
- 需求预测：XGBoost + Prophet（参考 PricePilot）
- RL 定价：Stable-Baselines3 PPO（参考 PricePilot）
- 竞品追踪：复用 data_agent 爬虫框架
- Web：Vue3 + ECharts

---

## 三、总体开发排期

| 步骤 | 模块 | 后端 | 前端 | 总工作量 | 优先级 |
|------|------|------|------|---------|--------|
| ① 基础 | 信息化基建 | ✅ | ✅ | 0 | P0（已完成） |
| ② 交付 | 工作流+驾驶舱 | ✅ | 5d | 5d + 2d/行业 | P0 |
| ③ 培训 | 说明书+视频+考证 | — | — | 13d（轻量） | P1 |
| ④ 情报 | 情报收集 Web | ✅ | 13d | 13d | P1 |
| ⑤ 营销 | GEO 投放 | 18d | 7d | 25d | P2 |
| ⑥ 裁员 | HR 评估 Web | 8d | 14d | 22d | P2 |
| ⑦ 定价 | 动态定价 | 21d | 12d | 33d | P3 |

**推荐交付顺序**：
1. ② 交付（5d）→ 立即可用
2. ④ 情报 Web（13d）→ 炫酷演示利器
3. ③ 培训（13d，可与 ④ 并行）
4. ⑥ 裁员 Web（22d）→ 后端已有，纯前端
5. ⑤ 营销（25d）→ 全新模块
6. ⑦ 定价（33d）→ 最复杂，最后做

**总工作量**：约 111 人天（不含培训 13d 则 98d）

---

## 四、Dify 工具集成规划

每完成一个增值模块，都按 ② 的模式注册为 Dify 自定义工具：

| 模块 | Dify 工具 | 说明 |
|------|----------|------|
| ④ 情报 | `track_intelligence` | 追踪关键词/品牌的情报动态 |
| ④ 情报 | `generate_report` | 生成情报报告 |
| ⑤ 营销 | `optimize_geo_content` | 优化内容让 AI 引擎引用 |
| ⑤ 营销 | `generate_ad_variants` | 生成多变体广告文案 |
| ⑥ 裁员 | `assess_ai_replacement` | 评估岗位 AI 替代度 |
| ⑥ 裁员 | `simulate_redundancy` | 模拟裁员方案 |
| ⑦ 定价 | `optimize_price` | 给定产品/场景输出最优定价 |
| ⑦ 定价 | `simulate_pricing` | What-if 定价模拟 |

---

## 五、商业模式建议

| 层级 | 包含 | 定价建议 |
|------|------|---------|
| 基础版（步骤 1-3） | 基建 + 交付 + 培训 | 一次性交付费 + 年维护费 |
| 增值模块（步骤 4-7 任选） | 情报 / 营销 / 裁员 / 定价 | 按模块年订阅 |
| 全家桶（步骤 1-7） | 全部 | 年订阅折扣 |

---

*文档路径：docs/v5-enterprise-delivery-plan.md*
*创建时间：2026-07-12*
*状态：规划中，待评审*
