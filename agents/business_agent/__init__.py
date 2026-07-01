"""Business System Agent — CRM, ERP, Workflow, Data Sync.

M2-T5: New sub-agent for the Supervisor-Worker framework.

Tools:
- business_query: Query business system data (CRM/ERP/Finance)
- system_status: Check system health and connectivity
- data_sync: Trigger data synchronization between systems
"""

from agents.business_agent.integration import register_business_tools

__all__ = ["register_business_tools"]
