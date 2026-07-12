"""Token usage tracking — persistence and aggregation.

Stores per-LLM-call token usage in a ring buffer and optionally in the
database (token_usage_log table). Provides aggregation queries for
the observability portal.

numpy-only: no pandas dependency.
"""

from __future__ import annotations

import logging
import math
import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("fde.observability.tokens")

# Ring buffer for recent token usage (in-memory, fast queries)
# Each entry: (timestamp, trace_id, model, prompt_tokens, completion_tokens,
#              total_tokens, cost_usd, agent_module, user_id, latency_ms)
_token_buffer: deque[tuple[float, str, str, int, int, int, float, str, str, float]] = deque(
    maxlen=50000
)

# Model pricing table (USD per 1K tokens)
# prompt = input price, completion = output price
_MODEL_PRICING: dict[str, dict[str, float]] = {
    "fde/mock-v1": {"prompt": 0.0, "completion": 0.0},
    "deepseek/deepseek-chat": {"prompt": 0.001, "completion": 0.002},
    "qwen/qwen-turbo": {"prompt": 0.0008, "completion": 0.0016},
    "zhipu/glm-4-flash": {"prompt": 0.0006, "completion": 0.0012},
}


def _compute_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Compute cost in USD based on model pricing table."""
    pricing = _MODEL_PRICING.get(model, {"prompt": 0.0, "completion": 0.0})
    return round(
        (prompt_tokens / 1000.0) * pricing["prompt"]
        + (completion_tokens / 1000.0) * pricing["completion"],
        6,
    )


def record_token_usage(
    trace_id: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: float = 0.0,
    agent_module: str = "",
    user_id: str = "",
) -> None:
    """Record a single LLM call's token usage.

    Writes to the in-memory ring buffer. DB persistence is optional
    and handled separately to avoid blocking the request path.
    """
    total = prompt_tokens + completion_tokens
    cost = _compute_cost(model, prompt_tokens, completion_tokens)

    _token_buffer.append(
        (
            time.time(),
            trace_id,
            model,
            prompt_tokens,
            completion_tokens,
            total,
            cost,
            agent_module,
            user_id,
            latency_ms,
        )
    )

    logger.debug(
        "token_usage model=%s prompt=%d completion=%d cost=%.6f",
        model,
        prompt_tokens,
        completion_tokens,
        cost,
    )


def get_token_usage_summary() -> dict[str, Any]:
    """Get aggregate token usage stats from the ring buffer."""
    if not _token_buffer:
        return {
            "total_calls": 0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "tokens_per_hour": 0.0,
        }

    records = list(_token_buffer)
    total_calls = len(records)
    total_prompt = sum(r[3] for r in records)
    total_completion = sum(r[4] for r in records)
    total_tokens = sum(r[5] for r in records)
    total_cost = sum(r[6] for r in records)

    # Tokens per hour (based on last 1h of data)
    now = time.time()
    recent_1h = [r for r in records if now - r[0] < 3600]
    tokens_per_hour = sum(r[5] for r in recent_1h)

    return {
        "total_calls": total_calls,
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 4),
        "tokens_per_hour": tokens_per_hour,
    }


def get_token_usage_grouped(
    group_by: str = "model",
    hours: int = 24,
) -> list[dict[str, Any]]:
    """Get token usage grouped by a dimension.

    Args:
        group_by: "model" | "user" | "agent" | "hour"
        hours: lookback window in hours

    Returns:
        List of dicts with group_key, group_value, total_tokens, total_cost, call_count
    """
    if not _token_buffer:
        return []

    now = time.time()
    cutoff = now - (hours * 3600)
    records = [r for r in _token_buffer if r[0] >= cutoff]

    groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total_tokens": 0, "total_cost": 0.0, "call_count": 0}
    )

    for r in records:
        ts, _trace, model, _prompt, _completion, total, cost, agent, user, _lat = r

        if group_by == "model":
            key = model
        elif group_by == "user":
            key = user or "anonymous"
        elif group_by == "agent":
            key = agent or "router_agent"
        elif group_by == "hour":
            dt = datetime.fromtimestamp(ts, tz=UTC)
            key = dt.strftime("%Y-%m-%d %H:00")
        else:
            key = "unknown"

        groups[key]["total_tokens"] += total
        groups[key]["total_cost"] += cost
        groups[key]["call_count"] += 1

    result = []
    for key, vals in sorted(groups.items()):
        result.append(
            {
                "group_key": group_by,
                "group_value": key,
                "total_tokens": vals["total_tokens"],
                "total_cost": round(vals["total_cost"], 4),
                "call_count": vals["call_count"],
            }
        )

    return result


def get_cost_report(period: str = "daily") -> list[dict[str, Any]]:
    """Get cost report aggregated by time period.

    Args:
        period: "daily" | "weekly" | "monthly"

    Returns:
        List of {period_label, total_cost, total_tokens, call_count}
    """
    if not _token_buffer:
        return []

    now = time.time()
    if period == "weekly":
        cutoff = now - 7 * 24 * 3600
    elif period == "monthly":
        cutoff = now - 30 * 24 * 3600
    else:
        cutoff = now - 24 * 3600

    records = [r for r in _token_buffer if r[0] >= cutoff]

    groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total_cost": 0.0, "total_tokens": 0, "call_count": 0}
    )

    for r in records:
        ts = r[0]
        dt = datetime.fromtimestamp(ts, tz=UTC)

        if period == "weekly":
            # Group by ISO week
            key = f"{dt.isocalendar().year}-W{dt.isocalendar().week:02d}"
        elif period == "monthly":
            key = dt.strftime("%Y-%m")
        else:
            key = dt.strftime("%Y-%m-%d")

        groups[key]["total_cost"] += r[6]
        groups[key]["total_tokens"] += r[5]
        groups[key]["call_count"] += 1

    return [
        {
            "period_label": k,
            "total_cost": round(v["total_cost"], 4),
            "total_tokens": v["total_tokens"],
            "call_count": v["call_count"],
        }
        for k, v in sorted(groups.items())
    ]


def get_routing_distribution() -> list[dict[str, Any]]:
    """Get routing rule hit distribution (which models were selected)."""
    if not _token_buffer:
        return []

    records = list(_token_buffer)
    model_counts: dict[str, int] = defaultdict(int)
    for r in records:
        model_counts[r[2]] += 1

    total = len(records)
    return [
        {
            "model": model,
            "count": count,
            "percentage": round(count / total * 100, 1),
        }
        for model, count in sorted(model_counts.items(), key=lambda x: x[1], reverse=True)
    ]


def get_failover_events() -> list[dict[str, Any]]:
    """Get failover events (when a request was retried on a different model).

    Currently returns empty list — failover tracking requires
    router_agent to emit events. Phase 2 stub.
    """
    return []


def get_model_pricing() -> list[dict[str, Any]]:
    """Get the model pricing table."""
    return [
        {
            "model": model,
            "prompt_price_per_1k": pricing["prompt"],
            "completion_price_per_1k": pricing["completion"],
        }
        for model, pricing in sorted(_MODEL_PRICING.items())
    ]


def estimate_tokens(text: str) -> int:
    """Estimate token count from text (rough: 1 token ~= 4 chars for English, 2 chars for CJK)."""
    if not text:
        return 0
    # Simple heuristic: count CJK chars as 1 token each, other chars as 0.25 tokens
    cjk_count = sum(1 for c in text if ord(c) > 0x4E00)
    other_chars = len(text) - cjk_count
    return cjk_count + math.ceil(other_chars / 4)
