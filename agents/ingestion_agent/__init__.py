"""Ingestion Agent — shared data ingestion pipeline (local files + connectors).

P0 establishes the persisted schema (ORM models in `database/models.py`) and the
Alembic migration. The active pipeline (Excel/PDF normalization, connector
adapter, embedding fan-out) is implemented in later phases (P1 / P2a / P2b).
"""
