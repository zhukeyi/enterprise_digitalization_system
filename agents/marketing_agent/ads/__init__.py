"""Ads subpackage: variant generation, A/B testing, budget allocation."""

from agents.marketing_agent.ads.ab_tester import ABTester
from agents.marketing_agent.ads.budget_allocator import BudgetAllocator
from agents.marketing_agent.ads.variant_generator import VariantGenerator

__all__ = ["ABTester", "BudgetAllocator", "VariantGenerator"]
