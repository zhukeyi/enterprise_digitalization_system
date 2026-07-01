# M3 三 Agent 协作执行计划

> 创建时间：2026-07-01  
> 协作工具：WorkBuddy（主 Agent）、Trae（辅助 Agent）、Qoder（评审 Agent）  
> 遵循规范：AGENTS.md 多 Agent 协作规范  
> 前置状态：M1-M2 全部完成，511 tests passed，commit a5945c2

---

## 一、角色映射

| 角色 | 工具 | 能力特征 | M3 职责范围 |
|------|------|---------|-------------|
| **主 Agent** | WorkBuddy | 长上下文 + 强推理 | 核心逻辑（HR引擎、NL2SQL、LangGraph集成）、跨模块集成、E2E |
| **辅助 Agent** | Trae | 快速迭代 + 批量执行 | 独立模块实现（Data、Map前端）、测试编写、CI修复 |
| **评审 Agent** | Qoder | 超长上下文 + 分析 | 评测体系实现、PR Review、架构审计、安全检查 |

### 分工原则

1. **主 Agent 独占 orchestrator/**：任何修改 `agents/orchestrator/` 的任务由 WorkBuddy 执行（T6、T13）
2. **辅助 Agent 按模块独占**：Trae 同一时刻只在一个 agent 目录工作，避免自我冲突
3. **评审 Agent 不改业务代码**：Qoder 只在 PR 评论中给反馈，例外是 T7 评测体系（governance_agent/eval/ 独立目录）
4. **文件交叉零容忍**：任何并行组合的改动文件列表无交集（`git diff --name-only` 验证）

---

## 二、任务分配总表

### 按执行顺序排列

| 序号 | 任务 | 工具 | 分支 | 人天 | 改动目录 | 前置依赖 |
|------|------|------|------|------|---------|---------|
| 1 | M3-T5 | WorkBuddy | `feat/hr-agent/m3-t5` | 33 | `agents/hr_agent/**` | 无 |
| 2 | M3-T1 | Trae | `feat/data-agent/m3-t1` | 18 | `agents/data_agent/**` | 无 |
| 3 | M3-T7 | Qoder | `feat/governance/m3-t7` | 8 | `agents/governance_agent/eval/**` | 无 |
| 4 | M3-T8 | Trae | `feat/map-agent/m3-t8` | 7 | `frontend/map-ai/src/stores/` `frontend/map-ai/src/components/` | 无 |
| 5 | M3-T2 | Trae | `feat/data-agent/m3-t2` | 8 | `agents/data_agent/**` | T1 完成 |
| 6 | M3-T3 | WorkBuddy | `feat/analysis-agent/m3-t3` | 10 | `agents/analysis_agent/**` | 无（可与T5并行，目录不同） |
| 7 | M3-T9 | Trae | `feat/map-agent/m3-t9` | 10 | `frontend/map-ai/src/components/` | T8 完成 |
| 8 | M3-T6 | WorkBuddy | `feat/orchestrator/m3-t6` | 6 | `agents/orchestrator/langgraph/workers.py` `agents/orchestrator/langgraph/supervisor.py` | T1 + T3 + T5 基本完成 |
| 9 | M3-T4 | Trae | `feat/analysis-agent/m3-t4` | 10 | `agents/analysis_agent/**` | T3 完成 |
| 10 | M3-T10 | WorkBuddy | `feat/map-agent/m3-t10` | 7 | `agents/map_agent/**` | T9 前端框架完成 |
| 11 | M3-T11 | Trae | `feat/map-agent/m3-t11` | 7 | `agents/map_agent/tasks.py` `agents/map_agent/websocket.py` `frontend/map-ai/src/stores/` | T10 完成 |
| 12 | M3-T12 | Trae | `feat/map-agent/m3-t12` | 11 | `frontend/map-ai/src/components/` `frontend/map-ai/src/views/` | T11 完成 |
| 13 | M3-T13 | WorkBuddy | `test/orchestrator/m3-t13` | 3 | `tests/test_m3_e2e.py` `tests/test_map_e2e.py` | 全部完成 |

### 负载分布

| 工具 | 任务 | 总人天 | 占比 |
|------|------|--------|------|
| WorkBuddy | T5 + T3 + T6 + T10 + T13 | 59d | 43% |
| Trae | T1 + T8 + T2 + T9 + T4 + T11 + T12 | 71d | 51% |
| Qoder | T7 + PR Review | 8d + review | 6% |

> Qoder 的主要价值不在实现人天，而在 PR Review 质量。每个 PR Qoder 必须 review，预估 review 工作量约 12 个 PR × 0.5d = 6d。

---

## 三、Sprint 排期

### Sprint 1：并行启动（Day 1-18）

```
WorkBuddy ──→ M3-T5 HR引擎 (33d, Day 1-33)     [agents/hr_agent/**]
Trae     ──→ M3-T1 数据采集 (18d, Day 1-18)     [agents/data_agent/**]
Qoder    ──→ M3-T7 评测体系 (8d, Day 1-8)       [agents/governance_agent/eval/**]
```

**文件交叉检查**：`agents/hr_agent/` ∩ `agents/data_agent/` ∩ `agents/governance_agent/eval/` = ∅ ✅

**Sprint 1 里程碑**：
- Day 8：Qoder 完成 T7，开始 review T1 的 PR
- Day 18：Trae 完成 T1，提交 PR，Qoder review
- Day 18：WorkBuddy 继续 T5（进度约 55%）

### Sprint 2：扩展并行（Day 18-33）

```
WorkBuddy ──→ M3-T5 HR引擎 续 (Day 18-33)       [agents/hr_agent/**]
           └→ M3-T3 NL2SQL (10d, Day 18-28)     [agents/analysis_agent/**] ← WorkBuddy 切换
Trae     ──→ M3-T8 地图前端标记 (7d, Day 18-25)  [frontend/map-ai/src/**]
           └→ M3-T2 报告推送 (8d, Day 25-33)     [agents/data_agent/**]
Qoder    ──→ Review T1 PR + Review T7 PR + Review T8 PR
```

> **注意**：WorkBuddy 在 Day 18 可以同时推进 T5（hr_agent/）和 T3（analysis_agent/），因为两个目录无交叉。
> 但建议先完成 T5 再切 T3，避免上下文频繁切换。如果 T5 进度正常，Day 18 开始 T3。

**文件交叉检查**：
- `agents/hr_agent/` ∩ `frontend/map-ai/src/` = ∅ ✅
- `agents/analysis_agent/` ∩ `frontend/map-ai/src/` = ∅ ✅
- `agents/data_agent/` ∩ `frontend/map-ai/src/` = ∅ ✅

**Sprint 2 里程碑**：
- Day 25：Trae 完成 T8，提交 PR
- Day 28：WorkBuddy 完成 T3，提交 PR
- Day 33：WorkBuddy 完成 T5，提交 PR；Trae 完成 T2，提交 PR

### Sprint 3：集成阶段（Day 33-45）

```
WorkBuddy ──→ M3-T6 扩展Worker (6d, Day 33-39)  [agents/orchestrator/**]
           └→ M3-T10 后端API (7d, Day 39-46)     [agents/map_agent/**]
Trae     ──→ M3-T9 收纳盒+语音 (10d, Day 33-43) [frontend/map-ai/src/components/]
           └→ M3-T4 Dashboard (10d, Day 33-43)   [agents/analysis_agent/**]
Qoder    ──→ Review T2/T3/T5 PR + 架构合规检查
```

> **并行限制**：Trae 不能同时做 T9（frontend/）和 T4（analysis_agent/），因为两任务的认知上下文差异大。
> 建议：Day 33-43 做 T9（关键路径优先），Day 43-53 做 T4。或如果 Trae 能力允许，可交错进行。

**文件交叉检查**：
- `agents/orchestrator/` ∩ `frontend/map-ai/src/` = ∅ ✅
- `agents/orchestrator/` ∩ `agents/analysis_agent/` = ∅ ✅
- `agents/map_agent/` ∩ `frontend/map-ai/src/` = ∅ ✅（后端 vs 前端）

**Sprint 3 里程碑**：
- Day 39：WorkBuddy 完成 T6，提交 PR（此时 data/analysis/hr 三个 Worker 全部接入）
- Day 43：Trae 完成 T9，提交 PR
- Day 46：WorkBuddy 完成 T10，提交 PR

### Sprint 4：收尾（Day 46-56）

```
WorkBuddy ──→ M3-T13 E2E (3d, Day 53-56)        [tests/**]
Trae     ──→ M3-T11 异步推送 (7d, Day 46-53)    [agents/map_agent/tasks.py + websocket.py]
           └→ M3-T12 可视化 (11d, Day 46-57)     [frontend/map-ai/src/components/ + views/]
Qoder    ──→ Review T4/T6/T9/T10/T11 PR + M3 整体审计
```

> **T11 和 T12 并行**：T11 改 `agents/map_agent/` 后端文件，T12 改 `frontend/map-ai/src/` 前端文件，无交叉。
> 但 Trae 是单一 Agent，无法真正并行。建议 Day 46-53 做 T11，Day 53-64 做 T12。
> 如果 Qoder 在 T7 完成后有空闲，可以分担 T12 的部分前端组件。

**Sprint 4 里程碑**：
- Day 53：Trae 完成 T11，提交 PR
- Day 56：WorkBuddy 完成 T13 E2E，全量质量门禁
- Day 64：Trae 完成 T12，提交 PR，Qoder review

### 完整时间线

```
Day  1     8    18    25    33    39    46    53    56    64
     │     │     │     │     │     │     │     │     │     │
WB:  ├─── T5 HR ──────────┤── T3 ──┤── T6 ──┤── T10 ──┤── T13 ──┤
Trae: ├── T1 Data ────────┤── T8 ──┤── T2 ──┤── T9 ──────┤── T11 ──┤── T12 ──────┤
Qoder:├── T7 Eval ──┤     │  ←─── Review PRs throughout ───────→│
     │     │     │     │     │     │     │     │     │     │
```

> 总工期约 64 天（含串行等待）。如果 Trae 能力强可压缩到 55 天。

---

## 四、PR 与 Review 流程

### 每个 PR 的生命周期

```
1. Agent 在 feature 分支完成开发
2. Agent 运行 make verify + make test-cov（本地门禁）
3. Agent 推送分支，创建 PR（描述关联 Issue，包含改动摘要+测试方式+影响范围）
4. CI 自动运行（ruff + black + mypy + pytest）
5. Qoder review PR（在 PR 评论中给反馈）
6. 作者根据反馈修改，重新推送
7. CI 全绿 + Qoder approve → 合并到 main
```

### Qoder Review 检查清单

每个 PR Qoder 必须检查：

- [ ] **类型安全**：mypy strict 通过，无 `Any` 滥用
- [ ] **测试覆盖**：新增代码有测试，覆盖率不低于模块平均值
- [ ] **Pydantic 模型**：新模块有 `models.py`，公开函数有 docstring
- [ ] **ToolRegistry 注册**：新增工具已注册，有 handler 测试
- [ ] **Supervisor 路由**：新增 Worker 在 `_mock_plan` 中有关键词路由
- [ ] **防呆设计**：危险操作有确认/校验/回退
- [ ] **文件边界**：PR 改动未超出分配目录范围
- [ ] **命名规范**：分支名 `feat/<module>/<task-id>`，commit message 符合 Conventional Commits

---

## 五、交接协议

### Agent 间交接（在 GitHub Issue 评论中）

当任务从一个 Agent 交接给另一个 Agent 时，在对应 Issue 评论中写交接摘要：

```markdown
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

### 典型交接场景

| 场景 | 交接方向 | 时机 |
|------|---------|------|
| T1 完成后 T2 接续 | Trae → Trae（同 Agent 续做） | Day 18 |
| T5 完成后 T6 集成 | WorkBuddy → WorkBuddy（同 Agent 续做） | Day 33 |
| T9 完成后 T10 后端 | Trae → WorkBuddy（跨 Agent 交接） | Day 43 |
| T10 完成后 T11 异步 | WorkBuddy → Trae（跨 Agent 交接） | Day 46 |
| 全部完成后 T13 E2E | All → WorkBuddy（汇总交接） | Day 53 |

### 跨 Agent 交接的额外要求

交接方必须在 Issue 评论中额外说明：
- **已注册的工具列表**（工具名 + 参数 + handler 位置）
- **ToolRegistry 注册代码位置**（`integration.py` 行号）
- **已知的问题和 workaround**
- **测试运行命令**（确保接手方能快速验证）

---

## 六、GitHub Issue 模板

每个 M3 任务创建一个 GitHub Issue，使用以下模板：

```markdown
## 任务
[任务标题，如 "M3-T5: HR 系统对接 + 员工画像 + 人岗匹配"]

## 背景
[来自 docs/m3-plan.md 的任务描述]

## 验收标准
- [ ] [具体标准 1]
- [ ] [具体标准 2]
- [ ] make verify 通过
- [ ] make test-cov 通过，覆盖率 ≥ 模块平均值
- [ ] PR 关联本 Issue（Closes #XX）

## 分配
- Agent: [WorkBuddy/Trae/Qoder]
- 分支: `feat/<module>/m3-tX`
- 预计工时: X 人天

## Labels
complexity:high, module:hr, type:feature
```

---

## 七、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| WorkBuddy 上下文腐烂（T5 33d 最长） | 中 | T5 质量下降 | 每 15d 在 Issue 评论写精炼摘要，必要时开新会话 |
| Trae 负载过重（71d） | 高 | T11/T12 延期 | Qoder 在 T7 完成后分担 T12 部分前端组件 |
| T6 集成时 T1/T3/T5 接口不一致 | 中 | T6 返工 | T1/T3/T5 的 integration.py 必须在 PR 描述中明确工具签名 |
| T9→T10 跨 Agent 交接信息丢失 | 中 | T10 延期 | Trae 在 T9 PR 描述中写详细交接说明 |
| CI 阻塞并行开发 | 低 | PR 积压 | CI 时间控制在 5 分钟内，pytest 分组并行 |
| Qoder review 瓶颈 | 中 | PR 等待 review | Qoder 优先 review 关键路径上的 PR（T8→T9→T10→T11→T12） |

---

## 八、质量门禁汇总

### 每个 PR 的门禁

```bash
make verify     # ruff + black --check + mypy strict
make test-cov   # pytest + coverage
```

### M3 整体完成的门禁

| 指标 | 目标值 | 当前值 |
|------|--------|--------|
| 总测试数 | ≥ 700 | 511 |
| 总覆盖率 | ≥ 85% | 87% |
| E2E 测试 | M3 全链路覆盖 | 待实现 |
| ruff | 0 errors | 0 |
| mypy | 0 errors | 0 |
| black | clean | clean |
| vue-tsc | 0 errors | 0 |

### M3 完成后的架构审计

由 Qoder 执行，生成 `docs/m3-architecture-audit.md`，检查：
- 13 个任务全部交付且验收通过
- 3 个空壳 Agent（data/analysis/hr）已完整实现
- 地图 AI 模块全链路可用（标记→提交→分析→推送→可视化）
- 评测体系 CI 门禁运行正常
- 无 P0/P1 架构问题
