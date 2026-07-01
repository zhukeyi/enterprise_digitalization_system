"""Tests for Business System Agent — M2-T5."""

from __future__ import annotations

from agents.business_agent.integration import (
    _business_query_handler,
    _data_sync_handler,
    _system_status_handler,
    register_business_tools,
)
from agents.orchestrator.tools.registry import ToolRegistry


class TestBusinessQueryHandler:
    def test_crm_customer_query(self) -> None:
        """Should return CRM customer data."""
        result = _business_query_handler(system="crm", entity="customer")
        assert result["count"] == 1240
        assert len(result["sample"]) == 2
        assert result["sample"][0]["name"] == "Acme Corp"

    def test_erp_inventory_query(self) -> None:
        """Should return ERP inventory data."""
        result = _business_query_handler(system="erp", entity="inventory")
        assert result["count"] == 8900
        assert result["sample"][0]["sku"] == "SKU-001"

    def test_finance_invoice_query(self) -> None:
        """Should return finance invoice data."""
        result = _business_query_handler(system="finance", entity="invoice")
        assert result["count"] == 278
        assert result["sample"][0]["id"] == "INV-9001"

    def test_unknown_system(self) -> None:
        """Should return informative message for unknown system."""
        result = _business_query_handler(system="unknown", entity="customer")
        assert result["count"] == 0
        assert "message" in result

    def test_query_passthrough(self) -> None:
        """Query string should be reflected in result."""
        query_text = "find top customers by revenue"
        result = _business_query_handler(system="crm", entity="customer", query=query_text)
        assert result["query"] == query_text


class TestSystemStatusHandler:
    def test_default_all_systems(self) -> None:
        """Should check all 5 systems by default."""
        result = _system_status_handler()
        assert len(result["systems"]) == 5
        assert "crm" in result["systems"]
        assert "erp" in result["systems"]

    def test_overall_status_degraded(self) -> None:
        """Finance is degraded → overall should be degraded."""
        result = _system_status_handler()
        assert result["overall_status"] == "degraded"

    def test_healthy_systems_only(self) -> None:
        """Checking only healthy systems should return healthy."""
        result = _system_status_handler(systems=["crm", "hr", "messaging"])
        assert result["overall_status"] == "healthy"

    def test_selective_systems(self) -> None:
        """Only check specified systems."""
        result = _system_status_handler(systems=["crm", "erp"])
        assert len(result["systems"]) == 2
        assert result["systems"]["crm"]["status"] == "healthy"


class TestDataSyncHandler:
    def test_validate_mode(self) -> None:
        """Validate mode should detect conflicts without syncing."""
        result = _data_sync_handler(
            source="crm", target="finance", entity="customer", mode="validate"
        )
        assert result["status"] == "ready"
        assert result["estimated_records"] == 156
        assert result["conflicts"] == 2

    def test_execute_mode(self) -> None:
        """Execute mode should perform actual sync."""
        result = _data_sync_handler(
            source="erp", target="finance", entity="invoice", mode="execute"
        )
        assert result["status"] == "completed"
        assert result["synced_records"] == 154

    def test_missing_source_returns_error(self) -> None:
        """Should return error if source/target not specified."""
        result = _data_sync_handler(source="", target="", mode="validate")
        assert "error" in result

    def test_default_mode_is_validate(self) -> None:
        """Default mode should be validate."""
        result = _data_sync_handler(source="crm", target="erp")
        assert result["mode"] == "validate"


class TestBusinessToolRegistration:
    def test_register_all_tools(self) -> None:
        """Should register 3 business system tools."""
        registry = ToolRegistry()
        register_business_tools(registry)

        tools = registry.get_tools_for_worker("business_system")
        assert len(tools) == 3

        tool_names = {t.name for t in tools}
        assert tool_names == {"business_query", "system_status", "data_sync"}

    async def test_business_query_dispatch(self) -> None:
        """Should dispatch business_query correctly."""
        registry = ToolRegistry()
        register_business_tools(registry)

        result = await registry.dispatch("business_query", system="crm", entity="customer")
        assert result["count"] == 1240

    async def test_system_status_dispatch(self) -> None:
        """Should dispatch system_status with params."""
        registry = ToolRegistry()
        register_business_tools(registry)

        result = await registry.dispatch("system_status", systems=["crm"])
        assert len(result["systems"]) == 1
        assert result["overall_status"] == "healthy"
