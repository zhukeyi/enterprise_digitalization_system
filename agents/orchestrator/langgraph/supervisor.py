"""Supervisor Node — LLM planner that routes tasks to workers.

The supervisor DOES NOT execute tools. It only:
1. Analyzes the user's request
2. Creates a structured execution plan (Pydantic output)
3. Dispatches to the appropriate worker(s)
4. Evaluates worker results and decides next action

This design ensures:
- LLM calls are minimal (only for planning, not execution)
- Deterministic tool execution (backend code, not LLM)
- Clear separation of concerns (plan vs execute)
- Observable and debuggable routing decisions

M1-T6: Supervisor with structured output
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.orchestrator.langgraph.state import (
    OrchestratorState,
    PlanStep,
    SupervisorPlan,
)
from agents.orchestrator.tools.registry import ToolRegistry

logger = logging.getLogger("fde.orchestrator.supervisor")

# ── Default worker mapping ──────────────────────────────────────────

WORKER_DESCRIPTIONS = {
    "rag": "Knowledge retrieval — search enterprise documents, answer questions with citations",
    "hr": "HR analysis — employee profiling, risk assessment, layoff simulation",
    "data": "Data pipeline — web scraping, data collection, RSS feeds",
    "analysis": "Data analysis — NL2SQL, interactive charts, statistical reports",
    "router": "Model gateway — route to different LLM providers, fallback chain",
    "governance": "Access control — user management, RBAC, audit logging",
    "compliance": "Compliance auditing — audit logs, risk checks, regulatory validation",
    "business_system": "Business system integration — CRM, ERP, workflow, data sync",
    "im": "Message hub — send, broadcast, session sync (WeCom/Feishu/DingTalk)",
    "map": "Spatial analysis — geographic query, correlation, region data",
}

# ── Supervisor prompt template ──────────────────────────────────────

SUPERVISOR_SYSTEM_PROMPT = """You are the FDE AI Platform Supervisor. Your job is to PLAN, not execute.

Given the conversation history and available tools, create an execution plan that specifies:
1. Which worker should handle each step
2. What specific tool to call (if applicable)
3. What arguments to pass to the tool

Available workers:
{worker_descriptions}

Available tools:
{tool_list}

Rules:
- You MUST output a structured plan (JSON with steps, reasoning, complexity, finish flag)
- NEVER execute tools yourself — only plan
- If the user's request is simple and no worker is needed, set finish=true
- If a tool is marked [DANGEROUS], it requires foolproof confirmation before execution
- Maximum 5 steps per plan
- If previous worker results are available, evaluate them before planning next steps

Output format (JSON):
{{"steps": [{{"worker": "...", "task": "...", "tool": "...", "tool_args": {{...}}}}], "reasoning": "...", "requires_rag": true/false, "complexity": "simple|medium|complex", "finish": true/false}}"""


# ══════════════════════════════════════════════════════════════════
# Supervisor Node
# ══════════════════════════════════════════════════════════════════


class SupervisorNode:
    """LangGraph node that acts as the supervisor planner.

    This node:
    1. Reads the current state (messages, worker_outputs)
    2. Calls the LLM to generate a structured plan
    3. Updates the state with the plan and next_worker
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        llm: Any | None = None,
        max_iterations: int = 10,
    ) -> None:
        self.tool_registry = tool_registry
        self.llm = llm  # Will be None in mock/dev mode
        self.max_iterations = max_iterations

    def __call__(self, state: OrchestratorState) -> dict[str, Any]:
        """Execute the supervisor node.

        Args:
            state: Current orchestrator state.

        Returns:
            State updates (plan, next_worker, etc.)
        """
        logger.info("Supervisor iteration=%d messages=%d", state.iteration, len(state.messages))

        # Safety: prevent infinite loops
        if state.iteration >= self.max_iterations:
            logger.warning("Max iterations reached (%d), forcing finish", self.max_iterations)
            return {
                "plan": SupervisorPlan(steps=[], reasoning="Max iterations reached", finish=True),
                "next_worker": "__end__",
                "iteration": state.iteration + 1,
            }

        # Build prompt context
        system_prompt = self._build_system_prompt()
        context_messages = self._build_context_messages(state)

        # Generate plan
        if self.llm is not None:
            plan = self._call_llm(system_prompt, context_messages)
        else:
            plan = self._mock_plan(state)

        # Determine next worker
        next_worker = self._determine_next_worker(plan)

        logger.info(
            "Supervisor plan: steps=%d next_worker=%s complexity=%s finish=%s",
            len(plan.steps),
            next_worker,
            plan.complexity,
            plan.finish,
        )

        return {
            "plan": plan,
            "next_worker": next_worker,
            "iteration": state.iteration + 1,
            "messages": [AIMessage(content=f"[Supervisor] Plan: {plan.reasoning}")],
        }

    def _build_system_prompt(self) -> str:
        """Build the system prompt with current tool & worker info."""
        worker_desc = "\n".join(f"- {name}: {desc}" for name, desc in WORKER_DESCRIPTIONS.items())
        tool_list = "\n".join(
            f"- {t.name} ({t.worker}): {t.description}{' [DANGEROUS]' if t.is_dangerous else ''}"
            for t in self.tool_registry.list_all()
        )

        return SUPERVISOR_SYSTEM_PROMPT.format(
            worker_descriptions=worker_desc,
            tool_list=tool_list or "No tools registered yet",
        )

    def _build_context_messages(self, state: OrchestratorState) -> list[Any]:
        """Build the message context for the LLM call."""
        messages = list(state.messages)

        # Add worker output context if available
        if state.worker_outputs:
            output_summary = "Previous worker results:\n"
            for worker, result in state.worker_outputs.items():
                output_summary += f"- {worker}: {str(result)[:200]}\n"
            messages.append(SystemMessage(content=output_summary))

        return messages

    def _call_llm(self, system_prompt: str, context_messages: list[Any]) -> SupervisorPlan:
        """Call the LLM to generate a structured plan.

        Uses structured output (Pydantic) to ensure the plan is parseable.
        Falls back to mock if LLM call fails.
        """
        try:
            full_messages = [*[SystemMessage(content=system_prompt)], *context_messages]
            response = self.llm.invoke(full_messages)  # type: ignore[union-attr]

            # Parse structured output
            plan = self._parse_llm_response(response.content)
            return plan
        except (ValueError, TypeError, RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.warning("LLM call failed: %s, falling back to mock", e)
            return self._mock_plan_from_messages(context_messages)

    def _parse_llm_response(self, content: str) -> SupervisorPlan:
        """Parse LLM response into a SupervisorPlan.

        Handles both JSON-string responses and already-parsed dicts.
        """

        # Try direct JSON parse
        try:
            data = json.loads(content)
            return self._parse_plan_json(data)
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

        # Try extracting JSON from markdown code blocks
        json_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", content, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                return self._parse_plan_json(data)
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

        # Fallback: treat as simple response
        logger.warning("Could not parse LLM response as structured plan, using fallback")
        return SupervisorPlan(steps=[], reasoning=content, finish=True)

    def _parse_plan_json(self, data: dict[str, Any]) -> SupervisorPlan:
        """Parse a dict into a SupervisorPlan."""
        return SupervisorPlan(
            steps=[PlanStep(**s) for s in data.get("steps", [])],
            reasoning=data.get("reasoning", ""),
            requires_rag=data.get("requires_rag", False),
            complexity=data.get("complexity", "simple"),
            finish=data.get("finish", False),
        )

    def _mock_plan(self, state: OrchestratorState) -> SupervisorPlan:
        """Generate a mock plan for development/testing without LLM.

        Uses simple heuristics to route requests.
        If worker_outputs already exist, check for remaining plan steps before finishing.
        """
        # If workers have already produced results, check if plan has more steps
        if state.worker_outputs:
            remaining = self._remaining_steps(state)
            if remaining:
                next_step = remaining[0]
                return SupervisorPlan(
                    steps=remaining,
                    reasoning=f"Continuing to next step: {next_step.worker}/{next_step.task[:50]}",
                    requires_rag=next_step.worker == "rag",
                    complexity="medium",
                    finish=False,
                )

            results_summary = ", ".join(
                f"{k}: {str(v)[:50]}" for k, v in state.worker_outputs.items()
            )
            return SupervisorPlan(
                steps=[],
                reasoning=f"All steps completed. Workers: {results_summary}",
                requires_rag="rag" in state.worker_outputs,
                complexity="medium",
                finish=True,
            )

        # Get the last user message
        last_user_msg: str = ""
        for msg in reversed(state.messages):
            if isinstance(msg, HumanMessage):
                last_user_msg = (
                    str(msg.content) if not isinstance(msg.content, str) else msg.content
                )
                break

        if not last_user_msg:
            return SupervisorPlan(steps=[], reasoning="No user message found", finish=True)

        # Simple keyword-based routing heuristics
        query_lower = last_user_msg.lower()

        steps: list[PlanStep] = []
        matched_workers: set[str] = set()

        # Check for RAG-related queries
        rag_keywords = ["知识库", "文档", "检索", "搜索", "查找", "knowledge", "search", "document"]
        if any(kw in query_lower for kw in rag_keywords):
            steps.append(
                PlanStep(
                    worker="rag",
                    task=f"Search knowledge base for: {last_user_msg[:100]}",
                    tool="rag_search",
                    tool_args={"query": last_user_msg},
                )
            )
            matched_workers.add("rag")

        # Check for compliance-related queries
        compliance_keywords = ["合规", "审计", "风险检查", "compliance", "audit", "regulatory"]
        if any(kw in query_lower for kw in compliance_keywords):
            steps.append(
                PlanStep(
                    worker="compliance",
                    task=f"Compliance check for: {last_user_msg[:100]}",
                    tool="compliance_summary",
                )
            )
            matched_workers.add("compliance")

        # Check for business system queries
        business_keywords = [
            "crm",
            "erp",
            "业务系统",
            "客户",
            "订单",
            "inventory",
            "invoice",
            "business",
        ]
        if any(kw in query_lower for kw in business_keywords):
            # Use system_status (no args needed) unless specific entity keywords are present
            if any(kw in query_lower for kw in ["客户", "订单", "customer", "order"]):
                steps.append(
                    PlanStep(
                        worker="business_system",
                        task=f"Query business systems for: {last_user_msg[:100]}",
                        tool="business_query",
                        tool_args={"system": "crm", "entity": "customer"},
                    )
                )
            else:
                steps.append(
                    PlanStep(
                        worker="business_system",
                        task=f"Check business system status for: {last_user_msg[:100]}",
                        tool="system_status",
                    )
                )
            matched_workers.add("business_system")

        # Check for IM/messaging queries
        im_keywords = ["通知", "消息", "发送", "广播", "notify", "message", "broadcast", "send"]
        if any(kw in query_lower for kw in im_keywords):
            steps.append(
                PlanStep(
                    worker="im",
                    task=f"Send IM notification for: {last_user_msg[:100]}",
                    tool="send_message",
                    tool_args={
                        "platform": "mock",
                        "target_id": "default-group",
                        "content": last_user_msg[:200],
                    },
                )
            )
            matched_workers.add("im")

        # Check for HR-related queries
        hr_keywords = ["员工", "裁员", "绩效", "hr", "employee", "layoff", "performance"]
        if any(kw in query_lower for kw in hr_keywords):
            steps.append(
                PlanStep(
                    worker="hr",
                    task=f"HR analysis for: {last_user_msg[:100]}",
                )
            )
            matched_workers.add("hr")

        # Check for data-related queries
        data_keywords = ["数据采集", "爬虫", "rss", "scrape", "crawl", "feed"]
        if any(kw in query_lower for kw in data_keywords):
            steps.append(
                PlanStep(
                    worker="data",
                    task=f"Data collection for: {last_user_msg[:100]}",
                )
            )
            matched_workers.add("data")

        # Check for analysis-related queries (only if no specific worker matched yet)
        analysis_keywords = ["分析", "报表", "统计", "chart", "analyze", "report"]
        if any(kw in query_lower for kw in analysis_keywords) and not matched_workers:
            steps.append(
                PlanStep(
                    worker="analysis",
                    task=f"Data analysis for: {last_user_msg[:100]}",
                )
            )
            matched_workers.add("analysis")

        # Check for governance/access-control queries
        governance_keywords = ["权限", "用户管理", "rbac", "access control", "governance"]
        if any(kw in query_lower for kw in governance_keywords):
            steps.append(
                PlanStep(
                    worker="governance",
                    task=f"Access control check for: {last_user_msg[:100]}",
                )
            )
            matched_workers.add("governance")

        # Check for map/spatial queries
        map_keywords = ["地图", "空间", "地理", "区域", "map", "spatial", "geographic", "region"]
        if any(kw in query_lower for kw in map_keywords):
            steps.append(
                PlanStep(
                    worker="map",
                    task=f"Spatial analysis for: {last_user_msg[:100]}",
                )
            )
            matched_workers.add("map")

        if steps:
            complexity = "complex" if len(steps) >= 3 else "medium" if len(steps) == 2 else "simple"
            return SupervisorPlan(
                steps=steps,
                reasoning=f"Routed to {len(steps)} worker(s): {', '.join(matched_workers)}",
                requires_rag="rag" in matched_workers,
                complexity=complexity,
                finish=False,
            )

        # Default: simple response, no worker needed
        return SupervisorPlan(
            steps=[],
            reasoning=f"Simple query, no specialized worker needed: {last_user_msg[:50]}",
            requires_rag=False,
            complexity="simple",
            finish=True,
        )

    def _mock_plan_from_messages(self, messages: list[Any]) -> SupervisorPlan:
        """Fallback mock plan when LLM fails."""
        last_user_msg: str = ""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                last_user_msg = (
                    str(msg.content) if not isinstance(msg.content, str) else msg.content
                )
                break

        return SupervisorPlan(
            steps=[PlanStep(worker="router", task=f"Handle query: {last_user_msg[:100]}")],
            reasoning="LLM call failed, routing to default worker",
            requires_rag=False,
            complexity="simple",
            finish=False,
        )

    def _determine_next_worker(self, plan: SupervisorPlan) -> str:
        """Determine the next worker to dispatch to.

        Returns:
            Worker name string, or "__end__" if plan is finished.
        """
        if plan.finish:
            return "__end__"

        if not plan.steps:
            return "__end__"

        # Return the first step's worker (subsequent steps handled iteratively)
        first_step = plan.steps[0]
        return first_step.worker

    def _remaining_steps(
        self,
        state: OrchestratorState,
    ) -> list[PlanStep]:
        """Find plan steps whose target worker has not yet produced output.

        Args:
            state: Current orchestrator state.

        Returns:
            List of PlanStep objects for workers that haven't run yet.
        """
        if state.plan is None:
            return []
        return [s for s in state.plan.steps if s.worker not in state.worker_outputs]
