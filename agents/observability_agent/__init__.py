"""Observability Agent — Platform-wide monitoring and diagnostics.

Provides:
- /healthz, /readyz, /livez — three-tier health probes
- /api/observability/overview — aggregated platform health score + KPIs
- /api/observability/health/components — per-component status matrix
- /api/observability/health/service-map — module dependency graph
- /api/observability/api/endpoints — auto-scanned API directory
- /api/observability/tokens/* — token usage and cost tracking
- /api/observability/rag/* — RAG chunk inspector and retrieval replay
- /api/observability/traces/* — trace span store and query
- /api/observability/audit/* — audit trail query and export
"""
