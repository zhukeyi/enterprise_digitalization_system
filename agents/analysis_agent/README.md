# Analysis Agent — 智能分析层 (含人力情报)

## 职责
- 统一数据查询网关（对接 ClickHouse / PostgreSQL / MySQL）
- NL2SQL 引擎（自然语言转 SQL）
- 交互式 Dashboard（图表组件化，拖拽布局）
- 下钻分析（点击图表逐层展开）
- 关联分析（拖拽两图表自动计算相关性）
- **人力情报模块（新增）**
  - 员工画像评估
  - 企业风险评估
  - 风险-能力匹配分析
  - 人员冗余度分析
  - 裁员评估（成本计算 + 体系影响分析）
  - 组织架构数据导入

## M3 任务
| 任务 | 说明 | 状态 |
|:---|:---|:---|
| M3-T7 | 数据查询网关 | 待开发 |
| M3-T8 | NL2SQL 引擎 | 待开发 |
| M3-T9 | 交互式 Dashboard | 待开发 |
| M3-T10 | 下钻分析 | 待开发 |
| M3-T11 | 关联分析 | 待开发 |
| M3-T12 | 人力情报模块 | NEW — 待开发 |

## 依赖
- `fde-ai-platform[analysis]`
- pandas / numpy / plotly / sqlalchemy
