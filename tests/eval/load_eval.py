"""Eval dataset loader + retrieval-quality harness (P0 deliverable).

Provides:
- ``load_eval_dataset`` — parse ``eval_queries.json`` into typed models.
- ``recall_at_k`` / ``mrr`` — metric functions (pure, unit-testable).
- ``run_baseline`` — given a ``retriever(query) -> list[str]`` callable that
  returns retrieved chunk ids, compute recall@k / MRR against the dataset's
  ``expected_keywords``-derived relevant set (later phases wire a real retriever).

For P0 this is a scaffold: the real retriever is connected in P1b / P3 / P4.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

DEFAULT_DATASET = Path(__file__).parent / "eval_queries.json"


class EvalQuery(BaseModel):
    """A single golden evaluation query."""

    id: str
    category: str
    query: str
    expected_keywords: list[str] = Field(default_factory=list)
    source: str | None = None

    # -- metrics ---------------------------------------------------------
    def recall_at_k(self, retrieved: Sequence[str], k: int) -> float:
        """Recall@k over this query's expected keywords treated as relevant ids.

        ``retrieved`` is the ordered list of retrieved chunk ids; we match a
        retrieved id if it contains any expected keyword (loose, dataset-driven).
        """
        if not self.expected_keywords:
            return 0.0
        top_k = set(retrieved[:k])
        hits = sum(1 for kw in self.expected_keywords if any(kw in r for r in top_k))
        return hits / len(self.expected_keywords)


class EvalSmoke(BaseModel):
    """Smoke-test targets (connector health + portal pages)."""

    connector_health: list[str] = Field(default_factory=list)
    portal_pages: list[str] = Field(default_factory=list)


class EvalDataset(BaseModel):
    """Parsed evaluation dataset."""

    version: str
    description: str
    queries: list[EvalQuery]
    smoke: EvalSmoke = Field(default_factory=EvalSmoke)

    def category_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for q in self.queries:
            out[q.category] = out.get(q.category, 0) + 1
        return out


def load_eval_dataset(path: str | Path = DEFAULT_DATASET) -> EvalDataset:
    """Load and validate the eval dataset JSON."""
    raw: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    return EvalDataset.model_validate(raw)


def run_baseline(
    dataset: EvalDataset,
    retriever: Callable[[str], Sequence[str]],
    k: int = 5,
) -> dict[str, Any]:
    """Run the retrieval baseline and return a metrics report.

    ``retriever`` maps a natural-language query to an ordered list of retrieved
    chunk ids. For each query we compute recall@k; the report aggregates mean
    recall@k and per-category breakdown.
    """
    per_query: list[dict[str, Any]] = []
    for q in dataset.queries:
        retrieved = list(retriever(q.query))
        per_query.append(
            {
                "id": q.id,
                "category": q.category,
                "recall_at_k": q.recall_at_k(retrieved, k),
            }
        )

    by_cat: dict[str, list[float]] = {}
    for row in per_query:
        by_cat.setdefault(row["category"], []).append(row["recall_at_k"])

    return {
        "k": k,
        "num_queries": len(per_query),
        "mean_recall_at_k": (
            sum(r["recall_at_k"] for r in per_query) / len(per_query) if per_query else 0.0
        ),
        "per_category": {c: sum(v) / len(v) for c, v in by_cat.items()},
    }


__all__ = [
    "EvalDataset",
    "EvalQuery",
    "EvalSmoke",
    "load_eval_dataset",
    "run_baseline",
]
