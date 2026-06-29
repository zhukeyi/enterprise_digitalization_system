"""Orchestrator — LangGraph Supervisor-Worker multi-agent orchestration.

Architecture:
- Supervisor: LLM-only planner (structured Pydantic output)
- Workers: Domain-specific agents that execute tools
- Message Bus: LangChain Message-based communication
- Tool Registry: Centralized tool discovery & dispatch

Flow:
  User Input → Supervisor (plan) → Worker(s) (execute) → Supervisor (evaluate) → Response

M1-T6: LangGraph framework core
"""

from __future__ import annotations

from agents.orchestrator.langgraph.graph import build_orchestrator_graph
from agents.orchestrator.langgraph.state import OrchestratorState
from agents.orchestrator.langgraph.supervisor import SupervisorNode
from agents.orchestrator.tools.registry import ToolRegistry

__all__ = [
    "OrchestratorState",
    "SupervisorNode",
    "ToolRegistry",
    "build_orchestrator_graph",
]
