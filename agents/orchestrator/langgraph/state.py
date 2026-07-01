"""Orchestrator State — global conversation state for LangGraph.

The state flows through the Supervisor-Worker graph:
  messages: conversation history (LangChain BaseMessage)
  next_worker: which worker the supervisor dispatches to
  worker_outputs: accumulated results from worker executions
  plan: current execution plan from supervisor
  metadata: trace info, timing, etc.

M2-T6: Added conflict detection, resolution, and final response fields.
M2-T8: Added merge_dict reducer for worker_outputs accumulation across steps.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


def merge_dict(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Reducer that merges dict updates instead of replacing.

    Used for worker_outputs so that each worker's return value
    {worker_name: result} accumulates across multi-step plans.
    """
    merged = dict(left)
    merged.update(right)
    return merged


# ══════════════════════════════════════════════════════════════════
# Conflict Models (M2-T6)
# ══════════════════════════════════════════════════════════════════


class ConflictReport(BaseModel):
    """A detected conflict between two or more worker outputs."""

    conflict_id: str = Field(description="Unique conflict identifier")
    source_workers: list[str] = Field(description="Which workers produced conflicting outputs")
    description: str = Field(description="Human-readable conflict description")
    severity: Literal["low", "medium", "high", "critical"] = Field(
        default="low", description="Severity level"
    )
    field: str = Field(default="", description="The specific field or key in conflict")
    resolution_strategy: Literal[
        "auto", "manual", "merge", "highest_confidence", "source_priority"
    ] = Field(default="auto", description="How to resolve the conflict")


class ConflictResolution(BaseModel):
    """Resolution decision for a specific conflict."""

    conflict_id: str = Field(description="Reference to ConflictReport.conflict_id")
    resolved: bool = Field(default=False)
    chosen_worker: str = Field(default="", description="Which worker's output to trust")
    chosen_value: Any = Field(default=None, description="The resolved value")
    reasoning: str = Field(default="", description="Why this resolution was chosen")


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
    worker_outputs: Annotated[dict[str, Any], merge_dict] = Field(
        default_factory=dict, description="Worker execution results"
    )
    plan: SupervisorPlan | None = Field(default=None, description="Current supervisor plan")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Trace metadata (trace_id, timing, etc.)",
    )
    iteration: int = Field(default=0, description="Current iteration count (safety limit)")
    error: str | None = Field(default=None, description="Error message if any worker fails")

    # ── M2-T6: Conflict Resolution ────────────────────────────────────
    conflicts: list[ConflictReport] = Field(
        default_factory=list,
        description="Detected conflicts between worker outputs",
    )
    conflict_resolved: bool = Field(
        default=False,
        description="Whether conflicts have been resolved",
    )
    conflict_resolutions: list[ConflictResolution] = Field(
        default_factory=list,
        description="Resolution decisions for each conflict",
    )
    final_response: str = Field(
        default="",
        description="Final aggregated response generated for the user",
    )
