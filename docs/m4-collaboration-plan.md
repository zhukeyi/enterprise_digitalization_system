# M4 双 Agent 协作执行计划

> 创建时间：2026-07-03  
> 协作工具：WorkBuddy（主 Agent）、Trae（辅助 Agent）  
> 遵循规范：AGENTS.md 多 Agent 协作规范  
> 前置状态：M1-M3 全部完成，697 tests passed，commit b160403  
> 参考：docs/m4-plan.md

---

## 一、角色映射

| 角色 | 工具 | 能力特征 | M4 职责范围 |
|------|------|---------|-------------|
| **主 Agent** | WorkBuddy | 长上下文 + 强推理 | 企微适配器（最复杂）、Docker 编排、架构审计/E2E、生产部署/交付 |
| **辅助 Agent** | Trae | 快速迭代 + 批量执行 | 飞书/钉钉适配器、Tauri 客户端、可观测底座、CI/CD Helm Charts |

> M4 不需要 Qoder（评审 Agent），因为 M4 的审计任务（T6）由 WorkBuddy 自行完成。  
> M4 是交付阶段，核心工作只有 7 个任务，无需三 Agent 协作。

### 分工原则

1. **WorkBuddy 独占 im_agent/adapters/wecom_adapter.py**（最复杂的适配器）
2. **WorkBuddy 独占 deploy/docker-compose.prod.yml + deploy/nginx/**（基础设施）
3. **WorkBuddy 独占 docs/ （审计文档、运维手册、架构文档）**
4. **Trae 独占 client_agent/src-tauri/**（Tauri Rust 项目）
5. **im_agent/adapters/ 中 feishu/dingtalk 适配器给 Trae**（可复用 wecom 模板）
6. **文件交叉零容忍**：任何并行组合的改动文件列表无交集

---

## 二、任务分配总表

| 序号 | 任务 | 工具 | 分支 | 人天 | 改动目录 | 前置依赖 |
|------|------|------|------|------|---------|---------|
| 1 | M4-T1-1 企微适配器 | WorkBuddy | `feat/im-agent/m4-t1-wecom` | 4 | `agents/im_agent/adapters/wecom_adapter.py` `agents/im_agent/webhook_routes.py` | 无 |
| 2 | M4-T3 Docker 编排 | WorkBuddy | `feat/deploy/m4-t3-prod-compose` | 5 | `deploy/**` | 无 |
| 3 | M4-T2 Tauri 客户端 | Trae | `feat/client-agent/m4-t2-tauri` | 12 | `agents/client_agent/src-tauri/**` `agents/client_agent/src/**` | 无 |
| 4 | M4-T1-2/3 飞书+钉钉 | Trae | `feat/im-agent/m4-t1-feishu-dingtalk` | 6 | `agents/im_agent/adapters/feishu_adapter.py` `agents/im_agent/adapters/dingtalk_adapter.py` | T1-1 完成 |
| 5 | M4-T4 可观测底座 | Trae | `feat/deploy/m4-t4-observability` | 8 | `deploy/prometheus/**` `deploy/grafana/**` `deploy/loki/**` `shared/sdk/otel_backend.py` `shared/sdk/metrics.py` | 无 |
| 6 | M4-T5 CI/CD 补全 | Trae | `feat/deploy/m4-t5-cicd` | 7 | `deploy/helm/**` `.github/workflows/deploy.yml` `deploy/scripts/**` | 无 |
| 7 | M4-T6 审计+E2E | WorkBuddy | `feat/docs/m4-t6-audit-e2e` | 4 | `docs/m3-architecture-audit.md` `tests/test_m4_e2e.py` | T1-T5 完成 |
| 8 | M4-T7 部署+交付 | WorkBuddy | `feat/docs/m4-t7-delivery` | 4 | `docs/operations/` `docs/architecture.md` `CHANGELOG.md` + 部署脚本 | T6 完成 |

### 负载分布

| 工具 | 任务 | 总人天 | 占比 |
|------|------|--------|------|
| WorkBuddy | T1(企微) + T3(Docker) + T6(审计) + T7(交付) | 17d | 34% |
| Trae | T1(飞书钉钉) + T2(Tauri) + T4(可观测) + T5(CI/CD) | 33d | 63% |
| 并行节省 | — | -1d | 2% (T1 内部并行 + T2/T4/T5 并行) |

---

## 三、Sprint 排期

### Sprint 1：并行启动（Day 1-12）

```
WorkBuddy ──→ T1-1 企微适配器 (4d, Day 1-4)
           └→ T3 Docker编排 (5d, Day 4-9)  ← 企微完成后切
Trae     ──→ T2 Tauri客户端 (12d, Day 1-12)  [agents/client_agent/**]
           └→ T4 可观测底座 (8d, Day 1-8)    [deploy/prometheus/** + shared/sdk/**] ← 与 T2 并行（不同目录）
```

**文件交叉检查**：
- `agents/im_agent/adapters/wecom_adapter.py` ∩ `agents/client_agent/src-tauri/` = ∅ ✅
- `deploy/docker-compose.prod.yml` ∩ `agents/client_agent/` = ∅ ✅
- `deploy/docker-compose.prod.yml` ∩ `deploy/prometheus/` = ∅ (T4 在 deploy/ 子目录, 与 T3 无文件冲突) ✅

**Sprint 1 里程碑**：
- Day 4：WorkBuddy 完成企微适配器, Trae 可基于此模板写飞书/钉钉
- Day 8：Trae 完成 T4 可观测底座 (Prometheus+Grafana+Loki+OTel)
- Day 9：WorkBuddy 完成 T3 Docker 编排
- Day 12：Trae 完成 T2 Tauri 客户端

### Sprint 2：串行收尾（Day 12-20）

```
WorkBuddy ──→ T6 审计+E2E (4d, Day 12-16)  ← 等 T2/T4/T5 完成后整体审计
           └→ T7 部署+交付 (4d, Day 16-20)
Trae     ──→ T1-2/3 飞书钉钉 (6d, Day 12-18) ← 等 T1-1 完成，可复用模板
           └→ T5 CI/CD (7d, Day 8-15)        ← T4 完成后即开始

注意：Trae 在 Day 12-15 需同时推进飞书钉钉和 Helm Charts，无文件冲突。
T5 7d 从 Day 8 开始（T4 完成后立即接续），Day 15 完成。
```

**Sprint 2 里程碑**：
- Day 15：Trae 完成 T5 CI/CD Helm Charts
- Day 16：WorkBuddy 完成 T6 审计+E2E
- Day 18：Trae 完成 T1 飞书钉钉适配器
- Day 20：WorkBuddy 完成 T7 生产部署 + 交付文档

### 完整时间线

```
Day  1     4     8  9     12    15 16    18    20
     │     │     │  │     │     │  │     │     │
WB:  ├─T1企微─┤     ├─T3 Docker────┤      ├─T6审计─┤─T7交付─┤
Trae:├────────T2 Tauri (12d) ────────────────────────────┤
     ├────T4 可观测(8d)────┤├──T5 CI/CD(7d)──┤           │
                            ├─T1飞书钉钉(6d)─────────────┤
     │     │     │  │     │     │  │     │     │
```

> 总工期约 20 天。关键路径：WorkBuddy 路径 (4+5+4+4=17d)，Trae 路径 (12d 以内都小于 17d)。

---

## 四、PR 与 Review 流程

### 简化流程（无 Qoder）

M4 不需要 Qoder review，改为 **WorkBuddy 自检 + Trae 交叉 review**：

```
1. Agent 在 feature 分支完成开发
2. Agent 运行 make verify + make test-cov（本地门禁）
3. Agent 推送分支，创建 PR
4. CI 自动运行（lint + type-check + test）
5. (Optional) 另一个 Agent review PR
6. CI 全绿 → 合并到 main
```

### WorkBuddy 自检清单（合并前）

每个 PR WorkBuddy 自己检查：

- [ ] **类型安全**：mypy strict 通过
- [ ] **测试覆盖**：新增代码有测试
- [ ] **文件边界**：PR 改动未超出分配目录范围
- [ ] **命名规范**：Commit message 符合 Conventional Commits
- [ ] **文档完整性**：新增模块有 `__init__.py` 和 docstring

---

## 五、交接协议

### 关键交接点

| 场景 | 交接方向 | 时机 | 交接内容 |
|------|---------|------|---------|
| 企微模板 → 飞书钉钉 | WorkBuddy → Trae | Day 4 | wecom_adapter.py 代码 + API mock 模式 |
| 可观测底座完成 | Trae → WorkBuddy | Day 8 | OTel exporter 实现 + 配置说明 |
| M4 全量完成后 E2E | Trae → WorkBuddy | Day 15 | 所有模块的接口说明 + tool 清单 |

### 交接格式（GitHub Issue 评论）

```markdown
@Trae 交接说明：

## 已完成
- agents/im_agent/adapters/wecom_adapter.py — 完整实现企微适配器
- agents/im_agent/webhook_routes.py — POST /im/webhook/{platform} 端点
- tests/test_im_real.py — 35+ 测试

## 飞书/钉钉复用时注意
- 复用 BaseIMAdapter 接口和 IMSendRequest/IMSendResponse 模型
- API mock 模式见 tests/test_im_real.py 的 httpx.MockTransport 用法
- 企微的加密解密逻辑不要复制到飞书（飞书用签名验证, 钉钉用加签）

## 验证方式
make test tests/test_im_real.py
```

---

## 六、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| Tauri macOS 构建失败 | 中 | T2 阻塞 | 先验证 `npm create tauri-app` 可运行, 再写代码 |
| Helm Charts 在目标 K8s 不兼容 | 低 | T5 不可用 | 同时提供 docker-compose.prod.yml 作为 fallback |
| Trae 上下文腐烂（T2 12d 最长）| 中 | T2 质量下降 | 每天在 Issue 写精炼摘要, 每 5d 开新会话 |
| 测试服务器 OCI 端口被封 | 高 | T7 无法验收 | 已在运维手册记录 OCI Console 操作步骤 |
| 企微 API 无测试环境 | 中 | T1 无法真实验证 | 全部用 API mock 测试, 生产环境手动配置 API Key |

---

## 七、GitHub Issue 模板

```markdown
## 任务
M4-TX: [任务标题]

## 背景
[来自 docs/m4-plan.md 的任务描述]

## 验收标准
- [ ] [具体标准]
- [ ] make verify 通过
- [ ] make test-cov 通过
- [ ] PR 关联本 Issue

## 分配
- Agent: [WorkBuddy/Trae]
- 分支: feat/<module>/m4-tX
- 预计工时: X 人天

## Labels
complexity:medium, module:<module>, type:feature
```

---

## 八、质量门禁时间线

| 检查点 | 时间 | 内容 |
|--------|------|------|
| Day 4 | T1-1 完成 | 企微适配器 tests + mypy clean |
| Day 8 | T4 完成 | Prometheus metrics + OTel exporter tests |
| Day 9 | T3 完成 | docker compose config 验证 |
| Day 12 | T2 完成 | Tauri cargo check + vue-tsc |
| Day 15 | T5 完成 | helm lint + GitHub Actions workflow 验证 |
| Day 16 | T6 完成 | 全量 make verify + make test-cov ≥ 800 tests |
| Day 20 | T7 完成 | 生产部署 + 安全扫描 + GitHub Release v1.0.0 |