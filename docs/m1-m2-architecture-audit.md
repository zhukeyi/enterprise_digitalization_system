# M1-M2 架构合规性与鲁棒性审计报告

> 审计时间：2026-07-01  
> 审计范围：fde-ai-platform M1 + M2 全部代码（~18,700 行 Python + 前端 Vue3）  
> 对照文档：README.md v2.0 开发计划  
> 质量门禁：506 tests passed | ruff 0 errors | black clean | mypy clean | 88% coverage

---

## 一、架构吻合度评估

### 1.1 里程碑任务对照

#### M1: 地基（计划 75 人天，8 个任务）

| 任务ID | 计划内容 | 实际完成 | 吻合度 |
|--------|----------|----------|--------|
| M1-T1 | Monorepo + CI/CD | ✅ 完整：pyproject.toml + Makefile + GitHub Actions + Docker Compose | 100% |
| M1-T2 | 可观测底座（Prometheus+Grafana+Loki+Langfuse） | ⚠️ 部分：shared/sdk 有 TraceContext 框架，但仅 stdout stub，未接 Langfuse | 30% |
| M1-T3 | 统一API网关 + 多模型适配器 + 路由策略 + 故障切换 | ✅ 完整：FastAPI 网关 + 4 适配器（Mock/OpenAI/Anthropic/Gemini）+ FallbackChain | 95% |
| M1-T4 | RAGFlow部署 + 企业连接器 + 文档质量分级 + 权限元数据 + 混合检索 | ⚠️ 偏离：未用 RAGFlow，自建 Qdrant+BM25+RAG 管线（含文档解析/分块/嵌入/混合检索） | 80%¹ |
| M1-T5 | Dify部署 + RAGFlow外部知识库接入 | ✅ Dify 已部署（测试服务器 12 容器），但 RAGFlow→自建 RAG 对接未做 | 70% |
| M1-T6 | LangGraph框架 + 全局状态 + Supervisor + 提示词 | ✅ 完整：StateGraph + SupervisorNode + 10 Workers + ToolRegistry + MessageBus | 95% |
| M1-T7 | 防呆组件基础设计 | ✅ AntiFoolproofMiddleware（中英文关键词 + 5步校验） | 90% |
| M1-T8 | 端到端集成测试 | ✅ test_e2e.py + test_smoke.py + 全量 506 测试 | 100% |

> ¹ M1-T4 技术路线偏离说明：计划用 RAGFlow 作为 RAG 底座，实际自建了完整的 Qdrant+BM25+BGE-M3 管线。  
> 功能覆盖等价（文档解析→分块→嵌入→混合检索），但底座不同。这是合理的工程决策（ARM 兼容性），  
> 但需在后续里程碑中补上 RAGFlow 集成或明确文档变更决策。

#### M2: 触点+智能体（计划 65 人天，8 个任务）

| 任务ID | 计划内容 | 实际完成 | 吻合度 |
|--------|----------|----------|--------|
| M2-T1 | 统一认证 + 细粒度权限引擎 | ✅ JWT + API Key + RBAC + ABAC + AuthMiddleware，26 tests | 100% |
| M2-T2 | 权限过滤检索 + 决策链日志 | ✅ auth_filter + DecisionChainLog + DecisionLogger，14 tests | 100% |
| M2-T3 | IM消息枢纽 + 企微/飞书/钉钉适配器 | ✅ IMWorker + 3 适配器 Stub + 12 Pydantic models，31 tests | 85%² |
| M2-T4 | Tauri客户端 + 快捷键 + 文本捕获 | ⚠️ Python SDK 完成（16 models + DesktopAuthManager + 17 tests），Tauri 壳未做 | 50%³ |
| M2-T5 | 子Agent Worker（合规/业务系统） | ✅ ComplianceWorker + BusinessSystemWorker + 6 tools，36 tests | 100% |
| M2-T6 | 冲突裁决 + Response Generator | ✅ ConflictDetector + ConflictResolver + ResponseGenerator + 4 策略，31 tests | 100% |
| M2-T7 | Dify Tool Node Integration | ✅ DifyBridge + /dify/* router + YAML 导出，15 tests | 100% |
| M2-T8 | 全链路集成测试 | ✅ 31 E2E tests（多步计划 + 冲突管线 + 跨模块） | 100% |

> ² M2-T3 适配器为 Stub（MockAdapter 实现，WeCom/Feishu/DingTalk 仅有接口定义），生产需对接真实 API。  
> ³ M2-T4 Tauri 客户端需 Rust 工具链，Python SDK 已就绪，TODO.md 记录了 T-1~T-6 待办。

### 1.2 模块对照（11 大模块 → 代码实现）

| 模块 | 计划 Agent | 代码目录 | 代码行数 | 测试数 | 状态 |
|------|-----------|----------|----------|--------|------|
| A 智能路由网关 | Router Agent | agents/router_agent/ | ~1,800 | 26 tests | ✅ 完整 |
| B RAG引擎 | RAG Agent | agents/rag_agent/ | ~3,500 | 19 tests | ✅ 自建管线 |
| C Dify编排 | Dify Agent | agents/dify_bridge/ | ~600 | 15 tests | ✅ 桥接层 |
| D 消息枢纽 | IM Agent | agents/im_agent/ | ~1,200 | 31 tests | ⚠️ Stub 适配器 |
| E 桌面助手 | Client Agent | agents/client_agent/ | ~700 | 17 tests | ⚠️ 仅 SDK |
| F 数据情报 | Data Agent | agents/data_agent/ | 0 行 | 0 tests | ❌ 空壳 |
| G 智能分析 | Analysis Agent | agents/analysis_agent/ | 0 行 | 0 tests | ❌ 空壳 |
| H 全栈治理 | Governance Agent | agents/governance_agent/ | ~2,000 | 40+ tests | ✅ 完整 |
| I 实施工具包 | Orchestrator | — | — | — | ❌ M4 阶段 |
| J HR决策 | HR Agent | agents/hr_agent/ | 0 行 | 0 tests | ❌ 空壳 |
| K LangGraph编排 | Orchestrator | agents/orchestrator/ | ~3,500 | 80+ tests | ✅ 完整 |
| L 地图AI | Map Agent | agents/map_agent/ + frontend/ | ~800 Python + Vue3 | 6 tests | ⚠️ 骨架 |

### 1.3 核心原则合规性

| 原则 | 合规性 | 证据 |
|------|--------|------|
| **模块化** | ✅ | 15 个独立 agent 包，松耦合，通过 ToolRegistry 通信 |
| **本地优先** | ✅ | BGE-M3 本地推理，Qdrant 本地部署，JWT 本地验证 |
| **LLM只规划后端执行** | ✅ | Supervisor 只生成 PlanStep，Worker 通过 ToolRegistry.dispatch 执行 |
| **权限硬过滤** | ✅ | auth_filter 在 RAG 检索后过滤，不经过 LLM |
| **零幻觉** | ⚠️ | RAG 返回带 source 的结果，但 LLM 合成答案层未实现（rag_answer 未注册） |
| **防呆设计** | ✅ | AntiFoolproofMiddleware + 中文关键词 + 5步校验流程 |

---

## 二、鲁棒性评估

### 2.1 优秀的方面 ✅

1. **异步一致性**：ToolRegistry.dispatch 正确支持 sync/async handler，BaseWorker._run_dispatch 桥接完整
2. **类型安全**：Pydantic BaseModel 用于 State/Plan/Conflict，mypy strict 模式通过
3. **错误边界**：BaseWorker.__call__ 捕获 7 类异常，Supervisor 有 max_iterations 安全阀
4. **冲突管线**：4 条检测规则 + 4 种裁决策略，全部确定性（无 LLM 依赖）
5. **多步计划执行**：merge_dict reducer 确保跨步骤累积，_remaining_steps 实现续步调度
6. **测试覆盖**：506 测试，88% 覆盖率，E2E 测试覆盖多步计划+冲突管线全链路
7. **代码卫生**：零 TODO/FIXME/HACK 注释，ruff+black+mypy 全绿
8. **CI/CD**：GitHub Actions 三阶段门禁（lint→type-check→test），Python 3.12+3.13 矩阵

### 2.2 需要关注的问题

#### P1 — 影响生产可靠性

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| 1 | `shared/` 全部逻辑在 `__init__.py`（4 个"胖 init"） | 可维护性差，无法单独导入模块 | 拆分为独立 .py 文件 |
| 2 | 3 个 Agent 为完全空壳（analysis/data/hr） | M3 任务依赖这些 Agent，需从头开始 | M3 阶段优先实现 |
| 3 | IM 适配器全是 Stub | 生产环境无法收发消息 | 对接真实 API |
| 4 | Tauri 桌面客户端未开始 | M2-T4 仅交付 Python SDK | 需 Rust 开发环境 |
| 5 | `_log_trace` 仅 print 到 stdout | 无真实可观测性 | 接入 Langfuse/OTel |
| 6 | docker-compose 仅有 dev 版本 | 无生产编排配置 | M4 阶段补充 |
| 7 | CI 仅 lint+type+test，缺 CD | 无自动部署流水线 | M4-T6 Helm+部署 |
| 8 | 可观测底座（M1-T2）仅完成 30% | Prometheus/Grafana/Loki 未部署 | 补全监控基础设施 |

#### P2 — 改进建议

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| 1 | `shared/prompts` 中 prompt 硬编码在 Python | 无法热更新 | 迁移到 YAML/Jinja2 |
| 2 | `shared/sdk` 的 TraceContext 非线程安全 | 多线程场景可能丢失 trace | 使用 contextvars |
| 3 | `_is_public_path` 前缀匹配过于宽松 | `/auth` 会匹配 `/authxxx` | 改用精确段匹配 |
| 4 | Supervisor mock_plan 关键词硬编码 | 无法扩展新意图 | 考虑可配置路由规则 |
| 5 | `agents/htmlcov/` 出现在源码树 | 污染目录结构 | 已在 .gitignore，但需清理 |
| 6 | `frontend/map-ai/.env` 实际存在 | 可能含敏感 token | 确认已被 .gitignore 排除 |
| 7 | 未见 conftest.py 在 agents/ 根目录 | pytest fixtures 可能重复 | 检查 fixtures 复用 |
| 8 | RAG `rag_answer` 工具未注册 | 零幻觉原则的 LLM 合成层缺失 | M3 阶段实现 |

---

## 三、软件工程规范评估

### 3.1 工程化工具链

| 维度 | 评分 | 说明 |
|------|------|------|
| **代码格式** | ★★★★★ | black 100 行宽 + ruff 10+ 规则集 |
| **类型检查** | ★★★★★ | mypy strict 模式，第三方库 ignore_missing_imports |
| **测试体系** | ★★★★☆ | 506 tests / 88% coverage，但 3 个 Agent 零测试 |
| **CI/CD** | ★★★★☆ | CI 三阶段门禁完整，CD 缺失 |
| **依赖管理** | ★★★★★ | pyproject.toml 分组 extras，版本锁定合理 |
| **文档** | ★★★☆☆ | README 详尽但代码内 docstring 参差不齐 |
| **版本控制** | ★★★★☆ | Conventional Commits，但无 branch protection 规则 |
| **安全** | ★★★★☆ | .gitignore 排除 .env，PII 类型标注，JWT 验证 |

### 3.2 架构模式合规

| README 定义 | 实现方式 | 合规 |
|-------------|----------|------|
| Supervisor-Worker 模式 | LangGraph StateGraph + 10 Workers | ✅ |
| LLM 只规划不执行 | Supervisor 生成 PlanStep，Worker 执行 Tool | ✅ |
| 结构化指令（Pydantic） | SupervisorPlan + PlanStep + ConflictReport | ✅ |
| 全局状态 TypedDict | OrchestratorState (Pydantic BaseModel) | ✅¹ |
| 冲突裁决节点 | ConflictDetector + ConflictResolver + ResponseGenerator | ✅ |
| 防呆 5 步校验 | AntiFoolproofMiddleware | ✅ |
| 权限硬过滤 | auth_filter 在 RAG 检索后过滤 | ✅ |

> ¹ README 定义用 TypedDict，实际用 Pydantic BaseModel。Pydantic 提供更好的类型验证和  
> JSON Schema 生成，是合理的改进。但 LangGraph 的 add_messages reducer 需要 Annotated 类型，  
> 已通过 `Annotated[list[BaseMessage], add_messages]` 正确处理。

### 3.3 代码规模与复杂度

| 指标 | 数值 | 评价 |
|------|------|------|
| Python 代码行数 | ~18,700 | 中型项目，合理 |
| 测试文件数 | 28 | 覆盖 12/15 个 Agent |
| 测试用例数 | 506 | 测试充分 |
| 代码/测试比 | ~37:1 | 优秀（行业平均 20:1） |
| 最大文件行数 | conflict_resolution.py ~717 | 临界，建议拆分 |
| 空文件数 | 23 个 __init__.py | 合理（包标记文件） |

---

## 四、总结

### 4.1 整体评价

M1-M2 阶段的开发与 README v2.0 计划 **高度吻合**（85%+），核心架构（Supervisor-Worker、  
ToolRegistry、冲突管线、权限引擎、防呆机制）均已落地并通过测试验证。主要偏差在于：

1. **RAG 底座替换**：RAGFlow → 自建 Qdrant+BM25 管线（合理的工程决策）
2. **M1-T2 可观测底座**：仅完成框架，未部署真实监控
3. **M2-T4 桌面客户端**：仅完成 Python SDK，Tauri 壳待 Rust 环境
4. **3 个 M3 Agent 空壳**：analysis/data/hr 尚未开始（符合里程碑规划）

### 4.2 鲁棒性评分

| 维度 | 评分 |
|------|------|
| 架构设计 | ★★★★☆ |
| 类型安全 | ★★★★★ |
| 错误处理 | ★★★★☆ |
| 测试覆盖 | ★★★★☆ |
| 代码卫生 | ★★★★★ |
| 生产就绪度 | ★★★☆☆ |

### 4.3 建议的下一步行动

1. **M3 优先级最高**：实现 analysis/data/hr 三个空壳 Agent
2. **补全可观测性**：接入 Langfuse 或至少 OTel exporter
3. **IM 适配器对接**：至少完成一个真实平台（企微推荐）
4. **shared/ 拆分**：将胖 `__init__.py` 拆为独立模块文件
5. **生产 Docker Compose**：在 M4 之前准备 `docker-compose.prod.yml`
6. **前端 .env 安全审查**：确认 `frontend/map-ai/.env` 不含真实密钥
