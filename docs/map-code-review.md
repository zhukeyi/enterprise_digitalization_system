# Map 板块 Code Review 报告

> 2026-07-09 | Reviewer: WorkBuddy | 65 tests passed | ruff 12 errors | mypy 8 errors

---

## 一、审查范围

| 层 | 文件数 | 总行数 | 覆盖 |
|----|--------|--------|------|
| 后端 agents/map_agent/ | 14 源 + 3 测试 | 4044 | models/routes/engine/interpreter/langgraph_nodes/location_enrich/marker_store/tag_extractor/tasks/websocket/foolproof/worker/demo_data |
| 前端 frontend/map-ai/src/ | 20 组件 + 3 store + 1 composable | 4067 | MapView/AnalysisBox/ResourcePanel/analysis store/markers store/useMap |
| **合计** | **41 文件** | **~8111 行** | |

---

## 二、问题汇总

### P0 — 安全/功能缺陷（必须修复）

| # | 文件 | 行号 | 问题 | 修复建议 |
|---|------|------|------|----------|
| P0-1 | location_enrich.py | 25 | **百度 AK 硬编码在源码中**：`BAIDU_AK = os.getenv("BAIDU_SERVER_AK", "HQmJZ8vYRU8pkaP8zxXRtxNplyOXNjFW")` — AK 泄露在 Git 仓库中 | 移除默认值，改为仅从环境变量读取；AK 写入服务器 `.env` 文件并加入 `.gitignore` |
| P0-2 | MapView.vue | 151, 147 | **XSS 注入风险**：marker click 事件中用 `innerHTML` 拼接 `name`/`note` 到 InfoWindow，恶意 note 可执行 JS（`<img onerror=alert(1)>`）| 对 name/note 做 HTML escape 后再拼接；或使用 DOM API 创建元素 |
| P0-3 | marker_store.py | 46-62 | **缓存与并发竞态**：`_load()` 缓存整个列表，多请求并发写时 `_save` 的 `self._cache = markers` 和 `os.replace` 之间无锁保护，可能丢数据 | 加 `threading.Lock` 保护 `_load/_save`；或 FastAPI 中将写操作改为 `async def` + `asyncio.Lock` |

### P1 — 代码质量/正确性（建议修复）

| # | 文件 | 行号 | 问题 | 修复建议 |
|---|------|------|------|----------|
| P1-1 | langgraph_nodes.py | 175 | `zip(indices, profiles)` 缺 `strict=True`（ruff B905）| 加 `strict=True` |
| P1-2 | langgraph_nodes.py | 16 | `import asyncio` 未使用（ruff F401）| 删除 |
| P1-3 | langgraph_nodes.py | 331 | 循环变量 `name` 未使用（ruff B007）| 改为 `_name` |
| P1-4 | location_enrich.py | 1-8 | docstring 含全角标点（ruff RUF002 ×8）| 全角标点→ASCII |
| P1-5 | location_enrich.py | 236 | 文件末尾无换行（ruff W292）| 加尾部换行 |
| P1-6 | routes.py | 131,234,266,328,352 | `dict` 返回类型缺泛型参数 `dict[str, Any]`（mypy type-arg ×5）| 加 `dict[str, Any]` |
| P1-7 | tag_extractor.py | 71 | `type: ignore[import-untyped]` 已不需要（mypy unused-ignore）| 删除该 type:ignore |
| P1-8 | engine.py | 134-151 | **统计引擎是假实现**：`_compute_coefficient` 用 `ratio similarity` 模拟"相关系数"，`max_val=0` 分支在 `a==0 and b==0` 已返回后仍存在（mypy unreachable）| 接入 scipy.stats.pearsonr；移除死代码 |
| P1-9 | engine.py | 113-114 | entity 找不到时默认值 `0` 静默通过，应报错或跳过 | 返回 `None` 或 raise，不应默认 0 |
| P1-10 | routes.py | 42-43 | **全局 dict 存 session 无限增长**：`_sessions: dict[str, AnalysisContext] = {}` 永不清理 | 加 TTL 清理或限制最大 session 数 |
| P1-11 | tasks.py | 197-201 | **异步分析未传 provided_entities**：`run_pipeline` 调用缺 `provided_entities` 参数，异步分析走 demo_data 查不到前端标注的 marker | 传 `request.entities` |
| P1-12 | location_enrich.py | 177-183 | **POI 请求"并行创建但串行执行"**：`poi_tasks` 用 dict comprehension 创建 coroutine，但 for 循环中逐个 `await`，实际串行 | 用 `asyncio.gather` 并行执行 |

### P2 — 架构/设计改进

| # | 文件 | 问题 | 修复建议 |
|---|------|------|----------|
| P2-1 | frontend | **5 个组件未被引用**：HelloWorld、AnalysisResult、MapHighlight、MapMarkerPlus、DrillDownPlus、SidebarPlus — 死代码增加维护负担 | 删除或标记为待使用 |
| P2-2 | AnalysisBox.vue | **结果面板内联在 AnalysisBox**（172-226行），AnalysisResult.vue 组件存在但未被使用 | 统一使用 AnalysisResult.vue 组件，移除内联代码 |
| P2-3 | MapView.vue | **双重 marker 渲染**：`markers[]`（来自 analysis store watch）和 `persistedMarkers[]`（来自 markersStore watch）可能重叠渲染同一点位 | 统一用一个数据源；或 watch 去重 |
| P2-4 | MapView.vue | `defineExpose({ map, flyTo })` 中 `map` 在 expose 时为 `null`（onMounted 后才赋值），外部拿到的可能是 null 引用 | 用 `ref` 暴露或 getter 函数 |
| P2-5 | AnalysisBox.vue | 大量 `as any` 类型断言（183, 184, 213, 215, 216行），分析结果应定义 TS interface | 新增 `AnalysisResultData` interface |
| P2-6 | marker_store.py | **单例路径不可配置**：`get_marker_store()` 使用固定 `~/.fde_markers.json`，无法区分多租户/多项目 | 支持 env var 配置路径，或按 project_id 分文件 |
| P2-7 | foolproof.py | `validate_voice_input` 已定义但无调用方（语音功能暂停）| 暂保留但标注 `# pragma: no cover` |
| P2-8 | worker.py | `MapWorker` 类只有 `name` 和 `description`，无 `execute()` 方法——继承 BaseWorker 但未实现核心逻辑 | 检查 BaseWorker 是否提供默认 execute；如需工具路由则补实现 |
| P2-9 | routes.py | `/map/analysis` 在函数体内 `from ... import run_pipeline`（延迟导入），但 `run_analysis_background` 在 tasks.py 也做了同样导入 | 统一在模块级导入或提取公共函数 |

---

## 三、亮点

1. **管线设计清晰**：4 节点流水线（fetch → enrich → correlate → interpret），每节点纯函数输入输出，可独立测试。
2. **标签提取策略合理**：关键词快速匹配 + jieba 兜底，jieba 缺失时降级到字符频率，优雅降级。
3. **原子写入**：marker_store 用 `tempfile + os.replace` 保证写操作原子性。
4. **测试覆盖好**：22 个 marker 测试覆盖 CRUD、搜索、标签、持久化跨实例。
5. **WebSocket 消息协议完善**：progress/result/error/keepalive 四类消息，支持多客户端同 session。
6. **地图供应商抽象层**：`useMap.ts` 封装百度/高德双后端切换，API 统一。

---

## 四、修复优先级建议

```
立即修复 (P0):
  1. 百度 AK 移出源码 → 环境变量
  2. InfoWindow XSS → HTML escape
  3. marker_store 并发锁

本轮修复 (P1):
  4. ruff 12 errors 全部修复（10分钟自动修复）
  5. mypy type-arg 补全
  6. 异步分析传 provided_entities
  7. POI 请求真正并行化
  8. engine.py 移除 unreachable 死代码

后续迭代 (P2):
  9. 删除 5 个死组件
  10. AnalysisResult 组件统一使用
  11. marker 双重渲染去重
  12. TS 类型完善
```

---

## 五、测试状态

```
后端: 65 passed, 0 failed (agents/map_agent/)
ruff: 12 errors (F401×1, B905×1, B007×1, RUF002×8, W292×1)
mypy: 8 errors (type-arg×5, unused-ignore×1, unreachable×1, arg-type×1)
前端: npm run build ✅ (vue-tsc + vite)
```
