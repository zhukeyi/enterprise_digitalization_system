# Spec Writing 示例

## 示例 1：原始需求 → 规格书

### 原始需求

> "给系统加一个任务完成后的消息通知功能。"

---

### 输出：M3-Notify: 任务完成通知系统需求规格书

#### 1. 任务摘要
- **一句话目标**：当 data/analysis/hr/map 等 Agent 任务完成时，向任务创建者发送通知
- **所属模块**：`im_agent`（发送）+ `orchestrator`（触发）+ `governance_agent`（审计日志）
- **预计复杂度**：中

#### 2. 背景与目标
- 当前各 Agent 任务执行后没有反馈机制，用户需要主动查询结果
- 目标：让任务状态变更是可感知的，提升系统响应性和用户体验
- 成功标准：任务完成通知触达率 ≥ 99%，通知延迟 < 5s，不阻塞主流程

#### 3. 用户故事
- 作为 **业务用户**，我希望分析任务完成后收到通知，以便及时查看结果
- 作为 **系统管理员**，我希望在通知失败时能看到审计日志，以便排查问题
- 作为 **开发者**，我希望通知渠道可扩展，以便后续接入企业微信/钉钉

#### 4. 验收标准
- `AC-001`: Given 用户创建了一个分析任务，When 任务成功完成，Then 用户在 5s 内收到站内信通知
- `AC-002`: Given 用户创建了一个分析任务，When 任务执行失败，Then 用户收到包含错误摘要的通知
- `AC-003`: Given 通知服务不可用，When 任务完成，Then 主任务流程不受影响，失败通知记录到审计日志
- `AC-004`: Given 用户关闭了通知功能，When 任务完成，Then 不发送通知

#### 5. 功能需求
- `FR-001`: `orchestrator` 在 Worker 节点执行完成后发布 `TaskCompletedEvent` 事件 (P0)
- `FR-002`: `im_agent` 订阅事件并调用对应适配器发送通知 (P0)
- `FR-003`: 通知内容包含：任务 ID、任务类型、状态、完成时间、结果链接 (P0)
- `FR-004`: 用户可在个人设置中开启/关闭通知 (P1)
- `FR-005`: 支持站内信和邮件两种渠道，WebHook 后续扩展 (P1)

#### 6. 非功能需求
- **性能**：通知发送不得阻塞 LangGraph 图执行，使用后台任务或事件队列
- **安全**：通知内容需脱敏，不包含敏感业务数据原始值
- **可观测性**：每次通知尝试记录到 `DecisionChainLog` 或专用审计表
- **兼容性**：与现有 `im_agent/adapters/` 架构兼容

#### 7. 数据模型设计

新增 Pydantic 模型（建议放在 `im_agent/models.py` 或 `shared/models/notification.py`）：

```python
class NotificationChannel(StrEnum):
    IN_APP = "in_app"
    EMAIL = "email"

class NotificationRequest(BaseModel):
    user_id: str
    channel: NotificationChannel
    title: str
    body: str
    action_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class NotificationPreference(BaseModel):
    user_id: str
    task_completed_in_app: bool = True
    task_completed_email: bool = False
```

#### 8. API / 接口契约

**内部事件（推荐，不暴露 HTTP API）**：

```python
class TaskCompletedEvent(BaseModel):
    task_id: str
    task_type: str  # "analysis" | "data" | "hr" | "map"
    status: str     # "success" | "failed"
    user_id: str
    completed_at: datetime
    result_summary: str
    result_url: str | None = None
```

**IM Agent 发送接口**：

```python
async def send_notification(req: NotificationRequest) -> NotificationResult:
    """..."""

class NotificationResult(BaseModel):
    success: bool
    channel: NotificationChannel
    error: str | None = None
```

#### 9. 错误处理与边界条件
- 用户不存在/已删除：静默丢弃，记录 warning
- 通知渠道配置缺失：降级为站内信；若站内信也失败，记录审计日志
- 通知服务超时：使用 `shared/utils/retry.py` 的 `retry_async`，最多 3 次，最终失败不阻塞主流程
- 通知内容过长：截断并附加 "..."

#### 10. 依赖与影响范围
- **依赖**：`im_agent/adapters/` 现有适配器、`governance_agent/decision_log.py`、LangGraph Worker 节点
- **影响文件**：
  - `agents/orchestrator/langgraph/workers.py`（任务完成时发布事件）
  - `agents/im_agent/tools.py`（新增 `send_notification` 工具）
  - `agents/governance_agent/database/models.py`（可能需要新增审计表）
- **新增依赖**：无需新增外部库（复用现有 IM 适配器和邮件 SMTP 库）

#### 11. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 通知风暴导致 IM 适配器限流 | 中 | 高 | 增加发送频率限制和批量发送能力 |
| 事件发布侵入 Worker 代码 | 中 | 中 | 通过 BaseWorker 生命周期钩子统一发布 |
| 用户关闭通知后仍收到 | 低 | 中 | 在发送前检查用户偏好配置 |

#### 12. 参考实现线索
- 类似事件机制可参考 `agents/orchestrator/messages/bus.py`
- IM 适配器模式见 `agents/im_agent/adapters/__init__.py`
- 审计日志参考 `agents/governance_agent/decision_log.py`
- 建议实现步骤：
  1. 定义 `TaskCompletedEvent` 和 `NotificationRequest` 模型
  2. 在 `BaseWorker.execute()` 完成后发布事件
  3. 在 `im_agent` 中新增事件处理器和发送工具
  4. 补单元测试和集成测试
