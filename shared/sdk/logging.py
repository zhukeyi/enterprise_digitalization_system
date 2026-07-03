"""Structured JSON logging for FDE AI Platform.

Integrates with Loki via JSON log format.
Usage:
    from shared.sdk.logging import setup_structured_logging
    setup_structured_logging()
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import UTC, datetime


class JSONFormatter(logging.Formatter):
    """JSON log formatter for Loki ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=UTC).isoformat()

        log_entry = {
            "timestamp": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Include extras from structured logging
        if hasattr(record, "trace_id"):
            log_entry["trace_id"] = record.trace_id  # type: ignore[attr-defined]
        if hasattr(record, "span_id"):
            log_entry["span_id"] = record.span_id  # type: ignore[attr-defined]
        if hasattr(record, "session_id"):
            log_entry["session_id"] = record.session_id  # type: ignore[attr-defined]
        if hasattr(record, "user_id"):
            log_entry["user_id"] = record.user_id  # type: ignore[attr-defined]

        # Include exception info
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = str(record.exc_info[1])

        return json.dumps(log_entry, default=str)


def setup_structured_logging(level: int | None = None) -> None:
    """Configure structured JSON logging for production.

    Args:
        level: Log level (default: INFO in production, DEBUG otherwise).
    """
    if level is None:
        level = logging.INFO if os.environ.get("FDE_ENV") == "production" else logging.DEBUG

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Quiet down noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


class StructuredLogger(logging.Logger):
    """Logger with structured context fields."""

    def __init__(self, name: str, level: int = logging.NOTSET) -> None:
        super().__init__(name, level)

    def with_context(self, **kwargs: str) -> None:
        """Add context fields to this logger's records."""
        for key, value in kwargs.items():
            setattr(self, key, value)

    def log_with(self, level: int, msg: str, **fields: str) -> None:
        """Log a message with additional structured fields."""
        extra = fields.copy()
        self.log(level, msg, extra=extra)