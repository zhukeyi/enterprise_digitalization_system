# logistics_agent 连接器平台 × FDE AI Platform 即插即用整合分析

> 目标：评估 `git@github.com:zhukeyi/logistics_agent.git`（一个独立的**连接器平台**）能否接入 FDE AI Platform，
> 并给出让「两边都是即插即用」所需的修改意见。
> 结论先行：**代码不能直接复用（语言不同），架构与概念高度可复用；通过定义一套统一的「连接器契约」即可让两边各自即插即用，互不绑架。**

---

## 1. logistics_agent 仓库现状（读了什么）

这是一个 **Java/Spring Boot（Maven 多模块）+ Python(FastAPI) 部署工具** 的连接器平台，分两大连接器族：

| 族 | 模块 | 对接系统 | 端口 |
|:--|:--|:--|:--|
| 企业系统 `enterprise-connector` | yonyou / kingdee / flux / otms / dynamics / mock | 用友、金蝶、富勒WMS、oTMS、Dynamics365 | 8091–8095, 8090 |
| 视频监控 `video-connector` | hikvision / dahua / ezviz / huawei / mock | 海康、大华、萤石、华为IVM | 8081–8084 |

**它已经具备的「即插即用」骨架（非常值得借鉴）：**

1. **插件契约 `ConnectorService` 接口**（`enterprise-connector-common`）
   所有 ERP/WMS/TMS 连接器实现同一接口（`getOrders/getInventory/getShipments/getEvents/health...`）。
   每加一个厂商 = 新增一个 Maven 模块 + 实现该接口，其他代码零改动。
2. **统一 REST 出口** `AbstractEnterpriseConnectorController` 把接口暴露成
   `GET /orders`、`GET /inventory`、`GET /shipments`、`GET /events`、`POST /orders`、`/health` 等标准端点。
3. **字段映射 `FieldMappingConfig`**（`connector.field-mapping.mappings` YAML）
   厂商字段名 → 标准字段名（如 `orderNo→orderNumber`、`cust_name→customerName`），正是你之前那个「字段不一致」问题已有的解法。
4. **标准数据模型**：`OrderModel / InventoryModel / ShipmentModel / MaterialModel / PartnerModel / EventModel / HealthModel`（企业族），
   `DeviceModel / ChannelModel / AlarmModel / StreamUrlModel`（视频族）。
5. **部署工具 `deploy-tool`（FastAPI + 前端）**：
   - `discovery.py`：端口扫描 + **TLS/JA3 指纹 + HTTP 指纹**自动识别子网里跑着哪些系统（用友/金蝶/海康…）；
   - `CONNECTOR_REGISTRY` 字典：`system_key → {name, port, category}`；
   - `docker-compose` 按 profile 一键拉起连接器；NL→SQL 查询；健康检查。
6. **12-factor 配置**：每个连接器 `application.yml` 全用环境变量（`YONYOU_ENABLED`、`YONYOU_BASE_URL`…），`docker-compose` 已带 healthcheck。

---

## 2. FDE 一侧现状（读了什么）

- `agents/orchestrator/tools/registry.py`：`ToolRegistry` + `ToolDefinition(name, description, worker, handler, parameters, is_dangerous, category)`。
  **这是连接器工具接入的精确接缝**——任何能力只要注册成 `ToolDefinition`，Supervisor 就能路由、前端就能看到。
- `agents/data_agent/scrapers/`：`ScraperRegistry`（SourceType→scraper），但只支持 `WEB/RSS/API` 三类通用抓取，**不感知业务实体**（订单/库存/设备），也没有 `system_type` 概念。
- **全仓库搜索 `ConnectorRegistry / SystemType / connector`：FDE 源码里完全没有连接器概念**（只有 echarts 依赖里出现 systemtype 字样）。即：FDE 当前对「业务系统数据」是空白。
- FDE 的**独有价值**是连接器平台没有的：`auth_filter`(ABAC)、`DecisionChainLog`(决策链审计)、`geo_guard`(地理防污染)。这些必须在数据出连接器后由 FDE 补上。

---

## 3. 核心结论：能不能用？

| 维度 | 结论 |
|:--|:--|
| **直接把代码搬进 FDE** | ❌ 不行。logistics_agent 是 Java；FDE 是 Python/FastAPI。不能 import，重写无必要。 |
| **整套架构/概念照搬** | ✅ 高度可复用。插件契约、字段映射、标准模型、registry+discovery 模式都能直接映射。 |
| **让 logistics_agent 作为外部连接器被 FDE 调用** | ✅ 最佳路径。它已经是「每厂商一个独立 REST 服务」的形态，FDE 用 HTTP 消费即可。 |
| **两边各自即插即用** | ✅ 可行，但需要一个**双方约定的「连接器契约」**，否则 FDE 只能硬编码端口/路径。 |

> 一句话：**不要合并代码，要统一契约。** logistics_agent 继续当独立的 Java 连接器平台（本身已即插即用）；
> FDE 增加一个「连接器适配层」去消费它（也让未来的 Python 连接器、第三方系统走同一层）。

---

## 4. 即插即用整合架构

```
                     ┌──────────────────────────────────────────────┐
                     │            FDE AI Platform (Python)           │
                     │                                                │
  用户/看板/Agent ──► │  Supervisor ──► connector_agent              │
                     │                 ├─ ConnectorRegistry           │
                     │                 ├─ ConnectorAdapter(HTTP)      │
                     │                 └─ 注册成 ToolDefinition ──────┼──► ToolRegistry
                     │                       │ 规范化                  │        │
                     │                       ▼                        │        ▼
                     │               Canonical Models          [ABAC/auth_filter + 决策链审计]
                     │                       │                        │
                     │                       ├──────────► 作为数据源 ──┼──► ingestion 管线(字段映射)
                     │                       │                        │        │ 切片 → 向量库 → RAG
                     └───────────────────────┼────────────────────────┘
                                              │  HTTP (统一契约)
                   ┌──────────────────────────┼───────────────────────────┐
                   ▼                          ▼                           ▼
          connector-yonyou:8091     connector-kingdee:8092      connector-hikvision:8081
          (Java/Spring Boot)        (Java/Spring Boot)         (Java/Spring Boot)
          /orders /inventory ...    /orders ...                /devices /stream /alarms ...
                   └──────────── 也可由 deploy-tool 的 discovery 自动发现并回写 FDE ──────┘
```

契约是唯一的耦合点，包含三件事：
1. **标准 REST 路径**（如 `/api/v1/connector/{entity}` 或沿用现有 `/orders` 等）；
2. **`/manifest` 自描述端点**（返回 system_key、category、支持实体、鉴权方式、版本）——让 FDE 免硬编码；
3. **标准响应信封**（现有 `ApiResponse<T>` 已具备，可复用）。

---

## 5. logistics_agent 需要的修改（让它对 FDE 即插即用）

> 原则：尽量小改，保留 Java 平台独立运行能力。

- **【M1】统一两套连接器契约。** 企业族与视频族的 `ConnectorService` 接口目前是分开的、模型包也不同。
  建议抽一个**共享 `ConnectorManifest`**（JSON）：声明 `system_key / category / entities[订单,库存,运单,设备,告警…] / operations[list,get,create,subscribe] / auth`，
  让 FDE 用一个适配器就能认所有连接器，而不是企业一套、视频一套。
- **【M2】新增 `/manifest` 端点（最关键）。** 现在 deploy-tool 里 `CONNECTOR_REGISTRY` 是**硬编码端口表**，
  这破坏了即插即用——FDE 换个端口就得改代码。改成每个连接器启动后暴露 `GET /manifest`，
  FDE 注册时只传 `base_url`，自己拉 manifest 推断能力。**这一步让 logistics_agent 从「半自动」变「真·即插即用」。**
- **【M3】稳定 base path。** 建议所有连接器统一前缀（如 `/api/v1/connector/...`），FDE 适配器拼接路径时不必记每家的差异。
- **【M4】字段映射与 FDE 对齐。** `FieldMappingConfig` 思路正确，但现在是**纯手写 YAML**。
  两种对齐方式二选一：① 把映射 schema 抽成和 FDE ingestion 计划里的 `field_mapping.yaml` **同一格式**，两边共享；
  ② 映射不上的字段改由 FDE ingestion 层的 `SchemaInference`（之前计划的自动推断）兜底。推荐 ①+② 组合。
- **【M5】明确安全边界。** 连接器自身 API 目前**无鉴权**。要么：连接器只监听内网 + 由 FDE 反向代理加 ABAC；
  要么：连接器支持接收 FDE 转发下来的租户 token。至少要在文档里写清信任边界，避免「即插即用」变成「即插即裸奔」。

---

## 6. FDE 需要的修改（让它能消费任意连接器并即插即用）

> 复用已有 `ToolRegistry` 接缝，不破坏现有架构。

- **【F1】新增 `agents/connector_agent/` 包：**
  - `models.py`：`ConnectorManifest`、`CanonicalEntity`（订单/库存/设备…）模型——可直接以 logistics_agent 的 `OrderModel` 等为蓝本；
  - `registry.py`：`ConnectorRegistry`（system_key → `ConnectorAdapter` 实例），支持 `register/unregister/list`；
  - `adapter.py`：`ConnectorAdapter`（httpx 客户端，拉 manifest，按契约拼路径，把响应归一到 Canonical 模型，套用 field_mapping）；
  - `tools.py`：把已注册连接器**动态注册成 `ToolDefinition`**（如 `connector_yonyou_get_orders`），挂到 `ToolRegistry`。
- **【F2】注册与发现 API：** `POST /connectors/register`（base_url + system_key + 凭据）→ 拉 manifest → 建 adapter → 注册工具；
  `GET /connectors`、`GET /connectors/{key}/health`（轮询，复用 deploy-tool 的 health 思路）。可把 deploy-tool 的 `discovery.py` **移植成 FDE 的一个扫描工具**（纯 Python，无需 Java），自动发现内网连接器并批量注册。
- **【F3】Supervisor 路由：** 在 Supervisor 的意图识别里加「业务系统查询」分支——"查用友的华东仓库存" → 命中 `connector_yonyou_*` 工具；
  未知连接器也能因 manifest 而动态可用，无需改 Supervisor 代码。
- **【F4】 ingestion 桥接（合并之前的多维数据输入任务）：** 连接器可作为**数据源**注册进 ingestion 管线——
  连接器实体（订单/库存 JSON）→ 经 `field_mapping.yaml` 归一 → 落地 Canonical 表 → 切片 → 向量库 → RAG。
  这样「业务系统数据」和「Word/PDF/Excel 文件」走同一条清洗/入库/检索链路，正是你上一轮要的能力。
- **【F5】ABAC 包裹：** 连接器读操作经过 `auth_filter`（按用户/角色过滤可见字段与行）+ `DecisionChainLog` 留痕；
  写操作（createOrder 等）标记 `is_dangerous=True` 走防呆二次确认。补上 logistics_agent 缺失的治理层。

---

## 7. 字段映射 / 标准模型对齐（与上一轮任务的关系）

- logistics_agent 的 `FieldMappingConfig` 与 FDE ingestion 计划的 `field_mapping.yaml` **是同一思想的两种实现**。
  建议统一为一份 schema：厂商字段别名 + 类型强转 + 兜底 `custom_fields`，**两边共享同一份 YAML 规范**（Java 侧 `@ConfigurationProperties` 读、Python 侧 pydantic 读）。
- logistics_agent 的 `OrderModel/InventoryModel/...` 可直接充当 FDE `CanonicalEntity` 的**初始字段定义**，
  省去重新设计标准 schema 的成本；视频族的 `DeviceModel/AlarmModel` 同理。

---

## 8. 推荐落地路径（与之前增量风格一致）

| 阶段 | 范围 | 产出 | 工作量 |
|:--|:--|:--|:--|
| **P0 契约定型** | 定义 `ConnectorManifest` JSON schema + 标准 REST 路径 + 响应信封 | `docs/connector-contract.md` | 小 |
| **P1 logistics 侧** | 给 1 个连接器（建议 mock 或 yonyou）加 `/manifest` 端点 + 统一 base path | 验证 M2/M3 | 小（1 模块） |
| **P1 FDE 侧** | `connector_agent` 骨架：registry + adapter + 注册 1 个 yonyou/mock 为 ToolDefinition | 验证 F1/F2/F3 | 中 |
| **P2 打通** | 接 ingestion 桥接，把连接器订单/库存喂进 RAG 并问答验证 | 验证 F4 | 中 |
| **P3 治理+扩展** | ABAC 包裹(F5)、discovery 移植、补齐 field_mapping 对齐、视频族接入 | 完整能力 | 大 |

**建议从 P0 + P1 两端各取最小切片先打通**（和之前「先搭骨架」的节奏一致）：
logistics 侧加 `/manifest`，FDE 侧能注册它并把它暴露成一个可问答的工具。这一步不依赖重依赖、不污染生产，却能把「即插即用」从概念变成可演示的事实。

---

## 9. 风险与注意

1. **语言边界不可逆**：Java 连接器与 Python FDE 只能服务间调用，无法共享进程内对象。契约就是唯一的契约，版本要向后兼容。
2. **视频流不进 RAG**：海康/大华的 RTSP/HLS 流是二进制流，不会进向量库；它们应作为「工具/流地址」暴露给看板，而不是 ingestion 数据源。别把视频族硬塞进文档型 RAG。
3. **契约漂移**：若 logistics_agent 改了路径/manifest，FDE 适配器要能优雅降级（manifest 拉不到就标 DOWN，不影响其他连接器）。
4. **凭据安全**：连接器的 `app_key/app_secret` 必须由 FDE 的密钥管理注入，绝不下发到前端；FDE 代理时再带租户上下文。
5. **不要重复造轮子**：FDE 已有 `ScraperRegistry` 只覆盖通用抓取；连接器是「业务实体级」抓取，二者并存不冲突，但注册入口建议统一到 `connector_agent`，避免两套发现机制。

---

## 10. 一句话总结

logistics_agent **不能当代码复用进 FDE，但作为「独立的 Java 连接器平台」是绝佳的外部数据源**——
它已经做到了「每厂商一个即插即用模块」。要让**两边**都即插即用，关键是补一个**双方约定的连接器契约（manifest + 标准路径 + 响应信封）**：
logistics_agent 加 `/manifest` 端点（M2），FDE 加 `connector_agent` 适配层把任意连接器注册成 `ToolDefinition` 并接进 ingestion/RAG（F1–F5）。
这样既保住 Java 平台的独立演进，又让 FDE 用同一套机制吃下用友/金蝶/海康/未来任何系统。

**需要我直接开始实现吗？** 我建议先做 P0（契约文档）+ P1（logistics 侧 `/manifest` + FDE 侧 `connector_agent` 骨架并注册一个 mock/yonyou 连通），最小代价验证「即插即用」。
