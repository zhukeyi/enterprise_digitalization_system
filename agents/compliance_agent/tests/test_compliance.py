"""Tests for Compliance Agent — M2-T5."""

from __future__ import annotations

from agents.compliance_agent.integration import (
    _audit_log_handler,
    _compliance_summary_handler,
    _risk_check_handler,
    register_compliance_tools,
)
from agents.orchestrator.tools.registry import ToolRegistry


class TestAuditLogHandler:
    def test_all_entries(self) -> None:
        """Should return all mock entries without filters."""
        result = _audit_log_handler()
        assert result["total_matched"] == 3
        assert len(result["entries"]) == 3
        assert result["query"]["action"] == ""

    def test_filter_by_action(self) -> None:
        """Should filter by action name."""
        result = _audit_log_handler(action="login")
        assert result["total_matched"] == 1
        assert result["entries"][0]["action"] == "user.login"

    def test_filter_by_user_id(self) -> None:
        """Should filter by partial user_id."""
        result = _audit_log_handler(user_id="00000000-0000")
        assert result["total_matched"] >= 1

    def test_limit_enforced(self) -> None:
        """Should respect the limit parameter."""
        result = _audit_log_handler(limit=1)
        assert result["total_matched"] == 3
        assert len(result["entries"]) == 1

    def test_no_match_returns_empty(self) -> None:
        """Should return empty when no entries match."""
        result = _audit_log_handler(action="nonexistent_action")
        assert result["total_matched"] == 0
        assert result["entries"] == []


class TestComplianceSummaryHandler:
    def test_default_period(self) -> None:
        """Should return summary for default period."""
        result = _compliance_summary_handler()
        assert result["period"] == "last_30_days"
        assert result["overall_status"] == "warning"
        assert "access_control" in result["domains"]
        assert "data_privacy" in result["domains"]

    def test_custom_period(self) -> None:
        """Should accept custom period."""
        result = _compliance_summary_handler(period="last_7_days")
        assert result["period"] == "last_7_days"

    def test_filtered_domains(self) -> None:
        """Should only return requested domains."""
        result = _compliance_summary_handler(domains=["access_control", "data_privacy"])
        assert len(result["domains"]) == 2
        assert result["overall_status"] == "compliant"

    def test_all_status_values(self) -> None:
        """Statuses should be one of: compliant, warning, non_compliant."""
        result = _compliance_summary_handler()
        statuses = {v["status"] for v in result["domains"].values()}
        assert statuses.issubset({"compliant", "warning", "non_compliant", "unknown"})


class TestRiskCheckHandler:
    def test_all_checks(self) -> None:
        """Should run all check types by default."""
        result = _risk_check_handler()
        assert result["check_type"] == "all"
        assert len(result["checks"]) == 3
        assert result["overall_risk"] == "medium"

    def test_specific_check_type(self) -> None:
        """Should only run the requested check."""
        result = _risk_check_handler(check_type="permissions")
        assert result["check_type"] == "permissions"
        assert len(result["checks"]) == 1
        assert result["overall_risk"] == "low"

    def test_risk_low_check(self) -> None:
        """Permissions check should return low risk."""
        result = _risk_check_handler(check_type="permissions")
        assert result["checks"]["permissions"]["risk_level"] == "low"

    def test_resource_passthrough(self) -> None:
        """Resource arg should be reflected in result."""
        result = _risk_check_handler(resource="document/doc-123")
        assert result["resource"] == "document/doc-123"


class TestComplianceToolRegistration:
    def test_register_all_tools(self) -> None:
        """Should register 3 compliance tools."""
        registry = ToolRegistry()
        register_compliance_tools(registry)

        tools = registry.get_tools_for_worker("compliance")
        assert len(tools) == 3

        tool_names = {t.name for t in tools}
        assert tool_names == {"audit_log_query", "compliance_summary", "risk_check"}

    async def test_tool_dispatch(self) -> None:
        """Should dispatch audit_log_query correctly."""
        registry = ToolRegistry()
        register_compliance_tools(registry)

        result = await registry.dispatch("audit_log_query", action="login")
        assert result["total_matched"] == 1
        assert "entries" in result

    async def test_risk_check_dispatch(self) -> None:
        """Should dispatch risk_check with params."""
        registry = ToolRegistry()
        register_compliance_tools(registry)

        result = await registry.dispatch("risk_check", check_type="data_access")
        assert result["check_type"] == "data_access"
        assert result["overall_risk"] == "low"
