# RAG Agent — 企业知识引擎

## 职责
- 向量数据库管理（Qdrant 本地优先 / Milvus 分布式备选）
- 文档解析器工厂（PDF / Word / Excel / PPT / Markdown）
- 分块策略（可配置块大小/重叠/分隔符）
- 嵌入模型（BGE-M3，ARM CPU 本机推理）
- 混合检索（BM25 + 向量 + RRF 融合）
- 权限过滤检索（RBAC + ABAC，知识库/文档/段落级）
- 决策链日志（问答上下文全量存储）

## M1 任务
| 任务 | 说明 | 状态 |
|:---|:---|:---|
| M1-T8 | 部署向量数据库 | Qdrant 已运行 |
| M1-T9 | 文档解析器工厂 | 待开发 |
| M1-T10 | 分块策略 | 待开发 |
| M1-T11 | BGE-M3 嵌入 | ARM CPU 推理 |
| M1-T12 | 混合检索 | BM25 + 向量 + RRF |

## 模型部署
- 嵌入模型：`BAAI/bge-m3`，本地 ARM CPU 推理
- 如性能不足可切换到 Qdrant 内置 M3 镜像或云端 API

## 依赖
- `fde-ai-platform[rag]`
- Qdrant / sentence-transformers / langchain / pymupdf
