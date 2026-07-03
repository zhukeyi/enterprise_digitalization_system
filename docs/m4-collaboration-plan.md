# M4 Solo 执行计划

> 创建时间：2026-07-03 | 修改时间：2026-07-03（solo 版本）  
> 执行者：WorkBuddy（单 Agent）  
> 遵循规范：AGENTS.md  
> 前置状态：M1-M3 全部完成，697 tests passed，commit b160403  
> 参考：docs/m4-plan.md

---

## 一、执行模式

**M4 由 WorkBuddy 独自完成，不涉及其他 Agent。**

| 角色 | 工具 | 职责 |
|------|------|------|
| **主 Agent** | WorkBuddy | M4-T1 ~ T7 全部 7 个任务 |

---

## 二、任务分配总表

| 序号 | 任务 | 分支 | 人天 | 改动目录 | 前置依赖 |
|------|------|------|------|---------|---------|
| 1 | M4-T1 IM 适配器 | `feat/im-agent/m4-t1` | 12 | `agents/im_agent/adapters/**` `agents/im_agent/webhook_routes.py` | 无 |
| 2 | M4-T2 Tauri 客户端 | `feat/client-agent/m4-t2` | 12 | `agents/client_agent/src-tauri/**` `agents/client_agent/src/**` | 无 |
| 3 | M4-T3 Docker 编排 | `feat/deploy/m4-t3` | 5 | `deploy/docker-compose.prod.yml` `deploy/nginx/**` | 无 |
| 4 | M4-T4 可观测底座 | `feat/deploy/m4-t4` | 8 | `deploy/prometheus/**` `deploy/grafana/**` `deploy/loki/**` `shared/sdk/otel_backend.py` `shared/sdk/metrics.py` | T3 完成 |
| 5 | M4-T5 CI/CD 补全 | `feat/deploy/m4-t5` | 7 | `deploy/helm/**` `.github/workflows/deploy.yml` `deploy/scripts/**` | T3,T4 完成 |
| 6 | M4-T6 审计+E2E | `feat/docs/m4-t6` | 4 | `docs/m3-architecture-audit.md` `tests/test_m4_e2e.py` | T1-T5 完成 |
| 7 | M4-T7 部署+交付 | `feat/docs/m4-t7` | 4 | `docs/operations/**` `docs/architecture.md` `CHANGELOG.md` | T6 完成 |

> 总计: 52 人天，7 个分支，7 次提交

---

## 三、执行排期

### 串行时间线

```
Day  1 ────────── 12 ────────── 24 ─────── 29 ───────── 37 ───────── 44 ──── 48 ──── 52
     │    T1       │     T2      │   T3   │    T4      │     T5     │  T6  │  T7  │
     │   IM适配    │   Tauri     │ Docker │  可观测    │   CI/CD    │ 审计 │ 交付 │
```

### 里程碑

| 时间 | 里程碑 | 内容 |
|------|--------|------|
| Day 12 | T1 完成 | IM 三平台适配器 + 35+ 测试 |
| Day 24 | T2 完成 | Tauri macOS 客户端 + dmg 构建 |
| Day 29 | T3 完成 | docker-compose.prod.yml + Nginx TLS |
| Day 37 | T4 完成 | Prometheus/Grafana/Loki/OTel |
| Day 44 | T5 完成 | Helm Charts + GitHub Actions deploy |
| Day 48 | T6 完成 | M3 审计报告 + E2E 验收 + 全量门禁 |
| Day 52 | T7 完成 | 生产部署 + 安全加固 + 交付文档 + v1.0.0 |

---

## 四、开发规范

### 每个任务的流程

```
1. 创建 feature 分支
2. 开发 + 测试
3. 本地门禁: make verify + make test-cov
4. 提交: Conventional Commits
5. 推送到 GitHub
6. CI 自动运行门禁
7. 合并到 main (Trunk-Based)
```

### 提交格式

```
feat(im-agent): M4-T1 WeCom/Feishu/DingTalk adapters real integration
feat(client-agent): M4-T2 Tauri desktop client macOS
docs(deploy): M4-T3 production docker compose orchestration
feat(deploy): M4-T4 observability stack (Prometheus/Grafana/Loki/OTel)
feat(deploy): M4-T5 Helm charts + CI/CD deployment pipeline
docs: M4-T6 M3 architecture audit + E2E acceptance tests
docs: M4-T7 production deployment + security + runbook + v1.0.0
```

### 质量自检清单（每个 PR）

- [ ] ruff 0 errors
- [ ] black clean
- [ ] mypy strict 通过
- [ ] pytest 全量通过
- [ ] 新增代码有测试
- [ ] 公开函数有 docstring
- [ ] 新增模块有 `__init__.py`
- [ ] 无 TODO/FIXME/HACK 残留

---

## 五、上下文管理策略

M4 共 52 天，为避免上下文过长导致质量下降：

1. **每个任务完成后**：在 Git commit message 中写精炼摘要（做了什么 + 关键决策 + 测试结果）
2. **每个里程碑（T1/2/3/4/5/6/7）完成后**：更新 working memory 日志
3. **如有必要**：在新会话中继续，通过 reading memory 和 git log 恢复上下文
4. **不追求一次性完成**：每完成一个任务就合并，保持 main 分支随时可部署

---

## 六、测试服务器信息

- **地址**：217.142.246.70 (Oracle ARM 2C/11G/96G, ubuntu)
- **SSH**：`ssh -i ~/ssh/arm.key ubuntu@217.142.246.70`
- **Dify**：http://217.142.246.70 (Docker, 12 容器)
- **FDE 后端**：已配置 systemd 服务
- **OCI 端口问题**：安全列表阻止外部端口，需在 OCI 控制台手动开放（T7 时处理）

---

## 七、风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| 上下文过长导致质量下降 | 每任务完成后开新会话 |
| Tauri Rust 编译不熟悉 | 优先 WebView 前端, Rust 部分用社区模板 |
| OCI 端口封锁 | 自签名证书 fallback, 运维手册记录 OCI 操作步骤 |
| 依赖安全漏洞 | T7 提前做 pip-audit，留缓冲时间修复 |
| 单线程 52d 漫长 | 每任务 commit 后即合并，保持 main 可部署 |