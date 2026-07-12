"""Alerting & Drift Detection (Phase 4).

Evaluates platform-health alert rules against live in-memory metrics
(trace stats, token cost, budget state) and detects metric drift by
comparing a rolling baseline window to the current snapshot.

This is the lightweight, single-instance alerting layer that complements
the Prometheus alert rules shipped under deploy/prometheus/. The app-side
engine is useful when Prometheus is not yet wired to scrape the instance.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("fde.observability.alerting")

# ── Default alert rules ──────────────────────────────────────────
# metric: error_rate | p95_ms | daily_cost_usd | budget_exceeded
# operator: gt | gte | lt | lte
_DEFAULT_RULES: dict[str, dict[str, Any]] = {
    "error_rate_high": {
        "metric": "error_rate",
        "operator": "gt",
        "threshold": 0.10,
        "severity": "warning",
        "enabled": True,
        "description": "Trace error rate exceeded 10%",
    },
    "latency_p95_high": {
        "metric": "p95_ms",
        "operator": "gt",
        "threshold": 2000.0,
        "severity": "warning",
        "enabled": True,
        "description": "P95 latency exceeded 2000 ms",
    },
    "daily_cost_spike": {
        "metric": "daily_cost_usd",
        "operator": "gt",
        "threshold": 5.0,
        "severity": "info",
        "enabled": True,
        "description": "Daily token spend exceeded $5",
    },
    "budget_exceeded": {
        "metric": "budget_exceeded",
        "operator": "gt",
        "threshold": 0,
        "severity": "critical",
        "enabled": True,
        "description": "One or more agent budgets exceeded",
    },
}

_alert_rules: dict[str, dict[str, Any]] = {k: dict(v) for k, v in _DEFAULT_RULES.items()}

# Fired alerts (ring buffer)
_alerts: deque[dict[str, Any]] = deque(maxlen=1000)

# Rolling baseline snapshots for drift detection
_BASELINE: deque[dict[str, Any]] = deque(maxlen=120)
_BASELINE_WINDOW = 30  # use last N snapshots as baseline

# Suppress duplicate alerts within this window (seconds)
_SUPPRESS_SECONDS = 300


def _cmp(value: float, operator: str, threshold: float) -> bool:
    if operator == "gt":
        return value > threshold
    if operator == "gte":
        return value >= threshold
    if operator == "lt":
        return value < threshold
    if operator == "lte":
        return value <= threshold
    return False


def get_alert_rules() -> list[dict[str, Any]]:
    """Return all configured alert rules."""
    return [{"id": rid, **rule} for rid, rule in _alert_rules.items()]


def set_alert_rule(
    rule_id: str,
    metric: str,
    operator: str,
    threshold: float,
    severity: str = "warning",
    enabled: bool = True,
    description: str = "",
) -> dict[str, Any]:
    """Create or update an alert rule."""
    _alert_rules[rule_id] = {
        "metric": metric,
        "operator": operator,
        "threshold": threshold,
        "severity": severity,
        "enabled": enabled,
        "description": description or f"{metric} {operator} {threshold}",
    }
    return {"id": rule_id, **_alert_rules[rule_id]}


def delete_alert_rule(rule_id: str) -> bool:
    """Delete an alert rule. Returns True if it existed."""
    return _alert_rules.pop(rule_id, None) is not None


def get_alerts(page: int = 1, page_size: int = 50, severity: str | None = None) -> dict[str, Any]:
    """Return fired alerts (newest first)."""
    items = sorted(_alerts, key=lambda a: a["ts_epoch"], reverse=True)
    if severity:
        items = [a for a in items if a["severity"] == severity]
    total = len(items)
    start_idx = (page - 1) * page_size
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
        "data": items[start_idx : start_idx + page_size],
    }


def _current_metrics() -> dict[str, Any]:
    """Gather the current metric snapshot from live stores."""
    from agents.observability_agent.token_tracker import get_cost_report
    from agents.observability_agent.trace_store import get_trace_stats

    stats = get_trace_stats()
    cost = get_cost_report("daily")
    daily_cost = 0.0
    if isinstance(cost, list):
        daily_cost = sum(c.get("total_cost", 0.0) for c in cost)
    elif isinstance(cost, dict):
        daily_cost = float(cost.get("total_cost", 0.0))

    # Budget exceeded flag
    budget_exceeded = 0
    try:
        from agents.observability_agent.budget import get_budget

        budgets = get_budget()
        for b in budgets.get("budgets", []):
            if b.get("status") == "exceeded":
                budget_exceeded = 1
                break
    except Exception:
        pass

    return {
        "error_rate": float(stats.get("error_rate", 0.0)),
        "p95_ms": float(stats.get("p95_ms", 0.0)),
        "daily_cost_usd": float(daily_cost),
        "budget_exceeded": float(budget_exceeded),
        "total_spans": int(stats.get("total_spans", 0)),
    }


def evaluate_alerts() -> dict[str, Any]:
    """Evaluate all enabled rules against current metrics.

    Returns a dict with the snapshot, triggered rules, active alerts,
    and a drift report. Records newly-fired alerts (with suppression).
    """
    metrics = _current_metrics()

    # Push baseline snapshot
    snapshot = {"ts_epoch": time.time(), **metrics}
    _BASELINE.append(snapshot)

    triggered = []
    now = time.time()
    for rid, rule in _alert_rules.items():
        if not rule.get("enabled", True):
            continue
        value = metrics.get(rule["metric"], 0.0)
        if _cmp(float(value), rule["operator"], float(rule["threshold"])):
            triggered.append({
                "rule_id": rid,
                "metric": rule["metric"],
                "value": value,
                "threshold": rule["threshold"],
                "severity": rule["severity"],
                "description": rule.get("description", ""),
            })
            # Record alert (suppress duplicates)
            _record_alert(rid, rule, value, now)

    drift = _compute_drift()

    return {
        "evaluated_at": datetime.now(UTC).isoformat(),
        "metrics": metrics,
        "triggered": triggered,
        "active_alerts": get_alerts(page_size=10)["data"],
        "drift": drift,
    }


def _record_alert(rule_id: str, rule: dict[str, Any], value: float, now: float) -> None:
    """Record an alert, suppressing duplicates within the window."""
    for a in _alerts:
        if a["rule_id"] == rule_id and (now - a["ts_epoch"]) < _SUPPRESS_SECONDS:
            return
    _alerts.append({
        "alert_id": f"{rule_id}-{int(now)}",
        "rule_id": rule_id,
        "severity": rule["severity"],
        "metric": rule["metric"],
        "value": value,
        "threshold": rule["threshold"],
        "message": rule.get("description", ""),
        "timestamp": datetime.now(UTC).isoformat(),
        "ts_epoch": now,
    })


def _compute_drift() -> dict[str, Any]:
    """Compare the latest snapshot to the baseline window mean."""
    if len(_BASELINE) < _BASELINE_WINDOW + 1:
        return {"status": "insufficient_data", "metrics": {}}

    recent = list(_BASELINE)[-_BASELINE_WINDOW:]
    baseline = list(_BASELINE)[: -_BASELINE_WINDOW]
    if not baseline:
        baseline = recent[:-1] or recent

    latest = _BASELINE[-1]
    result: dict[str, Any] = {"status": "ok", "metrics": {}}
    drift_flags = []

    for metric in ("error_rate", "p95_ms", "daily_cost_usd"):
        base_vals = [s.get(metric, 0.0) for s in baseline]
        base_mean = sum(base_vals) / max(len(base_vals), 1)
        cur = latest.get(metric, 0.0)
        if base_mean > 0:
            pct_change = (cur - base_mean) / base_mean * 100.0
        else:
            pct_change = 0.0 if cur == 0 else 100.0
        result["metrics"][metric] = {
            "baseline_mean": round(base_mean, 4),
            "current": round(cur, 4),
            "pct_change": round(pct_change, 2),
        }
        # Flag drift if more than 50% change AND absolute move is meaningful
        if abs(pct_change) >= 50.0 and abs(cur - base_mean) >= 0.01:
            drift_flags.append(metric)

    if drift_flags:
        result["status"] = "drift_detected"
        result["drifted_metrics"] = drift_flags

    return result


def get_drift_report() -> dict[str, Any]:
    """Return the current drift report (standalone endpoint)."""
    return _compute_drift()
