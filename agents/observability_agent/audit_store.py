"""Audit Trail — immutable, queryable audit log (Phase 4).

Provides an in-memory ring buffer of audit events with structured
query + CSV export. Mirrors the project-wide "single-instance,
in-memory storage" pattern used by the trace/metric stores.

Audit events are recorded for every security- and data-relevant
mutation: API key lifecycle, RAG document deletion/reindex, budget
changes, and explicit admin actions.
"""

from __future__ import annotations

import csv
import io
import logging
import time
import uuid
from collections import deque
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("fde.observability.audit")

# Ring buffer (single-instance deployment)
_audit_events: deque[dict[str, Any]] = deque(maxlen=50000)

# CSV column order for export
_EXPORT_COLUMNS = [
    "event_id",
    "timestamp",
    "actor",
    "action",
    "resource_type",
    "resource_id",
    "status",
    "detail",
    "ip",
    "trace_id",
]


def record_audit_event(
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str = "",
    status: str = "ok",
    detail: str = "",
    ip: str = "",
    trace_id: str = "",
) -> dict[str, Any]:
    """Record a single audit event.

    Returns the stored event dict (with generated event_id + timestamp).
    """
    event = {
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "ts_epoch": time.time(),
        "actor": actor or "system",
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id or "",
        "status": status,
        "detail": detail or "",
        "ip": ip or "",
        "trace_id": trace_id or "",
    }
    _audit_events.append(event)
    logger.info("audit %s %s/%s by %s", action, resource_type, resource_id, actor)
    return event


def get_audit_logs(
    page: int = 1,
    page_size: int = 20,
    actor: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    status: str | None = None,
    since: str | None = None,
) -> dict[str, Any]:
    """Query audit events with optional filters (newest first)."""
    since_ts = 0.0
    if since:
        try:
            since_ts = datetime.fromisoformat(since.replace("Z", "+00:00")).timestamp()
        except (ValueError, TypeError):
            since_ts = 0.0

    filtered = list(_audit_events)
    # newest first
    filtered.reverse()

    if actor:
        filtered = [e for e in filtered if e["actor"] == actor]
    if action:
        filtered = [e for e in filtered if e["action"] == action]
    if resource_type:
        filtered = [e for e in filtered if e["resource_type"] == resource_type]
    if status:
        filtered = [e for e in filtered if e["status"] == status]
    if since_ts:
        filtered = [e for e in filtered if e.get("ts_epoch", 0) >= since_ts]

    total = len(filtered)
    start_idx = (page - 1) * page_size
    page_items = filtered[start_idx : start_idx + page_size]

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
        "data": page_items,
    }


def export_audit_logs(
    format: str = "csv",
    actor: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    status: str | None = None,
) -> str:
    """Export audit events as CSV (only format supported currently)."""
    events = get_audit_logs(
        page=1,
        page_size=10**9,
        actor=actor,
        action=action,
        resource_type=resource_type,
        status=status,
    )["data"]

    if format != "csv":
        raise ValueError(f"Unsupported export format: {format}")

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for e in events:
        writer.writerow(e)
    return buf.getvalue()


def clear_audit_logs() -> int:
    """Clear all audit events (admin operation — returns count removed)."""
    count = len(_audit_events)
    _audit_events.clear()
    return count
