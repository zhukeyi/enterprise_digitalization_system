"""P3b 启动迁移：幂等 ALTER + FTS5 虚拟表创建（向后兼容旧库升级）。

``governance_agent.database.session.init_database()`` 仅 ``create_all``（**不**
ALTER），因此已部署的 SQLite 库缺少 P3b 新增列。本模块在启动时补齐
``raw_documents.content_hash / storage_ref`` 并创建 ``canonical_fts``，保证旧库
升级不丢数据、新库也能正常建表。

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
    logger.info("P3b schema migration applied (dialect=%s)", dialect)


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


__all__ = ["migrate_schema"]
