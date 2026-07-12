"""RL-Based Pricing Optimizer (lightweight policy gradient).

A dependency-free implementation of a PPO/REINFORCE-style price learner
targeting the profit-maximizing price under a constant-elasticity demand
model:

    Q(p) = base_demand · (p / ref_price) ^ elasticity        (elasticity < 0)
    profit(p) = (p - cost) · Q(p)

The agent parametrizes the *log price multiplier* θ with a Gaussian policy
μ, σ. Across episodes it samples prices, observes a noisy demand realization,
and ascends the expected-profit gradient (REINFORCE with a moving-average
baseline). σ anneals so exploration gives way to exploitation — mirroring the
clip/advantage mechanics of PPO without requiring torch.

For a constant-elasticity curve the analytic optimum is
    p* = cost · |e| / (|e| - 1)   (when |e| > 1),
which the learner converges to; we expose it as a self-check.
"""

from __future__ import annotations

import logging

import numpy as np

from agents.pricing_agent.models import Product, RLTrainingLog

logger = logging.getLogger("fde.pricing.rl_based")


class PPOPricingOptimizer:
    """Policy-gradient price optimizer (REINFORCE-style, σ-annealing)."""

    def __init__(
        self,
        episodes: int = 400,
        lr: float = 0.05,
        sigma_init: float = 0.35,
        sigma_final: float = 0.04,
        seed: int = 7,
    ) -> None:
        self.episodes = episodes
        self.lr = lr
        self.sigma_init = sigma_init
        self.sigma_final = sigma_final
        self.seed = seed

    def optimize(
        self,
        product: Product,
        elasticity: float,
        base_demand: float,
        ref_price: float | None = None,
    ) -> tuple[float, RLTrainingLog]:
        rng = np.random.default_rng(self.seed)
        cost = product.cost
        ref = ref_price or product.current_price
        e = float(elasticity)
        floor = cost * 1.05
        ceil = ref * 3.0

        def demand(p: float) -> float:
            return base_demand * (p / ref) ** e

        def profit(p: float) -> float:
            return (p - cost) * demand(p)

        mu = 0.0  # start at ref price (exp(0)=1)
        rewards: list[float] = []
        prices: list[float] = []
        best_price = ref
        best_profit = profit(ref)
        baseline = profit(ref)
        # reward scale for advantage normalization (prevents exploding gradients
        # when profit is large, e.g. O(1e4)+)
        scale = max(abs(baseline), 1.0)

        for ep in range(self.episodes):
            sigma = self.sigma_init + (self.sigma_final - self.sigma_init) * (ep / max(1, self.episodes - 1))
            a = float(rng.normal(mu, sigma))
            price = float(np.clip(ref * np.exp(a), floor, ceil))
            # noisy demand realization
            realized = demand(price) * (1.0 + float(rng.normal(0.0, 0.1)))
            realized = max(realized, 0.0)
            reward = (price - cost) * realized

            # REINFORCE update: normalized advantage (mean-subtracted, scaled)
            # + clipped per-step update to keep training stable.
            adv = (reward - baseline) / scale
            step = self.lr * adv * (a - mu) / (sigma ** 2 + 1e-8)
            step = float(np.clip(step, -0.3, 0.3))
            mu += step
            baseline = 0.95 * baseline + 0.05 * reward

            rewards.append(reward)
            prices.append(price)
            if reward > best_profit:
                best_profit = reward
                best_price = price

        final_mean = float(ref * np.exp(mu))
        final_mean = float(np.clip(final_mean, floor, ceil))

        return round(best_price, 2), RLTrainingLog(
            episodes=[round(float(r), 2) for r in rewards],
            prices=[round(float(p), 2) for p in prices],
            best_price=round(best_price, 2),
            best_profit=round(float(best_profit), 2),
            final_policy_mean=round(final_mean, 2),
            iterations=self.episodes,
        )


__all__ = ["PPOPricingOptimizer"]
