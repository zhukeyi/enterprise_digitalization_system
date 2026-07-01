"""Compliance Agent — audit logs, risk checks, regulatory validation.

M2-T5: New sub-agent for the LangGraph Supervisor-Worker framework.

Provides tools for:
- audit_log_query: Query and filter audit log entries
- compliance_summary: Generate compliance status summary
- risk_check: Run risk assessment against a policy/ruleset
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from agents.orchestrator.tools.registry import ToolDefinition, ToolRegistry

logger = logging.getLogger("fde.compliance")

# ══════════════════════════════════════════════════════════════════
# Tool Handlers
# ══════════════════════════════════════════════════════════════════


def _audit_log_handler(
    action: str = "",
    user_id: str = "",
    resource: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """Query audit logs with optional filters.

    In production, this would query the `audit_logs` table. For now,
    returns mock data that validates the tool interface.
    """
    filters = {
        "action": action,
        "user_id": user_id,
        "resource": resource,
        "limit": limit,
    }

    mock_entries = [
        {
            "id": str(uuid.uuid4()),
            "action": "user.login",
            "user_id": "00000000-0000-0000-0000-000000000001",
            "resource": "/auth/login",
            "timestamp": "2026-06-30T10:00:00Z",
            "ip": "192.168.1.100",
        },
        {
            "id": str(uuid.uuid4()),
            "action": "rag.search",
            "user_id": "00000000-0000-0000-0000-000000000001",
            "resource": "knowledge_base/fde_knowledge",
            "timestamp": "2026-06-30T10:05:00Z",
            "ip": "192.168.1.100",
        },
        {
            "id": str(uuid.uuid4()),
            "action": "doc.delete",
            "user_id": "00000000-0000-0000-0000-000000000002",
            "resource": "document/doc-123",
            "timestamp": "2026-06-30T10:10:00Z",
            "ip": "192.168.1.101",
        },
    ]

    filtered = mock_entries
    if action:
        filtered = [e for e in filtered if action.lower() in e["action"].lower()]
    if user_id:
        filtered = [e for e in filtered if user_id in e["user_id"]]
    if resource:
        filtered = [e for e in filtered if resource.lower() in e["resource"].lower()]

    return {
        "query": filters,
        "total_matched": len(filtered),
        "entries": filtered[:limit],
        "note": "Mock audit log data — production queries the audit_logs table",
    }


def _compliance_summary_handler(
    period: str = "last_30_days",
    domains: list[str] | None = None,
) -> dict[str, Any]:
    """Generate a compliance status summary for the specified period.

    Args:
        period: Time range ("today", "last_7_days", "last_30_days", "last_90_days").
        domains: Optional list of compliance domains to filter by.
    """
    if domains is None:
        domains = ["access_control", "data_privacy", "audit_trail", "pii_handling"]

    summary = {
        "access_control": {"status": "compliant", "issues": 0, "last_audit": "2026-06-29"},
        "data_privacy": {"status": "compliant", "issues": 0, "last_audit": "2026-06-28"},
        "audit_trail": {"status": "warning", "issues": 3, "last_audit": "2026-06-25"},
        "pii_handling": {"status": "compliant", "issues": 0, "last_audit": "2026-06-30"},
    }

    filtered_summary = {d: summary.get(d, {"status": "unknown"}) for d in domains}

    overall_status = "compliant"
    if any(v.get("status") == "warning" for v in filtered_summary.values()):
        overall_status = "warning"
    if any(v.get("status") == "non_compliant" for v in filtered_summary.values()):
        overall_status = "non_compliant"

    return {
        "period": period,
        "overall_status": overall_status,
        "domains": filtered_summary,
        "note": "Mock compliance summary — production integrates with real audit data",
    }


def _risk_check_handler(
    resource: str = "",
    check_type: str = "all",
) -> dict[str, Any]:
    """Run a risk assessment check against a resource or policy.

    Args:
        resource: Target resource to check (empty = all).
        check_type: Type of check ("all", "permissions", "data_access", "pii_exposure").
    """
    checks = {
        "permissions": {
            "status": "pass",
            "detail": "All RBAC permissions are correctly configured",
            "risk_level": "low",
        },
        "data_access": {
            "status": "pass",
            "detail": "No unauthorized data access detected",
            "risk_level": "low",
        },
        "pii_exposure": {
            "status": "warning",
            "detail": "2 documents contain unmasked PII in audit logs",
            "risk_level": "medium",
        },
    }

    if check_type != "all":
        checks = {k: v for k, v in checks.items() if k == check_type}

    risk_levels = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    overall_risk = max(
        (v.get("risk_level", "low") for v in checks.values()),
        key=lambda x: risk_levels.get(x, 0),
    )

    return {
        "resource": resource or "all",
        "check_type": check_type,
        "overall_risk": overall_risk,
        "checks": checks,
        "note": "Mock risk check — production uses real policy engine",
    }


# ══════════════════════════════════════════════════════════════════
# Registration
# ══════════════════════════════════════════════════════════════════


def register_compliance_tools(registry: ToolRegistry) -> None:
    """Register all compliance agent tools with the orchestrator registry.

    M2-T5: Connects compliance tools to the Supervisor-Worker framework.

    Args:
        registry: The orchestrator's ToolRegistry instance.
    """
    registry.register(
        ToolDefinition(
            name="audit_log_query",
            description="Query and filter audit log entries by action, user, resource, or date range",
            worker="compliance",
            handler=_audit_log_handler,
            parameters={
                "action": {
                    "type": "string",
                    "required": False,
                    "description": "Filter by action name (e.g., user.login, rag.search)",
                },
                "user_id": {
                    "type": "string",
                    "required": False,
                    "description": "Filter by user ID",
                },
                "resource": {
                    "type": "string",
                    "required": False,
                    "description": "Filter by resource path",
                },
                "limit": {
                    "type": "integer",
                    "required": False,
                    "default": 20,
                    "description": "Maximum results to return",
                },
            },
            category="compliance",
        )
    )

    registry.register(
        ToolDefinition(
            name="compliance_summary",
            description="Generate a compliance status summary covering access control, data privacy, audit trails, and PII handling",
            worker="compliance",
            handler=_compliance_summary_handler,
            parameters={
                "period": {
                    "type": "string",
                    "required": False,
                    "default": "last_30_days",
                    "description": "Time range: today, last_7_days, last_30_days, last_90_days",
                },
                "domains": {
                    "type": "array",
                    "required": False,
                    "description": "Compliance domains to include (default: all)",
                },
            },
            category="compliance",
        )
    )

    registry.register(
        ToolDefinition(
            name="risk_check",
            description="Run a risk assessment against resources or policies — checks permissions, data access, and PII exposure",
            worker="compliance",
            handler=_risk_check_handler,
            parameters={
                "resource": {
                    "type": "string",
                    "required": False,
                    "description": "Target resource to check (empty = all)",
                },
                "check_type": {
                    "type": "string",
                    "required": False,
                    "default": "all",
                    "description": "all, permissions, data_access, pii_exposure",
                },
            },
            category="compliance",
        )
    )

    logger.info(
        "Registered %d compliance tools",
        len(registry.get_tools_for_worker("compliance")),
    )
