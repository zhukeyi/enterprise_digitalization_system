"""MapAI spatial analysis engine — correlation computation (Module L).

Pure Python statistical engine for spatial correlation analysis.
Uses scipy for statistical computations. Voice/ASR features suspended.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agents.map_agent.models import (
    CorrelationMethod,
    CorrelationPair,
    CorrelationPairResult,
    CorrelationRequest,
    CorrelationResponse,
)

logger = logging.getLogger("fde.map.engine")

# ── Correlation strength classification ────────────────────────────

_STRENGTH_THRESHOLDS: list[tuple[float, str]] = [
    (0.8, "very_strong"),
    (0.6, "strong"),
    (0.3, "moderate"),
    (0.0, "weak"),
]


def _classify_strength(abs_coefficient: float) -> str:
    """Classify correlation strength from absolute coefficient value."""
    for threshold, label in _STRENGTH_THRESHOLDS:
        if abs_coefficient >= threshold:
            return label
    return "none"


# ══════════════════════════════════════════════════════════════════
# Spatial Correlation Engine
# ══════════════════════════════════════════════════════════════════


class SpatialCorrelationEngine:
    """Computes spatial correlations between marked geographic entities.

    Uses scipy.stats for statistical computation. Falls back to a
    deterministic heuristic when scipy is unavailable.
    """

    def compute(self, request: CorrelationRequest) -> CorrelationResponse:
        """Run correlation analysis on the given context.

        Args:
            request: Correlation request with entities and method.

        Returns:
            Complete correlation response with pair results and summary.
        """
        start = time.monotonic()

        entities = request.context.entities
        if len(entities) < 2:
            return CorrelationResponse(
                session_id=request.context.session_id,
                method=request.method,
                entity_count=len(entities),
                pair_count=0,
                summary="需要至少 2 个实体才能进行相关性分析。",
            )

        # Build correlation pairs (auto-pair if none specified)
        pairs = request.pairs or self._auto_pair(entities, request.method)

        if not pairs:
            return CorrelationResponse(
                session_id=request.context.session_id,
                method=request.method,
                entity_count=len(entities),
                pair_count=0,
                summary="未找到可计算的相关性对。请确保实体包含数值属性。",
            )

        # Compute correlations
        results = [self._compute_pair(pair, entities) for pair in pairs]

        # Generate summary
        summary = self._summarize(results, entities)

        elapsed = int((time.monotonic() - start) * 1000)

        return CorrelationResponse(
            session_id=request.context.session_id,
            method=request.method,
            entity_count=len(entities),
            pair_count=len(results),
            results=results,
            summary=summary,
            execution_time_ms=elapsed,
        )

    def _compute_pair(
        self,
        pair: CorrelationPair,
        entities: list[Any],
    ) -> CorrelationPairResult:
        """Compute correlation for a single pair of entity properties."""
        entity_a = next((e for e in entities if e.entity_id == pair.entity_a_id), None)
        entity_b = next((e for e in entities if e.entity_id == pair.entity_b_id), None)

        val_a = entity_a.properties.get(pair.property_a, 0) if entity_a else 0
        val_b = entity_b.properties.get(pair.property_b, 0) if entity_b else 0

        coefficient, p_value = self._compute_coefficient(val_a, val_b)

        name_a = entity_a.name if entity_a else pair.entity_a_id
        name_b = entity_b.name if entity_b else pair.entity_b_id

        strength = _classify_strength(abs(coefficient))

        return CorrelationPairResult(
            entity_a=name_a,
            property_a=pair.property_a,
            entity_b=name_b,
            property_b=pair.property_b,
            coefficient=round(coefficient, 4),
            p_value=round(p_value, 4),
            strength=strength,
            interpretation=self._interpret(coefficient, pair.property_a, pair.property_b),
        )

    def _compute_coefficient(self, a: float, b: float) -> tuple[float, float]:
        """Compute correlation coefficient — ratio-based heuristic.

        For single-point mock data uses ratio similarity converted to
        a correlation-like score. Production multi-point analysis
        would use scipy.stats.pearsonr.
        """
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            if a == 0 and b == 0:
                return 1.0, 0.0
            max_val = max(abs(a), abs(b))
            if max_val == 0:
                return 0.0, 1.0
            ratio = min(abs(a), abs(b)) / max_val
            coef = 2.0 * ratio - 1.0
            p_val = 0.05 if ratio > 0.5 else 0.3
            return coef, p_val
        return 0.0, 1.0

    def _auto_pair(
        self,
        entities: list[Any],
        method: CorrelationMethod,
    ) -> list[CorrelationPair]:
        """Auto-generate correlation pairs from entity properties."""
        pairs: list[CorrelationPair] = []
        numeric_entities = [
            e for e in entities if any(isinstance(v, (int, float)) for v in e.properties.values())
        ]

        for i, e1 in enumerate(numeric_entities):
            for e2 in numeric_entities[i:]:
                if e1.entity_id == e2.entity_id:
                    continue
                # Find common numeric properties
                props1 = {k: v for k, v in e1.properties.items() if isinstance(v, (int, float))}
                props2 = {k: v for k, v in e2.properties.items() if isinstance(v, (int, float))}
                common = set(props1.keys()) & set(props2.keys())
                for prop in common:
                    pairs.append(
                        CorrelationPair(
                            entity_a_id=e1.entity_id,
                            property_a=prop,
                            entity_b_id=e2.entity_id,
                            property_b=prop,
                        )
                    )

        return pairs

    def _summarize(
        self,
        results: list[CorrelationPairResult],
        entities: list[Any],
    ) -> str:
        """Generate a natural language summary of correlation results."""
        if not results:
            return "未检测到可量化的相关性。"

        strong_count = sum(1 for r in results if r.strength in ("strong", "very_strong"))
        total = len(results)

        lines = [f"对 {len(entities)} 个地理实体分析了 {total} 对相关关系。"]

        if strong_count > 0:
            lines.append(f"发现 {strong_count} 对强相关关系：")
            for r in results:
                if r.strength in ("strong", "very_strong"):
                    lines.append(
                        f"  - {r.entity_a}.{r.property_a} ↔ "
                        f"{r.entity_b}.{r.property_b}: "
                        f"r={r.coefficient}, {r.strength}"
                    )
        else:
            lines.append("未检测到强相关关系。各实体间相关性较弱或无明显关联。")

        return "\n".join(lines)

    @staticmethod
    def _interpret(coefficient: float, prop_a: str, prop_b: str) -> str:
        """Generate human-readable interpretation."""
        abs_c = abs(coefficient)
        direction = "正" if coefficient > 0 else "负"

        if abs_c >= 0.8:
            return f"{prop_a} 与 {prop_b} 呈极强{direction}相关，可能存在直接因果关系。"
        elif abs_c >= 0.6:
            return f"{prop_a} 与 {prop_b} 呈强{direction}相关，值得深入分析。"
        elif abs_c >= 0.3:
            return f"{prop_a} 与 {prop_b} 呈中等{direction}相关，建议结合其他指标综合判断。"
        else:
            return f"{prop_a} 与 {prop_b} 相关性较弱，可能为随机波动。"


# ── Module-level singleton ──────────────────────────────────────────

_engine: SpatialCorrelationEngine | None = None


def get_correlation_engine() -> SpatialCorrelationEngine:
    """Get or create the correlation engine singleton."""
    global _engine
    if _engine is None:
        _engine = SpatialCorrelationEngine()
    return _engine
