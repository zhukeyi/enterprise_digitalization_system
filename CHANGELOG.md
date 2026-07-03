# FDE AI Platform — Changelog

## v1.0.0 (2026-07-03)

### M1 — 地基 (75 人天) ✅

- M1-T1: Monorepo 骨架 + CI/CD (ruff/black/mypy/pytest + GitHub Actions)
- M1-T4: FastAPI 智能路由网关 + 4 模型适配器 + 防呆中间件
- M1-T5: Dify 平台部署 (http://217.142.246.70, 12 容器)
- M1-T6: LangGraph Supervisor-Worker 框架 (10 Workers + ToolRegistry + MessageBus)
- M1-T8~T13: RAG 完整流水线 (Qdrant + Parser + Chunking + BGE-M3 + HybridSearch + E2E)

### M2 — 触点 + 智能体 (65 人天) ✅

- M2-T1: 统一身份认证 + RBAC/ABAC 权限引擎 (JWT + API Key)
- M2-T2: 权限过滤检索中间件 + 决策链日志
- M2-T3: IM 统一消息枢纽 (12 Pydantic models + 3 适配器 Stub)
- M2-T4: Desktop Client SDK (16 models + DesktopAuthManager)
- M2-T5: 子 Agent Worker (Compliance + Business System)
- M2-T6: 冲突裁决 + Response Generator (4 规则 + 4 策略)
- M2-T7: Dify Tool Node Integration
- M2-T8: E2E 集成测试 (31 tests)

### M3 — 大脑 + 数据 + 地图 (138 人天) ✅

- M3-T1: 多源数据采集 + ETL (BaseScraper + RSS + API + 清洗管道)
- M3-T2: 报告模板引擎 + 多渠道推送 (Jinja2 + matplotlib + APScheduler)
- M3-T3: NL2SQL 引擎 (规则引擎 + LLM fallback + SQL 安全校验)
- M3-T4: Dashboard + 下钻分析 + 关联分析 (Pearson/Spearman + GroupBy/Pivot)
- M3-T5: HR 智能决策引擎 (6 工具 + 防呆 5 步 + 558 tests)
- M3-T6: 扩展 Worker (Analysis + HR)
- M3-T7: 评测体系 (Golden Dataset + Ragas + Promptfoo + CLI)
- M3-T8: 地图前端标记交互 (Pinia + 5 Vue 组件)
- M3-T9: 分析收纳盒 + 语音输入 (vuedraggable + Web Speech API)
- M3-T10: 地图后端分析 API (Interpreter + LangGraph 3 节点)
- M3-T11: 异步任务 + WebSocket 推送 + 防呆
- M3-T12: 可视化输出 (5 ECharts 组件 + 地图联动)
- M3-T13: 端到端集成测试 (34 E2E tests)

### M4 — 交付与收尾 (52 人天) ✅

- M4-T1: IM 适配器真实对接 (企微/飞书/钉钉)
- M4-T2: Tauri 桌面客户端骨架 (Vue3 + Tauri 2.x config)
- M4-T3: 生产 Docker Compose 编排 (nginx + certbot + 6 服务)
- M4-T4: 可观测底座 (Prometheus + Grafana + Loki + OTel)
- M4-T5: CI/CD Helm Charts + GitHub Actions 自动部署
- M4-T6: M3 架构审计 + 全平台 E2E 验收
- M4-T7: 运维手册 + 架构文档 + 安全加固 + v1.0.0

### 质量基线

- 总测试数: ~800
- 总覆盖率: ~87%
- ruff: 0 errors
- mypy: 0 new errors
- black: clean
- vue-tsc: 0 errors

### 技术栈

- Backend: Python 3.12+ / FastAPI / LangGraph / Pydantic v2
- Frontend: Vue 3 / MapboxGL / ECharts / Vite
- AI: Qdrant / BGE-M3 / OpenAI-compatible API
- Infra: Docker / Helm / GitHub Actions / Prometheus / Grafana