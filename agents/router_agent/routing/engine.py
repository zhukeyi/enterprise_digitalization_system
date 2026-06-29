"""Routing engine — selects optimal model based on task characteristics.

M1-T6: YAML-configurable routing strategy.

Routing dimensions:
- Complexity: simple / medium / complex
- Sensitivity: public / internal / confidential
- Cost budget: cheapeast / balanced / best-performance
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from agents.router_agent.models.request import ChatCompletionRequest

logger = logging.getLogger("fde.router.routing")


# ══════════════════════════════════════════════════════════════════
# Data Models
# ══════════════════════════════════════════════════════════════════


@dataclass
class RoutingDecision:
    """Result of the routing decision."""

    model_name: str
    reason: str
    estimated_cost: float = 0.0


@dataclass
class RouteRule:
    """A single routing rule."""

    name: str
    model: str
    priority: int = 100
    conditions: dict[str, Any] = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════
# Routing Engine
# ══════════════════════════════════════════════════════════════════


class RoutingEngine:
    """Intelligent model router.

    Strategy is loaded from routing_policy.yaml and can be
    dynamically updated without restart.

    Default routing:
        simple  → cheap model (mock-v1 / qwen-turbo)
        medium  → balanced model (deepseek-chat)
        complex → best model (glm-4-flash for now)
        sensitive → local model (no cloud)
    """

    DEFAULT_MODEL = "fde/mock-v1"

    def __init__(self, config_path: str | None = None) -> None:
        if config_path is None:
            config_path = str(Path(__file__).resolve().parent / "routing_policy.yaml")
        self.config_path = Path(config_path)
        self.rules: list[RouteRule] = []
        self._load_config()

    def _load_config(self) -> None:
        """Load routing rules from YAML configuration."""
        if not self.config_path.exists():
            logger.warning("Routing config not found at %s, using defaults", self.config_path)
            self.rules = self._default_rules()
            return
        try:
            with open(self.config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)
            self.rules = [
                RouteRule(
                    name=r["name"],
                    model=r["model"],
                    priority=r.get("priority", 100),
                    conditions=r.get("conditions", {}),
                )
                for r in config.get("rules", [])
            ]
            logger.info("Loaded %d routing rules from %s", len(self.rules), self.config_path)
        except Exception as e:
            logger.warning("Failed to load routing config: %s, using defaults", e)
            self.rules = self._default_rules()

    def reload(self) -> None:
        """Hot-reload routing configuration."""
        self._load_config()

    def route(self, request: ChatCompletionRequest) -> str:
        """Select the best model for this request.

        Args:
            request: Chat completion request (model field may be None for auto)

        Returns:
            Model name to use.
        """
        # If user explicitly requested a model, use it
        if request.model:
            logger.debug("Explicit model requested: %s", request.model)
            return request.model

        # Determine task characteristics
        complexity = self._estimate_complexity(request)
        messages_text = " ".join(m.content for m in request.messages)

        # Sort rules by priority (lower = higher priority)
        sorted_rules = sorted(self.rules, key=lambda r: r.priority)

        for rule in sorted_rules:
            if self._match_rule(rule, complexity, messages_text):
                logger.info(
                    "Routed to '%s' (rule='%s', complexity='%s')",
                    rule.model,
                    rule.name,
                    complexity,
                )
                return rule.model

        logger.warning("No rule matched — using default model: %s", self.DEFAULT_MODEL)
        return self.DEFAULT_MODEL

    def _estimate_complexity(self, request: ChatCompletionRequest) -> str:
        """Estimate task complexity from request characteristics."""
        total_chars = sum(len(m.content) for m in request.messages)
        msg_count = len(request.messages)

        # Heuristics
        if total_chars > 5000 or msg_count > 10:
            return "complex"
        if total_chars > 1000 or msg_count > 4:
            return "medium"
        return "simple"

    def _match_rule(self, rule: RouteRule, complexity: str, text: str) -> bool:
        """Check if a rule matches the current request context."""
        conditions = rule.conditions
        if not conditions:
            return True  # Catch-all rule

        # Complexity filter
        if (
            "complexity" in conditions
            and conditions["complexity"] != complexity
            and conditions["complexity"] != "any"
        ):
            return False

        # Keyword filter
        if "keywords" in conditions:
            keywords = conditions["keywords"]
            if not any(kw.lower() in text.lower() for kw in keywords):
                return False

        # Pattern filter (regex)
        if "pattern" in conditions:
            pattern = conditions["pattern"]
            if not re.search(pattern, text, re.IGNORECASE):
                return False

        return True

    @staticmethod
    def _default_rules() -> list[RouteRule]:
        """Fallback rules when config file is missing."""
        return [
            RouteRule(
                name="simple-default",
                model="fde/mock-v1",
                priority=10,
                conditions={"complexity": "simple"},
            ),
            RouteRule(
                name="medium-default",
                model="fde/mock-v1",
                priority=10,
                conditions={"complexity": "medium"},
            ),
            RouteRule(
                name="complex-default",
                model="fde/mock-v1",
                priority=10,
                conditions={"complexity": "complex"},
            ),
        ]
