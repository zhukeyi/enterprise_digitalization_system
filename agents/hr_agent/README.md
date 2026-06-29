# HR Agent — 人力情报Agent（新增模块）

## 职责

面向企业非技术管理者的 AI 辅助人力决策系统，所有操作内置防呆机制。

### 核心能力

| 功能模块 | 说明 | 防呆要求 |
|:---|:---|:---|
| **组织架构导入** | 支持拖拽/模板导入Excel/CSV/飞书/企微组织架构 | 格式校验、空值检测、重复人员警告 |
| **员工画像评估** | 技能标签化、绩效轨迹、潜力评分、离职风险预警 | 敏感信息脱敏、评分依据透明可溯源 |
| **企业风险评估** | 战略风险、运营风险、人才流失风险、合规风险 | 每次评估标注可信度和数据来源 |
| **风险-能力匹配** | 风险项←→员工能力的交叉矩阵，自动发现缺口和冗余 | 区别"数据缺失"vs"确实缺人" |
| **冗余度分析** | 基于岗位、技能、KPI 计算人员重叠度 | 最少保留人数阈值校验 |
| **裁员评估** | 模拟裁员方案：人选→成本→体系影响→替代方案 | 多重确认、不可逆操作警示、模拟预览 |
| **影响分析报告** | 裁员对部门协作、项目进度、知识留存的影响量化 | 图文报告，附通俗解释 |
| **替代方案推荐** | 转岗/兼岗/外部招聘成本对比 | 多方案并行对比 |

## 防呆机制（跨模块通用规则）

每个操作流程必须经过五步校验：

```
用户操作 → 【1. 可逆性检查】 → 【2. 影响范围评估】 → 【3. 通俗风险解释】
         → 【4. 二次确认弹窗】 → 【5. 操作日志+快照】
```

| 步骤 | 检查内容 | 技术实现 |
|:---|:---|:---|
| 1. 可逆性 | 此操作是否可撤销？多少时间内可撤回？ | 操作分类器（reversible/irreversible/needs_review） |
| 2. 影响范围 | 涉及人员数、部门数、关联项目数 | 影响图计算（依赖关系数据库查询） |
| 3. 风险解释 | 用通俗语言（非术语）说明可能后果 | LLM 生成+人工审核模板 |
| 4. 二次确认 | 弹窗展示风险摘要，用户必须再次确认 | 前端防呆组件（非简单 OK/Cancel） |
| 5. 快照 | 记录操作前的数据快照，支持回滚 | PostgreSQL 审计日志 + JSON diff |

## 技术架构

```
hr_agent/
├── __init__.py
├── main.py                   # FastAPI 路由
├── models/
│   ├── __init__.py
│   ├── employee.py           # 员工画像模型
│   ├── risk.py               # 企业风险模型
│   ├── org_chart.py          # 组织架构模型
│   └── layoff.py             # 裁员评估模型
├── services/
│   ├── __init__.py
│   ├── org_import.py         # 组织架构导入（Excel/CSV/API）
│   ├── profile_engine.py     # 员工画像分析引擎
│   ├── risk_matcher.py       # 风险-能力匹配引擎
│   ├── redundancy.py         # 冗余度计算
│   ├── layoff_simulator.py   # 裁员模拟器（成本/影响）
│   └── impact_analyzer.py    # 影响分析报告生成
├── anti_foolproof/
│   ├── __init__.py
│   ├── checker.py            # 防呆检查链
│   ├── risk_explainer.py     # 通俗风险解释（LLM）
│   └── confirmation.py       # 二次确认组件
├── dashboard/
│   ├── __init__.py
│   ├── pages/                # 前端页面
│   │   ├── org_view.py
│   │   ├── profile_page.py
│   │   ├── risk_matrix.py
│   │   └── layoff_sim.py
│   └── components/           # 可复用组件
│       ├── foolproof_modal.py  # 通用防呆弹窗
│       └── impact_chart.py
└── tests/
    ├── __init__.py
    ├── test_org_import.py
    ├── test_risk_matcher.py
    ├── test_layoff.py
    └── test_foolproof.py
```

## 数据模型

### Employee

```python
class Employee(BaseModel):
    id: str
    name: PiiString
    department: str
    position: str
    level: str                          # P1-P10
    hire_date: date
    skills: list[Skill]
    kpi_history: list[KpiRecord]
    projects: list[str]                 # 参与项目ID列表
    supervisor_id: str | None
    subordinates: list[str]             # 下属ID列表
    risk_score: float                   # 离职风险 0-1
    potential_score: float              # 发展潜力 0-1
    redundancy_score: float             # 冗余度 0-1
```

### EnterpriseRisk

```python
class EnterpriseRisk(BaseModel):
    id: str
    category: RiskCategory              # 战略/运营/人才/合规
    description: str
    severity: float                     # 0-1
    likelihood: float                   # 0-1
    required_skills: list[str]          # 所需应对技能
    affected_departments: list[str]
    confidence: float                   # 评估可信度 0-1
    data_sources: list[str]             # 数据来源（透明可溯源）
```

### LayoffScenario

```python
class LayoffScenario(BaseModel):
    id: str
    name: str                           # 方案名称
    target_employees: list[str]         # 目标人员ID列表
    reason: str                         # 裁员原因
    cost_breakdown: LayoffCost          # 成本明细
    impact: ImpactReport                # 影响分析
    alternatives: list[Alternative]     # 替代方案
    status: Literal["draft", "simulated", "pending_confirm", "confirmed", "cancelled"]
```

## 新增任务排期

| 任务ID | 里程碑 | 任务内容 | 依赖 | 交付物 |
|:---|:---|:---|:---|:---|
| **H1-T1** | M2 (触点) | 防呆机制基础设施：操作分类器 + 影响图计算 + 二次确认通用组件 | M1-T1 | 防呆中间件SDK（shared/sdk/） |
| **H1-T2** | M2 | 防呆风险解释器：LLM Prompt 模板 + 人工审核后备 | H1-T1 | 通俗化风险解释能力 |
| **H2-T1** | M3 (大脑) | 组织架构导入：Excel/CSV模板解析 + 飞书/企微 API 对接 | M2-T1 | 组织架构数据导入管道 |
| **H2-T2** | M3 | 员工画像引擎：技能提取+NLP+绩效分析+离职风险预测 | H2-T1 | 员工画像评估报告 |
| **H2-T3** | M3 | 企业风险评估：多维度风险建模 + 置信度评估 | 无 | 风险仪表板 |
| **H2-T4** | M3 | 风险-能力匹配矩阵 + 冗余度分析 | H2-T2 + H2-T3 | 交叉分析矩阵看板 |
| **H3-T1** | M4 (交付) | 裁员模拟器：成本计算 + 体系影响分析 + 替代方案对比 | H2-T4 | 裁员评估报告生成 |
| **H3-T2** | M4 | HR Dashboard 完整交互界面（含防呆弹窗） | H1-T1 + H2-T4 + H3-T1 | 可交互HR决策面板 |
| **H3-T3** | M4 | 集成测试 + 用户验收 | H3-T2 | 测试报告 + 用户手册 |

## 里程碑更新

| 里程碑 | 原时间 | 新增内容 | 调整后时间 |
|:---|:---|:---|:---|
| **M2: 触点** | 第3-4月 | + 防呆机制基础设施（H1-T1, H1-T2）集成到所有模块 | 不变 |
| **M3: 大脑** | 第5-6月 | + 人力情报核心能力（H2-T1~H2-T4） | **新增HR Agent** |
| **M4: 交付** | 第7-8月 | + 裁员评估 + HR Dashboard + 防呆全覆盖（H3-T1~H3-T3） | 新增约 20 人天 |

## 子Agent矩阵更新

| 子Agent | 简称 | 新增职责 | 新增任务数 |
|:---|:---|:---|:---|
| **Governance Agent** | 管家 | 防呆机制中间件基础设施 | +2 (H1-T1, H1-T2) |
| **HR Agent** (NEW) | 人力官 | 员工画像、风险评估、能力匹配、裁员模拟 | +6 (H2-T1~T4, H3-T1~T2) |
| **Analysis Agent** | 分析师 | HR Dashboard 交互界面 | +1 (H3-T2 协作) |

**总工作量更新**：原 240 人天 → ~290 人天（含缓冲 ~340 人天）