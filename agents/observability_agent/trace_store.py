"""Trace Viewer — in-memory trace span store and query.

Stores trace spans emitted by the @traced decorator and LLM calls.
Provides query + stats endpoints for the observability portal.

In-memory ring buffer (single-instance deployment). For multi-instance,
replace with a trace backend (Tempo/Jaeger/OTel collector).
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("fde.observability.traces")

# Ring buffer for trace spans
# Each entry: TraceSpan-like dict
_trace_spans: list[dict[str, Any]] = []
_max_spans = 20000


def record_span(
    trace_id: str,
    span_id: str,
    name: str,
    start_time: float,
    end_time: float | None = None,
    status: str = "ok",
    span_type: str = "http",
    attributes: dict[str, Any] | None = None,
    parent_span_id: str = "",
) -> None:
    """Record a trace span."""
    global _trace_spans
    duration_ms = ((end_time or time.time()) - start_time) * 1000
    _trace_spans.append(
        {
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "name": name,
            "start_time": start_time,
            "end_time": end_time or time.time(),
            "duration_ms": round(duration_ms, 2),
            "status": status,
            "span_type": span_type,
            "attributes": attributes or {},
        }
    )
    if len(_trace_spans) > _max_spans:
        _trace_spans = _trace_spans[-_max_spans:]


def get_traces(
    page: int = 1,
    page_size: int = 20,
    service: str | None = None,
    status: str | None = None,
    min_duration_ms: float | None = None,
) -> dict[str, Any]:
    """Get paginated trace list (one entry per trace_id)."""
    # Group spans by trace_id
    traces: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for span in _trace_spans:
        if status and span["status"] != status:
            continue
        if min_duration_ms is not None and span["duration_ms"] < min_duration_ms:
            continue
        traces[span["trace_id"]].append(span)

    # Build trace summaries
    summaries = []
    for trace_id, spans in traces.items():
        total_duration = max(s["duration_ms"] for s in spans)
        trace_status = "error" if any(s["status"] == "error" for s in spans) else "ok"
        root = next((s for s in spans if not s["parent_span_id"]), spans[0])
        summaries.append(
            {
                "trace_id": trace_id,
                "root_name": root["name"],
                "span_count": len(spans),
                "total_duration_ms": round(total_duration, 2),
                "status": trace_status,
                "start_time": datetime.fromtimestamp(root["start_time"], tz=UTC).isoformat(),
            }
        )

    # Sort by start_time desc
    summaries.sort(key=lambda x: x["start_time"], reverse=True)
    total = len(summaries)
    start_idx = (page - 1) * page_size
    page_items = summaries[start_idx : start_idx + page_size]

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
        "data": page_items,
    }


def get_trace_tree(trace_id: str) -> dict[str, Any] | None:
    """Get full span tree for a single trace."""
    spans = [s for s in _trace_spans if s["trace_id"] == trace_id]
    if not spans:
        return None

    total_duration = max(s["duration_ms"] for s in spans)
    trace_status = "error" if any(s["status"] == "error" for s in spans) else "ok"

    return {
        "trace_id": trace_id,
        "spans": spans,
        "total_duration_ms": round(total_duration, 2),
        "span_count": len(spans),
        "status": trace_status,
    }


def get_trace_stats() -> dict[str, Any]:
    """Get trace statistics: P50/P95/P99 + error rate + hot paths."""
    if not _trace_spans:
        return {
            "total_spans": 0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "error_rate": 0.0,
            "hot_paths": [],
        }

    durations = sorted(s["duration_ms"] for s in _trace_spans)
    n = len(durations)

    def _pct(p: float) -> float:
        if n == 1:
            return durations[0]
        idx = min(n - 1, int(p * n))
        return durations[idx]

    errors = sum(1 for s in _trace_spans if s["status"] == "error")

    # Hot paths (by name, sorted by avg duration)
    by_name: dict[str, list[float]] = defaultdict(list)
    for s in _trace_spans:
        by_name[s["name"]].append(s["duration_ms"])

    hot_paths = [
        {
            "name": name,
            "avg_ms": round(sum(durs) / len(durs), 2),
            "count": len(durs),
            "max_ms": round(max(durs), 2),
        }
        for name, durs in sorted(by_name.items(), key=lambda x: sum(x[1]) / len(x[1]), reverse=True)[:10]
    ]

    return {
        "total_spans": n,
        "p50_ms": round(_pct(0.5), 2),
        "p95_ms": round(_pct(0.95), 2),
        "p99_ms": round(_pct(0.99), 2),
        "error_rate": round(errors / n, 4),
        "hot_paths": hot_paths,
    }


def get_span_types() -> dict[str, int]:
    """Count spans by type."""
    counts: dict[str, int] = defaultdict(int)
    for s in _trace_spans:
        counts[s["span_type"]] += 1
    return dict(counts)
