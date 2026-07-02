# M3-T3: 数据查询网关 + NL2SQL 引擎 需求规格书

## 1. 任务摘要
- **一句话目标**：实现自然语言转 SQL 查询引擎，支持规则优先 + LLM fallback，含 SQL 安全校验和只读执行
- **所属模块**：`analysis_agent`
- **预计复杂度**：高

## 2. 背景与目标
- 当前 `analysis_agent` 为空壳，需要从零实现完整模块
- 痛点：业务用户无法直接写 SQL，需要自然语言交互方式查询数据库
- 成功标准：规则引擎覆盖 80% 常见查询；SQL 安全校验拦截所有危险操作；100% 只读执行

## 3. 用户故事
- 作为 **业务用户**，我希望用自然语言查询数据，以便无需学习 SQL 即可获取数据
- 作为 **系统管理员**，我希望所有自动生成的 SQL 经过安全校验，以便防止误删误改
- 作为 **开发者**，我希望 NL2SQL 有规则和 LLM 双通道，以便在无 LLM 时也能基本可用

## 4. 验收标准
- `AC-001`: Given 用户输入"查询所有销售额大于100万的记录"，When 系统执行 NL2SQL，Then 生成 `SELECT ... WHERE sales > 1000000` 并返回结果
- `AC-002`: Given SQL 包含 `DELETE FROM table`，When 安全校验执行，Then 拦截并返回错误
- `AC-003`: Given SQL 包含 `UPDATE` 或 `DROP` 无 WHERE，When 安全校验执行，Then 拦截并返回错误
- `AC-004`: Given 规则引擎无法匹配，When NL2SQL 执行，Then 返回 fallback 提示（LLM 通道需路由网关，Mock 模式返回提示信息）
- `AC-005`: Given 数据库不可用，When 查询执行，Then 返回友好错误信息而非崩溃
- `AC-006`: Given `schema_list` 工具被调用，When 执行，Then 返回可用表和字段列表

## 5. 功能需求
- `FR-001`: NL2SQL 规则引擎：关键词映射表名/字段名/操作符，生成基础 SELECT 语句 (P0)
- `FR-002`: SQL 安全校验器：拦截 DELETE/UPDATE/DROP/TRUNCATE，以及无 WHERE 的危险操作 (P0)
- `FR-003`: 查询执行器：只读模式执行 SQL，返回 Pydantic 格式化结果 (P0)
- `FR-004`: Schema 元数据提取：从 DB 读取表结构信息（表名、字段名、类型） (P0)
- `FR-005`: 注册 4 个工具到 ToolRegistry：nl2sql, sql_execute, schema_list, query_chart_data (P0)
- `FR-006`: LLM fallback 通道：复杂查询路由到智能网关（Mock 模式返回提示） (P1)
- `FR-007`: 查询结果图表数据格式化：支持 line/bar/pie/scatter 格式输出 (P1)

## 6. 非功能需求
- **性能**：规则引擎 NL2SQL < 50ms；SQL 执行依赖数据库响应
- **安全**：READ_ONLY 模式强制；SQL 注入检测（分号拼接、多语句）
- **可观测性**：每次 NL2SQL 转换记录原文→SQL 映射日志
- **兼容性**：复用 governance_agent 的 DB session（asyncpg）

## 7. 数据模型设计

```python
class NL2SQLRequest(BaseModel):
    query: str                    # 自然语言查询
    db_schema_id: str = "default" # 数据库 schema 标识
    max_results: int = 100        # 最大返回行数

class ColumnSchema(BaseModel):
    name: str
    data_type: str
    nullable: bool = True
    description: str = ""

class TableSchema(BaseModel):
    table_name: str
    columns: list[ColumnSchema]
    row_count: int | None = None
    description: str = ""

class DatabaseSchema(BaseModel):
    schema_id: str
    tables: list[TableSchema]

class SQLResult(BaseModel):
    sql: str                          # 最终执行的 SQL
    rows: list[dict[str, Any]]        # 查询结果行
    row_count: int                    # 返回行数
    columns: list[str]                # 列名列表
    execution_time_ms: float          # 执行耗时
    source: str                       # "rule_engine" | "llm_fallback"

class ChartData(BaseModel):
    chart_type: str                   # "line" | "bar" | "pie" | "scatter"
    labels: list[str]                 # X 轴标签
    datasets: list[ChartDataset]      # 数据集
    title: str = ""

class ChartDataset(BaseModel):
    label: str
    data: list[float | int | None]
    color: str | None = None

class NL2SQLResult(BaseModel):
    success: bool
    sql: str
    source: str                       # "rule_engine" | "llm_fallback"
    result: SQLResult | None = None
    error: str | None = None
    safety_check_passed: bool = True
```

## 8. API / 接口契约

注册到 ToolRegistry 的 4 个工具：

| 工具名 | 参数 | 返回 | 说明 |
|--------|------|------|------|
| `nl2sql` | query: str, db_schema_id: str, max_results: int | NL2SQLResult | NL 转 SQL 并执行 |
| `sql_execute` | sql: str, params: dict | SQLResult | 执行预编译 SQL（需安全校验） |
| `schema_list` | db_schema_id: str | DatabaseSchema | 列出表和字段 |
| `query_chart_data` | query: str, chart_type: str | ChartData | 查询并返回图表格式数据 |

## 9. 错误处理与边界条件
- 空查询：返回错误 "query is required"
- SQL 包含危险关键词：返回 `safety_check_passed=False` + 错误详情
- 数据库不可用：捕获连接异常，返回友好错误
- 查询结果为空：返回 `rows=[], row_count=0`
- 超过 max_results：截断并标注 `truncated=True`
- SQL 注入检测：检测分号拼接、注释符号、多语句

## 10. 依赖与影响范围
- **依赖**：`shared/models/base.py`、`agents/governance_agent/database/session.py`、`agents/orchestrator/tools/registry.py`
- **新增文件**：`agents/analysis_agent/models.py`, `schema_extractor.py`, `nl2sql.py`, `sql_safety.py`, `executor.py`, `integration.py`, `__init__.py`, `tests/test_analysis.py`
- **新增依赖**：复用已有 asyncpg + SQLAlchemy，无新增外部库
- **不影响**：不修改任何已有文件

## 11. 风险与缓解
| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 规则引擎覆盖率不足 | 中 | 中 | 提供丰富的关键词映射表 + LLM fallback |
| 无真实数据库时测试困难 | 高 | 高 | MockExecutor 提供内存模拟查询 |
| SQL 注入风险 | 低 | 高 | sql_safety 拦截分号/注释/多语句 + 参数化查询 |

## 12. 参考实现线索
- 工具注册模式：参考 `agents/hr_agent/integration.py`
- DB session：参考 `agents/governance_agent/database/session.py`
- 测试 _run helper：参考 `agents/hr_agent/tests/test_hr.py` 的 `_run()` 函数
- Mock 执行器：参考 `MockHRAdapter` 的内存数据模式
