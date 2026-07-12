"""Tests for the marketing_agent engine (GEO / ads / content / analytics)."""

from __future__ import annotations

from agents.marketing_agent.ads import ABTester, BudgetAllocator, VariantGenerator
from agents.marketing_agent.analytics import PerformanceTracker, ROIPredictor
from agents.marketing_agent.content import GEOWriter, MultilingualWriter, SEOWriter
from agents.marketing_agent.data_connector import get_connector
from agents.marketing_agent.geo import ContentOptimizer, KeywordStrategy, VisibilityTracker
from agents.marketing_agent.models import PlatformPerformance


def _brand():
    return get_connector().get_brands()[0]


# ── GEO visibility ───────────────────────────────────────────────


def test_visibility_tracker_runs():
    b = _brand()
    bv = VisibilityTracker().track(b.brand_id)
    assert 0 <= bv.geo_index <= 100
    assert len(bv.engines) == 5
    assert bv.cited_keywords <= bv.total_keywords


def test_stronger_brand_more_visible():
    brands = get_connector().get_brands()
    weak = min(brands, key=lambda x: x.strength)
    strong = max(brands, key=lambda x: x.strength)
    sv = VisibilityTracker().track(strong.brand_id).geo_index
    wv = VisibilityTracker().track(weak.brand_id).geo_index
    assert sv >= wv


# ── Keyword strategy ─────────────────────────────────────────────


def test_keyword_opportunity_in_range():
    b = _brand()
    plan = KeywordStrategy().plan(b.brand_id, top_n=20)
    assert plan
    for k in plan:
        assert 0 <= k["opportunity_score"] <= 100
    # sorted descending
    scores = [k["opportunity_score"] for k in plan]
    assert scores == sorted(scores, reverse=True)


# ── Content optimizer ────────────────────────────────────────────


def test_content_score_better_with_numbers_and_citations():
    bad = ContentOptimizer().score("标题", "一些泛泛的描述，没有数据。")
    good = ContentOptimizer().score(
        "指南", "我们实测提效 3 倍，引用 2026 行业基准报告，数据经第三方审计。"
    )
    assert good.eeat_score > bad.eeat_score
    assert good.citation_score > bad.citation_score
    assert good.suggestions  # always returns at least one suggestion


# ── GEO / SEO writer ─────────────────────────────────────────────


def test_geo_writer_produces_citable_content():
    piece = GEOWriter().write("云栖智能", "企业AI平台")
    assert piece.geo_optimized is True
    assert piece.citation_score >= 70
    assert "引用" in piece.body or "据" in piece.body


def test_seo_writer_outline():
    piece = SEOWriter().write("企业AI平台", "云栖智能")
    assert "##" in piece.body
    assert piece.geo_optimized is False


# ── Ads ──────────────────────────────────────────────────────────


def test_variant_generator_count_and_quality():
    variants = VariantGenerator().generate("云栖智能", "企业AI平台", n=5)
    assert len(variants) == 5
    for v in variants:
        assert 0 <= v.quality_score <= 100
        assert 0 < v.predicted_ctr < 0.2
    # sorted by quality desc
    qs = [v.quality_score for v in variants]
    assert qs == sorted(qs, reverse=True)


def test_ab_test_detects_winner():
    r = ABTester().compare("A", "B", 10000, 300, 10000, 420)
    assert r.significant is True
    assert r.winner == "B"
    assert r.lift_pct > 0
    assert r.p_value < 0.05


def test_ab_test_no_winner_when_close():
    r = ABTester().compare("A", "B", 1000, 30, 1000, 31)
    assert r.significant is False
    assert r.winner is None


def test_budget_allocator_beats_even_split():
    b = _brand()
    plats = get_connector().get_platforms(b.brand_id)
    alloc = BudgetAllocator().allocate(plats, 100000.0)
    assert alloc["uplift_pct"] >= 0
    total = sum(a["allocated_budget"] for a in alloc["allocations"])
    assert abs(total - 100000.0) < 1.0
    # higher ROAS platform gets more budget
    by_roas = sorted(alloc["allocations"], key=lambda a: a["current_roas"], reverse=True)
    assert by_roas[0]["allocated_budget"] >= by_roas[-1]["allocated_budget"]


# ── Analytics ────────────────────────────────────────────────────


def test_roi_predictor_monotone():
    b = _brand()
    plats = get_connector().get_platforms(b.brand_id)
    low = ROIPredictor().predict(plats, 20000.0)
    high = ROIPredictor().predict(plats, 80000.0)
    assert high.predicted_revenue > low.predicted_revenue
    assert 0 <= high.fit_r_squared <= 1


def test_performance_tracker_blended():
    b = _brand()
    perf = PerformanceTracker().aggregate(get_connector().get_platforms(b.brand_id))
    assert perf["blended_roas"] > 0
    assert len(perf["ranking"]) == 5
    # ranking sorted by roas desc
    roas = [r["roas"] for r in perf["ranking"]]
    assert roas == sorted(roas, reverse=True)


def test_platformperformance_roas_derived():
    p = PlatformPerformance(
        platform="X", spend=1000.0, revenue=3500.0, impressions=10000,
        clicks=300, conversions=20, roas=3.5, ctr=0.03, cpc=1000 / 300, conv_rate=20 / 300,
    )
    assert p.roas == 3.5
    assert p.ctr == 0.03
    assert p.cpc == 1000 / 300


# ── Edge cases ─────────────────────────────────────────────────────


def test_multilingual_writer_covers_all_target_langs():
    m = MultilingualWriter().write("云栖智能", "企业AI平台", ["en", "ja", "ko", "fr"])
    assert m.source_lang == "zh"
    assert set(m.target_langs) == {"en", "ja", "ko", "fr"}
    # every requested language (incl. source) has a generated piece
    for lang in ["zh", "en", "ja", "ko", "fr"]:
        assert lang in m.pieces
        assert m.pieces[lang].title
        assert m.pieces[lang].body
        assert m.pieces[lang].geo_optimized is True


def test_multilingual_writer_fallback_for_unknown_lang():
    # a language without a template falls back to a transliteration-style stub
    m = MultilingualWriter().write("云栖智能", "企业AI平台", ["xx"])
    assert "xx" in m.pieces
    assert "[xx]" in m.pieces["xx"].title


def test_ab_test_rejects_non_positive_impressions():
    import pytest

    with pytest.raises(ValueError):
        ABTester().compare("A", "B", 0, 0, 1000, 100)
    with pytest.raises(ValueError):
        ABTester().compare("A", "B", 1000, 100, -5, 0)


def test_ab_test_equal_ctr_no_winner():
    r = ABTester().compare("A", "B", 1000, 100, 1000, 100)
    assert r.winner is None
    assert r.lift_pct == 0.0


def test_ab_test_zero_clicks_no_division_error():
    # clicks_a = 0 must not raise (lift guarded)
    r = ABTester().compare("A", "B", 1000, 0, 1000, 50)
    assert r.lift_pct == 0.0
    assert r.ctr_a == 0.0
    assert r.significant is True
    assert r.winner == "B"


def test_budget_allocator_empty_platforms():
    alloc = BudgetAllocator().allocate([], 100000.0)
    assert alloc["allocations"] == []
    assert alloc["uplift_pct"] == 0.0
    assert alloc["blended_roas"] == 0.0


def test_budget_allocator_zero_budget_no_crash():
    b = _brand()
    plats = get_connector().get_platforms(b.brand_id)
    alloc = BudgetAllocator().allocate(plats, 0.0)
    assert alloc["blended_roas"] == 0.0
    # allocations still produced (proportional, all zero)
    assert len(alloc["allocations"]) == len(plats)


def test_roi_predictor_zero_spend():
    b = _brand()
    plats = get_connector().get_platforms(b.brand_id)
    pred = ROIPredictor().predict(plats, 0.0)
    # spend=0 → ROAS undefined → reported as 0, revenue falls to baseline (intercept)
    assert pred.predicted_roas == 0.0
    assert pred.predicted_revenue >= 0


def test_roi_predictor_needs_two_platforms():
    import pytest

    b = _brand()
    with pytest.raises(ValueError):
        ROIPredictor().predict(get_connector().get_platforms(b.brand_id)[:1], 5000.0)


def test_visibility_tracker_rejects_unknown_brand():
    import pytest

    with pytest.raises(ValueError):
        VisibilityTracker().track("NON_EXISTENT_BRAND")


def test_content_optimizer_empty_input_safe():
    s = ContentOptimizer().score("", "")
    assert 0 <= s.eeat_score <= 100
    assert 0 <= s.citation_score <= 100
    assert s.suggestions  # always offers improvement suggestions
