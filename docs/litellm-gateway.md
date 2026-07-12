# LiteLLM 网关统一 + 多租户基座（P0-A）

> 对应 `docs/oss-optimization-roadmap.md` 的 **P0-A** 阶段。
> 目标：用 LiteLLM 统一 100+ 模型接入、建立按租户的虚拟 Key / 预算 / 计费基座，
> 并以**灰度方式**接入，绝不破坏现有网关链路（风险 R1 缓解）。

---

## 1. 架构位置

```
调用方 (门户 / Dify / 其他 Agent)
        │  Authorization: Bearer <FDE API Key>  →  APIKeyMiddleware 鉴权
        ▼
FDE router_agent  /v1/chat/completions
        │  从请求头解析虚拟 Key → request.extra["litellm_key"]
        ▼
LiteLLMAdapter (BaseAdapter 实现, 仅配置时健康)
        │  httpx → OpenAI 兼容 /chat/completions
        ▼
LiteLLM Proxy :4000  ── 虚拟 Key 强制: 模型白名单 + 预算 + 限流 + 兜底
        │
        ▼
真实 Provider (DeepSeek / GLM / Qwen / ...)
```

- 现有 4 个适配器（Mock / DeepSeek-stub / Qwen-stub / GLM-stub）**保持不变**，
  作为 LiteLLM 未启用时的兜底路径。
- LiteLLM 不可用时，`LiteLLMAdapter.health_check()` 返回 `False`，从 `/v1/models`
  与 fallback 链中**隐形**——这是灰度 / 回退安全的核心机制。

## 2. 启用方式（环境变量）

| 变量 | 说明 | 默认值 |
| :--- | :--- | :--- |
| `LITELLM_PROXY_URL` | LiteLLM 代理地址；**设置即启用适配器** | 空（禁用） |
| `LITELLM_MASTER_KEY` | 代理管理 Key（生成虚拟 Key 用） | 空 |
| `LITELLM_DEFAULT_MODEL` | 未指定 model 时的别名 | `fde-default` |

仅当 `LITELLM_PROXY_URL` 非空时，`build_litellm_adapter()` 才返回一个已注册的
`LiteLLMAdapter`；否则返回 `None`，网关维持原状。

## 3. 部署（隔离、低风险）

配置文件：`deploy/litellm/config.yaml` + `deploy/litellm/docker-compose.yml`

```bash
cd deploy/litellm
cp .env.example .env        # 设置 LITELLM_MASTER_KEY + 各 Provider Key
docker compose up -d
curl -f http://localhost:4000/health/liveliness
```

- 独立容器 `fde-litellm`，端口 `:4000`，自有 bridge 网络，内存上限 **512M**。
- 不改动现有 FDE 后端 / nginx / Dify / Qdrant 链路。
- P0-B 会把它合并进主 `docker-compose.prod.yml`，并把
  `LITELLM_PROXY_URL=http://fde-litellm:4000` 注入 fde-backend 服务。

## 4. 多租户模型

对应 V5 商业模式（基础版 / 增值单模块 / 全家桶）：

| 订阅层 (`SubscriptionTier`) | 模型白名单 | 预算(USD) | 限流(RPM) | 模块授权 |
| :--- | :--- | :--- | :--- | :--- |
| `base` 基础版 | fde-economy, fde-default | 5 | 10 | 无（仅 ①②③） |
| `addon` 增值单模块 | + fde-premium | 50 | 60 | 指定 ④/⑤/⑥/⑦ |
| `enterprise` 全家桶 | + fde-frontier | 500 | 300 | ①-⑦ 全开 |

每个租户 → 一个 LiteLLM 虚拟 Key，Key 上绑定模型白名单 + `spend` 预算 + `max_parallel_requests`
限流；LiteLLM 代理**服务端强制**这些策略，FDE 网关 offload 了多租户鉴权与计费。

## 5. 租户管理 API（`/api/tenants`，需有效 API Key）

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| POST | `/api/tenants` | 创建租户 +（代理启用时）自动发放虚拟 Key |
| GET | `/api/tenants` | 租户列表 |
| GET | `/api/tenants/{id}` | 租户详情 + 其 Key 列表 |
| PATCH | `/api/tenants/{id}` | 局部更新（预算/白名单/模块授权/状态） |
| DELETE | `/api/tenants/{id}` | 软删租户 + 吊销其全部 Key |
| GET | `/api/tenants/{id}/key` | 当前有效 Key（脱敏） |
| POST | `/api/tenants/{id}/key/rotate` | 吊销旧 Key + 发放新 Key |

虚拟 Key 在创建/轮换时由 `LiteLLMKeyClient` 调 `/key/generate` 生成；
代理不可用时优雅降级（租户记录仍创建，Key 标记为未发放）。

## 6. 虚拟 Key 透传（端到端多租户）

1. 调用方持租户虚拟 Key 请求 FDE `/v1/chat/completions`，
   头 `Authorization: Bearer <tenant_virtual_key>`。
2. 网关解析该头，写入 `chat_request.extra["litellm_key"]`。
3. `LiteLLMAdapter.complete()` 将其作为 Bearer token 转发给代理；
   LiteLLM 据此强制该租户的策略。
4. 无虚拟 Key 时退化为适配器 `api_key`（单机开发模式）。

## 7. 代码清单

| 文件 | 职责 |
| :--- | :--- |
| `agents/router_agent/adapters/litellm_adapter.py` | `LiteLLMAdapter`（BaseAdapter 契约，httpx 直连，无 litellm 重依赖）+ 工厂 |
| `agents/router_agent/tenant/models.py` | `SubscriptionTier` / `Tenant` / `TenantKey` + 分级默认 |
| `agents/router_agent/tenant/store.py` | 内存租户存储（环形事件，与 observability 一致） |
| `agents/router_agent/tenant/litellm_keys.py` | 虚拟 Key 管理客户端（/key/generate /info /delete） |
| `agents/router_agent/tenant/router.py` | `/api/tenants` CRUD |
| `agents/router_agent/main.py` | 条件注册适配器 + 挂载租户路由 + Key 透传 |
| `deploy/litellm/*` | 代理部署配置 |

## 8. 测试

```bash
pytest agents/router_agent/tests/test_litellm_adapter.py \
       agents/router_agent/tests/test_tenant.py -q
```

覆盖：工厂灰度门禁、请求/响应映射、虚拟 Key 透传、错误分支；
租户 CRUD 生命周期、Key 生命周期、事件记录、Key 客户端 mock。
全部使用 `httpx.MockTransport`，无真实网络依赖。

## 9. 已知范围与后续

- **嵌入（embedding）未走 LiteLLM**：FDE 的 RAG 嵌入仍用本地 ONNX BGE（P4 已优化），
  质量与延迟更优；embedding 经 LiteLLM 透传为后续可选项。
- **角色级管理员授权**：当前租户路由由 app 级 APIKeyMiddleware 统一鉴权，
  细粒度 admin 角色是 P0-B 加固项。
- **持久化**：租户存储为单实例内存；多实例时需换 SQLite/Postgres。
