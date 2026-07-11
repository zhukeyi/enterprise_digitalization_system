# 资源容量评估（Resource Capacity Assessment）

> 落实工程评审 **F2**：单机 11G 资源容量未评估 → P0 产出评估表 + P6 拆分。
> 本文件为 `master-delivery-plan.md` §8 的详细版与方法论。
> 状态：**估算值**（无法在 sandbox 直连生产库实测），P0.5 spike / P3b 用实测替换。

---

## 1. 目标机器

测试服务器 `217.142.246.70`（Oracle ARM 2C / **11G** / 96G disk，Ubuntu）。
注意：内存仅 11G，是硬约束。其余服务（Dify 12 容器 / Qdrant / Postgres）已占 ~6G。

---

## 2. 容量评估表（估算）

| 服务 | 当前占用 | 计划新增 | 峰值 RAM | 能否单机 | 备注 |
|------|----------|----------|----------|----------|------|
| Dify 12 容器 | ~3.5G | — | ~4G | ✅ | 已运行 |
| Qdrant | ~1G | — | ~2G (万级) | ✅ | 已运行 |
| Postgres | ~1G | 4 表 | ~1.5G | ✅ | 已运行 |
| fde-backend | ~0.5G | ONNX | ~1.5G | ✅ | 含 ONNX 嵌入 |
| nginx | ~50M | /portal/ | ~50M | ✅ | — |
| Redis | — | 新增 | ~256M | ✅ | 轻量（P3b） |
| MinIO | — | 新增 | ~512M | ✅ | 轻量（P3b） |
| Docling (torch) | — | 按需 | ~1.5G | ⚠️ | **P0.5 spike 验证**；可能需按需启停 |
| BGE-Reranker (568M) | — | 按需 | ~1.2G | ⚠️ | **P0.5 spike 验证**；或走 P6b GPU |
| **合计** | ~6G | ~5G | **~11.8G** | **⚠️ 临界** | 11G 机器接近上限 |

---

## 3. 结论

- 单机可稳跑：Redis + MinIO + ONNX 嵌入 + 4 张新表。
- **Docling + Reranker 不能同时常驻**：必须按需加载（请求时拉起、闲置回收）或拆为
  独立微服务（P6b，需扩容 / GPU）。
- 若同时触发 Dify 高峰 + Docling + Reranker，会超 11G → OOM。缓解：限流 ingestion、
  Reranker 候选 ≤20、Docling 串行批处理。

---

## 4. 实测方法论（P0.5 / P3b 填充真实值）

在测试服务器执行，记录 `ps_mem` / `docker stats` 峰值：

1. **基线**：`docker stats --no-stream` 取当前占用快照。
2. **ONNX 嵌入**：warm-up 100 次取 RSS 增量（`/usr/bin/time -v`）。
3. **Docling**：解析 1 个 20 页 PDF，记录 torch 加载 + 推理峰值。
4. **Reranker**：单次候选 ≤20 重排延迟 + 内存（`P0.5` spike）。
5. 将实测填入上表「当前/峰值」列，更新 §8 与本文「结论」。

---

## 5. 扩容触发条件（进入 P6b）

满足任一即判定需扩容（不在当前 11G 周期）：

- Docling 与 Reranker 需并发常驻且无法串行化；
- Qdrant 向量规模进入百万级（RAM > 4G）；
- Postgres 单实例成写入瓶颈（需读写分离）。

→ 触发 `master-delivery-plan.md` P6b（分布式 Qdrant / PG 读写分离 / GPU 推理微服务）。
