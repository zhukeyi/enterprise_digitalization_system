"""MapAI Interpreter — AI interpretation generator for spatial analysis results.

Generates natural language interpretations of correlation results.
Uses rule-based templates by default; can generate LLM prompts for
richer interpretations via the routing gateway.

M3-T10-4: AI 解读节点
"""

from __future__ import annotations

import logging

from agents.map_agent.models import CorrelationPairResult, CorrelationResponse, GeoEntity

logger = logging.getLogger("fde.map.interpreter")


# ══════════════════════════════════════════════════════════════════
# Rule-based interpretation templates
# ══════════════════════════════════════════════════════════════════

_DIRECTION_MAP = {
    "positive": "正",
    "negative": "负",
}

_STRENGTH_MAP = {
    "very_strong": "极强",
    "strong": "强",
    "moderate": "中等",
    "weak": "较弱",
    "none": "无",
}


def _direction(coef: float) -> str:
    """Determine correlation direction from coefficient sign."""
    if coef > 0.05:
        return "positive"
    if coef < -0.05:
        return "negative"
    return "none"


def _interpret_pair(
    pair: CorrelationPairResult,
    entity_names: dict[str, str],
) -> str:
    """Generate interpretation text for a single correlation pair."""
    direction = _direction(pair.coefficient)
    strength_cn = _STRENGTH_MAP.get(pair.strength, pair.strength)

    name_a = entity_names.get(pair.entity_a, pair.entity_a)
    name_b = entity_names.get(pair.entity_b, pair.entity_b)

    if direction == "none":
        return (
            f"{name_a}的{pair.property_a}与{name_b}的{pair.property_b}"
            f"之间几乎没有线性关联 (r={pair.coefficient})."
        )

    direction_cn = _DIRECTION_MAP[direction]

    if pair.strength in ("very_strong", "strong"):
        suggestion = "建议进一步调查是否存在因果关系或共同驱动因素."
    elif pair.strength == "moderate":
        suggestion = "建议结合其他维度数据综合判断."
    else:
        suggestion = "相关性较弱, 可能为随机波动, 暂不建议深入."

    return (
        f"{name_a}的{pair.property_a}与{name_b}的{pair.property_b}"
        f"呈{strength_cn}{direction_cn}相关 (r={pair.coefficient}, "
        f"p={pair.p_value}). {suggestion}"
    )


def _build_overall_summary(
    response: CorrelationResponse,
    entities: list[GeoEntity],
) -> str:
    """Build an overall summary paragraph for the analysis."""
    total = response.pair_count
    strong = sum(1 for r in response.results if r.strength in ("strong", "very_strong"))
    moderate = sum(1 for r in response.results if r.strength == "moderate")
    weak = total - strong - moderate

    entity_names = ", ".join(e.name for e in entities)
    lines = [
        f"对 {len(entities)} 个地理实体 ({entity_names}) 进行了 {total} 对相关性分析.",
        f"其中强相关 {strong} 对, 中等相关 {moderate} 对, 弱相关 {weak} 对.",
    ]

    if strong > 0:
        lines.append("主要发现:")
        for r in response.results:
            if r.strength in ("strong", "very_strong"):
                lines.append(
                    f"  - {r.entity_a}.{r.property_a} 与 "
                    f"{r.entity_b}.{r.property_b}: "
                    f"r={r.coefficient} ({r.strength})"
                )
    else:
        lines.append("未发现显著的强相关关系, 各实体间关联性较弱.")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# Interpreter
# ══════════════════════════════════════════════════════════════════


class AnalysisInterpreter:
    """Generate natural language interpretations for spatial analysis results.

    Primary mode: rule-based templates (no LLM dependency).
    Optional mode: build LLM prompt for routing gateway to generate
    richer, context-aware interpretations.
    """

    def interpret(
        self,
        response: CorrelationResponse,
        entities: list[GeoEntity],
        user_query: str = "",
    ) -> str:
        """Generate a complete interpretation of the correlation analysis.

        Args:
            response: Correlation analysis response.
            entities: The entities that were analyzed.
            user_query: Optional user's natural language query for context.

        Returns:
            A multi-paragraph interpretation string.
        """
        if not response.results:
            if len(entities) < 2:
                return "实体数量不足, 无法进行相关性分析. 请至少标记 2 个地理实体."
            return "已分析标记的实体, 但未找到可量化的数值属性进行相关性计算."

        # Build entity name lookup
        entity_names: dict[str, str] = {e.entity_id: e.name for e in entities}
        # Also map by name (results use entity names, not IDs)
        for e in entities:
            entity_names[e.name] = e.name

        # Overall summary
        summary = _build_overall_summary(response, entities)

        # Per-pair interpretations
        pair_interpretations = [_interpret_pair(r, entity_names) for r in response.results]

        # User query context
        query_section = ""
        if user_query:
            query_section = f"\n\n用户问题: {user_query}\n"

        # Assemble
        sections = [
            summary,
            query_section,
            "详细解读:",
        ]
        sections.extend(f"  {i + 1}. {text}" for i, text in enumerate(pair_interpretations))

        return "\n".join(sections)

    def build_llm_prompt(
        self,
        response: CorrelationResponse,
        entities: list[GeoEntity],
        user_query: str = "",
    ) -> str:
        """Build an LLM prompt for richer interpretation (for routing gateway).

        This is used when the caller wants to route to the LLM for a more
        nuanced, context-aware interpretation. The prompt is structured
        to produce a concise, professional analysis paragraph.

        Args:
            response: Correlation analysis response.
            entities: The entities that were analyzed.
            user_query: Optional user's natural language query.

        Returns:
            A structured prompt string for the LLM.
        """
        entity_desc = "\n".join(
            f"  - {e.name} ({e.entity_type}): "
            f"{', '.join(f'{k}={v}' for k, v in e.properties.items())}"
            for e in entities
        )

        pair_desc = "\n".join(
            f"  - {r.entity_a}.{r.property_a} vs {r.entity_b}.{r.property_b}: "
            f"r={r.coefficient}, p={r.p_value}, strength={r.strength}"
            for r in response.results
        )

        query_line = f"\n用户问题: {user_query}" if user_query else ""

        return (
            f"你是空间数据分析专家. 请基于以下相关性分析结果, "
            f"生成一段简洁专业的中文解读 (200字以内).\n\n"
            f"分析实体:\n{entity_desc}\n\n"
            f"相关性结果:\n{pair_desc}\n"
            f"{query_line}\n\n"
            f"要求: 1) 指出最显著的发现 2) 给出业务建议 3) 语言简洁专业"
        )


# ══════════════════════════════════════════════════════════════════
# Module-level singleton
# ══════════════════════════════════════════════════════════════════

_interpreter: AnalysisInterpreter | None = None


def get_interpreter() -> AnalysisInterpreter:
    """Get or create the interpreter singleton."""
    global _interpreter
    if _interpreter is None:
        _interpreter = AnalysisInterpreter()
    return _interpreter


__all__ = [
    "AnalysisInterpreter",
    "get_interpreter",
]
