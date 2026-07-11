# RAG 性能提升方案（参照大厂生产实践）

> 目标：在现有 RAG 管线（Qdrant + BM25 + BGE + RRF 混合检索）之上，给出**分梯队、可落地、对照大厂**的性能/质量提升路线。
> 基准来自 `rag-deployment-verification-and-perf.md`（模拟 200 篇 → 877 chunk，三档规模实测）。

---

## 0. 当前基线（必须记住的数字）

| 指标 | 实测值 | 说明 |
|------|--------|------|
| 向量检索延迟 p99 | **~6 ms** | 语料 4 倍增长几乎不变（ANN 子线性） |
| 查询嵌入延迟 | **~30 ms** | **单次检索延迟主导项**（CPU 上 BGE 推理） |
| 混合检索端到端 | **~40 ms** | 已含查询嵌入 + BM25 + RRF 融合 |
| BM25 + RRF 融合开销 | ~4–7 ms | 相对向量检索可忽略 |
| 批量嵌入吞吐 | **4.5 chunk/s** | CPU 密集，灌库瓶颈 |
| 关键词 recall@5 | 0.20 → **0.97**（混合后） | 混合检索已被数据验证有效 |
| 整体 MRR | 0.12 → **0.30**（混合后） | 2.5 倍提升 |
| 纯向量 recall@1（语义） | **~0.04** | 小模型 + 合成高相似语料的悲观值；真实库更好 |

**结论**：检索架构（混合 + RRF）是对的，延迟也健康。真正的两大短板是
1. **质量天花板**：MRR 0.30、纯语义 recall 低 → 答案生成器用的是 top-1 chunk，rank-1 不准就直接错；
2. **查询嵌入 30ms** 占去单查大部分延迟，且灌库 CPU 慢。

大厂（Google / Meta / 微软 Azure AI Search / 亚马逊 Bedrock / 字节 / 百度千帆 / 阿里百炼 / 腾讯优图）的 RAG 优化，本质就是围绕这两点做「漏斗 + 精排 + 缓存 + 量化」。

---

## 1. 大厂都在用的 8 个手段（及对照）

| # | 手段 | 大厂实践 | 解决我们哪个短板 | 预期收益 |
|---|------|---------|----------------|---------|
| 1 | **两阶段重排 Cross-Encoder** | Databricks Mosaic（Recall@10 74%→89%）、Vanguard 混合检索、腾讯优图 Reranker 分层蒸馏、阿里 Qwen3-Reranker、Cohere Rerank | MRR 低、rank-1 不准 | NDCG@10 +5~15 点；MRR 估计 0.30→0.5+ |
| 2 | **查询改写**（HyDE / Multi-Query / Step-back） | Azure AI Search 查询扩展、RAG-Fusion 加权融合 | 纯语义 recall 低 | recall@5 +10~30% |
| 3 | **向量量化**（Scalar/Binary + Matryoshka） | Qdrant 官方量化、pgvector int8、Cohere embed 量化 | 内存/延迟/成本 | 内存 4~32x↓，检索 3~40x↑ |
| 4 | **分层索引**（RAPTOR / 父子 chunk / 句窗） | Microsoft GraphRAG、LlamaIndex SentenceWindow | chunk 边界信息丢失 | 答案完整性↑，幻觉↓ |
| 5 | **语义缓存** | 各大厂 RAG 服务标配 | 重复查询重复计算 | 命中查询延迟→<1ms，成本↓ |
| 6 | **嵌入推理加速**（ONNX/OpenVINO + batching） | 字节/百度自研推理优化 | 查询嵌入 30ms 主导 | 30ms→5~10ms |
| 7 | **混合检索调参**（RRF 权重 / α 融合） | Vanguard（BM25+向量加权，精度 +12%） | 已具备，需调优 | 边际提升 |
| 8 | **评测闭环**（标注集 + NDCG@10） | 所有大厂前置动作 | 不知道改了有没有用 | 防止回归 |

> **我们已免费拥有 7（混合+RRF）和 8 的部分（perf 脚本）。** 下面只规划增量。

---

## 2. 分梯队落地路线（按「性价比」排序）

### T0 — 零成本/极低成本「快赢」（建议先做）

| 项 | 改动 | 文件 | 预期 |
|----|------|------|------|
| **T0-1 查询嵌入换 ONNX/OpenVINO** | `EmbeddingModel._load` 支持 `FDE_RAG_EMBED_BACKEND=onnx`，用 `sentence-transformers` 的 ONNX export 或 `optimum` 推理；保持 API 不变 | `rag_agent/embeddings.py` | 30ms → ~5–10ms（单查端到端 40→~20ms） |
| **T0-2 语义缓存（LRU/Redis）** | 同义查询直接返回缓存的 top-k 上下文；以查询向量近邻命中判断 | 新增 `rag_agent/cache.py`，`_rag_search_handler` 前置 | 重复/近重复查询延迟 <1ms，CPU 省 |
| **T0-3 RRF 权重调优** | 在标注集上扫 `bm25_weight / vector_weight / rrf_k`，取最优 | `retriever.py` `HybridSearchConfig` | MRR 边际 +5~10% |
| **T0-4 评测闭环** | 把 `rag_perf_bench.py` 固化为 `make rag-eval`，加 50 条人工标注（query→相关 chunk_id） | `scripts/rag_eval.py` | 量化每次改动效果 |

> T0 全部可在**不引入新重依赖、不换模型**的前提下完成，半天到 1 天。

### T1 — 重排（质量提升最大杠杆）⭐

**为什么是最大杠杆**：我们的 `_rag_answer_handler` 直接拿 **top-1 chunk 当答案**（见 `integration.py:244`）。混合检索把相关块召回进 top-50，但 rank-1 常常不是最相关的——这正是 cross-encoder 的用武之地。大厂经验：cross-encoder 把"召回进了 top-50 但 rank 靠后"的块顶到 rank-1，NDCG@10 普遍 +5~15 点，词汇困难集 +20+。

**方案**：
- 新增 `rag_agent/reranker.py`：`CrossEncoderReranker`，模型默认 `BAAI/bge-reranker-v2-m3`（8k 上下文、多语含中文、10–20ms/doc、可自托管）。备选 `Qwen3-Reranker-4B`（阿里，中文更强）。
- `_rag_search_handler` 改为**漏斗**：先取 top-50（现有 BM25+向量+RRF）→ reranker 精排 → 返回 top-5。`RERANK_TOP_N` 可配。
- **ARM 现实约束**：2 核 ARM 跑 50 个 cross-encoder 推理可能 1–2s。两种务实做法：
  - 轻量版：`FlashRank`（`ms-marco-MiniLM-L6`）本地跑，整批 ~50ms，质量略低但够用；
  - 标准版：rerank 仅 top-10~20，并放到**独立 GPU/强机型**的 rerank 微服务（与 ARM 查询节点解耦）。
- 代码示意（不破坏现有 `rag_search` 契约）：
  ```python
  # integration.py 内
  candidates = await engine.search(query, top_k=50)        # 现有混合
  if reranker and candidates:
      reranked = reranker.rerank(query, [c.content for c in candidates], top_n=top_k)
      candidates = [candidates[i] for i in reranked.indices]
  ```

**预期**：MRR 0.30 → 0.50+，且"答案块"命中率大幅上升 → 直接降幻觉。

### T2 — 嵌入升级 + 量化（成本/规模）

| 项 | 做法 | 文件 | 预期 |
|----|------|------|------|
| **T2-1 升级到 bge-m3（1024d）** | 现已支持 `FDE_RAG_EMBEDDING_MODEL`，生产强机型重灌库 | `embeddings.py`（已就绪） | 语义 recall 显著高于 bge-small |
| **T2-2 Qdrant 标量量化** | `create_collection` 加 `quantization_config=ScalarQuantizationConfig()`（int8，4x 内存↓，~3–5x 检索↑，召回 ~99%） | `vector_store.py` | 内存/延迟双降，规模化的地基 |
| **T2-3 二值量化（可选）** | 高维（≥1024）模型配 Binary Quantization + 3x oversampling + rescore，32x 内存↓ | `vector_store.py` | 亿级向量也可跑；当前语料小，暂缓 |
| **T2-4 Matryoshka 截断** | bge-m3 支持 Matryoshka，可截断到 512d 再 int8 → 8x 存储↓ | `embeddings.py` | 存储/延迟再降 |

> 量化是 Qdrant 的**配置开关**，几乎零代码；唯一注意：小语料量化收益有限，建议 T2-2 随语料增长开启。

### T3 — 查询改写（补语义召回）

- 新增 `rag_agent/query_rewrite.py`，三种可选策略（开关控制）：
  - **HyDE**：用 LLM 生成"假设答案"再向量化，弥补 query-doc 语义鸿沟；
  - **Multi-Query / RAG-Fusion**：LLM 生成 3–5 个改写变体，分别检索后 RRF 再融合；
  - **Step-back**：先问"更抽象的问题"再检索，适合多跳。
- 改写只在**首轮检索**前做，rerank 仍用原始 query 保证相关性判断不被污染。
- **ARM 约束**：改写要调 LLM，走现有路由网关即可，不增加本地负担；但会增加一次 LLM 延迟（可异步/并行）。

**预期**：纯语义 recall@1 由 ~0.04 显著提升，复杂/口语化问法命中率↑。

### T4 — 切片与索引结构升级（补信息完整度）

- `chunking.py` 新增：
  - **SentenceWindowChunker**（句窗）：检索用小窗口，返回时扩成整段上下文 → 解决"答案句在 A chunk、支撑在 B chunk"；
  - **父子 chunk**（表格父/子已在 ingestion 计划中）：父存全文，子用于精确检索，命中后回贴父；
  - **RAPTOR 分层**（可选，重）：递归聚类→摘要→建树，回答全局/聚合性问题（"本季度各仓库存趋势？"）。
- `retriever.py` 命中后做"子→父"上卷，把完整上下文喂给答案生成。

### T5 — 规模化部署

- **嵌入/重排独立服务**：ARM 查询节点只做检索+融合；重推理（embed/rerank）放 GPU 微服务（与 T1 解耦一致）。
- **批处理 + 队列**：灌库走异步 worker（ARQ/Celery），批量 embed（已支持 `embed_batch`）压满 GPU。
- **Qdrant 分布式**：单节点 → 集群分片（`shard_number` / 复制），量化后内存可控。

---

## 3. 映射到现有代码的改动清单

| 文件 | 改动 |
|------|------|
| `rag_agent/embeddings.py` | T0-1 ONNX 后端开关；T2-1/4 模型与 Matryoshka 截断 |
| `rag_agent/vector_store.py` | T2-2/3 `create_collection` 量化配置；payload 索引（按 `source_system`/`doc_type` 过滤） |
| `rag_agent/reranker.py` | **新增**，T1 cross-encoder 重排 |
| `rag_agent/query_rewrite.py` | **新增**，T3 HyDE/Multi-Query |
| `rag_agent/cache.py` | **新增**，T0-2 语义缓存 |
| `rag_agent/chunking.py` | T4 句窗/父子/RAPTOR |
| `rag_agent/integration.py` | `_rag_search_handler` 串 rerank + rewrite + cache（漏斗） |
| `rag_agent/retriever.py` | T0-3 RRF 权重；T4 子→父上卷 |
| `scripts/rag_eval.py` | **新增**，T0-4 评测闭环（沉淀 perf 脚本） |

---

## 4. 推荐执行顺序与预期总收益

```
T0（快赢，1 天）→ T1（重排，质量最大杠杆，2–3 天）→ T2（量化，随规模开启）
                  → T3（改写，补语义）→ T4（切片结构）→ T5（规模化）
```

**累计预期**（相对基线）：
- 单查端到端延迟：40ms → **~20ms**（ONNX）+ 缓存命中趋近于 0；
- MRR：0.30 → **0.5+**（重排主导）；
- 答案块命中率：显著提升（直接降幻觉）；
- 语义 recall@1：~0.04 → **0.2+**（改写 + bge-m3）；
- 存储/成本：量化后 **4~32x↓**，支撑语料从千级到千万级向量。

> 每一步都用 T0-4 的标注集量化，避免"优化"变"退化"。**先 T0 + T1**，是性价比最高、且能在当前 ARM 机器上立即见效的组合。

---

## 5. 风险与注意

1. **重排在 ARM 上的延迟**：务必限制 rerank 候选数（top-10~20）或上独立 GPU 服务，否则 2 核机器会被拖垮。
2. **量化在小语料上收益有限**：457 点当前不开量化也没问题，等语料到 10 万+ 再开；且量化要"先关后开"对比评测。
3. **改写可能引入噪声**：Multi-Query 变体过多会稀释相关结果，需在标注集上调变体数（3–5 为宜）。
4. **不要为了重排丢掉混合检索**：RRF 负责"广召回"，reranker 负责"精排序"，二者是漏斗上下层，缺一不可。
5. **缓存的一致性**：文档更新后必须失效相关缓存（按 collection / source_system 维度失效）。
