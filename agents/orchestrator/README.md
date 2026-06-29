# Orchestrator — 主协调Agent

## 职责
- 任务拆解与调度（M1-M4 全局协调）
- 跨Agent集成测试（端到端验证）
- 部署工具编写（Helm Charts、一键部署脚本）
- 文档维护（API/部署/运维）
- 评测体系搭建（Braintrust、Promptfoo CI、Golden Dataset）

## 目录结构
```
orchestrator/
├── __init__.py
├── main.py              # CLI入口
├── scheduler.py         # 任务调度引擎
├── deploy_utils.py      # 部署工具
├── evaluation/          # 评测模块
│   ├── __init__.py
│   ├── golden_dataset.py
│   └── promptfoo_config.py
└── tests/
    └── __init__.py
```

## 依赖
- 无外部依赖（纯协调逻辑）
- 通过 API 调用其他 Agent

## 开发规范
- 遵守 `shared/sdk/` 埋点规范
- 所有调度日志写入决策链
