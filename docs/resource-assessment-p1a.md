# P1-A I-3: Chromium 资源评估与拆机方案

> 评估 crawl4ai 的 Chromium 渲染对 Oracle ARM 主机（2C/11G/96G）的影响，给出是否需要拆 worker 机的结论。

---

## 1. 主机资源现状

| 组件 | 预估内存占用 | 说明 |
|------|-------------|------|
| OS + systemd | ~500 MB | Ubuntu 22.04 ARM64 |
| Postgres 16 | ~200 MB | 仅 LiteLLM 虚拟 Key |
| LiteLLM Proxy | ~1.5 GB | 已设 memory limit |
| Qdrant | ~500 MB | 向量库 |
| FDE Backend (FastAPI) | ~400 MB | 主服务 |
| Dify | ~1.5 GB | Docker stack |
| Nginx | ~50 MB | 反代 |
| **小计** | **~4.65 GB** | |
| **可用余量** | **~6.35 GB** | 11G - 4.65G |

## 2. Chromium (crawl4ai) 内存需求

| 场景 | 预估内存 | 说明 |
|------|---------|------|
| 单页渲染（轻量） | 200-400 MB | 文本为主的新闻页 |
| 单页渲染（重度） | 500-800 MB | 含大量 JS/图片的 SPA |
| 并发 2 页 | 800 MB-1.6 GB | 默认 crawl4ai 并发 |
| 并发 3 页 | 1.2-2.4 GB | 高并发场景 |

## 3. 结论：主机内运行，限制并发

**结论：可以不拆 worker 机，但必须严格限制 crawl4ai 并发。**

理由：
1. 主机可用余量 ~6.35 GB，单页 Chromium 渲染 200-400 MB，余量充足。
2. RSSHub 已禁用 Puppeteer（PuppeteerWSEndpoint 设为空），JS 渲染全部走 crawl4ai。
3. crawl4ai 默认并发 2 页，限制为 1 页后峰值内存 ~400 MB，远低于安全线。

### 安全线计算

```
当前已用: ~4.65 GB
crawl4ai 1页: +0.4 GB
RSSHub + Redis: +0.6 GB
预估总用: ~5.65 GB (51%)
安全线 70%: 7.7 GB
余量到安全线: ~2.05 GB
```

**判定：5.65 GB / 11 GB = 51%，在 70% 安全线以内。**

## 4. 压测建议

部署后执行以下压测验证：

```bash
# 1. 启动 RSSHub
cd deploy/rsshub && docker compose up -d

# 2. 监控内存
watch -n 2 'free -m | grep Mem'

# 3. 触发 crawl4ai 采集（单页）
curl -X POST http://localhost:8000/api/intelligence/collect \
  -H 'Content-Type: application/json' \
  -d '{"source_type":"crawl4ai","url":"https://example.com","max_items":1}'

# 4. 检查内存峰值
# 如果内存超过 7.7 GB (70%)，立即降低并发或拆 worker
```

## 5. 拆 Worker 机方案（备用）

如果压测超过 70% 安全线，执行拆机：

### 架构

```
[主主机 11G]                     [Worker 机 4G+]
  FDE Backend                      crawl4ai Worker
  LiteLLM                          Chromium
  Qdrant
  Dify
  RSSHub
      │
      │ HTTP (内网)
      ▼
  crawl4ai Worker API
```

### Worker 机配置

| 项 | 最低配置 | 推荐 |
|----|---------|------|
| CPU | 1C ARM | 2C ARM |
| 内存 | 4 GB | 8 GB |
| 磁盘 | 20 GB | 50 GB |
| 网络 | 内网可达主机 | 同子网 |

### Worker API 设计

Worker 机运行一个轻量 FastAPI 服务：
- `POST /render` — 接收 URL，返回 Markdown
- `GET /health` — 健康检查
- 限制并发为 1（单页渲染）

主机的 `Crawl4AIScraper` 通过 `FDE_CRAWL4AI_WORKER_URL` 环境变量路由到 worker。

### 何时执行拆机

| 指标 | 阈值 | 动作 |
|------|------|------|
| 主机内存 | >70% 持续 5min | 拆机 |
| crawl4ai 渲染超时 | >30s/页 | 拆机 |
| 主服务 P99 延迟 | >2s | 拆机 |

---

## 6. 环境变量配置

在 `.env` 中添加：

```bash
# crawl4ai 配置
FDE_CRAWL4AI_BACKEND=auto          # auto/crawl4ai/fallback
FDE_CRAWL4AI_TIMEOUT=60             # 单页超时秒数
FDE_CRAWL4AI_WORKER_URL=            # 空=本地，有值=远程 worker

# RSSHub 配置
FDE_RSSHUB_BASE_URL=http://localhost:1200
```
