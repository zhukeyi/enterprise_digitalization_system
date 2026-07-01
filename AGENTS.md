# AGENTS.md — FDE AI Platform 多 Agent 协作规范

## 项目概述

FDE AI Platform 是企业级 AI 数字化平台，可私有化部署。
技术栈：Python 3.11+ / FastAPI / LangGraph / Qdrant / Vue 3。
当前阶段：M1-M2 完成（核心骨架 + 触点集成 + 智能体编排），M3 待启动。

## 构建与测试

```bash
make install          # 创建 venv + 安装依赖
make install-all      # 安装全部可选依赖（含重型 RAG 依赖）
make test             # 运行全部测试
make test-unit        # 仅单元测试
make test-cov         # 测试 + 覆盖率报告
make lint             # ruff 检查
make format           # Black 格式化
make typecheck        # mypy strict 检查
make verify           # 完整静态检查门禁 (format-check + lint + typecheck)
make docker-up        # 启动开发服务 (PostgreSQL / Redis / Qdrant / MinIO)
make docker-down      # 停止开发服务
make pre-commit       # 运行所有 pre-commit hooks
```

## 目录结构

```
enterprise_digitalization_system/
├── agents/                        # 所有 Agent 模块
│   ├── orchestrator/              # LangGraph 编排器（Supervisor-Worker 核心）
│   │   ├── langgraph/             #   状态定义、图构建、Supervisor、Worker 节点
│   │   │   ├── state.py           #     OrchestratorState (Pydantic + Annotated reducer)
│   │   │   ├── supervisor.py      #     Supervisor 规划节点（只规划不执行）
│   │   │   ├── workers.py         #     10 个 Worker 节点（确定性执行工具）
│   │   │   ├── conflict_resolution.py  # 冲突检测 + 裁决 + 响应生成
│   │   │   └── graph.py           #     StateGraph 组装（Supervisor→Worker→Conflict→Response）
│   │   ├── tools/                 #   ToolRegistry 工具注册与分发（async dispatch）
│   │   └── messages/              #   消息总线（LangChain Message 封装）
│   ├── router_agent/              # 模型网关（OpenAI 兼容 API）
│   │   ├── adapters/              #   LLM Provider 适配器（Mock/DeepSeek/Qwen/GLM）
│   │   ├── routing/               #   YAML 配置的路由策略引擎 + Failover 链
│   │   └── middleware/            #   Tracing + Anti-foolproof 中间件
│   ├── rag_agent/                 # RAG 知识库检索
│   │   ├── vector_store.py        #   Qdrant 客户端封装
│   │   ├── embeddings.py          #   BGE-M3 嵌入模型
│   │   ├── document_parser.py     #   多格式文档解析 (PDF/Docx/Xlsx/PPTx/MD/TXT)
│   │   ├── chunking.py            #   分块策略 (Fixed/Semantic/Recursive)
│   │   ├── retriever.py           #   混合检索 (BM25 + Vector + RRF)
│   │   ├── auth_filter.py         #   权限感知搜索过滤器（RBAC + ABAC）
│   │   └── integration.py         #   RAG 工具注册（rag_search + rag_ingest + rag_answer）
│   ├── governance_agent/          # 权限与审计
│   │   ├── database/models.py     #   User/ApiKey/AuditLog/Permission/DecisionChainLog ORM
│   │   ├── auth/security.py       #   JWT(HS256) + bcrypt + API Key(SHA256)
│   │   ├── auth/dependencies.py   #   get_current_user / require_role / check_permission
│   │   ├── auth/router.py         #   FastAPI Auth API (/auth/*)
│   │   ├── middleware/__init__.py #   AuthMiddleware (JWT stateless + 路由白名单)
│   │   └── decision_log.py        #   决策链日志服务（plan→worker→final 全链追踪）
│   ├── compliance_agent/          # 合规审核 Agent
│   │   ├── integration.py         #   3 工具：audit_log_query / compliance_summary / risk_check
│   │   └── tests/                 #   11 个测试
│   ├── business_agent/            # 业务系统集成 Agent（CRM/ERP/Finance）
│   │   ├── integration.py         #   3 工具：business_query / system_status / data_sync
│   │   └── tests/                 #   13 个测试
│   ├── im_agent/                  # IM 统一消息枢纽
│   │   ├── models.py              #   12 个 Pydantic 模型 + 3 个 StrEnum
│   │   ├── adapters/__init__.py   #   BaseIMAdapter + Mock/WeCom/Feishu/DingTalk
│   │   ├── tools.py               #   3 工具：send_message / broadcast / query_session
│   │   └── tests/                 #   31 个测试
│   ├── client_agent/              # Desktop Client SDK（Python 集成层）
│   │   ├── models.py              #   16 个 Pydantic 模型 + 5 个 StrEnum
│   │   ├── auth.py                #   DesktopAuthManager (JWT + 原子文件缓存)
│   │   └── tests/                 #   17 个测试
│   ├── dify_bridge/               # Dify Tool Node 桥接（管理后台）
│   │   ├── bridge.py              #   ToolRegistry→Dify spec 转换 + YAML 导出
│   │   └── router.py              #   FastAPI /dify/* 路由
│   ├── data_agent/                # 数据采集（M3 待实现）
│   ├── analysis_agent/            # 数据分析 NL2SQL（M3 待实现）
│   ├── hr_agent/                  # HR 分析（M3 待实现）
│   └── map_agent/                 # 地图空间分析（M3 待实现）
├── shared/                        # 跨模块共享
│   ├── sdk/                       #   可观测性 SDK 适配层
│   │   ├── trace.py               #     TraceContext + PII 脱敏
│   │   ├── context.py             #     contextvars 线程安全 TraceContext
│   │   ├── decorators.py          #     @traced 装饰器
│   │   ├── backends.py            #     日志后端 + register_backend
│   │   └── otel_backend.py        #     OTel/Langfuse 可插拔后端 (FDE_OTEL_ENABLED=1)
│   ├── utils/                     #   通用工具
│   │   ├── config.py              #     load_config
│   │   ├── ids.py                 #     new_uuid / short_id
│   │   ├── hashing.py             #     hash_content
│   │   ├── retry.py               #     retry_async（非阻塞 asyncio.sleep）
│   │   └── validators.py          #     ensure_dir / safe_filename
│   ├── models/                    #   共享 Pydantic 模型
│   │   ├── base.py                #     TimestampedModel
│   │   ├── pii.py                 #     PiiString
│   │   ├── user.py                #     User
│   │   └── api.py                 #     PaginatedResponse / HealthResponse / ErrorDetail
│   └── prompts/                   #   共享 Prompt 模板注册表
│       ├── templates.py           #     SYSTEM_ROUTER / SYSTEM_RAG / SYSTEM_ANTI_FOOLPROOF
│       └── registry.py            #     get_prompt / register_prompt / list_prompts
├── frontend/map-ai/               # Vue 3 + Vite 前端（MapAI 看板 + AI 对话）
├── tests/                         # 顶层集成测试 + E2E 测试
├── docs/                          # 架构审计报告 + Code Review 记录
├── pyproject.toml                 # 项目配置 + 可选依赖分组
├── docker-compose.dev.yml         # 开发环境服务 (PG/Redis/Qdrant/MinIO)
└── Makefile                       # 统一命令入口
```

## 代码风格与规范

- 行宽 100，Black 格式化，Ruff 检查
- mypy strict 模式运行于 `conftest.py shared/ agents/ tests/`
- Python 3.11+ 语法（`StrEnum`、`X | Y` 联合类型、`Self`）
- 提交前必须通过 pre-commit hooks
- 异步函数中使用 `await asyncio.sleep()`，禁止 `time.sleep()`
- 新增模块必须包含 `__init__.py`、`models.py`（Pydantic 模型）、`tests/` 目录

## 产出物质量基线

- 新增代码必须有对应测试，覆盖率不低于模块平均值
- 新增公开函数/类必须有 docstring
- 新增模块必须有 `__init__.py` 导出说明（`__all__`）
- PR 描述必须包含"影响范围"字段，列出可能受影响的模块
- 新增工具必须注册到 ToolRegistry 并有 handler 测试
- 新增 Worker 必须在 Supervisor `_mock_plan` 中添加关键词路由

## 提交规范

```
feat(module): 简要描述
fix(module): 简要描述
test(module): 简要描述
refactor(module): 简要描述
docs(module): 简要描述
chore: 简要描述
```

- 每个 PR 关联一个 GitHub Issue（在 PR 描述中写 `Closes #XX`）
- PR 必须通过 CI（ruff + black + mypy + pytest）
- PR 必须至少 1 个 approve 后合并

## 分支命名规范

```
feat/<module>/<task-id>     # 新功能
fix/<module>/<task-id>      # bug 修复
test/<module>/<task-id>     # 测试补充
refactor/<module>/<task-id> # 重构
docs/<module>/<task-id>     # 文档
```

示例：`feat/rag-agent/m3-t1`、`fix/orchestrator/m2-t8`、`test/governance/edge-cases`

---

## 多 Agent 协作流程

### 角色分工

| Agent | 适用任务 | 选型理由 | 推荐模型特征 |
|-------|----------|----------|-------------|
| **主 Agent** | 架构设计、核心逻辑、跨模块集成、P0 bug | 深度推理能力强 | 长上下文 + 强推理 |
| **辅助 Agent** | 测试编写、bug 修复、文档补充、批量修改 | 成本低、迭代快 | 快速 + 低成本 |
| **评审 Agent** | 代码评审、安全审计、重构建议、架构分析 | 长上下文分析能力强 | 超长上下文 |

> 具体使用哪个 AI 产品担任各角色由团队自行决定，上表仅描述能力需求。

### 典型任务分配示例

| 任务 | 角色 | 示例 |
|------|------|------|
| 实现 LangGraph 新 Worker | 主 Agent | 新增 ComplianceWorker + 工具注册 + 图集成 |
| 为现有模块补边界测试 | 辅助 Agent | 为 ConflictDetector 补空输入/类型边界测试 |
| 全模块 Code Review | 评审 Agent | M1-M2 架构合规性审计 |
| 修 ruff/mypy 报错 | 辅助 Agent | 批量修复类型标注 |
| 设计冲突裁决算法 | 主 Agent | 4 检测规则 + 4 裁决策略 |

### 工作模式：串行主线 + 并行辅助

三个 agent **不追求同时写同一模块的代码**，而是按以下方式协作：

```
主线 Agent ──→ 核心功能开发（独占分支）
辅助 Agent ──→ 独立任务：补测试、修 CI、写文档（不冲突的文件）
评审 Agent ──→ 已完成代码的 review（只读 + 评论，不改代码）
```

只有在主线 Agent 和辅助 Agent 的工作**确认无文件交叉**时，才使用 Git Worktree 并行：

```bash
# 仅当需要并行开发时启用
git worktree add ../fde-agent-a  feat/rag-agent/m3-t1
git worktree add ../fde-agent-b  test/governance/edge-cases

# 并行开发前检查文件交叉
git diff --name-only main...feat/rag-agent/m3-t1   > /tmp/files-a.txt
git diff --name-only main...test/governance/edge-cases > /tmp/files-b.txt
comm -12 <(sort /tmp/files-a.txt) <(sort /tmp/files-b.txt)
# 输出为空 = 无冲突，可安全并行；有输出 = 需协调
```

> **无文件交叉判断标准**：两个任务的改动文件列表无交集（通过 `git diff --name-only` 验证）。不确定时，默认串行。

### 核心工作流

```
1. 人创建 GitHub Issue
   - 标题遵循 Conventional Commits 格式
   - 描述中包含：背景、预期行为、验收标准
   - Label 体系（三套，正交）：
     - 复杂度：complexity:high / complexity:medium / complexity:low
     - 模块：module:router / module:rag / module:langgraph / module:map / module:governance / module:compliance / module:business / module:im / module:client / module:data / module:analysis / module:hr
     - 类型：type:feature / type:bug / type:test / type:refactor / type:docs
   - Assign 给对应 agent

2. Agent 开始工作
   - 先读本文件 (AGENTS.md) 了解项目约束
   - 再读 Issue 描述了解任务要求
   - 按需读具体代码文件（不要一次性加载全库）

3. Agent 提交 PR
   - PR 描述关联 Issue（Closes #XX）
   - PR 描述包含：改动摘要、测试方式、影响范围
   - CI 自动运行（lint + typecheck + test）

4. 评审 Agent Review
   - 人分配评审 agent review PR
   - 评审 agent 在 PR 评论中给出反馈
   - 作者修改后重新提交

5. 合并
   - CI 全绿 + 至少 1 approve → 合并到 main
   - Issue 自动关闭
```

### 渐进式上下文加载（防上下文腐烂）

agent 在读代码时遵循以下顺序，避免一次性加载过多上下文：

```
第 1 步：读 AGENTS.md（本文件）→ 了解项目约束和目录结构
第 2 步：读目标模块的 __init__.py + README.md → 了解模块职责
第 3 步：读目标文件 → 按需读取具体实现
第 4 步：如需了解跨模块关系 → 只读 import 链涉及的文件
```

**禁止**：在开始任务时一次性扫描整个代码库。

### 任务交接协议

当 agent 需要交接（会话过长、任务切换、能力不匹配）时：

**在 GitHub Issue 评论中写交接摘要**，格式：

```
@[下一个agent] 交接说明：

## 已完成
- [具体改动 1]（文件路径）
- [具体改动 2]（文件路径）

## 未完成
- [剩余任务 1]
- [剩余任务 2]

## 关键决策
- [为什么选择方案 A 而不是方案 B]

## 验证方式
`make test tests/test_xxx.py`
```

**不需要**单独创建交接文档文件。Git 提交历史 + Issue 评论就是最可靠的交接上下文。

### 纠偏机制

| 场景 | 处理方式 |
|------|----------|
| CI 失败 | CI 自动阻断合并，作者必须修复 |
| 代码风格漂移 | pre-commit hooks + ruff/black CI 自动拦截 |
| Issue 3 天无更新 | 人介入判断是否 blocked，重新分配或调整范围 |
| Agent 输出质量下降 | 人开新会话，在 Issue 评论中留下精炼摘要供新会话参考 |
| Agent 产出无法编译/运行 | 人检查 Issue 描述是否清晰 → 补充上下文 → 重新分配或改为主 Agent 接手 |
| 跨模块冲突 | 人协调，明确各 agent 的文件边界 |

### Token / 上下文管理原则

- **任务粒度控制**：一个 Issue 应该是一个聚焦任务，预期 1-2 个会话内完成
- **及时拆分**：如果一个 Issue 在 30 轮对话内没完成，拆成多个子 Issue
- **不追求自动监控**：token 管理是人的责任，不是 agent 的责任
- **交接靠 Issue 评论**：不依赖 agent 在上下文腐烂后写出高质量交接文档

## 本地调试端口分配

多 agent 同时本地调试时，各使用不同端口避免冲突：

| Agent | 端口范围 | 分配规则 |
|-------|----------|----------|
| 主 Agent | 8080 | 默认，Router Agent 主服务 |
| 辅助 Agent | 8081-8089 | 按需递增，先到先得 |
| 评审 Agent | 8090 | 只读分析，固定 |

通过环境变量 `FDE_PORT=8081` 指定，不修改代码中的默认值。

多 agent 同时调试时，在 Issue 评论中声明占用的端口号，避免撞车。
