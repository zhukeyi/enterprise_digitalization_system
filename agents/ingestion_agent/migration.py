"""P3b/P6a 启动迁移：幂等 ALTER + FTS5 虚拟表 + ingest_tasks 创建。

``governance_agent.database.session.init_database()`` 仅 ``create_all``（**不**
ALTER），因此已部署的 SQLite 库缺少后续新增列/表。本模块在启动时补齐。

所有操作均**幂等**（先查列 / 表是否存在，再决定是否 ALTER / CREATE）。
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from agents.ingestion_agent.fts import ensure_fts_table

logger = logging.getLogger("fde.migration")


async def migrate_schema(engine: AsyncEngine) -> None:
    """执行 P3b schema 迁移（幂等）。应在 ``init_database()`` 之后调用。"""
    dialect = engine.dialect.name
    if dialect == "sqlite":
        async with engine.begin() as conn:
            await _add_column_sqlite(conn, "raw_documents", "content_hash", "VARCHAR(64)")
            await _add_column_sqlite(conn, "raw_documents", "storage_ref", "VARCHAR(512)")
    else:
        # Postgres 路径（生产未启用，留作兼容）：ALTER + 可选 GIN 索引。
        async with engine.begin() as conn:
            await _add_column_postgres(conn, "raw_documents", "content_hash", "VARCHAR(64)")
            await _add_column_postgres(conn, "raw_documents", "storage_ref", "VARCHAR(512)")

    await ensure_fts_table(engine)
    # P6a: create ingest_tasks table (if not exists)
    await _ensure_table(engine, "ingest_tasks")
    logger.info("P3b/P6a schema migration applied (dialect=%s)", dialect)


async def _add_column_sqlite(conn, table: str, column: str, col_type: str) -> None:
    res = await conn.execute(text(f"PRAGMA table_info({table})"))
    names = {row[1] for row in res.fetchall()}
    if column not in names:
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
        logger.info("ALTER %s ADD %s %s", table, column, col_type)


async def _add_column_postgres(conn, table: str, column: str, col_type: str) -> None:
    res = await conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    )
    if res.first() is None:
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
        logger.info("ALTER %s ADD %s %s", table, column, col_type)


async def _ensure_table(engine: AsyncEngine, table_name: str) -> None:
    """Idempotent table creation for non-ORM-managed tables."""
    dialect = engine.dialect.name
    if dialect == "sqlite":
        async with engine.begin() as conn:
            res = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
                {"t": table_name},
            )
            if res.first() is None:
                await conn.execute(
                    text(
                        """CREATE TABLE ingest_tasks (
                            id VARCHAR(36) PRIMARY KEY,
                            status VARCHAR(20) NOT NULL DEFAULT 'pending',
                            filename VARCHAR(512) NOT NULL,
                            file_hash VARCHAR(128),
                            doc_type VARCHAR(128) NOT NULL,
                            content_type VARCHAR(128),
                            progress_pct INTEGER DEFAULT 0,
                            total_chunks INTEGER DEFAULT 0,
                            indexed_chunks INTEGER DEFAULT 0,
                            canonical_count INTEGER DEFAULT 0,
                            result JSON,
                            error_message TEXT,
                            raw_id VARCHAR(36),
                            storage_ref VARCHAR(512),
                            created_at DATETIME NOT NULL DEFAULT (datetime('now')),
                            updated_at DATETIME NOT NULL DEFAULT (datetime('now'))
                        )"""
                    )
                )
                await conn.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_ingest_tasks_status ON ingest_tasks(status)")
                )
                await conn.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_ingest_tasks_file_hash ON ingest_tasks(file_hash)")
                )
                logger.info("Created table %s", table_name)


__all__ = ["migrate_schema"]
