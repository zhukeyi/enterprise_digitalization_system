"""Customs data store (P1-C, C-4).

Provides:

* ``CustomsStore`` — SQLite persistence for ``TradeRecord`` and ``BuyerEntity``
  with query / trend / top-buyer accessors. Uses stdlib ``sqlite3`` wrapped in
  ``asyncio.to_thread`` (no new dependency; safe for the single-node host).
* ``BuyerVectorIndex`` — semantic-ish retrieval over buyer profiles. Supplies an
  in-memory bag-of-words index (zero-dependency, used in tests) and a Qdrant-backed
  index that lazily imports ``qdrant-client`` and reuses the existing Qdrant
  instance for buyer embedding search.

Storage growth must be monitored on the single-node host; ingest via offline ETL.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from agents.data_agent.customs_models import BuyerEntity, TradeRecord

__all__ = [
    "BuyerVectorIndex",
    "CustomsStore",
    "InMemoryBuyerVectorIndex",
    "QdrantBuyerVectorIndex",
]

# ══════════════════════════════════════════════════════════════════
# SQLite store
# ══════════════════════════════════════════════════════════════════

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trade_records (
    id TEXT PRIMARY KEY,
    hs_code TEXT,
    hs_description TEXT,
    reporter_country TEXT,
    partner_country TEXT,
    port TEXT,
    trade_flow TEXT,
    value_usd REAL,
    quantity REAL,
    quantity_unit TEXT,
    year INTEGER,
    period TEXT,
    tier TEXT,
    provider TEXT,
    collected_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tr_hs ON trade_records(hs_code);
CREATE INDEX IF NOT EXISTS idx_tr_country ON trade_records(reporter_country, partner_country);
CREATE INDEX IF NOT EXISTS idx_tr_port ON trade_records(port);
CREATE INDEX IF NOT EXISTS idx_tr_year ON trade_records(year);

CREATE TABLE IF NOT EXISTS buyers (
    id TEXT PRIMARY KEY,
    raw_name TEXT,
    normalized_name TEXT,
    country TEXT,
    source_country TEXT,
    import_count INTEGER DEFAULT 0,
    total_value_usd REAL DEFAULT 0.0,
    top_hs_codes TEXT,
    top_ports TEXT,
    first_seen TEXT,
    last_seen TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_buyer_norm ON buyers(normalized_name);
CREATE INDEX IF NOT EXISTS idx_buyer_country ON buyers(country);
"""


def _buyer_id(normalized_name: str, country: str | None) -> str:
    return f"{normalized_name}|{country or ''}"


def _sync_init(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


def _sync_upsert_trade(conn: sqlite3.Connection, records: list[TradeRecord]) -> int:
    rows = [
        (
            r.id,
            r.hs_code,
            r.hs_description,
            r.reporter_country,
            r.partner_country,
            r.port,
            r.trade_flow.value,
            r.value_usd,
            r.quantity,
            r.quantity_unit,
            r.year,
            r.period,
            r.tier.value,
            r.provider,
            r.collected_at.isoformat(),
        )
        for r in records
    ]
    conn.executemany(
        """
        INSERT INTO trade_records (
            id, hs_code, hs_description, reporter_country, partner_country, port,
            trade_flow, value_usd, quantity, quantity_unit, year, period, tier, provider,
            collected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            hs_description=excluded.hs_description,
            value_usd=excluded.value_usd,
            quantity=excluded.quantity,
            collected_at=excluded.collected_at
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def _sync_upsert_buyers(conn: sqlite3.Connection, buyers: list[BuyerEntity]) -> int:
    count = 0
    for b in buyers:
        bid = _buyer_id(b.normalized_name, b.country)
        existing = conn.execute(
            "SELECT import_count, total_value_usd, top_hs_codes, top_ports, first_seen, last_seen "
            "FROM buyers WHERE id = ?",
            (bid,),
        ).fetchone()
        if existing:
            import_count = existing[0] + b.import_count
            total_value = (existing[1] or 0.0) + b.total_value_usd
            hs_codes = _merge_top(existing[2], b.top_hs_codes)
            ports = _merge_top(existing[3], b.top_ports)
            first_seen = min(existing[4] or "", b.first_seen or "") or None
            last_seen = max(existing[5] or "", b.last_seen or "") or None
            conn.execute(
                """
                UPDATE buyers SET raw_name=?, normalized_name=?, country=?, source_country=?,
                    import_count=?, total_value_usd=?, top_hs_codes=?, top_ports=?,
                    first_seen=?, last_seen=?, updated_at=?
                WHERE id=?
                """,
                (
                    b.raw_name,
                    b.normalized_name,
                    b.country,
                    b.source_country,
                    import_count,
                    total_value,
                    json.dumps(hs_codes),
                    json.dumps(ports),
                    first_seen,
                    last_seen,
                    b.updated_at.isoformat(),
                    bid,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO buyers (
                    id, raw_name, normalized_name, country, source_country, import_count,
                    total_value_usd, top_hs_codes, top_ports, first_seen, last_seen, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bid,
                    b.raw_name,
                    b.normalized_name,
                    b.country,
                    b.source_country,
                    b.import_count,
                    b.total_value_usd,
                    json.dumps(b.top_hs_codes),
                    json.dumps(b.top_ports),
                    b.first_seen,
                    b.last_seen,
                    b.updated_at.isoformat(),
                ),
            )
        count += 1
    conn.commit()
    return count


def _merge_top(existing_json: str | None, incoming: list[str], top: int = 5) -> list[str]:
    """Merge and re-rank a stored top-N list with new entries (by frequency heuristic)."""
    merged: dict[str, int] = {}
    if existing_json:
        try:
            for item in json.loads(existing_json):
                merged[item] = merged.get(item, 0) + 1
        except (ValueError, TypeError):
            pass
    for item in incoming:
        merged[item] = merged.get(item, 0) + 1
    return sorted(merged, key=lambda k: merged[k], reverse=True)[:top]


def _sync_count(conn: sqlite3.Connection, table: str) -> int:
    cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
    return int(cur.fetchone()[0])


def _sync_search(conn: sqlite3.Connection, filters: dict[str, Any]) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if filters.get("hs_code"):
        clauses.append("hs_code LIKE ?")
        params.append(f"{filters['hs_code']}%")
    if filters.get("reporter_country"):
        clauses.append("reporter_country = ?")
        params.append(filters["reporter_country"])
    if filters.get("partner_country"):
        clauses.append("partner_country = ?")
        params.append(filters["partner_country"])
    if filters.get("port"):
        clauses.append("port = ?")
        params.append(filters["port"])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    limit = int(filters.get("limit", 50))
    cur = conn.execute(
        f"SELECT * FROM trade_records{where} ORDER BY year DESC LIMIT ?", [*params, limit]
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]


def _sync_trend(conn: sqlite3.Connection, hs_code: str, group_by: str) -> list[dict[str, Any]]:
    col = "year" if group_by == "year" else "period"
    rows = conn.execute(
        f"SELECT {col} AS bucket, SUM(value_usd) AS value, SUM(quantity) AS quantity, COUNT(*) AS records "
        "FROM trade_records WHERE hs_code LIKE ? GROUP BY bucket ORDER BY bucket",
        (f"{hs_code}%",),
    ).fetchall()
    return [{"bucket": r[0], "value_usd": r[1], "quantity": r[2], "records": r[3]} for r in rows]


def _sync_top_buyers(conn: sqlite3.Connection, country: str | None, limit: int) -> list[dict[str, Any]]:
    where = " WHERE country = ?" if country else ""
    params = [country] if country else []
    cur = conn.execute(
        f"SELECT * FROM buyers{where} ORDER BY total_value_usd DESC LIMIT ?",
        [*params, limit],
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]


class CustomsStore:
    """SQLite-backed store for customs trade records and buyer entities."""

    def __init__(self, db_path: str = ":memory:") -> None:
        """Initialize store.

        Args:
            db_path: SQLite path (``:memory:`` for tests; file path for production).
        """
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    async def init(self) -> None:
        """Create tables (idempotent)."""
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        await asyncio.to_thread(_sync_init, self._conn)

    async def upsert_trade_records(self, records: list[TradeRecord]) -> int:
        """Insert or update trade records. Returns number of rows written."""
        if self._conn is None:
            await self.init()
        assert self._conn is not None
        return await asyncio.to_thread(_sync_upsert_trade, self._conn, records)

    async def upsert_buyers(self, buyers: list[BuyerEntity]) -> int:
        """Insert or update buyer entities (aggregated). Returns rows written."""
        if self._conn is None:
            await self.init()
        assert self._conn is not None
        return await asyncio.to_thread(_sync_upsert_buyers, self._conn, buyers)

    async def search(
        self,
        *,
        hs_code: str | None = None,
        reporter_country: str | None = None,
        partner_country: str | None = None,
        port: str | None = None,
        limit: int = 50,
    ) -> list[TradeRecord]:
        """Query trade records by optional filters."""
        if self._conn is None:
            await self.init()
        assert self._conn is not None
        rows = await asyncio.to_thread(
            _sync_search,
            self._conn,
            {
                "hs_code": hs_code,
                "reporter_country": reporter_country,
                "partner_country": partner_country,
                "port": port,
                "limit": limit,
            },
        )
        return [_row_to_trade_record(r) for r in rows]

    async def trend(self, hs_code: str, group_by: str = "year") -> list[dict[str, Any]]:
        """Aggregate trade value/quantity over time for an HS code prefix."""
        if self._conn is None:
            await self.init()
        assert self._conn is not None
        return await asyncio.to_thread(_sync_trend, self._conn, hs_code, group_by)

    async def top_buyers(self, country: str | None = None, limit: int = 20) -> list[BuyerEntity]:
        """Return top buyer entities by footprint."""
        if self._conn is None:
            await self.init()
        assert self._conn is not None
        rows = await asyncio.to_thread(_sync_top_buyers, self._conn, country, limit)
        return [_row_to_buyer(r) for r in rows]

    async def count_trade_records(self) -> int:
        """Return total number of stored trade records."""
        if self._conn is None:
            await self.init()
        assert self._conn is not None
        return await asyncio.to_thread(_sync_count, self._conn, "trade_records")

    async def count_buyers(self) -> int:
        """Return total number of stored buyer entities."""
        if self._conn is None:
            await self.init()
        assert self._conn is not None
        return await asyncio.to_thread(_sync_count, self._conn, "buyers")

    async def close(self) -> None:
        """Close the underlying connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None


def _row_to_trade_record(r: dict[str, Any]) -> TradeRecord:
    from agents.data_agent.customs_models import DataSourceTier, TradeFlow

    return TradeRecord(
        id=r["id"],
        hs_code=r.get("hs_code", ""),
        hs_description=r.get("hs_description", ""),
        reporter_country=r.get("reporter_country", ""),
        partner_country=r.get("partner_country", ""),
        port=r.get("port", ""),
        trade_flow=TradeFlow(r.get("trade_flow", "import")),
        value_usd=float(r.get("value_usd", 0.0) or 0.0),
        quantity=r.get("quantity"),
        quantity_unit=r.get("quantity_unit"),
        year=int(r.get("year", 0) or 0),
        period=r.get("period", ""),
        tier=DataSourceTier(r.get("tier", "tier1")),
        provider=r.get("provider", ""),
    )


def _row_to_buyer(r: dict[str, Any]) -> BuyerEntity:
    from datetime import UTC, datetime

    def _parse(ts: Any) -> datetime:
        if not ts:
            return datetime.now(UTC)
        try:
            return datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            return datetime.now(UTC)

    return BuyerEntity(
        id=r["id"],
        raw_name=r.get("raw_name", ""),
        normalized_name=r.get("normalized_name", ""),
        country=r.get("country"),
        source_country=r.get("source_country"),
        import_count=int(r.get("import_count", 0) or 0),
        total_value_usd=float(r.get("total_value_usd", 0.0) or 0.0),
        top_hs_codes=json.loads(r["top_hs_codes"]) if r.get("top_hs_codes") else [],
        top_ports=json.loads(r["top_ports"]) if r.get("top_ports") else [],
        first_seen=r.get("first_seen"),
        last_seen=r.get("last_seen"),
        updated_at=_parse(r.get("updated_at")),
    )


# ── Process-wide singleton (backend FastAPI use) ──────────────────

_DEFAULT_CUSTOMS_DB = os.environ.get(
    "FDE_CUSTOMS_DB",
    str(Path(__file__).resolve().parent / "data" / "customs.db"),
)
_store_singleton: CustomsStore | None = None


async def get_customs_store() -> CustomsStore:
    """Return a process-wide file-backed ``CustomsStore`` singleton.

    Tests construct their own ``:memory:`` store and should not use this.
    """
    global _store_singleton
    if _store_singleton is None:
        db_path = _DEFAULT_CUSTOMS_DB
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        _store_singleton = CustomsStore(db_path=db_path)
        await _store_singleton.init()
    return _store_singleton


# ══════════════════════════════════════════════════════════════════
# Buyer vector index (semantic-ish retrieval)
# ══════════════════════════════════════════════════════════════════


def _tokenize(text: str) -> list[str]:
    return [t for t in re.split(r"\s+", text.lower()) if t]


class BuyerVectorIndex(ABC):
    """Abstract semantic-ish index over buyer profiles."""

    @abstractmethod
    def add(self, buyer: BuyerEntity) -> None:
        """Index a buyer entity."""

    @abstractmethod
    def search(self, query: str, top_k: int = 10) -> list[tuple[BuyerEntity, float]]:
        """Return top-k buyers ranked by similarity to ``query``."""


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in keys)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class InMemoryBuyerVectorIndex(BuyerVectorIndex):
    """Zero-dependency in-memory bag-of-words index (used in tests / small scales)."""

    def __init__(self) -> None:
        self._buyers: list[BuyerEntity] = []
        self._vectors: list[dict[str, float]] = []

    def add(self, buyer: BuyerEntity) -> None:
        tokens = _tokenize(f"{buyer.normalized_name} {' '.join(buyer.top_hs_codes)}")
        vec: dict[str, float] = {}
        for t in tokens:
            vec[t] = vec.get(t, 0.0) + 1.0
        self._buyers.append(buyer)
        self._vectors.append(vec)

    def search(self, query: str, top_k: int = 10) -> list[tuple[BuyerEntity, float]]:
        qvec = dict.fromkeys(_tokenize(query), 1.0)
        scored = [
            (b, _cosine(qvec, v)) for b, v in zip(self._buyers, self._vectors, strict=False)
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [(b, round(s, 4)) for b, s in scored[:top_k]]


class QdrantBuyerVectorIndex(BuyerVectorIndex):
    """Qdrant-backed buyer index reusing the existing Qdrant instance.

    Lazily imports ``qdrant-client`` and accepts a deterministic ``embed`` callable
    (default: hashing bag-of-words vector) so it works without a heavy ML model.
    """

    COLLECTION = "fde_customs_buyers"

    def __init__(
        self,
        client: Any | None = None,
        embed: Any | None = None,
        vector_size: int = 256,
    ) -> None:
        """Initialize.

        Args:
            client: A ``qdrant_client.QdrantClient`` (injected; created lazily otherwise).
            embed: Callable ``(BuyerEntity) -> list[float]`` (default: hashing vector).
            vector_size: Dimension of the embedding vector.
        """
        self._client = client
        self._embed = embed or self._default_embed
        self._vector_size = vector_size

    def _ensure_client(self) -> Any:
        if self._client is None:
            from qdrant_client import QdrantClient

            self._client = QdrantClient(url="http://localhost:6333")
        return self._client

    def _ensure_collection(self) -> None:
        client = self._ensure_client()
        from qdrant_client.models import Distance, VectorParams

        if not client.collection_exists(self.COLLECTION):
            client.create_collection(
                self.COLLECTION,
                vectors_config=VectorParams(size=self._vector_size, distance=Distance.COSINE),
            )

    @staticmethod
    def _default_embed(buyer: BuyerEntity) -> list[float]:
        """Deterministic hashing vector (falls back when no embedder is available)."""
        vec = [0.0] * 256
        tokens = _tokenize(f"{buyer.normalized_name} {' '.join(buyer.top_hs_codes)}")
        for t in tokens:
            h = hash(t) % 256
            vec[h] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def add(self, buyer: BuyerEntity) -> None:
        self._ensure_collection()
        client = self._ensure_client()
        from qdrant_client.models import PointStruct

        client.upsert(
            self.COLLECTION,
            points=[
                PointStruct(
                    id=abs(hash(buyer.normalized_name + str(buyer.country))),
                    vector=self._embed(buyer),
                    payload={
                        "raw_name": buyer.raw_name,
                        "normalized_name": buyer.normalized_name,
                        "country": buyer.country,
                        "top_hs_codes": buyer.top_hs_codes,
                    },
                )
            ],
        )

    def search(self, query: str, top_k: int = 10) -> list[tuple[BuyerEntity, float]]:
        # Query embedding requires an embedder; without one we cannot vectorize free text.
        raise NotImplementedError(
            "QdrantBuyerVectorIndex.search requires an embedder that maps free text to a vector. "
            "Inject a text embedder via the constructor for production use."
        )
