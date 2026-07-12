# FDE Dify 通用工作流模板

> 以下 5 个模板覆盖 V5 七步法中的核心业务场景，可在 Dify 中快速导入并按客户行业微调。
> 导入方式：Dify 工作室 → 创建空白工作流 → 按下方节点拓扑搭建 → 绑定 FDE Custom Tool

---

## 可导入 DSL 文件（一键导入）

除下方文本拓扑外，本目录提供 5 个可直接导入的 Dify DSL（JSON）：

| 文件 | 模板 | 绑定 FDE 工具 |
|------|------|--------------|
| `contract-analysis.json` | 合同智能分析 | `upload_file` |
| `data-qa.json` | 经营数据问答 | `ask_data` |
| `intel-briefing.json` | 情报简报生成 | `track_intelligence` + `generate_intel_report` |
| `pricing-advisor.json` | 智能定价建议 | `optimize_price` |
| `redundancy-eval.json` | 裁员方案评估 | `simulate_redundancy` |

> 导入前提：先在 Dify 导入 `docs/fde-dify-openapi.yaml`（provider 名 `fde_data_tool`），DSL 中的工具节点才能解析。

---

## 模板 1：合同智能分析

**适用场景**：法务/采购部门批量分析合同条款，提取关键风险点

```
[开始]
  → [LLM: 提取合同要素] (模型: qwen-max)
      prompt: "从以下合同文本中提取：合同方、金额、期限、违约条款、知识产权归属。输出 JSON。"
  → [工具: ask_data] (query: "类似合同的历史分析结果")
  → [LLM: 风险评估] (模型: qwen-max)
      prompt: "对比历史数据，评估当前合同的违约风险和不利条款。"
  → [结束: 输出分析报告]
```

**绑定工具**：`ask_data`
**预计耗时**：3-5 秒/份

---

## 模板 2：经营数据问答

**适用场景**：管理层通过自然语言查询经营数据

```
[开始]
  → [问题分类器] (判断：数据查询 / 知识库问答 / 闲聊)
  → 分支 A (数据查询):
      → [工具: ask_data] (query: 用户问题)
      → [LLM: 格式化] → [结束]
  → 分支 B (知识库问答):
      → [工具: ask_data] (query: 用户问题, doc_type: "knowledge_base")
      → [LLM: 格式化] → [结束]
  → 分支 C (闲聊):
      → [LLM: 通用回复] → [结束]
```

**绑定工具**：`ask_data`
**典型问题**："上月销售额多少"、"哪些产品利润率最高"

---

## 模板 3：情报简报生成

**适用场景**：每日/每周自动生成外部情报简报

```
[开始]
  → [工具: track_intelligence] (source_type: "rss", max_items: 20)
  → [工具: generate_intel_report]
  → [LLM: 生成简报] (模型: qwen-max)
      prompt: "基于以下情报数据，生成一份结构化简报，包含：
        1. 重要事件摘要（3-5条）
        2. 行业趋势分析
        3. 竞品动态
        4. 建议关注事项"
  → [结束: 输出 Markdown 简报]
```

**绑定工具**：`track_intelligence` + `generate_intel_report`
**调度**：可配置 Dify 定时触发，每日 8:00 自动执行

---

## 模板 4：定价建议生成

**适用场景**：产品经理为指定商品获取 AI 定价建议

```
[开始]
  → [输入: product_id]
  → [工具: optimize_price] (product_id, strategy: "rl_optimal")
  → [工具: simulate_pricing] (product_id, new_price: 优化结果.recommended_price)
  → [LLM: 生成建议报告] (模型: qwen-max)
      prompt: "基于定价优化结果和 What-if 模拟数据，生成一份定价建议报告，包含：
        1. 当前价格 vs 建议价格
        2. 预期收入/利润变化
        3. 竞品定价对比
        4. 调价风险评估
        5. 建议执行方案（一次性/分步）"
  → [结束: 输出定价建议报告]
```

**绑定工具**：`optimize_price` + `simulate_pricing`

---

## 模板 5：裁员方案评估

**适用场景**：HR 部门模拟部门裁员方案并评估影响

```
[开始]
  → [输入: department_id]
  → [工具: simulate_redundancy] (department_id)
  → [LLM: 生成评估报告] (模型: qwen-max)
      prompt: "基于部门冗余分析结果，生成一份人机协作优化建议报告，包含：
        1. 冗余现状概览（冗余率、涉及人数、预计节省）
        2. 可优化岗位清单及建议
        3. 风险评估（业务连续性/士气/合规）
        4. 保守方案（推荐人机协作而非直接裁员）
        5. 实施建议与时间表"
  → [结束: 输出评估报告]
```

**绑定工具**：`simulate_redundancy`
**注意**：此工作流输出仅供参考，最终决策需人工确认（系统内置防呆 5 步）

---

## 导入说明

1. 确保 FDE Custom Tool 已在 Dify 中导入（使用 `docs/fde-dify-openapi.yaml`）
2. 在 Dify 工作室中创建新工作流
3. 按模板拓扑依次拖入节点
4. 在工具节点中选择对应的 FDE 工具
5. 配置 LLM 节点的模型和 prompt
6. 测试运行，确认数据流正确
7. 发布并配置访问权限

## 按行业定制

以上模板为通用版本。按行业交付时，调整 LLM 节点的 prompt 即可：

| 行业 | 定制要点 |
|------|----------|
| 制造业 | 合同分析侧重供应链条款；定价侧重原材料成本波动 |
| 零售业 | 情报简报侧重消费趋势；定价侧重促销节奏 |
| 金融业 | 合同分析侧重合规条款；裁员评估侧重合规风险 |
| 科技业 | 情报简报侧重技术动态；定价侧重订阅模式 |
