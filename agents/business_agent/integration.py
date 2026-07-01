"""Business System Agent — CRM, ERP, Workflow, Data Sync.

M2-T5: New sub-agent for the LangGraph Supervisor-Worker framework.

Provides tools for:
- business_query: Query business systems (CRM/ERP/Finance)
- system_status: Check system health and connectivity
- data_sync: Trigger data synchronization between systems
"""

from __future__ import annotations

import logging
from typing import Any

from agents.orchestrator.tools.registry import ToolDefinition, ToolRegistry

logger = logging.getLogger("fde.business")

# ══════════════════════════════════════════════════════════════════
# Tool Handlers
# ══════════════════════════════════════════════════════════════════


def _business_query_handler(
    system: str = "",
    entity: str = "",
    query: str = "",
) -> dict[str, Any]:
    """Query a business system for data.

    Supports CRM, ERP, finance, and other enterprise systems.

    Args:
        system: Target system name ("crm", "erp", "finance", "hr").
        entity: Entity type to query (e.g., "customer", "order", "invoice").
        query: Natural language or structured query string.
    """
    # Mock responses per system + entity
    mock_responses: dict[str, dict[str, Any]] = {
        "crm_customer": {
            "entity": "customer",
            "system": "crm",
            "count": 1240,
            "sample": [
                {"id": "C001", "name": "Acme Corp", "status": "active", "revenue": "$2.4M"},
                {"id": "C002", "name": "Beta Ltd", "status": "active", "revenue": "$1.8M"},
            ],
        },
        "crm_order": {
            "entity": "order",
            "system": "crm",
            "count": 453,
            "sample": [
                {"id": "O-5001", "customer": "Acme Corp", "amount": "$45K", "status": "fulfilled"},
            ],
        },
        "erp_inventory": {
            "entity": "inventory",
            "system": "erp",
            "count": 8900,
            "sample": [
                {"sku": "SKU-001", "name": "Widget A", "stock": 234, "reorder_point": 100},
                {"sku": "SKU-002", "name": "Gadget B", "stock": 12, "reorder_point": 50},
            ],
        },
        "finance_invoice": {
            "entity": "invoice",
            "system": "finance",
            "count": 278,
            "sample": [
                {
                    "id": "INV-9001",
                    "amount": "$12,500",
                    "due_date": "2026-07-15",
                    "status": "pending",
                },
            ],
        },
    }

    key = f"{system}_{entity}" if system and entity else ""
    result = mock_responses.get(key)

    if result:
        result["query"] = query
        result["note"] = "Mock business data — production connects to real system APIs"
        return result

    return {
        "system": system or "all",
        "entity": entity or "all",
        "query": query,
        "count": 0,
        "message": f"No mock data for system='{system}', entity='{entity}'. "
        f"Available combinations: {list(mock_responses.keys())}",
        "note": "Mock business data — production connects to real system APIs",
    }


def _system_status_handler(
    systems: list[str] | None = None,
) -> dict[str, Any]:
    """Check the operational status of business systems.

    Args:
        systems: Optional list of system names to check. Defaults to all.
    """
    if systems is None:
        systems = ["crm", "erp", "finance", "hr", "messaging"]

    status_map = {
        "crm": {"status": "healthy", "latency_ms": 45, "uptime_pct": 99.9},
        "erp": {"status": "healthy", "latency_ms": 120, "uptime_pct": 99.7},
        "finance": {"status": "degraded", "latency_ms": 850, "uptime_pct": 98.2},
        "hr": {"status": "healthy", "latency_ms": 35, "uptime_pct": 99.99},
        "messaging": {"status": "healthy", "latency_ms": 10, "uptime_pct": 99.95},
    }

    checked = {s: status_map.get(s, {"status": "unknown"}) for s in systems}

    overall = "healthy"
    statuses = [v.get("status") for v in checked.values()]
    if "down" in statuses:
        overall = "down"
    elif "degraded" in statuses:
        overall = "degraded"

    return {
        "overall_status": overall,
        "systems": checked,
        "checked_at": "2026-06-30T14:00:00Z",
        "note": "Mock system status — production uses real health checks",
    }


def _data_sync_handler(
    source: str = "",
    target: str = "",
    entity: str = "",
    mode: str = "validate",
) -> dict[str, Any]:
    """Trigger or validate data synchronization between business systems.

    Args:
        source: Source system (e.g., "crm").
        target: Target system (e.g., "finance").
        entity: Entity to sync (e.g., "customer", "invoice").
        mode: "validate" (dry run) or "execute" (actual sync).
    """
    if not source or not target:
        return {
            "error": "Both source and target systems must be specified",
            "mode": mode,
        }

    sync_id = f"sync-{source}-{target}-{entity}" if entity else f"sync-{source}-{target}"

    if mode == "validate":
        return {
            "sync_id": sync_id,
            "source": source,
            "target": target,
            "entity": entity or "all",
            "mode": "validate",
            "status": "ready",
            "estimated_records": 156,
            "conflicts": 2,
            "note": "Validation complete — 2 conflicts detected. Run with mode='execute' to sync.",
        }

    # mode == "execute"
    return {
        "sync_id": sync_id,
        "source": source,
        "target": target,
        "entity": entity or "all",
        "mode": "execute",
        "status": "completed",
        "synced_records": 154,
        "skipped": 2,
        "duration_ms": 1250,
        "note": "Sync completed — 154 records synced, 2 skipped due to conflicts.",
    }


# ══════════════════════════════════════════════════════════════════
# Registration
# ══════════════════════════════════════════════════════════════════


def register_business_tools(registry: ToolRegistry) -> None:
    """Register all business system agent tools with the orchestrator registry.

    M2-T5: Connects business tools to the Supervisor-Worker framework.

    Args:
        registry: The orchestrator's ToolRegistry instance.
    """
    registry.register(
        ToolDefinition(
            name="business_query",
            description="Query business systems (CRM/ERP/Finance/HR) for customer, order, inventory, or invoice data",
            worker="business_system",
            handler=_business_query_handler,
            parameters={
                "system": {
                    "type": "string",
                    "required": True,
                    "description": "Target system: crm, erp, finance, hr",
                },
                "entity": {
                    "type": "string",
                    "required": False,
                    "description": "Entity type: customer, order, inventory, invoice",
                },
                "query": {
                    "type": "string",
                    "required": False,
                    "description": "Natural language or structured query",
                },
            },
            category="business",
        )
    )

    registry.register(
        ToolDefinition(
            name="system_status",
            description="Check the operational health and connectivity status of business systems (CRM, ERP, Finance, HR, Messaging)",
            worker="business_system",
            handler=_system_status_handler,
            parameters={
                "systems": {
                    "type": "array",
                    "required": False,
                    "description": "List of system names to check (default: all)",
                },
            },
            category="business",
        )
    )

    registry.register(
        ToolDefinition(
            name="data_sync",
            description="Trigger or validate data synchronization between business systems (CRM↔ERP↔Finance)",
            worker="business_system",
            handler=_data_sync_handler,
            parameters={
                "source": {
                    "type": "string",
                    "required": True,
                    "description": "Source system: crm, erp, finance",
                },
                "target": {
                    "type": "string",
                    "required": True,
                    "description": "Target system: crm, erp, finance",
                },
                "entity": {
                    "type": "string",
                    "required": False,
                    "description": "Entity to sync: customer, order, invoice",
                },
                "mode": {
                    "type": "string",
                    "required": False,
                    "default": "validate",
                    "description": "validate (dry run) or execute (actual sync)",
                },
            },
            category="business",
        )
    )

    logger.info(
        "Registered %d business system tools",
        len(registry.get_tools_for_worker("business_system")),
    )
