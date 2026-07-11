# 测试规约（Testing Spec）

> 落实工程评审 **F1**：测试策略缺失 → 每阶段 ≥80% 覆盖 + CI 门禁。
> 本文件为所有后续阶段（P0→P7）的测试基线，Stage Gate 引用见
> `master-delivery-plan.md` §7。

---

## 1. 原则

1. **测试先行**：新功能先写测试（或 TDD），再写实现。
2. **覆盖率门禁**：每个阶段新增 Python 代码行覆盖率 **≥80%**；低于阈值 CI 红灯。
3. **CI 全绿方可进入下一阶段**（F11 Stage Gate）：`lint + format + typecheck + test` 全绿。
4. **不污染生产**：集成/端到端测试连独立 DB / Qdrant 隔离集合，禁止打生产数据。
5. **可重复、确定性**：禁止测试间共享可变全局状态；时间/随机用可注入桩。

---

## 2. 测试分层（金字塔）

| 层 | 目录 | 工具 | 比例 | 说明 |
|----|------|------|------|------|
| 单元 | `tests/unit/` | pytest + 轻量 mock | ~70% | 纯函数 / 模型 / 工具，最快 |
| 集成 | `tests/integration/` | pytest + testcontainers/本地服务 | ~20% | API ↔ DB ↔ 工具，真实组件 |
| 端到端 | `tests/e2e/` | pytest + 真 HTTP / LangGraph | ~10% | 全链路（如 MVS 上传→问答） |

评测（retrieval 质量）单独见 `tests/eval/` + `docs/master-delivery-plan.md` §2.3。

---

## 3. 工程约定

- **框架**：`pytest`。
- **覆盖率**：`pytest --cov=agents --cov-report=term-missing --cov-fail-under=80`。
- **标记**：`@pytest.mark.slow`（重集成）、`@pytest.mark.integration`、`@pytest.mark.unit`。
  CI 默认 `-m "not slow"`；nightly 跑全量。
- **fixture**：共享 fixture 放 `tests/conftest.py`；DB fixture 用事务回滚（不落盘）。
- **异步**：`pytest-asyncio`，`asyncio_mode = auto`。
- **类型**：`mypy --strict` 在 CI 中运行（见 `.github/workflows/ci.yml`）。
- **导入**：源码以 `agents.*` / `shared.*` 绝对导入，测试加 `conftest.py` 注入仓库根。

---

## 4. 命名与结构

```
tests/
  unit/            # 对应 agents/<agent>/tests/ 也可；本目录放跨模块单测
  integration/     # API + DB 集成
  e2e/             # 全链路
  eval/            # 评测集 + 加载器（P0 建立）
  conftest.py
```

- 测试文件：`test_*.py`；函数：`test_<行为>_<预期>`。
- Mock 外部：LLM / 百度地图 / 连接器 HTTP 用 `respx` 或 `unittest.mock`。

---

## 5. CI Stage Gate（F7/F11）

每次 PR 必须：

```yaml
jobs:
  quality:
    steps:
      - run: make lint        # ruff
      - run: make format      # black --check
      - run: make typecheck   # mypy --strict
      - run: make test        # pytest + cov≥80
      - run: make db-check    # alembic check（ORM 与 DB 一致）
```

四项全绿 + 验收标准达成 + 评测不降级 + 阶段文档增量产出 → 进入下一阶段。

---

## 6. P0 阶段测试要求

P0 本身交付契约/表/规范，**测试交付物**为：

1. `tests/test_connector_contract.py` — 契约模型单测（semver 校验、字段映射、缺字段降级）。
2. `tests/eval/test_eval_dataset.py` — 评测集结构校验（≥50 查询、分域、合法 JSON）。
3. `tests/integration/test_alembic_0003.py`（可选）— 在测试库跑 `upgrade head` 验证 4 表存在。

目标：P0 阶段新增代码覆盖 ≥80%，且为后续 P1/P2 提供可复用测试脚手架。
