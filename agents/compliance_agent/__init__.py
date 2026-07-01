"""Compliance Agent — audit logs, risk checks, regulatory validation.

M2-T5: New sub-agent for the Supervisor-Worker framework.

Tools:
- audit_log_query: Query and filter audit log entries
- compliance_summary: Generate compliance status summary
- risk_check: Run risk assessments against resources/policies
"""

from agents.compliance_agent.integration import register_compliance_tools

__all__ = ["register_compliance_tools"]
