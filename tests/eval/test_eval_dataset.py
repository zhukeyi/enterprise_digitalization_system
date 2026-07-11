"""Tests for the evaluation dataset scaffold (P0 deliverable)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.eval.load_eval import EvalQuery, load_eval_dataset, run_baseline

_DATASET = Path(__file__).parent / "eval_queries.json"


def test_dataset_loads_and_has_minimum_queries() -> None:
    ds = load_eval_dataset(_DATASET)
    assert ds.version == "1.0.0"
    assert len(ds.queries) >= 50, f"expected >=50 queries, got {len(ds.queries)}"


def test_every_query_has_required_fields() -> None:
    ds = load_eval_dataset(_DATASET)
    ids = set()
    for q in ds.queries:
        assert q.id and q.category and q.query
        assert q.id not in ids, f"duplicate query id: {q.id}"
        ids.add(q.id)


def test_categories_are_represented() -> None:
    ds = load_eval_dataset(_DATASET)
    cats = ds.category_counts()
    # We expect coverage across the major business domains.
    for expected in ("sales_order", "shipment", "hr", "finance", "analysis", "map_geo"):
        assert expected in cats and cats[expected] > 0


def test_smoke_targets_present() -> None:
    ds = load_eval_dataset(_DATASET)
    assert "logistics_yonyou" in ds.smoke.connector_health
    assert "/portal/map" in ds.smoke.portal_pages


def test_recall_at_k_is_zero_without_keywords() -> None:
    # A query with no expected keywords yields 0.0 (avoid divide-by-zero).
    q = EvalQuery(id="x", category="c", query="q")
    assert q.recall_at_k([], k=5) == 0.0


def test_recall_at_k_counts_keyword_hits() -> None:
    ds = load_eval_dataset(_DATASET)
    q = ds.queries[0]  # q01: keywords include "SO2026060001"
    # retrieved chunk ids that contain the expected keywords
    retrieved = [f"chunk_{kw}" for kw in q.expected_keywords]
    score = q.recall_at_k(retrieved, k=5)
    assert score == 1.0


def test_run_baseline_aggregates_mean_recall() -> None:
    ds = load_eval_dataset(_DATASET)

    def fake_retriever(query: str) -> list[str]:
        # perfect retriever: returns a chunk containing every keyword of the
        # matching query (we cheat by scanning all queries for the query text).
        for q in ds.queries:
            if q.query == query:
                return [f"chunk_{kw}" for kw in q.expected_keywords]
        return []

    report = run_baseline(ds, fake_retriever, k=5)
    assert report["num_queries"] == len(ds.queries)
    assert report["mean_recall_at_k"] == 1.0
    assert set(report["per_category"].keys()) == set(ds.category_counts().keys())


@pytest.mark.parametrize("k", [1, 3, 5, 10])
def test_recall_at_k_respects_k(k: int) -> None:
    ds = load_eval_dataset(_DATASET)
    q = ds.queries[0]
    # Only the first keyword is "retrieved"; with k=1 recall should be 1/N.
    retrieved = [f"chunk_{q.expected_keywords[0]}"]
    score = q.recall_at_k(retrieved, k=k)
    assert score == 1 / len(q.expected_keywords)
