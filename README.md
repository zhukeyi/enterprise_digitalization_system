# FDE AI Platform

企业级AI数字化平台 — 可复用、可私有化部署的完整AI能力矩阵。

## 项目结构

```
fde-ai-platform/
├── agents/                    # 各子Agent工作目录
│   ├── orchestrator/          # 主协调Agent（任务拆解与调度）
│   ├── router-agent/          # 智能路由网关
│   ├── rag-agent/             # RAG引擎
│   ├── im-agent/              # 统一消息枢纽
│   ├── client-agent/          # 桌面客户端
│   ├── data-agent/            # 数据情报服务
│   ├── analysis-agent/        # 智能分析层
│   └── governance-agent/      # 全栈治理与可观测性
├── shared/                    # 共享代码
│   ├── models/                # 公共数据模型（PII脱敏结构、权限Schema）
│   ├── sdk/                   # 统一埋点适配层
│   ├── prompts/               # 共享提示词模板
│   └── utils/                 # 通用工具函数
├── deploy/                    # 部署相关
│   ├── helm/                  # Helm Charts
│   ├── scripts/               # 一键部署脚本
│   └── config-templates/      # 按规模的配置模板
├── tests/                     # 测试
│   ├── integration/           # 跨模块集成测试
│   ├── golden-datasets/       # 评测基准数据集
│   └── promptfoo/             # Promptfoo评测配置
└── docs/                      # 文档
    ├── api/                   # OpenAPI规范
    ├── deployment/            # 部署手册
    └── operations/            # 运维手册
```

## 技术栈

| 层级 | 选型 |
|:---|:---|
| 后端 | Python 3.11+ / FastAPI |
| 前端/客户端 | TypeScript + React (Dashboard) / Tauri (桌面客户端) |
| 向量数据库 | Qdrant (本地优先) / Milvus (分布式备选) |
| 关系数据库 | PostgreSQL |
| 时序/分析库 | ClickHouse |
| 缓存/队列 | Redis |
| 容器编排 | Docker Compose (开发) / Kubernetes + Helm (生产) |
| 可观测 | Langfuse (自托管) + Prometheus/Grafana |
| 评测 | Braintrust + Promptfoo |

## 快速开始

```bash
# 安装依赖
make install

# 启动开发环境
make dev

# 运行测试
make test

# 代码检查
make lint
```

## 开发里程碑

| 里程碑 | 时间 | 目标 |
|:---|:---|:---|
| M1 地基 | 第1-2月 | 检索 + 路由能力跑通 |
| M2 触点 | 第3-4月 | IM机器人 + 桌面端雏形 |
| M3 大脑 | 第5-6月 | 分析 + 数据情报能力 |
| M4 交付 | 第7-8月 | 完整产品矩阵 + 实施工具包 |

## 开发规范

- Python: PEP8 + Black + ruff + mypy
- 提交信息: Conventional Commits (`feat(router): add failover policy`)
- 分支策略: Trunk-Based (`feature/agent-name/task-id` → `main`)
- 测试覆盖: 核心模块 ≥ 80%

## License

MIT
