# M3 Trae 任务细化

> Agent: Trae（辅助 Agent）
> 分工来源: docs/m3-collaboration-plan.md (commit 646e715)
> 总任务: 7 个 (T1, T8, T2, T9, T4, T11, T12)，共 71 人天
> 编写时间: 2026-07-01

---

## 一、Trae 分工总览

| 序号 | 任务 | 分支 | 人天 | 改动目录 | 前置依赖 | Sprint |
|------|------|------|------|---------|---------|--------|
| 1 | M3-T1 | `feat/data-agent/m3-t1` | 18 | `agents/data_agent/**` | 无 | S1 (Day 1-18) |
| 2 | M3-T8 | `feat/map-agent/m3-t8` | 7 | `frontend/map-ai/src/stores/` `frontend/map-ai/src/components/` | 无 | S2 (Day 18-25) |
| 3 | M3-T2 | `feat/data-agent/m3-t2` | 8 | `agents/data_agent/**` | T1 完成 | S2 (Day 25-33) |
| 4 | M3-T9 | `feat/map-agent/m3-t9` | 10 | `frontend/map-ai/src/components/` | T8 完成 | S3 (Day 33-43) |
| 5 | M3-T4 | `feat/analysis-agent/m3-t4` | 10 | `agents/analysis_agent/**` | T3 完成 (WorkBuddy) | S3 (Day 43-53) |
| 6 | M3-T11 | `feat/map-agent/m3-t11` | 7 | `agents/map_agent/tasks.py` `agents/map_agent/websocket.py` `frontend/map-ai/src/stores/` | T10 完成 (WorkBuddy) | S4 (Day 46-53) |
| 7 | M3-T12 | `feat/map-agent/m3-t12` | 11 | `frontend/map-ai/src/components/` `frontend/map-ai/src/views/` | T11 完成 | S4 (Day 53-64) |

### 执行顺序与依赖

```
Sprint 1:  T1 (数据采集, 18d) ──────────────────────┐
Sprint 2:  T8 (地图前端标记, 7d) → T2 (报告推送, 8d) ┘
Sprint 3:  T9 (收纳盒+语音, 10d) → T4 (Dashboard, 10d)
Sprint 4:  T11 (异步推送, 7d) → T12 (可视化, 11d)
```

### 与其他 Agent 的交接点

| 交接点 | 方向 | 时机 | 交接内容 |
|--------|------|------|---------|
| T1→T2 | Trae→Trae（自续） | Day 18 | data_agent 模块结构 + integration.py 工具签名 |
| T8→T9 | Trae→Trae（自续） | Day 25 | 前端 Store 结构 + 组件命名约定 |
| T9→T10 | Trae→WorkBuddy | Day 43 | 前端 API 调用契约 (POST /api/analysis/correlate 的 request/response) |
| T3→T4 | WorkBuddy→Trae | Day 28 | analysis_agent models.py + nl2sql.py 接口签名 |
| T10→T11 | WorkBuddy→Trae | Day 46 | map_agent/routes.py 后端 API + LangGraph 节点实现 |

---

## 二、各任务详细执行方案

---

### M3-T1: 多源爬虫 + 数据采集 + 清洗管道 + 分析流水线（18 人天）

**分支**: `feat/data-agent/m3-t1`
**改动目录**: `agents/data_agent/**`
**前置状态**: 空壳（仅 `__init__.py` + `tests/__init__.py`）

#### 1. 产出文件清单

```
agents/data_agent/
├── __init__.py              # 模块导出
├── models.py                # T1-1: SourceConfig, CollectedItem, DataQualityReport
├── scrapers/
│   ├── __init__.py          # 导出 BaseScraper, HTTPScraper, RSSScraper, APIScraper
│   ├── base.py              # T1-2: BaseScraper 抽象基类
│   ├── http_scraper.py      # T1-2: HTTP 爬虫 (httpx + selectolax)
│   ├── rss_scraper.py       # T1-3: RSS Feed 采集器 (feedparser)
│   └── api_scraper.py       # T1-4: REST API 适配器 (httpx)
├── cleaning.py              # T1-5: 数据清洗管道 (去重/标准化/PII脱敏)
├── pipeline.py              # T1-6: DataPipeline ETL 流水线
├── integration.py           # T1-7: ToolRegistry 注册 (4 个工具)
└── tests/
    ├── __init__.py
    ├── test_models.py       # 模型验证测试
    ├── test_scrapers.py     # 爬虫单元测试 (mock httpx)
    ├── test_cleaning.py     # 清洗管道测试
    ├── test_pipeline.py     # ETL 流水线测试
    └── test_integration.py  # 工具注册 + dispatch 测试
```

#### 2. 子任务拆分与执行顺序

| 子任务 | 内容 | 人天 | 关键技术决策 |
|--------|------|------|-------------|
| T1-1 | models.py — Pydantic 模型定义 | 2 | SourceConfig(source_type: enum, url, auth_config), CollectedItem(id, source, content, raw_html, metadata, collected_at), DataQualityReport(completeness, uniqueness, validity_score) |
| T1-2 | scrapers/base.py + http_scraper.py | 4 | BaseScraper: `async def fetch(url) -> CollectedItem`; HTTPScraper: httpx.AsyncClient + selectolax HTML 解析; 复用 shared/utils/retry.py 的 retry_async |
| T1-3 | scrapers/rss_scraper.py | 2 | feedparser 库; 异步包装 (run_in_executor); 支持 Atom/RSS 2.0 |
| T1-4 | scrapers/api_scraper.py | 2 | httpx.AsyncClient; 支持 Bearer token / API Key 认证; 分页处理 |
| T1-5 | cleaning.py | 3 | 去重: hash_content (复用 shared/utils/hashing.py); 标准化: 字段映射 + 类型转换; PII 脱敏: 复用 shared/models/pii.py 的 PiiString; 输出: CleanedItem |
| T1-6 | pipeline.py | 3 | DataPipeline: `async def run(config) -> PipelineResult`; 三阶段 extract→transform→load; extract 调用 scraper, transform 调用 cleaning, load 写入内存/DB stub |
| T1-7 | integration.py + tests | 2 | 参照 rag_agent/integration.py 模式; register_data_tools(registry); 4 个工具 handler 均为 async |

#### 3. 注册工具签名

```python
# integration.py — 参照 agents/rag_agent/integration.py 的 register_rag_tools 模式

register_data_tools(registry: ToolRegistry) -> None:
    # 工具 1: data_collect
    ToolDefinition(
        name="data_collect",
        description="从指定数据源采集数据 (web/rss/api)",
        worker="data",
        handler=_data_collect_handler,  # async def _data_collect_handler(source_type, query, max_items=50) -> dict
        parameters={
            "source_type": {"type": "string", "required": True, "description": "web, rss, api"},
            "query": {"type": "string", "required": True, "description": "URL or search query"},
            "max_items": {"type": "integer", "required": False, "default": 50},
        },
        category="data",
    )

    # 工具 2: data_clean
    ToolDefinition(
        name="data_clean",
        description="清洗原始数据 (去重/标准化/PII脱敏)",
        worker="data",
        handler=_data_clean_handler,  # async def _data_clean_handler(raw_items) -> dict
        parameters={
            "raw_items": {"type": "array", "required": True, "description": "原始采集数据列表"},
        },
        category="data",
    )

    # 工具 3: data_pipeline
    ToolDefinition(
        name="data_pipeline",
        description="执行完整 ETL 流水线 (extract→transform→load)",
        worker="data",
        handler=_data_pipeline_handler,  # async def _data_pipeline_handler(source_config, transform_config) -> dict
        parameters={
            "source_config": {"type": "object", "required": True},
            "transform_config": {"type": "object", "required": False, "default": {}},
        },
        category="data",
    )

    # 工具 4: data_quality_report
    ToolDefinition(
        name="data_quality_report",
        description="生成数据质量报告 (完整性/唯一性/有效性)",
        worker="data",
        handler=_data_quality_report_handler,  # async def _data_quality_report_handler(dataset_id) -> dict
        parameters={
            "dataset_id": {"type": "string", "required": True},
        },
        category="data",
    )
```

#### 4. 依赖管理

需在 `pyproject.toml` 的 `[project.optional-dependencies]` 中添加 `data` 分组:

```toml
[project.optional-dependencies]
data = [
    "httpx>=0.27",
    "selectolax>=0.3",
    "feedparser>=6.0",
]
```

轻量依赖，可放入主依赖 `[project.dependencies]`。最终决定在 T1-1 开发时确认。

#### 5. 验收标准

- [ ] `make verify` 通过 (ruff + black + mypy strict)
- [ ] `make test agents/data_agent/` 全绿，覆盖率 ≥ 85%
- [ ] 4 个工具成功注册到 ToolRegistry，dispatch 测试通过
- [ ] Mock 模式下可完整运行 ETL 流水线（不需要真实网络请求）
- [ ] PR 描述包含工具签名表，供 T6 集成参考

---

### M3-T8: 全局状态管理 + 地图/弹窗/下钻"+"按钮 + UI反馈（7 人天）

**分支**: `feat/map-agent/m3-t8`
**改动目录**: `frontend/map-ai/src/stores/` `frontend/map-ai/src/components/`
**前置状态**: 前端已有 Vue3 + Pinia 骨架 (stores/chat.ts, components/MapView.vue)

#### 1. 产出文件清单

```
frontend/map-ai/src/
├── stores/
│   └── analysis.ts           # T8-1: Pinia Store — markedEntities CRUD + LocalStorage
├── components/
│   ├── MapMarkerPlus.vue     # T8-2: 地图 Marker "+" 按钮
│   ├── SidebarPlus.vue       # T8-3: 侧边栏 "+" 按钮
│   ├── DrillDownPlus.vue     # T8-4: 下钻信息框 "+" 按钮
│   └── EntityToast.vue       # T8-5: UI 反馈 Toast 提示
├── types/
│   └── analysis.ts           # TypeScript 类型定义 (GeoEntity, AnalysisContext)
└── composables/
    └── useEntityMarking.ts   # 组合式函数，封装标记逻辑
```

#### 2. 子任务拆分

| 子任务 | 内容 | 人天 | 关键点 |
|--------|------|------|--------|
| T8-1 | stores/analysis.ts + types/analysis.ts | 2 | Pinia store: `markedEntities: GeoEntity[]`, actions: addEntity/removeEntity/clearAll; LocalStorage 持久化通过 pinia-plugin-persistedstate; 类型与后端 map_agent/models.py 对齐 |
| T8-2 | MapMarkerPlus.vue | 2 | Mapbox GL Marker 点击事件 → 调用 useEntityMarking().toggleMark(entity); 防重复: entity_id 去重; 视觉: 已标记实体高亮 |
| T8-3 | SidebarPlus.vue | 1 | 监控弹窗/侧边栏实体的 "+" 按钮; emit('mark', entity) 事件 |
| T8-4 | DrillDownPlus.vue | 1 | 下钻信息框中的 "+" 按钮; 支持从下钻结果直接标记 |
| T8-5 | EntityToast.vue + composables/useEntityMarking.ts | 1 | Toast: 标记成功/失败/重复提示; useEntityMarking: 统一入口，封装 store 操作 + Toast 触发 |

#### 3. 类型定义（与后端对齐）

```typescript
// types/analysis.ts — 对齐 agents/map_agent/models.py

export interface GeoPoint {
  lng: number
  lat: number
  label?: string
}

export interface GeoEntity {
  entity_id: string
  name: string
  location: GeoPoint
  entity_type: string  // point, polygon, building, region, route
  properties: Record<string, unknown>
  data_source: string  // manual, api, db_query
  marked_at: string  // ISO datetime
}
```

#### 4. Pinia Store 设计

```typescript
// stores/analysis.ts
import { defineStore } from 'pinia'
import type { GeoEntity } from '@/types/analysis'

export const useAnalysisStore = defineStore('analysis', {
  state: () => ({
    markedEntities: [] as GeoEntity[],
    session_id: '' as string,
    loading: false,
  }),
  getters: {
    entityCount: (state) => state.markedEntities.length,
    entityIds: (state) => state.markedEntities.map(e => e.entity_id),
    hasEntity: (state) => (id: string) => state.markedEntities.some(e => e.entity_id === id),
  },
  actions: {
    addEntity(entity: GeoEntity): boolean  // 去重，返回是否成功
    removeEntity(entity_id: string): boolean
    clearAll(): void
    setSession(id: string): void
  },
  persist: {
    key: 'fde-analysis-context',
    storage: localStorage,
    paths: ['markedEntities', 'session_id'],
  },
})
```

#### 5. 验收标准

- [ ] `npm run type-check` (vue-tsc) 0 errors
- [ ] `npm run build` 成功
- [ ] 地图上点击 Marker 可标记/取消标记实体，刷新页面后状态保留（LocalStorage）
- [ ] 侧边栏和下钻信息框的 "+" 按钮功能正常
- [ ] 重复标记同一实体有 Toast 提示
- [ ] 无 console.error / console.warn

---

### M3-T2: 报告模板引擎 + 定制化推送服务（8 人天）

**分支**: `feat/data-agent/m3-t2`
**改动目录**: `agents/data_agent/**`
**前置**: M3-T1 完成

#### 1. 产出文件清单

```
agents/data_agent/
├── report_models.py          # T2-1: ReportTemplate, ReportInstance, ReportConfig
├── report_renderer.py        # T2-2: Jinja2 渲染 + matplotlib 图表
├── push_service.py           # T2-3: 多渠道推送 (邮件/IM/Webhook)
├── scheduler.py              # T2-4: APScheduler 轻量调度
└── tests/
    ├── test_report.py        # 报告生成测试
    └── test_push.py          # 推送服务测试
```

#### 2. 子任务拆分

| 子任务 | 内容 | 人天 | 关键点 |
|--------|------|------|--------|
| T2-1 | report_models.py | 2 | ReportTemplate(jinja2_template, chart_configs), ReportInstance(template_id, data, rendered_html, generated_at), ReportConfig(schedule, recipients, channels) |
| T2-2 | report_renderer.py | 2 | Jinja2 Environment (from_string); matplotlib 生成 PNG (bar/line/pie); 图片 base64 嵌入 HTML; 支持模板继承 |
| T2-3 | push_service.py | 2 | 复用 im_agent/adapters/ 的 Webhook 模式; 邮件: smtplib (async via run_in_executor); IM: 调用 im_agent tools.py 的 send_message; Webhook: httpx.AsyncClient POST |
| T2-4 | scheduler.py | 1 | APScheduler AsyncIOScheduler; register_report_job(config); 支持 cron/interval 触发; 轻量，不引入 Celery |
| T2-5 | 测试 | 1 | Mock Jinja2 渲染; Mock matplotlib (验证调用，不验证图片); Mock smtplib + httpx |

#### 3. 额外工具注册

```python
# 追加到 integration.py 或新建 report_integration.py

# 工具 5: report_generate
ToolDefinition(
    name="report_generate",
    description="基于模板生成数据报告 (Jinja2 + 图表)",
    worker="data",
    handler=_report_generate_handler,  # async def _report_generate_handler(template_id, data) -> dict
    parameters={
        "template_id": {"type": "string", "required": True},
        "data": {"type": "object", "required": True},
    },
    category="report",
)

# 工具 6: report_push
ToolDefinition(
    name="report_push",
    description="推送报告到指定渠道 (邮件/IM/Webhook)",
    worker="data",
    handler=_report_push_handler,  # async def _report_push_handler(report_id, channels, recipients) -> dict
    parameters={
        "report_id": {"type": "string", "required": True},
        "channels": {"type": "array", "required": True, "description": "email, im, webhook"},
        "recipients": {"type": "array", "required": True},
    },
    category="report",
)
```

#### 4. 验收标准

- [ ] `make verify` 通过
- [ ] Mock 数据可生成 HTML 报告（含 base64 图片）
- [ ] 推送服务 Mock 模式可发送到 im_agent 的 MockAdapter
- [ ] 调度器可注册/取消定时任务（不需要真实运行 cron）
- [ ] 覆盖率 ≥ 85%

---

### M3-T9: 分析收纳盒组件 + 拖拽排序 + 语音输入混合框 + 代词提示（10 人天）

**分支**: `feat/map-agent/m3-t9`
**改动目录**: `frontend/map-ai/src/components/`
**前置**: M3-T8 完成

#### 1. 产出文件清单

```
frontend/map-ai/src/
├── components/
│   ├── AnalysisBox.vue       # T9-1: 全局悬浮分析收纳盒
│   ├── EntityCard.vue        # T9-2: 实体卡片 (可拖拽排序)
│   ├── VoiceTextInput.vue    # T9-3: 语音+文字混合输入
│   └── PronounHint.vue       # T9-4: 代词指代提示
├── api/
│   └── analysis.ts           # T9-5: 分析提交 API
├── composables/
│   └── useSpeechRecognition.ts  # Web Speech API 封装
└── types/
    └── analysis.ts           # 扩展 AnalysisRequest, AnalysisResponse
```

#### 2. 子任务拆分

| 子任务 | 内容 | 人天 | 关键点 |
|--------|------|------|--------|
| T9-1 | AnalysisBox.vue | 4 | 全局浮窗 (position: fixed); 拖拽移动 (vue3-draggable 或原生 mousedown/mousemove); 最小化/展开切换; 内嵌 EntityCard 列表; 空状态提示 |
| T9-2 | EntityCard.vue | 2 | vuedraggable (Vue3 兼容版) 拖拽排序; 卡片显示 entity name/type/properties; 删除按钮; 点击高亮对应地图 Marker |
| T9-3 | VoiceTextInput.vue | 2 | Web Speech API (webkitSpeechRecognition); 降级: 不支持时显示纯文本输入; 语音转文字追加到输入框 (不是替换); 录音中视觉反馈 |
| T9-4 | PronounHint.vue | 1 | 检测输入中的代词 (它/它们/这个); 显示 "已选中: {entity_name}" 提示; 点击提示可切换指代实体 |
| T9-5 | api/analysis.ts | 1 | `POST /api/analysis/correlate` 请求; request: { session_id, entity_ids, query, voice_text }; 响应加载状态管理 |

#### 3. 依赖管理

```json
// frontend/map-ai/package.json 新增
"vuedraggable": "^4.1.0"
```

Web Speech API 是浏览器原生 API，无需额外依赖。

#### 4. 交接给 WorkBuddy (T10) 的 API 契约

```typescript
// api/analysis.ts — T10 后端需实现的 API 契约

interface AnalysisRequest {
  session_id: string
  entity_ids: string[]          // 收纳盒中的实体 ID
  query: string                 // 用户输入的分析指令
  voice_text?: string           // 语音转文字内容（可选）
}

interface AnalysisResponse {
  session_id: string
  correlation_results: Array<{
    entity_a: string
    entity_b: string
    coefficient: number
    strength: string
    interpretation: string
  }>
  ai_interpretation: string     // LLM 生成的自然语言解读
  execution_time_ms: number
}

// POST /api/analysis/correlate → AnalysisResponse
```

**交接要求**: T9 PR 描述中必须包含此 API 契约，供 WorkBuddy 在 T10 后端实现时对齐。

#### 5. 验收标准

- [ ] `npm run type-check` 0 errors
- [ ] `npm run build` 成功
- [ ] 收纳盒可拖拽移动、最小化、展开
- [ ] 实体卡片可拖拽排序、删除
- [ ] 语音输入在不支持的浏览器中自动降级为纯文本
- [ ] 代词提示正确显示已选实体
- [ ] 提交分析请求时显示 loading 状态

---

### M3-T4: Dashboard + 下钻分析 + 关联分析（10 人天）

**分支**: `feat/analysis-agent/m3-t4`
**改动目录**: `agents/analysis_agent/**`
**前置**: M3-T3 完成 (WorkBuddy 负责)

#### 1. 产出文件清单

```
agents/analysis_agent/
├── dashboard_models.py        # T4-1: DashboardConfig, Widget, Filter
├── drill_down.py              # T4-2: DrillDownEngine (层级递进 + 筛选传递)
├── correlation.py             # T4-3: 跨表关联发现 + 统计关联
├── aggregation.py             # T4-4: GroupBy + Pivot + TimeSeries
└── tests/
    ├── test_dashboard.py      # Dashboard 模型 + 布局测试
    ├── test_drill_down.py     # 下钻引擎测试
    ├── test_correlation.py    # 关联分析测试
    └── test_aggregation.py    # 聚合服务测试
```

#### 2. 子任务拆分

| 子任务 | 内容 | 人天 | 关键点 |
|--------|------|------|--------|
| T4-1 | dashboard_models.py | 2 | DashboardConfig(id, name, widgets, filters, layout); Widget(type: chart/table/metric, data_source, position, config); Filter(field, operator, value) |
| T4-2 | drill_down.py | 3 | DrillDownEngine: `async def drill(query, level, filters) -> DrillResult`; 层级: region→province→city→district; 筛选传递: 上级 filter 自动应用到下级; 聚合: 每层返回 GroupBy 结果 |
| T4-3 | correlation.py | 2 | CorrelationEngine: `async def find_correlations(table_a, table_b, method) -> list[Correlation]`; 跨表: 通过外键 JOIN 发现; 统计: Pearson/Spearman 相关系数; 阈值: r > 0.6 报告 |
| T4-4 | aggregation.py | 2 | AggregationService: `async def aggregate(query, group_by, agg_func) -> AggResult`; GroupBy: 单字段/多字段; Pivot: 行列转换; TimeSeries: 按时间粒度聚合 (hour/day/week/month) |
| T4-5 | 测试 | 1 | Mock 数据库查询; 验证下钻层级正确; 验证关联发现逻辑; 验证聚合结果格式 |

#### 3. 与 T3 (WorkBuddy) 的接口对齐

**交接内容**: WorkBuddy 在 T3 完成后，需在 T3 PR 描述中提供:
- `analysis_agent/models.py` 的完整 Pydantic 模型定义
- `nl2sql.py` 的 `NL2SQLEngine` 类签名
- `executor.py` 的 `QueryExecutor` 类签名
- `sql_safety.py` 的校验接口

Trae 在 T4 中复用 T3 的 executor 执行聚合/下钻查询，不重复实现 SQL 执行逻辑。

#### 4. 额外工具注册

```python
# 追加到 analysis_agent/integration.py (由 WorkBuddy 在 T3 创建，Trae 在 T4 扩展)

# 工具: dashboard_query
ToolDefinition(
    name="dashboard_query",
    description="查询 Dashboard 数据 (下钻/关联/聚合)",
    worker="analysis",
    handler=_dashboard_query_handler,
    parameters={
        "dashboard_id": {"type": "string", "required": True},
        "widget_id": {"type": "string", "required": False},
        "drill_level": {"type": "string", "required": False},
        "filters": {"type": "array", "required": False, "default": []},
    },
    category="dashboard",
)
```

#### 5. 验收标准

- [ ] `make verify` 通过
- [ ] 下钻引擎支持 4 级层级 (region→province→city→district)
- [ ] 关联分析可发现 r > 0.6 的强相关
- [ ] 聚合支持 GroupBy + Pivot + TimeSeries
- [ ] Mock 模式下全部可运行（不需要真实 DB）
- [ ] 覆盖率 ≥ 85%

---

### M3-T11: 异步任务 Celery + WebSocket 推送 + 防呆设计（7 人天）

**分支**: `feat/map-agent/m3-t11`
**改动目录**: `agents/map_agent/tasks.py` `agents/map_agent/websocket.py` `frontend/map-ai/src/stores/`
**前置**: M3-T10 完成 (WorkBuddy)

#### 1. 产出文件清单

```
agents/map_agent/
├── tasks.py                  # T11-1: Celery 异步任务
├── websocket.py              # T11-2: WebSocket 推送通道
├── foolproof.py              # T11-4: 防呆校验中间件
└── tests/
    ├── test_tasks.py         # 异步任务测试 (Celery eager mode)
    └── test_websocket.py     # WebSocket 测试

frontend/map-ai/src/
├── stores/
│   └── analysis.ts           # T11-3: 扩展，新增 WebSocket 接收逻辑
└── composables/
    └── useWebSocket.ts       # WebSocket 连接管理
```

#### 2. 子任务拆分

| 子任务 | 内容 | 人天 | 关键点 |
|--------|------|------|--------|
| T11-1 | tasks.py | 2 | Celery app (broker=Redis); @celery_app.task `run_analysis_task(session_id, entity_ids, query)`; 内部调用 T10 的 LangGraph 节点; 完成后通过 WebSocket 推送结果 |
| T11-2 | websocket.py | 2 | FastAPI WebSocket `/ws/analysis/{session_id}`; ConnectionManager 管理活跃连接; broadcast_to_session(session_id, message); 消息格式: `{type, data, timestamp}` |
| T11-3 | stores/analysis.ts 扩展 | 1 | useWebSocket composable; ws.onmessage → 更新 store.analysisResult; 连接/断开/重连状态管理; 心跳检测 |
| T11-4 | foolproof.py | 2 | 校验: 空实体列表拦截; 语音转文字失败降级提示; 权限校验 (用户是否有权分析该区域); 返回 `{ok, error_code, message}` |

#### 3. 降级策略

```python
# tasks.py — Celery 降级方案
# 如果 Celery + Redis 部署不可用，降级为 FastAPI BackgroundTasks

# 方式 1: Celery (生产)
from celery import Celery
celery_app = Celery("fde_map", broker=redis_url)

@celery_app.task
async def run_analysis_task(session_id, entity_ids, query):
    ...

# 方式 2: FastAPI BackgroundTasks (开发/降级)
from fastapi import BackgroundTasks

async def run_analysis_background(
    background_tasks: BackgroundTasks,
    session_id: str,
    entity_ids: list[str],
    query: str,
):
    background_tasks.add_task(_run_analysis, session_id, entity_ids, query)
```

#### 4. WebSocket 消息协议

```typescript
// 前端接收的消息格式
interface WSMessage {
  type: 'analysis_start' | 'analysis_progress' | 'analysis_complete' | 'analysis_error'
  data: {
    session_id: string
    progress?: number        // 0-100, 仅 progress 类型
    result?: AnalysisResponse  // 仅 complete 类型
    error?: string           // 仅 error 类型
  }
  timestamp: string  // ISO datetime
}
```

#### 5. 验收标准

- [ ] `make verify` 通过
- [ ] Celery eager mode (CELERY_ALWAYS_EAGER=True) 下异步任务可测试
- [ ] WebSocket 连接可建立，消息可推送
- [ ] 防呆: 空实体列表返回明确错误，不执行分析
- [ ] 前端 WebSocket 断线可自动重连
- [ ] 覆盖率 ≥ 80%

---

### M3-T12: 热力图 + 散点矩阵 + 时间序列 + 地图联动 + 结果看板（11 人天）

**分支**: `feat/map-agent/m3-t12`
**改动目录**: `frontend/map-ai/src/components/` `frontend/map-ai/src/views/`
**前置**: M3-T11 完成

#### 1. 产出文件清单

```
frontend/map-ai/src/
├── components/
│   ├── HeatmapChart.vue      # T12-1: ECharts 热力图
│   ├── ScatterMatrix.vue     # T12-2: ECharts 散点矩阵
│   ├── TimeSeriesChart.vue   # T12-3: ECharts 时间序列
│   └── MapHighlight.vue      # T12-4: Mapbox flyTo + 高亮联动
├── views/
│   └── AnalysisResult.vue    # T12-5: 分析结果看板整合
└── composables/
    └── useECharts.ts         # ECharts 实例管理 + resize 监听
```

#### 2. 子任务拆分

| 子任务 | 内容 | 人天 | 关键点 |
|--------|------|------|--------|
| T12-1 | HeatmapChart.vue | 3 | ECharts heatmap series; 数据: entity × property 矩阵; 颜色映射: value → color scale (绿→黄→红); tooltip 显示具体值 |
| T12-2 | ScatterMatrix.vue | 2 | ECharts scatter series; X/Y 轴: 两个 property; 散点大小: 第三个 property; 点击散点 → 触发 MapHighlight |
| T12-3 | TimeSeriesChart.vue | 2 | ECharts line series; 时间轴: X 轴; 多实体多属性: 多条线; 缩放: dataZoom 组件; 标记: markPoint/markLine |
| T12-4 | MapHighlight.vue | 2 | Mapbox GL flyTo({center, zoom}); 高亮图层: 添加/移除 highlight fill; 点击图表元素 → 地图飞到对应实体; 双向联动: 点击地图 → 图表高亮 |
| T12-5 | AnalysisResult.vue | 2 | 整合 4 个图表组件 + AI 解读文本; 响应式布局 (grid); 导出: 截图 (html2canvas) + 分享链接; 空状态处理 |

#### 3. ECharts 封装

```typescript
// composables/useECharts.ts
import { ref, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'

export function useECharts(domRef: Ref<HTMLElement | null>) {
  const chart = ref<echarts.ECharts | null>(null)

  onMounted(() => {
    if (domRef.value) {
      chart.value = echarts.init(domRef.value)
      window.addEventListener('resize', handleResize)
    }
  })

  onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
    chart.value?.dispose()
  })

  function handleResize() {
    chart.value?.resize()
  }

  function setOption(option: echarts.EChartsOption) {
    chart.value?.setOption(option, { notMerge: true })
  }

  return { chart, setOption }
}
```

#### 4. 依赖管理

```json
// frontend/map-ai/package.json 确认已有
"echarts": "^5.5.0",
"mapbox-gl": "^3.0.0"

// 可能需要新增
"html2canvas": "^1.4.0"  // T12-5 截图导出
```

#### 5. 验收标准

- [ ] `npm run type-check` 0 errors
- [ ] `npm run build` 成功
- [ ] 热力图正确渲染 entity × property 矩阵
- [ ] 散点矩阵点击可触发地图 flyTo
- [ ] 时间序列图支持 dataZoom 缩放
- [ ] 地图与图表双向联动 (点图表→地图飞，点地图→图表高亮)
- [ ] 看板可截图导出
- [ ] 无内存泄漏 (组件卸载时 dispose ECharts + 移除 resize 监听)

---

## 三、跨任务一致性约定

### 1. 后端 Python 模块

所有新增 Python 文件遵守:
- `from __future__ import annotations` 首行
- Pydantic 模型放 `models.py`（或 `*_models.py`）
- 工具注册参照 `agents/rag_agent/integration.py` 的 `register_*_tools(registry)` 模式
- 异步 handler 用 `async def`，禁止 `time.sleep()`
- 日志: `logger = logging.getLogger("fde.{module}")`
- 异常捕获: 具体异常类型，禁止裸 `except Exception`（参照 P1 修复）

### 2. 前端 Vue 组件

所有新增 Vue 文件遵守:
- `<script setup lang="ts">` 组合式 API
- Props 用 `defineProps<T>()` 类型化
- Emit 用 `defineEmits<T>()` 类型化
- Store 通过 `useXxxStore()` 获取
- API 调用集中在 `api/` 目录
- 组件卸载时清理: `onUnmounted(() => { ... })`

### 3. 测试命名

```
tests/test_{module}.py         # 后端
test_{component}.spec.ts       # 前端 (如配置了 Vitest)
```

### 4. PR 描述模板

```markdown
## 关联 Issue
Closes #XX

## 改动摘要
[1-3 句话]

## 新增工具
| 工具名 | 参数 | 功能 |
|--------|------|------|
| ... | ... | ... |

## 影响范围
- [列出可能受影响的模块/文件]

## 测试方式
`make test agents/data_agent/`
`npm run type-check`

## 交接信息（如有）
[跨 Agent 交接时填写 API 契约/接口签名]
```

---

## 四、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| T1 爬虫依赖 (httpx/selectolax) 与 ARM 兼容性 | 低 | T1 编译失败 | 提前 `pip install` 验证; selectolax 有 ARM wheel |
| T9 Web Speech API 浏览器兼容性 | 中 | 语音输入不可用 | 已设计降级方案: 不支持时纯文本输入 |
| T4 接收 T3 接口时发现不兼容 | 中 | T4 返工 | T3 PR 描述必须包含接口签名; T4 开始前先 review T3 代码 |
| T11 Celery + Redis 部署复杂度 | 低 | 异步任务不可用 | 已设计降级方案: FastAPI BackgroundTasks |
| T12 ECharts + Mapbox 联动内存泄漏 | 中 | 前端卡顿 | useECharts composable 统一管理 dispose + resize |
| Trae 负载过重 (71d, 7 个任务) | 高 | T11/T12 延期 | 严格按 Sprint 执行; Qoder 在 T7 完成后可分担 T12 前端组件 |

---

## 五、Sprint 执行检查点

每个 Sprint 结束时在对应 Issue 评论中更新:

```markdown
## Sprint X 检查点 (Day XX)

### 已完成
- [x] M3-TX: [简要]

### 进行中
- [ ] M3-TY: [进度百分比]

### 阻塞项
- [如有]

### 下一 Sprint 计划
- [任务列表]
```
