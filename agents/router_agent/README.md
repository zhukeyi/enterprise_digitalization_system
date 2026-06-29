# Router Agent — 智能路由网关

## 职责
- 统一 API 网关（FastAPI，OpenAI 兼容格式）
- 多模型适配器（DeepSeek / Qwen / GLM ≥ 3家）
- 智能路由策略引擎（YAML 配置化）
- 故障自动切换（Fallback Chain，< 3s）

## API 端点
| 端点 | 方法 | 说明 |
|:---|:---|:---|
| `/v1/chat/completions` | POST | 统一对话入口（OpenAI 兼容） |
| `/v1/models` | GET | 可用模型列表 |
| `/health` | GET | 健康检查 |

## 路由策略
路由规则在 `routing_policy.yaml` 中配置：
- `simple` → 便宜模型（Qwen-7B）
- `medium` → 平衡模型（DeepSeek-V2）
- `complex` → 强模型（DeepSeek-R1 / Qwen-Max）
- `sensitive` → 本地模型（不进云端）

## 依赖
- `fde-ai-platform[router]`
- FastAPI + uvicorn + httpx
