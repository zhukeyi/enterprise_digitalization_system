# M3-T10: 地图后端分析 API + LangGraph 节点 需求规格书

## 1. 任务摘要
- **一句话目标**：扩展 map_agent 后端，新增 LangGraph 分析流水线节点（实体数据获取→相关性计算→AI 解读）和分析 API
- **所属模块**：`map_agent`
- **预计复杂度**：中

## 2. 背景与目标
- map_agent 已有基础骨架（models/engine/routes/worker），但缺少 LangGraph 节点编排和 AI 解读能力
- 目标：构建完整的"标记→提交→分析→解读"后端流水线
- 成功标准：LangGraph 3 节点串联执行，返回相关性结果 + AI 自然语言解读

## 3. 用户故事
- 作为 **业务用户**，我希望提交标记的地理实体后自动获得相关性分析和 AI 解读，以便理解空间关系
- 作为 **开发者**，我希望分析流水线以 LangGraph 节点形式编排，以便后续扩展和复用

## 4. 验收标准
- `AC-001`: Given 用户提交 2+ 实体，When 调用分析 API，Then 返回相关性结果 + AI 解读文本
- `AC-002`: Given 实体不足 2 个，When 调用分析 API，Then 返回 400 错误
- `AC-003`: Given LangGraph 流水线执行，When 3 个节点依次运行，Then 每个节点输出可追踪
- `AC-004`: Given LLM 不可用，When AI 解读节点执行，Then 降级为规则模板解读（不报错）

## 5. 功能需求
- `FR-001`: 新增 `langgraph_nodes.py` — 3 个 LangGraph 节点函数 (P0)
- `FR-002`: 新增 `interpreter.py` — AI 解读生成器（规则模板 + LLM prompt builder） (P0)
- `FR-003`: 新增 `pipeline.py` — LangGraph 流水线编排（3 节点串联） (P0)
- `FR-004`: 扩展 `routes.py` — 新增 POST /map/analysis 完整分析端点 (P0)
- `FR-005`: 测试覆盖所有新模块 (P0)

## 6. 非功能需求
- **性能**：分析流水线 < 2s（mock 数据）
- **可观测性**：每个节点记录执行时间和输出摘要
- **兼容性**：不修改已有 models.py / engine.py / demo_data.py

## 7. 数据模型设计

```python
class AnalysisRequest(BaseModel):
    entity_ids: list[str]          # 要分析的实体 ID 列表
    method: str = "pearson"        # 相关性方法
    query: str = ""                # 用户的自然语言查询

class AnalysisResult(BaseModel):
    request: AnalysisRequest
    entities: list[GeoEntity]      # 参与分析的实体
    correlation: CorrelationResponse  # 相关性结果
    interpretation: str            # AI 解读文本
    execution_time_ms: int
    nodes_traced: list[str]        # 节点执行追踪
```

## 8. API / 接口契约
- `POST /map/analysis` — 输入 AnalysisRequest，输出 AnalysisResult
- LangGraph 节点：`fetch_entities` → `compute_correlation` → `generate_interpretation`

## 9. 错误处理
- 实体 ID 不存在：跳过，记录 warning
- 实体不足 2 个：返回 400
- LLM 不可用：降级为规则模板

## 10. 依赖与影响范围
- **新增文件**：`langgraph_nodes.py`, `interpreter.py`, `pipeline.py`, 扩展 `routes.py`, 扩展 `tests/`
- **不修改**：`models.py`, `engine.py`, `demo_data.py`, `worker.py`

## 11. 风险与缓解
| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| LLM 不可用 | 高 | 中 | 规则模板降级 |
| LangGraph 依赖版本变化 | 低 | 低 | 用纯函数节点，不强依赖 langgraph 内部 API |

## 12. 参考实现线索
- 相关性引擎：复用 `agents/map_agent/engine.py` 的 `SpatialCorrelationEngine`
- Demo 数据：复用 `agents/map_agent/demo_data.py`
- 模型：复用 `agents/map_agent/models.py`
