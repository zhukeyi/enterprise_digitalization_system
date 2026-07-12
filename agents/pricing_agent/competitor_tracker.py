"""Competitor Tracker — monitor competitor prices vs own price.

Produces a positioning snapshot: cheaper / parity / premium relative to the
competitor average. In production ``get_competitor_prices`` would call the
data_agent crawler (reuse the multi-source RSS/HTTP framework) to scrape live
competitor listings; here we use the connector's seeded demo prices.
"""

from __future__ import annotations

import logging

from agents.pricing_agent.data_connector import get_connector
from agents.pricing_agent.models import CompetitorSnapshot

logger = logging.getLogger("fde.pricing.competitor")


class CompetitorTracker:
    """Track and position competitor pricing for a product."""

    def snapshot(self, product_id: str) -> CompetitorSnapshot:
        connector = get_connector()
        product = connector.get_product(product_id)
        if product is None:
            raise ValueError(f"商品不存在: {product_id}")

        comps = connector.get_competitor_prices(product_id)
        if not comps:
            return CompetitorSnapshot(
                product_id=product_id,
                own_price=product.current_price,
                competitors=[],
                avg_competitor=product.current_price,
                min_competitor=product.current_price,
                max_competitor=product.current_price,
                position="parity",
            )

        prices = [c.price for c in comps]
        avg = sum(prices) / len(prices)
        own = product.current_price

        if own < avg * 0.97:
            position = "cheaper"
        elif own > avg * 1.03:
            position = "premium"
        else:
            position = "parity"

        return CompetitorSnapshot(
            product_id=product_id,
            own_price=own,
            competitors=comps,
            avg_competitor=round(avg, 2),
            min_competitor=round(min(prices), 2),
            max_competitor=round(max(prices), 2),
            position=position,
        )


__all__ = ["CompetitorTracker"]
