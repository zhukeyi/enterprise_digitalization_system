# 连接器契约规格（Connector Contract）

> 唯一事实源（SoR）for 跨仓库契约。FDE ↔ Java 连接器（logistics_agent 等）之间的
> 即插即用协议。本文件对应主计划 **P0** 阶段交付物，落实评审计 F6（契约版本化）。
> 凭证相关细节见 [`credential-storage-spec.md`](./credential-storage-spec.md) (F13)。

---

## 1. 设计目标

1. **即插即用**：任意 Java 连接器只要暴露 `GET /manifest` 并实现约定端点，即可被 FDE
   自动注册为可问答的数据源，无需 FDE 改码。
2. **统一落库**：本地文件（A）与连接器（B）都归一成 `CanonicalDocument`，走同一条
   ingestion 管线，落同一套表 (`canonical_documents`)，进同一个 Qdrant。
3. **版本化、向后兼容**（F6）：契约含 `schema_version`（semver）。破坏性变更需 FDE 与
   连接器**双端同步**发布；FDE 收到未知/不兼容版本时**优雅降级 + 告警**，而非崩溃。

---

## 2. 契约模型（代码即真相）

代码定义在 `shared/contracts/connector_contract.py`（Pydantic v2，零后端依赖，
可被子仓库直接 import）：

| 模型 | 用途 |
|------|------|
| `ConnectorManifest` | 连接器在 `GET /manifest` 返回的自描述元数据 |
| `CanonicalDocument` | 归一后的标准实体，落 `canonical_documents` |
| `FieldMapping` / `FieldMappingRule` | 原始 payload → `CanonicalDocument.fields` 的声明式映射 |
| `apply_field_mapping(raw, mapping)` | 执行映射的纯函数（缺字段不抛错，写 `metadata.mapping_warnings`） |

---

## 3. ConnectorManifest v1

连接器在 `GET /manifest` 返回：

```json
{
  "schema_version": "1.0.0",
  "connector_id": "logistics_yonyou",
  "name": "用友物流连接器",
  "description": " expose yonyou logistics entities to FDE",
  "protocol": "rest",
  "base_url": "https://logistics.internal",
  "auth_type": "api_key",
  "capabilities": ["query", "list_entities"],
  "entity_types": ["sales_order", "shipment"],
  "field_mapping_ref": "config/field_mapping.yaml",
  "health_check_path": "/actuator/health"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `schema_version` | string(semver) | ✅ | 本 manifest 契约版本；FDE 校验 MAJOR |
| `connector_id` | string | ✅ | 稳定唯一 id，建议 `<域>_<系统>` |
| `name` | string | ✅ | 可读名 |
| `description` | string? | ❌ | |
| `protocol` | `rest`\|`grpc` | ❌ | 默认 `rest` |
| `base_url` | string? | ❌ | API 根地址 |
| `auth_type` | `none`\|`api_key`\|`oauth2`\|`basic` | ❌ | 默认 `none` |
| `capabilities` | string[] | ❌ | 声明能力，用于 Supervisor 路由 |
| `entity_types` | string[] | ❌ | 能提供哪些 `doc_type` |
| `field_mapping_ref` | string? | ❌ | `field_mapping.yaml` 路径/URL |
| `health_check_path` | string? | ❌ | FDE 健康检查轮询路径 |

校验：`schema_version` 必须符合 semver 2.0.0，否则 manifest 被拒（400）。

---

## 4. CanonicalDocument

归一后实体（与来源无关）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `doc_type` | string | 规范实体类型，如 `sales_order` |
| `title` | string | 预览/检索用标题 |
| `fields` | object | 归一后的规范字段 |
| `doc_id` | string? | 源系统内稳定 id（幂等 upsert 键） |
| `source_ref` | string? | 溯源：`connector://<id>/<type>/<pk>` 或 `local://<hash>` |
| `language` | string? | ISO 639-1 |
| `content_hash` | string? | 归一 payload 哈希，去重用 |
| `metadata` | object? | 非规范附加信息（含 `mapping_warnings`） |

---

## 5. FieldMapping schema（`field_mapping.yaml`）

```yaml
schema_version: "1.0.0"
connector_id: logistics_yonyou
doc_type: sales_order
rules:
  - source_path: data.orderNo      # 支持列表下标: items.0.sku
    target_field: order_no
    transform: to_upper            # 可选
    required: true                 # 缺失则写 mapping_warnings
```

- `source_path`：对原始 payload 的点路径，支持 dict 键与 list 下标。
- `target_field`：写入 `CanonicalDocument.fields` 的规范字段名。
- `transform`：可选转换（`to_upper` / `to_iso_date` / `coalesce` / ...）。
- `required`：缺失时是否告警（不抛错，保证单字段失败不丢整条文档）。

示例见 `config/field_mapping.yaml`。

---

## 6. 版本兼容矩阵（F6）

| FDE 支持 | 连接器 `schema_version` | 行为 |
|----------|--------------------------|------|
| 1.x | `1.0.0` / `1.2.3` | ✅ 完全兼容（MAJOR 相同，向后兼容） |
| 1.x | `2.0.0`（未来） | ⚠️ MAJOR 不同 → **优雅降级**：连接器标记为 `incompatible`，不注册工具，发告警；已注册旧版工具继续服务 |
| 1.x | 非法 / 缺失 | ❌ manifest 被拒，记录审计 |

**破坏性变更流程**：连接器 bump MAJOR → 同时发版 FDE 侧适配器 → 灰度切流。

---

## 7. FDE 侧消费流程（P1 实现）

```
GET /manifest ──► 校验 schema_version
   ├─ 兼容 ──► 存 connector_registry（manifest JSONB + 健康）
   │           ──► 加载 field_mapping.yaml ──► 注册 ToolDefinition
   └─ 不兼容 ─► 标记 incompatible + 告警，跳过注册
```

---

## 8. 凭证（F13 摘要）

`connector_registry.credentials_encrypted` 列 **仅存密文**（pgcrypto 对称/公钥加密），
**绝不存明文** AppID/Secret/Token。详见 [`credential-storage-spec.md`](./credential-storage-spec.md)。
