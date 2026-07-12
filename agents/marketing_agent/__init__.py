"""Marketing Agent — GEO visibility, ads optimisation, content & analytics.

Self-contained, numpy-only engine for the V5 marketing module. All math is real
(OLS, z-test, ROAS-weighted allocation) and deterministic via seeded demo data.
"""

from agents.marketing_agent.ads import ABTester, BudgetAllocator, VariantGenerator
from agents.marketing_agent.analytics import PerformanceTracker, ROIPredictor
from agents.marketing_agent.content import GEOWriter, SEOWriter
from agents.marketing_agent.geo import ContentOptimizer, KeywordStrategy, VisibilityTracker

__all__ = [
    "ABTester",
    "BudgetAllocator",
    "ContentOptimizer",
    "GEOWriter",
    "KeywordStrategy",
    "PerformanceTracker",
    "ROIPredictor",
    "SEOWriter",
    "VariantGenerator",
    "VisibilityTracker",
]
