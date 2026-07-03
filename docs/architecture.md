# FDE AI Platform — System Architecture

## Overview

FDE AI Platform is an enterprise AI digitalization system with 15 agent modules coordinated by a LangGraph Supervisor-Worker architecture. It supports private deployment with local AI inference.

## Architecture Diagram

```
                          ┌─────────────────────┐
                          │   Nginx (TLS)        │
                          │   certbot auto-renew  │
                          └───────┬─────────────┘
                                  │
                  ┌───────────────┴───────────────┐
                  │                               │
          ┌───────▼──────┐                ┌───────▼──────┐
          │  Frontend     │                │  Backend API │
          │  Vue3/MapboxGL│                │  FastAPI     │
          │  Port 80/443  │                │  Port 8000   │
          └───────────────┘                └───────┬──────┘
                                                  │
                          ┌───────────────────────┤
                          │                       │
                  ┌───────▼──────┐        ┌───────▼──────┐
                  │  Supervisor  │        │    Metrics    │
                  │  LangGraph    │        │  Prometheus   │
                  │  10 Workers   │        │  /metrics     │
                  └───────┬──────┘        └───────────────┘
                          │
          ┌───────┬───────┼───────┬───────┬───────┐
          │       │       │       │       │       │
    ┌─────▼──┐ ┌─▼──┐ ┌──▼──┐ ┌─▼───┐ ┌─▼───┐ ┌─▼────┐
    │RAG    │ │HR  │ │Data│ │Map  │ │IM   │ │Router│
    │Qdrant │ │    │ │    │ │     │ │     │ │      │
    │BGE-M3 │ │    │ │    │ │     │ │     │ │      │
    └───────┘ └────┘ └────┘ └─────┘ └─────┘ └──────┘
                                                            
    ┌─────┐ ┌─────┐ ┌─────────┐ ┌──────┐ ┌──────────┐
    │Auth │ │Gov  │ │Analysis │ │Biz   │ │Compliance│
    │JWT  │ │Audit│ │NL2SQL   │ │CRM   │ │Risk      │
    └─────┘ └─────┘ └─────────┘ └──────┘ └──────────┘
```

## Data Flow

```
User Request → Nginx → FastAPI → AuthMiddleware (JWT)
    → Router Agent (model selection + adapter)
    → Supervisor (LangGraph plan)
    → Worker (rag/hr/data/analysis/map/im) → ToolRegistry.dispatch
    → Conflict Resolver → Response Generator → User Response
```

## Infrastructure

```
┌──────────────────────────────────────────┐
│  Docker Compose / Helm (K8s)             │
│  ┌────────┐ ┌────────┐ ┌───────┐        │
│  │Postgres│ │ Redis  │ │Qdrant │        │
│  │   v16  │ │   v7   │ │v1.13  │        │
│  └────────┘ └────────┘ └───────┘        │
│  ┌────────┐ ┌────────┐ ┌──────────────┐ │
│  │ MinIO  │ │Promethe│ │Grafana+Loki  │ │
│  │        │ │ us     │ │              │ │
│  └────────┘ └────────┘ └──────────────┘ │
└──────────────────────────────────────────┘
```

## Module Index

| Module | Agent | Purpose | Lines |
|--------|-------|---------|-------|
| A | router_agent | Model gateway, routing, failover | ~1,800 |
| B | rag_agent | Qdrant + BM25 + BGE-M3 RAG | ~3,500 |
| C | dify_bridge | Dify tool node bridge | ~600 |
| D | im_agent | WeCom/Feishu/DingTalk adapters | ~2,800 |
| E | client_agent | Tauri desktop client SDK | ~1,400 |
| F | data_agent | Multi-source data collection | ~2,000 |
| G | analysis_agent | NL2SQL + Dashboard | ~3,000 |
| H | governance_agent | Auth + RBAC + Audit + Eval | ~2,000 |
| I | deploy/ | Docker + Helm + CI/CD | ~600 |
| J | hr_agent | Employee profiling + Risk + Layoff | ~5,000 |
| K | orchestrator | LangGraph Supervisor-Worker | ~3,500 |
| L | map_agent | Spatial analysis + Mapbox | ~4,000 |
| — | shared/ | SDK + Models + Prompts + Utils | ~1,000 |

## Key Design Decisions

1. **LLM plans, backend executes**: Supervisor generates PlanStep JSON, Workers dispatch tools deterministically
2. **Local-first**: BGE-M3 runs on ARM CPU, Qdrant locally deployed, JWT verified locally
3. **No hallucination**: RAG returns source-attributed results, `rag_answer` tool uses extractive summarization
4. **Foolproof design**: HR 5-step validation, SQL safety checker, map anti-empty-entity
5. **Hard auth filtering**: `auth_filter` runs after RAG retrieval, before LLM, no token inspection

## Security

- JWT (HS256) + API Key (SHA256) dual auth
- RBAC (roles) + ABAC (attributes) permissions
- CSP, HSTS, X-Frame-Options headers
- SQL injection prevention (statements validated before execution)
- Rate limiting (10 req/s API, 5 req/min auth)

## Testing

- 800+ tests across 15 modules
- 87% code coverage
- E2E tests covering 5 full pipelines
- ruff + black + mypy strict (zero errors)