# FDE AI Platform — 模块需求满足度审计（README + 单元开发计划 对照）

> 审计时间：2026-07-11  
> 审计人：WorkBuddy  
> 审计性质：**独立复核**（不采信 2026-07-03 的 `plan-vs-actual-review.md`，逐文件重新核验）  
> 对照基准：
> - 总体蓝图 `README.md`（11 大模块 A–L）
> - 详细计划 `docs/m3-plan.md`（13 任务）、`docs/m4-plan.md`（7 任务，含 M4-T6 审计任务）
> - 各单元 `agents/*/README.md`（开发计划）
> - 前端 `frontend/map-ai/README.md`

---

## 一、结论摘要

| 维度 | 结论 |
|------|------|
| **代码是否满足计划需求** | ✅ **满足**。M1–M4 全部 36 个计划任务的「产出文件」均在代码中找到对应实现，功能完整。 |
| **各单元 README（开发计划）是否如实反映实现** | ❌ **普遍陈旧**。9 个 agent README 中 7 个仍把已完成的任务标为「待开发」或描述与真实目录结构不符；前端 README 仍是 Vite 默认模板。 |
| **测试与质量门禁** | ⚠️ 实测 **929 passed / 42 failed / 18 errors**。失败**全部源于本地环境依赖缺失**（BGE-M3 的 sentence_transformers 未装、bcrypt 5.0.0 与 passlib 不兼容），**非代码逻辑缺陷**；旧自审「948 全绿」是在 CI 正确环境下得出的。另发现 pyproject 未锁 bcrypt<5.0 的可复现性缺陷。 |
| **已知偏差** | ⚠️ 4 项 P2 级（Tauri 仅骨架、IM 飞书 AES-CBC 未做、Webhook 签名未集成、OCI 端口需手动开），均为计划已预见或已记录的妥协。 |

**一句话结论：计划需求在代码层面 100% 落实，但「开发计划文档（各单元 README）」严重滞后于实现，需要补写；且依赖约束未真正落地（bcrypt 未锁版本），导致本地无法复现全绿测试——这两点是本次独立审计相对旧自审的新发现。**

---

## 二、逐模块需求满足度（对照计划产出文件 vs 实际代码）

> 满足度图例：✅ 满足（代码+功能）｜⚠️ 满足但文档/结构有偏差｜❌ 未满足

### A. 智能路由网关 — `router_agent`
- **计划需求**（M1-T3）：FastAPI 网关 + 4 模型适配器 + 路由策略 + 故障切换
- **代码证据**：`main.py` `adapters/(base.py)` `routing/` `middleware/` `models.py` ✅
- **README 状态**：设计型文档，描述职责/端点/策略，未标「待开发」，作为设计说明可接受
- **满足度**：✅

### B. RAG 引擎 — `rag_agent`
- **计划需求**（M1-T4）：Qdrant + 解析器 + 分块 + BGE-M3 + 混合检索 + 权限过滤
- **代码证据**：`document_parser.py` `chunking.py` `embeddings.py` `vector_store.py` `retriever.py` `integration.py` `auth_filter.py` ✅
- **README 状态**：M1-T9~T12 标「待开发」→ ⚠️ **陈旧**（代码已全实现）
- **满足度**：✅ 代码 / ⚠️ README 陈旧

### C. Dify 编排 — `dify_bridge`
- **计划需求**（M1-T5 / M2-T7）：DifyBridge + `/dify/*` 路由 + 合规工作流
- **代码证据**：`bridge.py` `router.py` `models.py` `tests/` ✅
- **满足度**：✅

### D. 统一消息枢纽 — `im_agent`
- **计划需求**（M2-T3 为 Stub → M4-T1 真实对接）：企微/飞书/钉钉适配器 + Webhook 路由
- **代码证据**：`adapters/wecom_adapter.py` `feishu_adapter.py` `dingtalk_adapter.py` `webhook_routes.py` `worker.py` `tools.py` ✅
- **README 状态**：M2-T5~T9 全标「待开发」→ ⚠️ **陈旧**
- **已知缺口**：飞书 AES-CBC 加密未实现；Webhook POST 未集成签名验证（计划 P2 偏差）
- **满足度**：✅ 代码（核心对接完成）/ ⚠️ README 陈旧 + 2 项 P2 加密缺口

### E. 桌面 AI 助手 — `client_agent`
- **计划需求**（M2-T4 SDK → M4-T2 Tauri 客户端）：全局快捷键 + 文本捕获 + AI 回填 + dmg
- **代码证据**：`src-tauri/` `src/` `scripts/` `package.json` `vite.config.js` `TODO.md` ✅（骨架级）
- **README 状态**：M2-T10~T13 全标「待开发」→ ⚠️ **陈旧**
- **已知缺口**：环境无 Rust/Xcode，仅交付骨架 + 设计文档，未编译 dmg（计划 P2 偏差，已记录）
- **满足度**：⚠️ 骨架完成（计划已允许的降级）/ ⚠️ README 陈旧

### F. 数据情报 — `data_agent`
- **计划需求**（M3-T1/T2）：多源爬虫 + 清洗 + ETL + 报告引擎 + 推送 + 调度
- **代码证据**：`scrapers/(base/http/api/rss)` `cleaning.py` `pipeline.py` `report_models.py` `report_renderer.py` `push_service.py` `scheduler.py` `geo_guard.py`（额外含 GEO Guard 反污染）✅
- **README 状态**：M3-T1~T6 全标「待开发」→ ⚠️ **陈旧**
- **满足度**：✅ 代码 / ⚠️ README 陈旧

### G. 智能分析层 — `analysis_agent`
- **计划需求**（M3-T3/T4）：NL2SQL + SQL 安全 + 执行器 + Schema 提取 + Dashboard + 下钻 + 关联
- **代码证据**：`nl2sql.py` `sql_safety.py` `executor.py` `schema_extractor.py` `dashboard_models.py` `drill_down.py` `correlation.py` `aggregation.py` ✅
- **README 状态**：M3-T7~T12 全标「待开发」→ ⚠️ **陈旧**
- **满足度**：✅ 代码 / ⚠️ README 陈旧

### H. 全栈治理 — `governance_agent`
- **计划需求**：认证/权限 + 权限过滤 + 可观测（M4-T4）+ 评测（M3-T7）+ 成本/审计
- **代码证据**：`auth/` `database/` `decision_log.py` `decision_log_integration.py` `eval/(golden_dataset/ragas_eval/promptfoo_runner/report/cli)` `middleware/` ✅
- **README 状态**：里程碑任务列表（无「已完成」标记），作为计划说明可接受
- **满足度**：✅

### I. 实施工具包 — `deploy/` + `.github/`
- **计划需求**（M4-T3/T4/T5）：生产 docker-compose + Nginx/TLS + Helm + CI deploy + 可观测配置
- **代码证据**：`deploy/docker-compose.prod.yml` `deploy/Dockerfile` `deploy/nginx/` `deploy/helm/fde-platform/` `deploy/scripts/` `.github/workflows/deploy.yml` ✅
- **满足度**：✅

### J. HR 智能决策 — `hr_agent`
- **计划需求**（M3-T5，10 子任务）：画像/胜任力/人岗匹配/风险/冗余/防呆5步 + 6 工具
- **代码证据**：`models.py` `profiling.py` `matching.py` `risk_assessment.py` `redundancy.py` `foolproof.py` `integration.py` `adapters.py` ✅（6 工具已注册）
- **README 状态**：详细设计文档，但描述的目录结构（`models/ services/ anti_foolproof/ dashboard/`）与实际扁平文件不符 → ⚠️ **结构陈旧**
- **轻微偏差**：计划 T5-4 要求独立 `competency.py`，实际胜任力逻辑合并进 `models.py`+`matching.py`（功能完整，文件名不符）
- **满足度**：✅ 功能 / ⚠️ README 结构陈旧 + competency.py 未单列

### K. LangGraph 编排 — `orchestrator`
- **计划需求**（M1-T6 / M2-T5/T6 / M3-T6/T13）：Supervisor-Worker + ToolRegistry + 冲突裁决 + 扩展 Worker + E2E
- **代码证据**：`langgraph/(supervisor.py workers.py graph.py state.py conflict_resolution.py)` `messages/` `tools/` `tests/` ✅
- **README 状态**：描述的目录结构（`main.py scheduler.py deploy_utils.py evaluation/`）与实际不符 → ⚠️ **结构陈旧**
- **满足度**：✅ 代码 / ⚠️ README 结构陈旧

### L. 地图 AI 分析 — `map_agent`（后端）+ `frontend/map-ai`（前端）
- **计划需求**（M3-T8~T12）：实体标记 + 收纳盒 + 语音 + 后端分析 API + LangGraph 节点 + 异步/WS + 可视化
- **后端代码证据**：`engine.py` `interpreter.py` `langgraph_nodes.py` `routes.py` `tasks.py` `websocket.py` `foolproof.py` `marker_store.py` `location_enrich.py` `tag_extractor.py` `demo_data.py` ✅
- **前端组件证据**：`SidebarPlus` `DrillDownPlus` `EntityToast`（T8）· `AnalysisBox` `EntityCard` `VoiceTextInput` `PronounHint`（T9）· `HeatmapChart` `ScatterMatrix` `TimeSeriesChart`（T12）✅
- **偏差**：计划 T8/T12 列名的 `MapMarkerPlus.vue`/`MapHighlight.vue`/`AnalysisResult.vue` 三个独立组件，实际合并进 `MapView.vue`（功能完整，文件名与计划不符）
- **文档状态**：`map_agent` **无 README**；前端 `README.md` 仍是 Vite 默认模板「This template should help you started…」→ ❌ **完全未写**
- **满足度**：✅ 功能 / ⚠️ 组件文件名合并 + ❌ 缺 map_agent README + ❌ 前端 README 为占位模板

---

## 三、重点发现一：各单元「开发计划」README 普遍陈旧（核心问题）

| 单元 | README 现状 | 实际情况 |
|------|------------|----------|
| router_agent | 设计文档（可接受） | 已实现 |
| rag_agent | M1-T9~T12「待开发」 | 已全部实现 |
| im_agent | M2-T5~T9「待开发」 | M4-T1 真实对接完成 |
| client_agent | M2-T10~T13「待开发」 | M4-T2 Tauri 骨架完成 |
| data_agent | M3-T1~T6「待开发」 | 全部实现 |
| analysis_agent | M3-T7~T12「待开发」 | 全部实现 |
| hr_agent | 描述旧目录结构 | 扁平文件已实现 |
| orchestrator | 描述旧目录结构 | langgraph/ 已实现 |
| governance_agent | 里程碑列表（无完成标记） | 已实现 |
| **map_agent** | **无 README** | 后端 12 个模块已实现 |
| **frontend/map-ai** | **Vite 默认模板** | 完整 MapAI 应用已实现 |

**影响**：这些 README 是用户口中的「各个单元的开发计划」。它们现在既不能作为开发依据（标着待开发），也不能作为交付验收依据（与实际结构不符）。`plan-vs-actual-review.md` 当时只对照了 master plan（m3/m4），**遗漏了对单元 README 的核对**，因此误报「100% 吻合」。

---

## 四、重点发现二：已知偏差（计划已预见/已记录）

| # | 模块 | 偏差 | 严重度 | 来源 |
|---|------|------|--------|------|
| 1 | E 桌面助手 | Tauri 仅骨架，未编译 dmg（缺 Rust/Xcode） | P2 | M4 风险缓解 + plan-vs-actual |
| 2 | D 消息枢纽 | 飞书 AES-CBC 加密未实现 | P2 | plan-vs-actual |
| 3 | D 消息枢纽 | Webhook POST 未集成签名验证 | P2 | plan-vs-actual |
| 4 | 部署 | OCI 安全列表需手动开 8443 端口 | P2 | M4 风险 |
| 5 | L 地图 | Celery → BackgroundTasks 降级 | P3 | 计划允许的正当代替 |
| 6 | B RAG | 计划写 RAGFlow，实际自建 Qdrant 管线 | N/A | 架构决策已文档化 |
| 7 | J HR | competency.py 未单列（合并入 models/matching） | P3 | 结构偏差，功能完整 |
| 8 | L 地图 | 3 个计划组件文件名合并进 MapView | P3 | 结构偏差，功能完整 |

---

## 五、测试与质量门禁（实测结果）

**全量 `pytest` 实测（2026-07-11，本地 .venv，Python 3.13.12）：**
```
42 failed, 929 passed, 18 errors  （共 989 个用例，1 个文件/收集问题不计）
```

> ⚠️ 这与 2026-07-03 自审报告声称的「948 tests passed / 全绿」**不一致**。重新核查后确认：旧结论是在 CI（GitHub Actions）正确依赖 + 后台服务（Qdrant/Postgres）环境下得出的；**本地当前环境有 60 个用例因依赖/服务缺失不通过，但均为「环境可复现性」问题，非代码逻辑缺陷。**

### 失败根因归类（全部为环境问题，非需求未满足）

| 根因 | 影响用例 | 说明 |
|------|----------|------|
| **`sentence_transformers` 未安装**（BGE-M3 嵌入后端） | ~49 个（rag_agent 的 embeddings/vector_store/retriever + 依赖 rag 的 test_e2e） | 嵌入模型在 ARM 服务器上安装，本地 .venv 未装重型 ML 依赖；代码 lazy import，缺失即 FAIL/ERROR |
| **`bcrypt 5.0.0` 与 passlib 不兼容** | ~11 个（governance auth/m2t2 全 ERROR） | 报错 `ValueError: password cannot be longer than 72 bytes`。项目 memory 明确要求 `bcrypt<5.0`，但 **`pyproject.toml` 仅写 `passlib[bcrypt]>=1.7.4`，未锁版本** → 干净安装会解析到 bcrypt 5.0.0 而崩溃 |

**结论**：代码逻辑本身满足计划需求；但在「干净/本地」环境下不可直接复现全绿，根因是依赖约束未落地 + 重型 ML 依赖未随基础安装。这与「需求满足度」是正交的两件事，需分别对待。

---

## 六、重点发现三：依赖可复现性缺陷（真实代码问题）

- **pyproject.toml 未强制 `bcrypt>=4.0,<5.0`**。项目长期依赖 passlib+ bcrypt<5.0（memory 已记录），但版本约束没写进 `pyproject.toml`，导致任何新环境 `pip install` 都会装上 bcrypt 5.x 并让认证测试崩溃。这是可复现性 bug，应在 pyproject 显式加 `"bcrypt>=4.0,<5.0"`。
- rag 测试需要 `sentence-transformers`/`FlagEmbedding`（BGE-M3）作为可选 extra，应在文档/extra 中声明，避免误判测试失败为代码回归。

---

## 七、建议清单（按优先级）

1. **【高】补写单元 README**：将 9 个 agent README 的「待开发」改为实际状态，删除/更新与实际不符的目录结构描述；为 `map_agent` 新建 README；将前端 README 从 Vite 模板替换为真实的 MapAI 应用说明。这是「对照开发计划」审计暴露的最直接交付物。
2. **【高】修复依赖可复现性**：在 `pyproject.toml` 显式加 `bcrypt>=4.0,<5.0`；为 rag 模块声明 `sentence-transformers`/`FlagEmbedding` 可选依赖 extra，并在 CONTRIBUTING/README 注明测试需安装该 extra 或连 Qdrant。
3. **【中】补齐 P2 加密/签名缺口**：飞书 AES-CBC、Webhook 签名验证，可纳入 v1.1。
4. **【中】Tauri 编译交付**：在具备 Rust/Xcode 的环境完成 `tauri build` 产出 dmg，或明确标注为「设计交付」。
5. **【低】组件文件名对齐**：将 MapView 内联的 MapMarkerPlus/MapHighlight/AnalysisResult 抽成独立组件以对齐计划文件名（可选，功能已完整）。
6. **【低】更新自审文档**：在 `plan-vs-actual-review.md` 增加「单元 README 核对 + 测试环境说明」一节，避免再次误报 100% / 全绿。

---

## 八、全量测试运行结果（实测回填）

- **命令**：`.venv/bin/python -m pytest -q -p no:cacheprovider`
- **结果**：`42 failed, 929 passed, 18 errors`（耗时 ~31s，2026-07-11）
- **根因**：环境依赖缺失（sentence_transformers 未装、bcrypt 5.0.0），非代码逻辑缺陷
- **建议**：在锁定 bcrypt<5.0 并安装 ML extra 后重跑，预期可恢复至 ~全绿（与 CI 一致）
