# M4 详细拆分与执行计划

> 创建时间：2026-07-03 | 修改时间：2026-07-03（solo 版本）  
> 里程碑：M4 — 交付与收尾（第7-8月）  
> 计划总量：52 人天  
> 执行模式：**WorkBuddy 单 Agent 串行执行**  
> 前置状态：M1-M3 全部完成，697 tests passed，commit b160403  
> 参考文档：docs/v2-plan-analysis.md 阶段4, docs/m1-m2-architecture-audit.md P1遗留问题

---

## 一、M4 总览

| 维度 | 数据 |
|------|------|
| **任务数** | 7 个（M4-T1 ~ M4-T7） |
| **人天** | 52 人天 |
| **执行者** | WorkBuddy（单 Agent） |
| **涉及模块** | im_agent, client_agent, deploy/, .github/, shared/sdk/, 测试服务器 |
| **性质** | 交付收尾：补全 Stub → 真实对接、补全缺失的运维基础设施、安全加固、验收文档 |
| **核心交付** | IM 真实对接 + Tauri 客户端 + 生产级运维 + 可观测底座 + 验收 |

### M4 与 M1-M3 的区别

- M1-M3 是「构建期」：从零到一，实现 13 个 Agent + 697 测试
- M4 是「交付期」：Stub → 生产、补齐运维、安全加固、文档验收
- M4 不再新增 Agent 或核心功能，而是把已有的「骨架」变成「可交付产品」

### 依赖关系图

```
M4-T1 (IM 对接, 12d)
    │
    ▼
M4-T2 (Tauri 客户端, 12d) ─── 独立模块，无代码交叉
    │
    ▼
M4-T3 (Docker 编排, 5d)  ─── 基础设施层
    │
    ▼
M4-T4 (可观测底座, 8d)   ─── 依赖 T3 的服务定义
    │
    ▼
M4-T5 (CI/CD 补全, 7d)   ─── 依赖 T3/T4
    │
    ▼
M4-T6 (M3 审计+E2E, 4d)  ─── 依赖 T1-T5 全部完成
    │
    ▼
M4-T7 (生产部署+交付, 4d) ─── 依赖 T6
```

> T1 和 T2 任务内容独立，可互换顺序。T1 先做是因为企微适配器已有完整的 ABC 框架，上手快。

---

## 二、任务详细拆分

### M4-T1: IM 适配器真实对接（企微 + 飞书 + 钉钉）（12 人天）

**所属模块**：im_agent  
**前置状态**：ABC + MockAdapter 已完成，WeComAdapter/FeishuAdapter/DingTalkAdapter 仅有类定义（pass stub），31 tests passed  
**目标**：对接三个 IM 平台的真实 Webhook + API, 实现收发消息

#### 当前代码状态

```
agents/im_agent/
├── models.py          # 12 个 Pydantic 模型 + 3 个 StrEnum (✅ 完整)
├── adapters/
│   └── __init__.py    # BaseIMAdapter ABC + MockAdapter 完整 + WeCom/Feishu/DingTalk 仅 pass
├── tools.py           # 3 工具：send_message / broadcast / query_session (✅ 完整)
└── tests/             # 31 tests (✅ MockAdapter 覆盖)
```

#### 子任务拆分

| 子任务 | 内容 | 人天 | 产出文件 |
|--------|------|------|---------|
| T1-1 | 企微适配器完整实现 | 4 | `im_agent/adapters/wecom_adapter.py` — 应用消息 API + 回调加解密 + 富文本 |
| T1-2 | 飞书适配器完整实现 | 3 | `im_agent/adapters/feishu_adapter.py` — 飞书开放平台 API + 事件订阅 |
| T1-3 | 钉钉适配器完整实现 | 3 | `im_agent/adapters/dingtalk_adapter.py` — 钉钉机器人 API + 回调 |
| T1-4 | Webhook 路由 + 回调端点 | 1 | `im_agent/webhook_routes.py` — FastAPI 统一回调端点 `/im/webhook/{platform}` |
| T1-5 | 集成测试 + API mock 测试 | 1 | `tests/test_im_real.py` — 用 httpx mock API 响应验证适配器行为 |

#### 验收标准

- 企微适配器可发送文本/markdown/图片消息（API mock 验证）
- 飞书适配器可发送消息 + 接收事件（API mock 验证）
- 钉钉适配器可发送消息 + 接收回调（API mock 验证）
- `/im/webhook/{platform}` 端点正确处理 GET 验证 + POST 回调
- 35+ 新增测试（每个适配器 10+）

---

### M4-T2: Tauri 桌面客户端实现（12 人天）

**所属模块**：client_agent  
**前置状态**：Python SDK 已完成（16 models + DesktopAuthManager + 17 tests），Tauri 壳未开始  
**目标**：构建 macOS 原生桌面 AI 助手，支持全局快捷键唤起 + 文本捕获 + AI 回填  
**参考**：agents/client_agent/TODO.md (T-1~T-6 详细待办)

#### 子任务拆分

| 子任务 | 内容 | 人天 | 产出文件 |
|--------|------|------|---------|
| T2-1 | Tauri 项目骨架搭建 | 2 | `client_agent/src-tauri/` + `client_agent/src/` — Vue 3 + Vite + Tauri 2.x |
| T2-2 | macOS 核心能力 (快捷键 + 文本捕获 + 回填) | 3 | `src-tauri/src/` — global shortcut + accessibility + clipboard |
| T2-3 | 认证流程 + AI API 对接 | 2 | `src/` — 登录 UI + SSE 流式响应 |
| T2-4 | 窗口管理 + 系统托盘 + 设置面板 | 2 | `src/components/` — 悬浮窗 + 托盘菜单 + 设置页 |
| T2-5 | 打包与签名 (macOS dmg) | 1 | `scripts/build.sh` — `tauri build + codesign + create-dmg` |
| T2-6 | 测试 + CI 构建流水线 | 2 | `tests/` + `.github/workflows/tauri-ci.yml` — macOS runner 构建 |

#### 验收标准

- macOS dmg 可安装运行
- 全局快捷键 `Cmd+Shift+Space` 唤起悬浮窗
- 可选中任意文本 → 快捷键 → 文本自动填入输入框
- AI 回复可一键回填到当前光标位置
- 系统托盘图标 + 退出菜单
- JWT 自动续期
- GitHub Actions macOS runner 自动构建 dmg

---

### M4-T3: 生产级 Docker Compose 编排（5 人天）

**所属模块**：deploy/  
**前置状态**：仅有 docker-compose.dev.yml（开发环境），deploy/ 目录全空  
**目标**：生产级容器编排，含健康检查、资源限制、日志驱动、Secret 管理

#### 子任务拆分

| 子任务 | 内容 | 人天 | 产出文件 |
|--------|------|------|---------|
| T3-1 | docker-compose.prod.yml 编写 | 2 | `deploy/docker-compose.prod.yml` — 全部服务生产配置 |
| T3-2 | Nginx 反向代理 + TLS 自动续期 | 1 | `deploy/nginx/` — Let's Encrypt certbot + 安全头 |
| T3-3 | 环境变量管理 + Secret 注入 | 1 | `deploy/config-templates/` — `.env.prod` 模板 + Docker secrets |
| T3-4 | 健康检查 + 自动重启 + 日志轮转 | 1 | `deploy/healthcheck.sh` + `deploy/docker-compose.override.yml` |

#### 服务清单

| 服务 | 生产配置要点 |
|------|-------------|
| fde-backend | FastAPI + 4 workers (gunicorn), 资源限制 2G/2CPU |
| fde-frontend | Nginx 静态文件 + API 反代, 资源限制 256M/0.5CPU |
| postgres | `max_connections=200`, WAL 归档, pg_dump 定时备份 |
| redis | `maxmemory 512mb`, AOF 持久化 |
| qdrant | 持久化卷, API key 认证 |
| nginx | Let's Encrypt HTTPS, HSTS, CSP, X-Frame-Options |
| certbot | 自动续期 cron, 证书卷共享 |

---

### M4-T4: 可观测底座补全（Prometheus + Grafana + Loki + OTel）（8 人天）

**所属模块**：shared/sdk/ + deploy/  
**前置状态**：shared/sdk/otel_backend.py 仅有 stdout stub（`FDE_OTEL_ENABLED=0`），M1-T2 仅完成 30%  
**目标**：生产级可观测三件套（Metrics + Logs + Traces）+ Langfuse LLM 可观测

#### 子任务拆分

| 子任务 | 内容 | 人天 | 产出文件 |
|--------|------|------|---------|
| T4-1 | Prometheus + Grafana 部署 + 仪表板 | 2 | `deploy/prometheus/` + `deploy/grafana/dashboards/` |
| T4-2 | FastAPI metrics 端点 + 自定义指标 | 2 | `shared/sdk/metrics.py` — request count/latency/error rate + worker 指标 |
| T4-3 | Loki 日志聚合 + 日志结构化 | 1 | `deploy/loki/` + `shared/sdk/logging.py` — JSON 结构化日志 |
| T4-4 | OTel exporter 真实接入 | 2 | `shared/sdk/otel_backend.py` — OTLP HTTP exporter + Langfuse 集成 |
| T4-5 | 告警规则 + Alertmanager | 1 | `deploy/prometheus/alerts.yml` — 5 条关键告警 |

#### Metrics 指标设计

| 指标名 | 类型 | 说明 |
|--------|------|------|
| `fde_http_requests_total` | Counter | HTTP 请求总数（按 method/endpoint/status） |
| `fde_http_request_duration_seconds` | Histogram | 请求耗时分布 |
| `fde_worker_tasks_total` | Counter | Worker 任务执行总数（按 worker_name/status） |
| `fde_tool_calls_total` | Counter | 工具调用总数（按 tool_name） |
| `fde_rag_search_duration_seconds` | Histogram | RAG 检索耗时 |
| `fde_active_sessions` | Gauge | 活跃会话数 |

#### 告警规则

| 告警 | 条件 | 严重级别 |
|------|------|---------|
| HighErrorRate | `rate(fde_http_requests_total{status=~"5.."}[5m]) > 0.05` | critical |
| HighLatency | `histogram_quantile(0.95, fde_http_request_duration_seconds) > 2` | warning |
| WorkerFailureRate | `rate(fde_worker_tasks_total{status="failed"}[5m]) > 0.1` | critical |
| RAGLatencySpike | `rate(fde_rag_search_duration_seconds_bucket{le="1"}[5m]) < 0.9` | warning |
| DatabaseConnectionPool | `fde_db_connections_active > 180` | warning |

---

### M4-T5: CI/CD 补全（Helm Charts + 自动部署流水线）（7 人天）

**所属模块**：deploy/ + .github/  
**前置状态**：CI 已有 3 阶段门禁（lint + type-check + test），CD 完全缺失；deploy/helm/ 为空  
**目标**：K8s Helm Charts + GitHub Actions 自动部署 + 蓝绿部署

#### 子任务拆分

| 子任务 | 内容 | 人天 | 产出文件 |
|--------|------|------|---------|
| T5-1 | Helm Chart 编写 | 3 | `deploy/helm/fde-platform/` — Chart.yaml + values.yaml + templates/ |
| T5-2 | GitHub Actions deploy job | 2 | `.github/workflows/deploy.yml` — tag push → build → deploy |
| T5-3 | 数据库迁移自动化 | 1 | `deploy/scripts/migrate.sh` + Alembic 集成 |
| T5-4 | 蓝绿部署脚本 + 回滚 | 1 | `deploy/scripts/deploy-blue-green.sh` + `deploy/scripts/rollback.sh` |

#### Helm Chart 资源清单

```yaml
templates/
├── deployment-backend.yaml     # FastAPI Deployment
├── deployment-frontend.yaml    # Nginx + 静态文件
├── service.yaml               # ClusterIP
├── ingress.yaml                # TLS + 路由规则
├── configmap.yaml              # 非敏感配置
├── secret.yaml                 # DB密码/JWT密钥 (SealedSecret)
├── pvc.yaml                   # Qdrant 持久化
├── hpa.yaml                   # 水平自动伸缩 (CPU > 70%)
└── service-monitor.yaml       # Prometheus Operator ServiceMonitor
```

#### 验收标准

- `helm install fde ./deploy/helm/fde-platform` 可部署到 K8s
- GitHub tag push → 自动构建 Docker image → push GHCR
- 蓝绿部署脚本可切换 active/inactive deployment
- 回滚脚本基于 Helm rollback
- 数据库迁移可自动执行（UP + DOWN 验证）

---

### M4-T6: M3 架构审计 + 全平台 E2E 验收测试（4 人天）

**所属模块**：全局  
**前置**：M4-T1 ~ T5 全部完成  
**目标**：对 M3 全部交付物做架构合规性审计 + 全链路 E2E 验收测试  
**参考**：docs/m1-m2-architecture-audit.md（审计模板）

#### 子任务拆分

| 子任务 | 内容 | 人天 | 产出文件 |
|--------|------|------|---------|
| T6-1 | M3 架构合规性审计 | 2 | `docs/m3-architecture-audit.md` — 模块对照/吻合度/鲁棒性 |
| T6-2 | 全平台 E2E 验收测试 | 1 | `tests/test_m4_e2e.py` — M1+M2+M3 全链路 + M4 新增功能 |
| T6-3 | 质量门禁终验 | 1 | 全量 make verify + make test-cov + 覆盖率报告 |

#### M3 架构审计检查清单

- [ ] 13 个 M3 任务全部交付有 Git 提交记录
- [ ] 3 个空壳 Agent（data/analysis/hr）→ 完整实现（模块对照验证）
- [ ] 地图 AI 模块全链路可用（标记→提交→分析→推送→可视化）
- [ ] 评测体系 CI 门禁运行正常
- [ ] NL2SQL 安全校验生效（拦截 DELETE/UPDATE/DROP）
- [ ] 防呆 5 步校验在 HR 和地图模块中正常工作
- [ ] IM 适配器从 Stub 升级到真实对接（M4-T1 验证）
- [ ] 桌面客户端可构建运行（M4-T2 验证）
- [ ] 生产 Docker Compose 可一键启动（M4-T3 验证）
- [ ] 可观测仪表板可访问（M4-T4 验证）
- [ ] Helm Charts 可部署（M4-T5 验证）

#### E2E 验收测试覆盖

```
全链路 1: 认证 → RAG检索 → Supervisor规划 → Worker执行 → 冲突裁决 → 响应生成
全链路 2: 数据采集 → NL2SQL → Dashboard → 下钻 → 关联分析
全链路 3: 地图标记 → 分析提交 → 相关性计算 → 异步推送 → 可视化
全链路 4: IM消息接收 → Worker处理 → IM消息发送（M4 新增）
全链路 5: 桌面客户端 → 认证 → AI对话 → 回填（M4 新增）
```

#### 质量门禁终验目标

| 指标 | M3 完成时 | M4 目标 |
|------|----------|---------|
| 总测试数 | ~697 | ≥ 800 |
| 总覆盖率 | ~87% | ≥ 85% |
| ruff | 0 | 0 |
| mypy | 0 | 0 |
| black | clean | clean |
| vue-tsc | 0 errors | 0 errors |

---

### M4-T7: 生产部署 + 安全加固 + 交付文档（4 人天）

**所属模块**：全局  
**前置**：M4-T6 完成  
**目标**：生产环境部署、安全加固、操作手册、最终交付

#### 子任务拆分

| 子任务 | 内容 | 人天 | 产出文件 |
|--------|------|------|---------|
| T7-1 | 生产环境部署到测试服务器 | 1 | SSH 部署脚本 + 服务验证 |
| T7-2 | 安全加固 | 1 | OWASP Top 10 检查 + 依赖漏洞扫描 + Secret 扫描 |
| T7-3 | 运维操作手册 | 1 | `docs/operations/runbook.md` — 启动/停止/备份/恢复/扩容 |
| T7-4 | 架构文档补全 + Release Notes | 1 | `docs/architecture.md` + `CHANGELOG.md` v1.0.0 |

#### 运维操作手册内容

```
docs/operations/runbook.md:
  - 服务启动/停止/重启流程
  - 健康检查 endpoint
  - 数据库备份/恢复流程
  - 日志查看与故障排查
  - 扩容/缩容指南
  - 证书续期流程
  - 常见问题 FAQ
```

#### 验收标准

- 测试服务器上生产部署成功, HTTPS 可访问
- 安全扫描通过（无高危漏洞）
- 运维手册包含 6+ 个操作场景
- 架构文档包含 11 大模块说明 + 数据流图
- CHANGELOG.md 包含 M1~M4 全部功能摘要
- GitHub Release v1.0.0 发布

---

## 三、执行顺序与排期

### 串行执行计划（WorkBuddy 单 Agent）

```
顺序 1: M4-T1 (IM 适配器, 12d)      — 最成熟的补全任务，已有完整 ABC 框架
顺序 2: M4-T2 (Tauri 客户端, 12d)    — 独立模块，无代码交叉
顺序 3: M4-T3 (Docker 编排, 5d)      — 基础设施层开始
顺序 4: M4-T4 (可观测底座, 8d)       — 依赖 T3 的服务定义
顺序 5: M4-T5 (CI/CD 补全, 7d)       — 依赖 T3/T4
顺序 6: M4-T6 (M3 审计+E2E, 4d)     — 依赖 T1-T5 全部完成
顺序 7: M4-T7 (生产部署+交付, 4d)    — 依赖 T6

总工期: 52 天（串行）
```

### 时间线

```
Day  1──────12──────24────29─────37─────44────48─────52
     │  T1     │  T2   │ T3 │  T4   │  T5  │ T6 │ T7 │
     │  IM适配  │ Tauri │ DC │ 可观测 │ CI/CD│审计│交付│
```

> T1 和 T2 各 12d 是最重的两个任务，其余 5 个任务（29d）较为轻量。

---

## 四、M1-M2 审计遗留问题在 M4 中的处理

| 遗留问题 | 审计编号 | M4 处理 | 对应任务 |
|----------|----------|---------|---------|
| IM 适配器全是 Stub | P1-3 | 真实对接企微/飞书/钉钉 API | M4-T1 |
| Tauri 桌面客户端未开始 | P1-4 | Tauri 项目搭建 + macOS 客户端 | M4-T2 |
| docker-compose 仅有 dev 版本 | P1-6 | 编写 docker-compose.prod.yml | M4-T3 |
| CI 缺 CD（无自动部署流水线） | P1-7 | Helm Charts + GitHub Actions deploy | M4-T5 |
| 可观测底座仅 30%（M1-T2） | P1-8 | Prometheus + Grafana + Loki + OTel | M4-T4 |
| _log_trace 仅 print 到 stdout | P1-5 | OTel exporter 真实接入 | M4-T4-4 |
| shared/ 全部逻辑在 __init__.py | P1-1 | ✅ 已在 M1-M2 审计修复中完成 | — |
| _is_public_path 前缀匹配过松 | P2-3 | ✅ 已在 M1-M2 审计修复中完成 | — |
| TraceContext 非线程安全 | P2-2 | ✅ 已在 M1-M2 审计修复中完成 | — |
| RAGFlow 集成决策未明确 | 审计 1.1 | M4 不做 RAGFlow（自建 Qdrant 管线已验证可用） | 文档说明 |

---

## 五、质量门禁

每个子任务完成时必须通过：

```bash
make verify          # ruff + black --check + mypy
make test-cov        # pytest + coverage ≥ 模块平均值
```

M4 整体完成时额外要求：

```bash
# 全量门禁
make verify
make test-cov    # 覆盖率 ≥ 85%, 总测试数 ≥ 800

# 前端
cd frontend/map-ai && npm run type-check   # vue-tsc 0 errors
cd frontend/map-ai && npm run build        # 构建成功

# Tauri
cd agents/client_agent && cargo check       # Rust 编译通过

# 部署
docker compose -f deploy/docker-compose.prod.yml config  # 配置验证
helm lint deploy/helm/fde-platform/                        # Helm 验证

# 安全
pip-audit                      # Python 依赖无已知漏洞
npm audit --production         # 前端依赖无高危漏洞
```

---

## 六、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| IM API 文档变更 | 低 | T1 适配器需重写 | Mock API 响应, 适配器层隔离 |
| Tauri macOS 构建环境不可用 | 中 | T2 无法交付 | 先用 npm create tauri-app 验证, 无 Xcode 也可构建 WebView |
| 测试服务器被 OCI 安全列表封端口 | 高 | T7 部署不可达 | 已确认需手动在 OCI Console 开端口, 记录在运维手册 |
| Let's Encrypt 证书获取失败 | 中 | T3 HTTPS 不可用 | 自签名证书作为 fallback, 端口 8443 |
| Helm Chart 在客户 K8s 版本不兼容 | 低 | T5 部署失败 | 使用 K8s 1.25+ 稳定 API, 避免 beta |
| 可观测底座资源消耗过大 | 中 | 测试服务器 OOM | Prometheus 保留策略 7d, Loki 保留策略 3d |
| 单 Agent 52d 上下文过长 | 中 | 后期质量下降 | 每个任务完成后写精炼摘要, 每 2 周开新会话 |

---

## 七、交付清单

M4 完成后应交付：

### 代码交付

- [ ] IM 适配器（企微/飞书/钉钉）完整实现 + 测试
- [ ] Tauri macOS 桌面客户端源码 + 构建脚本
- [ ] 生产 Docker Compose 编排文件
- [ ] Prometheus + Grafana + Loki 配置
- [ ] OTel exporter 真实实现
- [ ] Helm Charts
- [ ] CI/CD deploy workflow
- [ ] 数据库迁移脚本 (Alembic)

### 文档交付

- [ ] `docs/m3-architecture-audit.md` — M3 架构审计报告
- [ ] `docs/operations/runbook.md` — 运维操作手册
- [ ] `docs/architecture.md` — 系统架构文档
- [ ] `CHANGELOG.md` — 版本变更记录
- [ ] GitHub Release v1.0.0

### 运行交付

- [ ] 生产部署到测试服务器
- [ ] HTTPS 可访问（Let's Encrypt 或自签名）
- [ ] Grafana 仪表板可访问
- [ ] macOS dmg 安装包