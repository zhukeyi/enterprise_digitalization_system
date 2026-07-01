# FDE AI Platform — Code Review Report
**日期**: 2026-06-30
**范围**: M1-T6 LangGraph Orchestrator + M1-T4 RAG Integration + M3-T8 MapAI Frontend
**代码量**: ~5,800 行 (43 files)

---

## 总览

| 维度 | 评分 | 说明 |
|------|------|------|
| 架构设计 | ★★★★☆ | Supervisor-Worker 分离清晰，ToolRegistry 解耦良好 |
| 类型安全 | ★★★☆☆ | Mypy 已清零，但有 3 处 type: ignore 掩盖了真实问题 |
| 错误处理 | ★★★☆☆ | 有基础 try/catch，但缺少特定异常类型和恢复策略 |
| 测试覆盖 | ★★★★☆ | 277 测试全绿，但缺少 E2E 和并发场景测试 |
| 前端质量 | ★★☆☆☆ | 骨架可用，但缺少错误边界、资源清理和类型定义 |

---

## P0 — 必须修复（运行时 Bug）

### 1. ⚠️ Async Handler 被 Sync 调用 — `ToolRegistry.dispatch()`

**文件**: `agents/orchestrator/tools/registry.py:118`
**问题**: `_rag_search_handler` 是 `async def`，但 `dispatch()` 同步调用 `tool.handler(**kwargs)`，返回的是一个 **coroutine 对象**，不是实际结果。

```python
# registry.py:118 — 当前代码
result = tool.handler(**kwargs)  # 如果 handler 是 async，返回 coroutine！

# rag_agent/integration.py:38 — handler 是 async
async def _rag_search_handler(query: str, top_k: int = 5) -> dict[str, Any]:
    ...
```

**影响**: 当 RAGWorker 通过 `tool_registry.dispatch("rag_search", query=query)` 调用时，得到的是 `<coroutine object>` 而非搜索结果。Worker 的 `str(result)[:500]` 会输出 coroutine 的 repr 字符串。

**修复方案**:
```python
import asyncio
import inspect

def dispatch(self, tool_name: str, **kwargs: Any) -> Any:
    tool = self._tools.get(tool_name)
    if tool is None:
        raise KeyError(f"Tool '{tool_name}' not found")
    
    result = tool.handler(**kwargs)
    # 如果 handler 是 async，同步等待结果
    if inspect.iscoroutine(result):
        result = asyncio.run(result)
    return result
```

### 2. ⚠️ RAGWorker.execute 中 msg.content 类型不安全

**文件**: `agents/orchestrator/langgraph/workers.py:150`
**问题**: `query = msg.content` 直接赋值，但 LangChain 的 `BaseMessage.content` 类型是 `str | list[str | dict]`。Supervisor 已修复此问题（`supervisor.py:251`），但 Worker 中遗漏。

```python
# workers.py:150 — 当前代码
query = msg.content  # 可能是 list，传给 search 会报错

# supervisor.py:251 — 已修复的版本
last_user_msg = str(msg.content) if not isinstance(msg.content, str) else msg.content
```

**修复**: 统一使用 `str(msg.content)` 或提取辅助函数。

### 3. ⚠️ `_rag_ingest_handler` 中 `doc_info["path"]` 会 KeyError

**文件**: `agents/rag_agent/integration.py:99`
**问题**: 使用 `doc_info["path"]` 直接索引，如果 `path` 键不存在会抛出 `KeyError`，虽然外层有 try/catch，但错误信息不友好。

```python
# 当前
parsed = parser.parse(doc_info["path"])

# 应改为
path = doc_info.get("path")
if not path:
    raise ValueError(f"Document info missing 'path' key: {doc_info}")
```

---

## P1 — 应修复（设计缺陷）

### 4. Bare `Exception` 捕获范围过大

**文件**: `supervisor.py:183`, `workers.py:89`, `integration.py:66`, `integration.py:114`

四处 `except Exception as e` 捕获了所有异常，包括 `KeyboardInterrupt` 和 `SystemExit`。

```python
# supervisor.py:183
except Exception as e:
    logger.warning("LLM call failed: %s, falling back to mock", e)
```

**建议**: 改为 `except (json.JSONDecodeError, ValueError, RuntimeError, ConnectionError) as e`，或至少 `except Exception as e`（Python 3 不会捕获 `KeyboardInterrupt`/`SystemExit` 因为它们继承自 `BaseException`，但仍应缩小范围以避免吞掉意外错误）。

### 5. `_parse_llm_response` 代码重复

**文件**: `supervisor.py:194-226`

JSON 解析逻辑完全重复了两遍（direct parse + markdown extraction），应提取为辅助方法：

```python
def _parse_plan_json(self, data: dict) -> SupervisorPlan:
    """Parse dict into SupervisorPlan."""
    return SupervisorPlan(
        steps=[PlanStep(**s) for s in data.get("steps", [])],
        reasoning=data.get("reasoning", ""),
        requires_rag=data.get("requires_rag", False),
        complexity=data.get("complexity", "simple"),
        finish=data.get("finish", False),
    )
```

### 6. Mapbox Token 硬编码占位符 + Logo 隐藏

**文件**: `frontend/map-ai/src/components/MapView.vue:6`, `style.css:217`

```typescript
// MapView.vue:6 — placeholder token 无法加载地图
mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN || 'pk.placeholder'
```

```css
/* style.css:217 — 隐藏 Mapbox logo 违反免费版 ToS */
.mapboxgl-ctrl-logo { display: none !important; }
```

**影响**:
- 无 token 时地图完全无法渲染，但没有错误提示
- 隐藏 logo 违反 Mapbox 免费版服务条款

**修复**:
```typescript
const token = import.meta.env.VITE_MAPBOX_TOKEN
if (!token || token === 'pk.placeholder') {
  console.error('VITE_MAPBOX_TOKEN not set. Map will not load.')
  return
}
mapboxgl.accessToken = token
```

### 7. TiptapEditor 未在卸载时销毁编辑器

**文件**: `frontend/map-ai/src/components/TiptapEditor.vue`

```typescript
// 缺少 onUnmounted 生命周期
import { onUnmounted } from 'vue'

onUnmounted(() => {
  editor?.destroy()
})
```

**影响**: 组件卸载后 Tiptap 内部事件监听器不会清除，导致内存泄漏。

### 8. Chat Store 的 setTimeout 未清理

**文件**: `frontend/map-ai/src/stores/chat.ts:26-41`

```typescript
simulateAgentResponse() {
  this.loading = true
  setTimeout(() => {  // 如果组件在 800ms 内卸载，回调仍会执行
    ...
    this.loading = false
  }, 800)
}
```

**修复**: 返回 timeout ID，在组件卸载时 clear，或改用 ref + watch 模式。

### 9. `_rag_ingest_handler` 每次调用创建新连接

**文件**: `agents/rag_agent/integration.py:85-86`

```python
# 每次调用都创建新的 VectorStore 和 Qdrant 连接
qdrant_config = QdrantConfig()
vector_store = VectorStore(qdrant_config)
```

**建议**: 将 VectorStore 作为模块级单例或通过依赖注入传入。

---

## P2 — 建议改进

### 10. Mock 路由无多意图检测

**文件**: `supervisor.py:257-333`

查询 "搜索员工绩效数据" 同时匹配 RAG 和 HR 关键词，但 RAG 先匹配就返回了，不会路由到 HR。

**建议**:
- 增加 confidence score
- 支持 multi-step plan（已有 PlanStep list，但 mock 只生成单步）
- 考虑使用 LLM 做意图分类

### 11. `worker_outputs` 同名 Worker 结果被覆盖

**文件**: `workers.py:84`

```python
return {
    "worker_outputs": {self.name: result},  # 同一 worker 二次执行会覆盖
}
```

如果 RAG Worker 被调用两次，第二次结果覆盖第一次。考虑改为 `list` 或追加模式。

### 12. MessageType 应改为 StrEnum

**文件**: `agents/orchestrator/messages/bus.py:28-36`

```python
# 当前：普通类 + 字符串常量
class MessageType:
    USER_INPUT = "user_input"

# 建议：StrEnum（Python 3.11+）
class MessageType(StrEnum):
    USER_INPUT = "user_input"
```

### 13. 前端 API 层无类型定义和错误处理

**文件**: `frontend/map-ai/src/api/index.ts`

```typescript
// 返回 any，无类型安全
export async function chatCompletion(messages: { role: string; content: string }[]) {
  return api.post('/v1/chat/completions', { messages })
}

// 应定义响应类型 + try/catch
interface ChatResponse {
  choices: { message: { content: string } }[]
}

export async function chatCompletion(messages: ChatMessage[]): Promise<ChatResponse> {
  try {
    const res = await api.post<ChatResponse>('/v1/chat/completions', { messages })
    return res.data
  } catch (error) {
    console.error('Chat API failed:', error)
    throw new Error('AI 服务暂时不可用')
  }
}
```

### 14. 缺少 `.env.example` 文件

**文件**: `frontend/map-ai/` 缺少

前端使用了 `VITE_MAPBOX_TOKEN` 和 `VITE_API_URL` 两个环境变量，但没有 `.env.example` 文件指导开发者。

### 15. `route_from_supervisor` 闭包捕获 workers

**文件**: `graph.py:92-108`

`route_from_supervisor` 定义在 `build_orchestrator_graph` 内部，捕获了 `workers` 变量。虽然功能正确，但难以独立测试。

---

## P3 — 优化建议

| # | 位置 | 建议 |
|---|------|------|
| 16 | supervisor.py:192,208 | `import json` / `import re` 应移到模块顶部 |
| 17 | 多处 | `[:200]` `[:500]` `[:100]` 等魔法数字应定义为常量 |
| 18 | bus.py:108 | `uuid.uuid4()[:8]` 只取 8 字符有碰撞风险 |
| 19 | TiptapEditor.vue:28-34 | 内联 style 应改为 CSS class |
| 20 | registry.py | 缺少线程安全保护（当前单线程可接受） |
| 21 | supervisor.py | mock 关键词列表硬编码，应可配置 |
| 22 | test_graph.py | 缺少多 Worker 串联执行（RAG→Analysis）的 E2E 测试 |

---

## 架构亮点（做得好的部分）

1. **Supervisor-Worker 分离** — LLM 只规划不执行，Worker 确定性执行工具，职责清晰
2. **ToolRegistry 解耦** — Worker 不直接调用 RAG 引擎，通过 Registry 间接分发，可测试性好
3. **State 设计** — Pydantic BaseModel + `add_messages` reducer，类型安全且支持消息累积
4. **防呆机制预留** — `is_dangerous` 标记 + `FOOLPROOF_ALERT` 消息类型已预埋
5. **Mock/LLM 双模式** — Supervisor 支持无 LLM 的 mock 模式，开发测试零成本
6. **LangGraph 图结构** — 条件边 + 迭代计数器 + max_iterations 安全阀，防止死循环

---

## 修复优先级建议

```
立即修复（阻塞生产）:
  P0-1: ToolRegistry.dispatch async 支持
  P0-2: RAGWorker msg.content 类型安全
  P0-3: _rag_ingest_handler KeyError 防护

本周修复（影响质量）:
  P1-6: Mapbox token 校验 + 错误提示
  P1-7: TiptapEditor destroy
  P1-8: Chat setTimeout 清理
  P1-4: Exception 范围缩小

下个迭代（代码质量）:
  P2-10: 多意图路由
  P2-11: worker_outputs 累积
  P2-13: 前端 API 类型定义
  P2-14: .env.example
```

---

**Review by**: Code Review Agent
**Files reviewed**: 18 source files + 8 test files + 8 frontend files
**Total lines reviewed**: ~5,800
