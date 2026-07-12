"""Cost Canary — per-agent daily budget monitoring and degradation.

Tracks cumulative token cost per agent_module per day. When spending
exceeds a budget threshold, emits warnings and can trigger model
degradation (e.g., GPT-4o → GPT-4o-mini).

Designed as a lightweight in-memory system suitable for single-instance
deployments. For multi-instance, replace with Redis-backed counters.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from agents.observability_agent.token_tracker import _token_buffer

logger = logging.getLogger("fde.observability.budget")

# Budget store: {agent_module: {"daily_limit_usd": float, "current_spend_usd": float, "date": str}}
_budgets: dict[str, dict[str, Any]] = {}

# Degradation mapping: when budget exceeded, downgrade model
_DEGRADATION_MAP: dict[str, str] = {
    "deepseek/deepseek-chat": "fde/mock-v1",
    "qwen/qwen-turbo": "fde/mock-v1",
    "zhipu/glm-4-flash": "fde/mock-v1",
}

# Events log (in-memory, recent 500)
_budget_events: list[dict[str, Any]] = []


def _today_key() -> str:
    """Get today's date key (UTC)."""
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _reset_if_new_day(agent_module: str) -> None:
    """Reset daily spend counter if it's a new day."""
    today = _today_key()
    if agent_module in _budgets and _budgets[agent_module].get("date") != today:
        _budgets[agent_module]["current_spend_usd"] = 0.0
        _budgets[agent_module]["date"] = today


def set_budget(agent_module: str, daily_limit_usd: float) -> dict[str, Any]:
    """Set or update the daily budget for an agent module.

    Args:
        agent_module: Name of the agent (e.g., "rag_agent", "orchestrator")
        daily_limit_usd: Maximum allowed daily spend in USD

    Returns:
        Budget info dict
    """
    today = _today_key()
    _budgets[agent_module] = {
        "agent_module": agent_module,
        "daily_limit_usd": daily_limit_usd,
        "current_spend_usd": _budgets.get(agent_module, {}).get("current_spend_usd", 0.0),
        "date": today,
        "status": "ok",
        "percentage": 0.0,
    }
    _reset_if_new_day(agent_module)
    _recalculate(agent_module)

    logger.info("Budget set for %s: $%.4f/day", agent_module, daily_limit_usd)
    return _budgets[agent_module]


def get_budget(agent_module: str | None = None) -> dict[str, Any]:
    """Get budget info for one or all agent modules."""
    if agent_module:
        _reset_if_new_day(agent_module)
        _recalculate(agent_module)
        if agent_module in _budgets:
            return _budgets[agent_module]
        return {
            "agent_module": agent_module,
            "daily_limit_usd": 0.0,
            "current_spend_usd": 0.0,
            "status": "no_budget",
            "percentage": 0.0,
        }

    # Return all budgets
    for mod in list(_budgets.keys()):
        _reset_if_new_day(mod)
        _recalculate(mod)

    return {
        "budgets": list(_budgets.values()),
        "degradation_map": _DEGRADATION_MAP,
    }


def _recalculate(agent_module: str) -> None:
    """Recalculate current spend for an agent from the token buffer."""
    if agent_module not in _budgets:
        return

    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_ts = today_start.timestamp()

    # Sum today's spend for this agent
    spend = sum(r[6] for r in _token_buffer if r[0] >= cutoff_ts and r[7] == agent_module)

    _budgets[agent_module]["current_spend_usd"] = round(spend, 6)

    limit = _budgets[agent_module]["daily_limit_usd"]
    if limit > 0:
        pct = (spend / limit) * 100
        _budgets[agent_module]["percentage"] = round(pct, 1)

        if pct >= 100:
            _budgets[agent_module]["status"] = "exceeded"
            _emit_event(agent_module, "exceeded", spend, limit)
        elif pct >= 80:
            _budgets[agent_module]["status"] = "warning"
            _emit_event(agent_module, "warning", spend, limit)
        else:
            _budgets[agent_module]["status"] = "ok"
    else:
        _budgets[agent_module]["percentage"] = 0.0
        _budgets[agent_module]["status"] = "ok"


def _emit_event(
    agent_module: str, event_type: str, current_spend: float, limit: float
) -> None:
    """Emit a budget event (deduplicated within same hour)."""
    # Deduplicate: skip if same event in last hour
    now = time.time()
    recent = [e for e in _budget_events if now - e["timestamp"] < 3600]
    for e in recent:
        if e["agent_module"] == agent_module and e["type"] == event_type:
            return

    event = {
        "timestamp": now,
        "datetime": datetime.now(UTC).isoformat(),
        "agent_module": agent_module,
        "type": event_type,
        "current_spend_usd": round(current_spend, 6),
        "daily_limit_usd": limit,
        "percentage": round(current_spend / limit * 100, 1) if limit > 0 else 0,
    }
    _budget_events.append(event)

    # Keep only last 500 events
    if len(_budget_events) > 500:
        _budget_events[:] = _budget_events[-500:]

    if event_type == "exceeded":
        logger.warning(
            "BUDGET EXCEEDED: %s spent $%.4f (limit $%.4f) — degradation recommended",
            agent_module,
            current_spend,
            limit,
        )
    elif event_type == "warning":
        logger.warning(
            "BUDGET WARNING: %s at %.1f%% of daily limit ($%.4f/$%.4f)",
            agent_module,
            event["percentage"],
            current_spend,
            limit,
        )


def get_budget_events(hours: int = 24) -> list[dict[str, Any]]:
    """Get budget events from the last N hours."""
    cutoff = time.time() - (hours * 3600)
    return [
        {
            "datetime": e["datetime"],
            "agent_module": e["agent_module"],
            "type": e["type"],
            "current_spend_usd": e["current_spend_usd"],
            "daily_limit_usd": e["daily_limit_usd"],
            "percentage": e["percentage"],
        }
        for e in _budget_events
        if e["timestamp"] >= cutoff
    ]


def check_degradation(agent_module: str, requested_model: str) -> str | None:
    """Check if a model should be degraded due to budget exceeded.

    Returns the degraded model name, or None if no degradation needed.
    """
    _reset_if_new_day(agent_module)
    _recalculate(agent_module)

    budget = _budgets.get(agent_module)
    if not budget or budget["status"] != "exceeded":
        return None

    degraded = _DEGRADATION_MAP.get(requested_model)
    if degraded:
        logger.info(
            "DEGRADATION: %s model %s → %s (budget exceeded)",
            agent_module,
            requested_model,
            degraded,
        )
    return degraded
