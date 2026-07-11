"""FTS5 全文索引（P3b：Postgres GIN(JSONB) 的 SQLite 等价实现）。

计划 P3b 要求「Postgres GIN(JSONB)」索引归一文档以支持**词法召回**；部署用
SQLite，故以 FTS5 虚拟表等价实现，并提供与方言无关的索引 / 查询封装：

* 生产（SQLite）：``canonical_fts`` 虚拟表（FTS5）+ **LIKE 兜底**（CJK 无空格，
  FTS5 默认 ``unicode61`` 逐字分词，短语查询过严，故对 CJK 子串用 LIKE 召回，
  保证中文词法召回真正可用）。
* Postgres：本模块 no-op（GIN 索引由迁移负责，超出本次范围），仅保留接口兼容。

所有函数对「表不存在 / 方言不支持」均**不抛错**，调用方（pipeline）可安全忽略，
不会因 FTS 故障阻断入库主链路。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

logger = logging.getLogger("fde.fts")

FTS_TABLE = "canonical_fts"

# 与 reranker.tokenize 保持一致：CJK 逐字 / ASCII 按词。
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text or "")


def _fts_text_from_canonical(orm: Any) -> str:
    """渲染一条 CanonicalDocument 的可检索文本（标题 + 字段值）。"""
    parts = [orm.title or ""]
    payload = orm.canonical_payload
    if isinstance(payload, dict):
        for v in payload.values():
            if isinstance(v, (str, int, float, bool)):
                parts.append(str(v))
    return " ".join(parts).strip()


def _is_sqlite(obj: Any) -> bool:
    dialect = getattr(getattr(obj, "bind", None), "dialect", None)
    if dialect is None:
        dialect = getattr(obj, "dialect", None)
    return getattr(dialect, "name", "sqlite") == "sqlite"


async def ensure_fts_table(engine: AsyncEngine) -> None:
    """创建 FTS5 虚拟表（若不存在）。非 SQLite 方言跳过（由 GIN 负责）。"""
    if engine.dialect.name != "sqlite":
        return
    async with engine.begin() as conn:
        await conn.execute(
            text(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE} "
                f"USING fts5(canonical_document_id UNINDEXED, title, content, raw_document_id UNINDEXED)"
            )
        )


async def index_canonical(
    session: AsyncSession,
    orm: Any,
    *,
    raw_document_id: str | None = None,
) -> None:
    """把一条 CanonicalDocument 写入（或更新）FTS 索引。

    非 SQLite 方言或表缺失时静默跳过（不阻断主链路）。
    """
    if not _is_sqlite(session):
        return
    text_content = _fts_text_from_canonical(orm)
    rid = raw_document_id
    if rid is None and hasattr(orm, "raw_document_id"):
        rid = orm.raw_document_id
    try:
        await session.execute(
            text(f"DELETE FROM {FTS_TABLE} WHERE canonical_document_id = :cid"),
            {"cid": orm.id},
        )
        await session.execute(
            text(
                f"INSERT INTO {FTS_TABLE}"
                f"(canonical_document_id, title, content, raw_document_id) "
                f"VALUES (:cid, :title, :content, :rid)"
            ),
            {
                "cid": orm.id,
                "title": orm.title or "",
                "content": text_content,
                "rid": rid,
            },
        )
    except Exception as exc:  # 表缺失等：不阻断入库
        logger.debug("FTS index skipped for %s: %s", orm.id, exc)


async def fts_lexical_search(
    session: AsyncSession,
    query: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """词法召回：ASCII 词走 FTS5 MATCH（精确），CJK / 子串走 LIKE 兜底。

    返回去重、按分数降序的结果列表：``{canonical_document_id, raw_document_id,
    title, score}``。非 SQLite 方言返回空列表。
    """
    if not _is_sqlite(session) or not query or not query.strip():
        return []

    merged: dict[str, dict[str, Any]] = {}

    # 1) ASCII 词走 FTS5 MATCH（AND 召回，分数来自 rank）
    ascii_tokens = [t for t in _tokenize(query) if re.search(r"[A-Za-z0-9]", t)]
    if ascii_tokens:
        match_q = " ".join(ascii_tokens)
        try:
            rows = await session.execute(
                text(
                    f"SELECT canonical_document_id, raw_document_id, title, rank "
                    f"FROM {FTS_TABLE} WHERE {FTS_TABLE} MATCH :q ORDER BY rank LIMIT :lim"
                ),
                {"q": match_q, "lim": limit},
            )
            for r in rows:
                cid = r[0]
                # FTS5 rank 为负（越大越好），转成正分
                score = -float(r[3]) if r[3] is not None else 0.0
                merged[cid] = {
                    "canonical_document_id": cid,
                    "raw_document_id": r[1],
                    "title": r[2],
                    "score": score,
                }
        except Exception as exc:
            logger.debug("FTS MATCH fallback failed: %s", exc)

    # 2) LIKE 兜底（覆盖 CJK 子串，如「杭州」）
    like_q = f"%{query.strip()}%"
    try:
        rows = await session.execute(
            text(
                f"SELECT canonical_document_id, raw_document_id, title "
                f"FROM {FTS_TABLE} WHERE content LIKE :q OR title LIKE :q LIMIT :lim"
            ),
            {"q": like_q, "lim": limit},
        )
        for r in rows:
            cid = r[0]
            if cid not in merged:
                merged[cid] = {
                    "canonical_document_id": cid,
                    "raw_document_id": r[1],
                    "title": r[2],
                    "score": 0.5,
                }
    except Exception as exc:
        logger.debug("FTS LIKE fallback failed: %s", exc)

    return sorted(merged.values(), key=lambda x: x["score"], reverse=True)[:limit]


__all__ = [
    "FTS_TABLE",
    "ensure_fts_table",
    "fts_lexical_search",
    "index_canonical",
]
