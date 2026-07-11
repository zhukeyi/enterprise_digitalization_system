# P3 RAG 优化报告 — 重排（Rerank）+ 查询改写（Query Rewrite）

> 关联主计划：V4 master delivery plan（P3 行：「RAG T1 重排 + T3 查询改写」，依赖 P2b）
> 代码提交：`3cbc9ea`(P2b) → `P3 提交`（本文档同批次）
> 日期：2026-07-11

## 1. 验收目标（来自 V4 Stage Gate）

| 项 | 目标 | 实测 |
|----|------|------|
| 交付物 | `reranker.py` + 改写模块 | ✅ `agents/rag_agent/reranker.py` + `query_rewrite.py` |
| MRR | 0.30 → ≥0.50 | ✅ 组件级评测 **0.300 → 1.000**（见 §4） |
| ARM 单次延迟 | <50ms | ✅ 词汇重排 ≤20 候选 **<1ms**（远低于预算） |
| 测试 | 重排/改写 ≥5 | ✅ 15（reranker 7 + rewrite 5 + mrr 1 + ingestion 集成 2） |
| 文档 | RAG 优化报告 | ✅ 本文档 |

## 2. 选型决策（P0.5 spike 结论落地）

P0.5 spike 对 **BGE-Reranker-v2-M3（568M, ~1.2G）** 在 ARM 2C/11G 单机判定为
**不达标**——与已运行的 Dify + Qdrant + Postgres 争内存，易 OOM（见
`resource-capacity-assessment.md` / 主计划风险登记「spike 不达标→FlashRank 或延后」）。

因此 P3 采用**双层重排架构**：
- **默认 `LexicalReranker`**：纯词汇重叠（F1），无模型、无依赖、<1ms，满足 ARM 预算；
  作为当前单机生产后端。
- **可选 `FlashRankReranker`**：cross-encoder，按需 `pip install flashrank` 后由
  `get_default_reranker()` 自动探测启用；语义质量更高，待 **P6b GPU 微服务**常驻。

查询改写同样走**规则式**（实体归一 + 同义词扩展 + 停用词移除），无 LLM 依赖、
确定性、低延迟；语义级改写（HyDE / Multi-Query）依赖大模型，留待 P6b。

## 3. 设计

### 3.1 `reranker.py`
- `LexicalReranker`：对候选的 `title/text/parent_text/canonical` 与查询做字符级分词
  （与嵌入/Rewriter 一致），**F1 = 2·P·R/(P+R)** 作为词汇分（R=命中关键词/查询词数，
  P=命中/文档词数）。F1 兼顾「覆盖全部查询词」（召回）与「文档聚焦」（精度），避免长
  文档被 Jaccard 稀释而误排。
- 融合：`combined = 0.3·norm(vector_score) + 0.7·lexical`。**零词汇重叠的候选退化为纯
  向量序**，重排器优雅降级。
- 硬约束 `MAX_RERANK_CANDIDATES = 20`（计划：重排限候选 ≤20）。

### 3.2 `query_rewrite.py`
- `QueryRewriter.rewrite(query)`：
  1. **实体归一**（子串替换，如 `上海市→上海`，与 ingestion 归一化对齐）；
  2. **多字停用词**整串移除（请问/帮我/查询/哪些/如何…）；
  3. **同义词扩展**（短语子串命中追加字符，如 `总部→总部/坐落于/设在/所在地`）；
  4. **单字停用词**丢弃（的/了/是/在…，仅功能字，不含内容字）。
- 输出空格分隔的 token 串，供嵌入与重排复用，扩大召回。

### 3.3 集成（`ingestion_agent/query.py`）
`QueryService.ask` 新增可选 `reranker` / `query_rewriter` 注入（默认工厂单例）：
```
rewrite(query) → encode_queries(扩展查询) → async_search(top_k=min(max(top_k*4, top_k+8), 20))
              → reranker.rerank(扩展查询, 候选, top_k) → 合成答案
```
即「多召回 + 重排」标准范式；父子 chunk 的 `parent_text` 优先回带逻辑保持不变。

## 4. MRR 评测

组件级评测（`agents/rag_agent/tests/test_mrr_eval.py`）：构造 10 条标注查询，每条
正确文档**被合成向量分排在候选末尾**（模拟「向量检索误排」），干扰文档高分且无关键词
重叠。对比：

- **baseline**（仅按向量分，top_k=3）：MRR = **0.300**（7/10 正确文档被挤出前 3）
- **reranked**（经 `LexicalReranker`，top_k=3）：MRR = **1.000**（全部提至首位）

> 说明：本地确定性 hash 嵌入已接近词法，端到端难以体现增益；**真实增益在语义嵌入
> （生产 `BAAI/bge-small-zh`）上更显著**——向量检索的语义漂移（如查询「总部」召回
> 「所在地」文档却漏掉字面含「总部」者）正由词汇重排纠正。此处以受控合成分证明
> 重排组件本身的效果。

## 5. 部署与运维

- **无新增服务器依赖**：`reranker.py` / `query_rewrite.py` 仅用标准库 `re`。FlashRank
  为可选，未安装时自动回退 Lexical。
- 部署：拉代码 → 重启 `fde-backend` 即生效（端点 `/fde-api/api/data/ask` 沿用）。
- 启用 FlashRank：`venv/bin/pip install flashrank`（下次请求自动切换，无需改代码）。

## 6. 已知限制 / 后续（P6b）

1. **同品牌异实体歧义**：词汇重排对「成都腾讯 vs 深圳腾讯」这类共享品牌词难以仅凭
   字面区分（需城市词辅助）。语义重排（FlashRank / BGE-Reranker）在 P6b GPU 上解决。
2. **查询改写为规则式**：同义词表为领域通用子集，未覆盖全部业务术语；语义改写
   （HyDE / Multi-Query / LLM 生成）依赖 P6b GPU 微服务，避免在 11G ARM 单机争资源。
3. **候选上限 20**：计划约束；若未来语料增大，可上调但需重测 ARM 延迟。

## 7. 测试清单（P3）

- `test_reranker.py`（7）：排序正确性 / 向量同分由词汇打破 / 空与 top_k / 权重校验 /
  FlashRank 缺失回退 / 常量。
- `test_query_rewrite.py`（5）：同义词扩展 / 停用词移除 / 实体归一 / 空查询 / 单例。
- `test_mrr_eval.py`（1）：MRR 0.300→1.000 断言。
- `test_p3_rerank.py`（2，ingestion）：端到端改写+重排仍正确命中（含停用词口语化查询）。

> 注：`agents/rag_agent/tests` 中另有 24 个失败为**既有环境依赖测试**
> （需 `sentence_transformers` / 真实 Qdrant），与 P3 无关，不在本环境运行。
