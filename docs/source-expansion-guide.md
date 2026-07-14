# P1-A I-6: 情报源扩展配置手册

> 本手册指导运维人员部署 RSSHub 自托管实例和 crawl4ai Scraper，扩展 FDE 情报模块的数据源覆盖。

---

## 1. 架构概览

```
                    ┌────────────────────────────────┐
                    │        FDE Backend              │
                    │  (data_agent / pipeline)        │
                    └──────┬──────┬──────┬────────────┘
                           │      │      │
            ┌──────────────┘      │      └──────────────┐
            ▼                     ▼                     ▼
    ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
    │  RSSScraper  │     │ RSSHubScraper│     │Crawl4AI      │
    │  (直接 RSS)  │     │ (RSSHub 路由)│     │Scraper       │
    └──────┬───────┘     └──────┬───────┘     └──────┬───────┘
           │                    │                     │
           ▼                    ▼                     ▼
    外部 RSS Feed         RSSHub :1200          目标网页 (HTTP)
    (BBC/NYT/etc)         (1000+ 路由)          (LLM-ready Markdown)
```

## 2. RSSHub 部署

### 2.1 前置条件

- Docker + Docker Compose 已安装
- 端口 1200 可用（不与 LiteLLM :4000、Qdrant :6333 冲突）

### 2.2 部署步骤

```bash
# 1. 进入部署目录
cd deploy/rsshub

# 2. 复制环境变量模板
cp .env.example .env

# 3. (可选) 设置访问密钥
# 编辑 .env，设置 RSSHUB_ACCESS_KEY=your-secret-key

# 4. 启动
docker compose up -d

# 5. 验证
curl http://localhost:1200/healthz
# 期望返回: ok
```

### 2.3 验证路由

```bash
# 测试一个 RSSHub 路由
curl http://localhost:1200/reuters/business

# 应返回 RSS XML 格式的 feed
```

### 2.4 资源限制

| 组件 | 内存限制 | CPU 限制 |
|------|---------|---------|
| RSSHub | 512 MB | 0.5 CPU |
| Redis (缓存) | 96 MB | 0.25 CPU |

总占用约 600 MB，对 11G 主机影响可忽略。

## 3. crawl4ai Scraper 配置

### 3.1 后端选择

crawl4ai Scraper 支持三种模式，通过环境变量 `FDE_CRAWL4AI_BACKEND` 控制：

| 值 | 行为 | 适用场景 |
|----|------|---------|
| `auto` (默认) | 优先 crawl4ai，不可用时回退 HTTP | 生产推荐 |
| `crawl4ai` | 强制使用 crawl4ai（需安装） | 需 JS 渲染的页面 |
| `fallback` | 强制使用 HTTP + regex 转换 | 无 Chromium 环境 |

### 3.2 安装 crawl4ai（可选）

```bash
# 在 FDE venv 中安装
source venv/bin/activate
pip install crawl4ai

# crawl4ai 会自动下载 Chromium（约 200MB 磁盘）
python -c "from crawl4ai import AsyncWebCrawler; print('OK')"
```

> **注意**：crawl4ai 需要 Chromium，会占用额外 200-400 MB 内存。详见 `docs/resource-assessment-p1a.md`。

### 3.3 环境变量

在 `.env` 中配置：

```bash
# crawl4ai 后端选择
FDE_CRAWL4AI_BACKEND=auto

# 单页超时（秒）
FDE_CRAWL4AI_TIMEOUT=60

# 远程 Worker URL（留空=本地渲染）
FDE_CRAWL4AI_WORKER_URL=

# RSSHub 基地址
FDE_RSSHUB_BASE_URL=http://localhost:1200
```

## 4. 数据源类型

P1-A 新增两种 SourceType：

| SourceType | 枚举值 | 用途 |
|------------|--------|------|
| `RSSHUB` | `rsshub` | 订阅 RSSHub 路由（1000+ 站点） |
| `CRAWL4AI` | `crawl4ai` | 网页深度抓取（LLM-ready Markdown） |

### 4.1 RSSHub 数据源配置

**单路由**：

```json
{
  "source_type": "rsshub",
  "url": "/reuters/business",
  "max_items": 50
}
```

**批量路由**（通过 metadata.routes）：

```json
{
  "source_type": "rsshub",
  "url": "",
  "max_items": 30,
  "metadata": {
    "routes": ["/reuters/business", "/bbc/world", "/nytimes/home"]
  }
}
```

### 4.2 crawl4ai 数据源配置

```json
{
  "source_type": "crawl4ai",
  "url": "https://example.com/industry-report",
  "max_items": 5
}
```

crawl4ai 返回单个 CollectedItem，content 为 LLM-ready Markdown。

## 5. 预置贸易情报路由

`rsshub_scraper.py` 内置了外贸情报常用路由：

| 分类 | 路由 | 说明 |
|------|------|------|
| **news_global** | `/reuters/business` | 路透商业 |
| | `/bbc/world` | BBC 世界 |
| | `/nytimes/home` | 纽约时报首页 |
| | `/theguardian/world` | 卫报世界 |
| **tech_industry** | `/hackernews` | Hacker News |
| | `/techcrunch` | TechCrunch |
| | `/theverge/tech` | The Verge |
| **trade_policy** | `/wti/news` | WTO 新闻 |
| | `/unctad/news` | UNCTAD 新闻 |
| **china_trade** | `/cs/news` | 海关总署 |
| | `/mofcom/news` | 商务部 |

通过代码获取：

```python
from agents.data_agent.scrapers.rsshub_scraper import get_default_routes
routes = get_default_routes()  # 返回所有预置路由
```

## 6. API 调用示例

### 6.1 触发 RSSHub 采集

```bash
curl -X POST http://localhost:8000/api/intelligence/collect \
  -H 'Content-Type: application/json' \
  -d '{
    "source_type": "rsshub",
    "url": "/reuters/business",
    "max_items": 20
  }'
```

### 6.2 触发 crawl4ai 采集

```bash
curl -X POST http://localhost:8000/api/intelligence/collect \
  -H 'Content-Type: application/json' \
  -d '{
    "source_type": "crawl4ai",
    "url": "https://example.com/market-analysis",
    "max_items": 1
  }'
```

### 6.3 Python 调用

```python
from agents.data_agent.models import SourceConfig, SourceType
from agents.data_agent.pipeline import DataPipeline

pipeline = DataPipeline()

# RSSHub
config = SourceConfig(
    source_type=SourceType.RSSHUB,
    url="/reuters/business",
    max_items=30,
)
result = await pipeline.run(config)

# crawl4ai
config = SourceConfig(
    source_type=SourceType.CRAWL4AI,
    url="https://example.com/report",
    max_items=5,
)
result = await pipeline.run(config)
```

## 7. 故障排查

| 症状 | 可能原因 | 解决方案 |
|------|---------|---------|
| RSSHub 返回 502 | 容器未启动 | `docker compose logs rsshub` |
| RSSHub 路由返回空 | 路由不存在或被封锁 | 检查 https://docs.rsshub.app/routes |
| crawl4ai 超时 | 页面 JS 渲染慢 | 增大 `FDE_CRAWL4AI_TIMEOUT` |
| crawl4ai 回退到 HTTP | crawl4ai 未安装 | 安装 crawl4ai 或接受 fallback |
| 内存过高 | Chromium 占用 | 限制并发为 1，或拆 worker 机 |

## 8. 运维清单

- [ ] RSSHub 容器运行中（`docker ps | grep rsshub`）
- [ ] RSSHub 健康检查通过（`curl localhost:1200/healthz`）
- [ ] Redis 缓存运行中（`docker ps | grep rsshub-redis`）
- [ ] `.env` 中 `FDE_RSSHUB_BASE_URL` 配置正确
- [ ] crawl4ai 后端选择合理（`FDE_CRAWL4AI_BACKEND`）
- [ ] 主机内存 < 70%（`free -m`）
- [ ] 采集 API 可达（`curl localhost:8000/api/intelligence/overview`）
