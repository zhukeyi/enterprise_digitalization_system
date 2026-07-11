"""Shared cross-repository contracts (connector / ingestion / portal).

These models are the single source of truth for the wire format exchanged
between the FDE platform and external Java connectors (e.g. logistics_agent).
They are intentionally dependency-light (Pydantic only) so both the Python
backend and external repos can import them without pulling the whole project.
"""
