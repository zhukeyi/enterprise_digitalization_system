"""FDE Platform — unified observability SDK adaptation layer.

All agents MUST use this module instead of directly depending
on Langfuse / Braintrust / OpenTelemetry SDKs.

This ensures:
- Consistent Trace ID propagation across all modules
- Easy swap of observability backends
- PII auto-masking before data leaves the VPC
"""

from __future__ import annotations

from shared.sdk.backends import (
    _log_trace,
    _registered_backends,
    get_backend,
    register_backend,
)
from shared.sdk.decorators import traced
from shared.sdk.trace import TraceContext, get_trace_id, sanitize_pii

__all__ = [
    "TraceContext",
    "_log_trace",
    "_registered_backends",
    "get_backend",
    "get_trace_id",
    "register_backend",
    "sanitize_pii",
    "traced",
]
