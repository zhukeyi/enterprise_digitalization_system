# FDE RAG 切片/向量化可视化与可维护性 — 社区动向研究与可行性建议

> 研究目标：评估是否有必要为 FDE 的 RAG 模块做类似 FastGPT 的可视化切片界面，并能检索底层切片/向量化方式、出问题时可维护。
> 研究方法：GitHub 与开发者社区动向调研 + FDE 代码现状审计（未改动任何文件）。

---

## 一、结论速览

**有必要做，但应按 ROI 分层落地，不要一上来就做 FastGPT 式全功能拖拽编排。**

- **社区共识**：RAG 失效 80–90% 的根因在**数据管线与切片**，而非 LLM；"切片层是黑盒"被普遍视为生产事故根源。可视化检视 + 检索回放 + 引用维护，已成为企业级 RAG 的**标配能力**，而非锦上添花。
- **FDE 现状**：底层数据（Qdrant payload + Postgres 表）已具备，但**零读接口、零维护界面**。更关键的是，我在代码里发现一个真实的**嵌入模型配置一致性隐患**（见第五节），恰好说明为什么现在就需要可观测性面板——连团队内部都没有单一事实来源说明"现在到底用什么模型向量化"。
- **推荐路径**：先做 T0（切片只读检视 + 文档删除/重建维护），再做 T1（检索回放/引用改删，对标 FastGPT 核心卖点），T2（交互式切片 Playground）按需。

---

## 二、GitHub / 社区动向证据

### 2.1 FastGPT（标杆，26K+ star，40 万+ 开发者）
FastGPT 的知识库能力明确包含：
- chunk 记录的**修改与删除**、源文件存储
- 手动输入 / 直接分段 / QA 拆分导入
- 混合检索 & 重排、标签过滤
- **知识库单点搜索测试**（检索回放）
- **对话时反馈引用并可修改与删除**
- **完整上下文呈现**、**完整模块中间值呈现**、高级编排 Debug 模式

即：FastGPT 已经把"可视化切片 + 检索回放 + 引用维护"作为核心卖点。对标它方向正确。

### 2.2 2025–2026 涌现的专项调试/可视化工具（这是明确趋势）
| 项目 | 时间 | 定位 |
|---|---|---|
| **raglens** | 2025-08 | token 级 / chunk 级诊断：`chunking_sanity`、`plot_chunk_geometry`、`semantic_similarity_matrix`、retrieval 诊断 |
| **rag-tui** | 2026-06（Show HN） | 终端可视化切片调试器，实时看 chunk 边界/重叠、批量测试命中率、一键导出 LangChain/LlamaIndex 配置。作者原话："tired of guessing `chunk_size=1000` and `overlap=200` ... hoping for the best" |
| **RAGTrace** | 2025 | Vue3 + D3/ECharts 的 RAG 可视化诊断平台：Heatmap、力导向图、ChunkRanking、AnswerTracing（证据链追踪） |
| **LangFuse** | 7.4K star | LLM 全链路追踪（Embedding/Retriever/LLM 耗时、Token 成本），把 RAG 黑盒变"玻璃盒" |

结论：RAG 可观测性（observability）在 2025–2026 已成为独立赛道，资本与社区都在投入。

### 2.3 社区痛点共识（开发者社区高频内容）
- *"RAG 效果差，80% 的问题和模型无关"*（阿里云开发者社区）
- *"从 Demo 到生产：检索失效 3 个深层原因 — 元数据过滤、Embedding 微调、可视化调试(Observability)。不看实际召回的数据块，永远不知道为什么错"*（掘金）
- *"为什么你的 RAG 在生产环境总翻车？问题出在切片……切片日志是调试 RAG 的唯一真话来源"*（网易）
- *"90% 的情况问题在检索不在生成；chunk 策略第一步走错后面全废；混合检索 向量+BM25 是标配"*（稀土掘金调优实战）
- 反复出现的可观测性诉求：**检索回放、chunk 命中率/MRR、引用可改删、切片日志、失败案例聚类**。

---

## 三、FDE 现状与缺口（基于代码探索）

### 3.1 已有的底层数据（利好）
- **Qdrant** 集合 `fde_documents`：payload 存 `text / parent_text / canonical / doc_type / title / source / raw_id / block_kind` → 切片原文、父子关系、来源都在。
- **Postgres**：`raw_documents / canonical_documents / document_chunks`（含 `parent_chunk_id` 自关联、`embedding_id`、`metadata_json`）。
- 两套切片实现：`rag_agent/chunking.py`（FixedSize/Semantic/Recursive，但**未被 ingestion 调用**）、`ingestion_agent/chunking.py`（实际生效的父子切片）。

### 3.2 缺失能力（7 项）
1. 无"按 doc_id 浏览 chunks"读接口与页面。
2. 无 chunk 原文 / 切片方式 / 父子关系查看（Postgres 的 `metadata_json`、`parent_chunk_id` **实际未写入** → 父子链无法从 Postgres 还原，只存于 Qdrant payload）。
3. 无删除文档接口（Qdrant + Postgres + FTS 级联清理缺失）。
4. 无重建 / 重索引、BM25 重建触发接口。
5. 无向量预览 / 检索回放 API。
6. 无切片策略选择 UI（两套 chunker 割裂，生产路径不可配策略名）。
7. 无 chunk 级质量 / 命中率诊断（仅测试脚本 `_run_chunking_checks.py`）。

### 3.3 一个真实的"现在就该修"隐患（可观测性的理由）
代码里嵌入模型默认值**不一致**：
- `rag_agent/embeddings.py:48` 的 `get_default_model_name()` 默认 `BAAI/bge-m3`（dim 1024）；
- 但 ONNX 后端读取的 env 名是 **`FDE_RAG_EMBEDING_MODEL`（拼写错误，少一个 D）**，默认 `BAAI/bge-small-zh-v1.5`（dim 512）；
- `ingestion_agent/store.py:37` 默认后端是 `pytorch`。

后果：
1. 拼写错误导致 ONNX 路径**根本读不到** `FDE_RAG_EMBEDDING_MODEL`；
2. 项目记忆里写的是 `bge-small-zh-v1.5`，但 pytorch 默认是 `bge-m3` —— **连团队内部都没有单一事实来源说明"现在到底用什么模型向量化"**。

这正是切片/向量化可观测面板要解决的头等事：每个集合/文档应能直接显示"用了哪个模型、多少维、什么后端"。

---

## 四、建议方案（按 ROI 三层）

### T0 — 切片检视 + 文档维护（必须做，低成本高价值）≈ 3–4 天
- **后端**：新增只读 API `GET /api/rag/docs`、`GET /api/rag/docs/{id}/chunks`、`GET /api/rag/chunks/{id}`（返回 text、parent_text、chunking 方式、embedding 模型/维度/后端、来源、相似度预览）；新增 `DELETE /api/rag/docs/{id}`（Qdrant+Postgres+FTS 级联）；`POST /api/rag/docs/{id}/reindex`。
- **前端**：portal 新增 `RagInspectorView`（文档列表 → chunk 详情抽屉），先只读，再加删除/重建按钮（带防呆确认）。
- **价值**：立刻把"黑盒"变"玻璃盒"，出问题时能定位是哪段被切坏。

### T1 — 检索回放/调试（对标 FastGPT 核心卖点）≈ 3–5 天
- **后端**：`POST /api/rag/debug/retrieve`（输入 query → 返回召回 chunks、向量相似度、rerank 分数、query rewrite 结果；复用现有 HybridSearch + QueryRewrite + Reranker）。
- **前端**：`RagDebugView`：输入框 + 召回结果列表（高亮命中、显示分数、显示引用）；支持对某个 chunk 标记"有误/修改/删除"（写回反馈，类似 FastGPT 引用维护）。
- **价值**：直接对应社区最高频诉求"检索回放 + 引用改删"，是 FastGPT 差异化的核心。

### T2 — 交互式切片 Playground（高投入，按需）≈ 5–8 天
- **前端**：`ChunkPlaygroundView`：实时调 chunk_size / overlap / 策略（递归/语义/固定/父子），文本流彩色切分预览、标"坏 chunk"（句中切断）、相似度矩阵。
- **后端**：统一两套 chunker 为单一可配工厂，暴露 `POST /api/rag/chunk/preview`。
- **价值**：对标 raglens/rag-tui，但 ROI 低于 T0/T1；建议在企业客户真正提出"我要自己调切片"时再做。

---

## 五、工作量与风险

- **总估算**：T0 约 3–4 天，T1 约 3–5 天，T2 约 5–8 天。T0+T1 约 1.5–2 周即可达到"类 FastGPT 核心可维护性"。
- **前置风险**：
  1. 先补齐 Postgres `metadata_json` / `parent_chunk_id` 落库，让父子链可被查询；
  2. 顺手修掉 embedding env 命名拼写 bug（`EMBEDING` → `EMBEDDING`）并统一默认值；
  3. 维护界面必须带防呆（删除/重建是危险操作，需二次确认 + 操作审计）。
- **不建议**：一上来就做全功能拖拽编排 Flow（FastGPT 重头戏），ROI 低且偏离 FDE 当前企业七步法主线。

---

## 六、下一步建议

1. **推荐先做 T0**（切片检视 + 维护）——这是"有没有必要"的明确答案：有必要且最划算。
2. 若认可，可直接进入实现：先补后端读/删/重建接口 + 修 embedding 一致性，再做 portal 检视页面。
3. 是否现在开始 T0 实现？或先就范围/优先级确认？

---

*调研日期：2026-07-12 ｜ 涉及仓库：FastGPT、raglens、rag-tui、RAGTrace、LangFuse ｜ FDE 代码审计范围：`agents/rag_agent/`、`agents/ingestion_agent/`、`frontend/portal/`*
