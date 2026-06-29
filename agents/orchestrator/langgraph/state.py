"""Orchestrator State — global conversation state for LangGraph.

The state flows through the Supervisor-Worker graph:
  messages: conversation history (LangChain BaseMessage)
  next_worker: which worker the supervisor dispatches to
  worker_outputs: accumulated results from worker executions
  plan: current execution plan from supervisor
  metadata: trace info, timing, etc.
"""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

# ══════════════════════════════════════════════════════════════════
# Supervisor Plan — structured output from LLM
# ══════════════════════════════════════════════════════════════════


class PlanStep(BaseModel):
    """A single step in the supervisor's execution plan."""

    worker: str = Field(description="Target worker agent name (rag/hr/data/analysis/router)")
    task: str = Field(description="Task description for the worker")
    tool: str | None = Field(default=None, description="Specific tool to call within the worker")
    tool_args: dict[str, Any] = Field(default_factory=dict, description="Arguments for the tool")
    priority: int = Field(default=1, ge=1, le=5, description="Priority level (1=highest)")


class SupervisorPlan(BaseModel):
    """Structured plan output from the supervisor LLM."""

    steps: list[PlanStep] = Field(default_factory=list, description="Ordered execution steps")
    reasoning: str = Field(default="", description="Supervisor's reasoning for the plan")
    requires_rag: bool = Field(default=False, description="Whether RAG retrieval is needed")
    complexity: str = Field(default="simple", description="Estimated task complexity")
    finish: bool = Field(default=False, description="Whether the conversation is complete")


# ══════════════════════════════════════════════════════════════════
# Orchestrator State — TypedDict for LangGraph
# ══════════════════════════════════════════════════════════════════


class OrchestratorState(BaseModel):
    """Full state of the orchestrator graph.

    This model is used as the state schema for the LangGraph StateGraph.
    Messages use the add_messages reducer to append rather than replace.
    """

    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    next_worker: str = Field(default="", description="Next worker to dispatch to")
    worker_outputs: dict[str, Any] = Field(
        default_factory=dict, description="Worker execution results"
    )
    plan: SupervisorPlan | None = Field(default=None, description="Current supervisor plan")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Trace metadata (trace_id, timing, etc.)",
    )
    iteration: int = Field(default=0, description="Current iteration count (safety limit)")
    error: str | None = Field(default=None, description="Error message if any worker fails")
