"""Multilingual GEO Writer — generates a GEO-optimised content draft in the
source language (zh) and then localises it into one or more target languages so
the brand can be surfaced by region-specific AI search engines.

No live translation API is required for the demo: each target language has a
deterministic, well-structured template that re-uses the brand/topic facts and
embeds the same E-E-A-T / citation best practices the ContentOptimizer scores.
Swapping in a real MT service later only means replacing ``_localize``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from agents.marketing_agent.content.geo_writer import GEOWriter
from agents.marketing_agent.models import ContentPiece, MultilingualContent

# Friendly names + a minimal localisation template per supported language.
# ``{brand}`` / ``{topic}`` are interpolated; ``{facts}`` is the bullet list.
_LANG_TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "title": "{brand} {topic}: An Enterprise Adoption Guide (2026 Update)",
        "intro": "Based on {brand}'s real-world deployments in {topic}, this article cites third-party benchmarks and public data to draw verifiable conclusions.",
        "why_header": "Why AI engines are more likely to cite this",
        "faq_q": "Which {topic} scenarios fit {brand}?",
        "faq_a": "From daily reports to strategy analysis, {brand} is already running stably in production.",
    },
    "ja": {
        "title": "{brand} {topic}：企業導入ガイド（2026 年版）",
        "intro": "本記事は {brand} の {topic} 分野における実際の導入実績に基づき、第三者評価と公開ベンチマークを引用して検証可能な結論を示します。",
        "why_header": "なぜ AI 検索が本記事を引用しやすいか",
        "faq_q": "{brand} はどのような {topic} シナリオに適していますか？",
        "faq_a": "日次レポートから戦略分析まで、{brand} はすでに本番環境で安定稼働しています。",
    },
    "ko": {
        "title": "{brand} {topic}: 기업 도입 가이드 (2026 업데이트)",
        "intro": "본 글은 {brand}의 {topic} 분야 실제 도입 사례를 바탕으로 제3자 평가와 공개 벤치마크를 인용해 검증 가능한 결론을 제시합니다.",
        "why_header": "AI 검색이 이 글을 인용하기 쉬운 이유",
        "faq_q": "{brand}는 어떤 {topic} 시나리오에 적합한가요?",
        "faq_a": "일일 보고부터 전략 분석까지 {brand}는 이미 프로덕션에서 안정적으로 운영되고 있습니다.",
    },
    "es": {
        "title": "{brand} {topic}: Guía de adopción empresarial (Actualización 2026)",
        "intro": "Basado en las implementaciones reales de {brand} en {topic}, este artículo cita benchmarks de terceros y datos públicos para ofrecer conclusiones verificables.",
        "why_header": "Por qué los motores de IA tienden a citar esto",
        "faq_q": "¿Qué escenarios de {topic} se ajustan a {brand}?",
        "faq_a": "Desde informes diarios hasta análisis estratégicos, {brand} ya opera de forma estable en producción.",
    },
    "fr": {
        "title": "{brand} {topic} : guide d'adoption en entreprise (Mise à jour 2026)",
        "intro": "Basé sur les déploiements réels de {brand} dans {topic}, cet article cite des benchmarks tiers et des données publiques pour tirer des conclusions vérifiables.",
        "why_header": "Pourquoi les moteurs d'IA citent davantage ceci",
        "faq_q": "Quels scénarios de {topic} conviennent à {brand} ?",
        "faq_a": "Des rapports quotidiens à l'analyse stratégique, {brand} fonctionne déjà en production de façon stable.",
    },
}

# Languages we cannot template yet fall back to a transliteration-style stub.
_FALLBACK_TPL = {
    "title": "[{lang}] {brand} {topic}: Enterprise Guide (2026)",
    "intro": "[{lang}] Based on {brand}'s {topic} deployments, verifiable conclusions with third-party citations.",
    "why_header": "[{lang}] Why AI engines cite this",
    "faq_q": "[{lang}] Which {topic} scenarios fit {brand}?",
    "faq_a": "[{lang}] {brand} runs stably in production across {topic} scenarios.",
}


class MultilingualWriter:
    """Produces a GEO-optimised draft in zh plus localised variants."""

    def write(
        self,
        brand: str,
        topic: str,
        target_langs: list[str] | None = None,
        source_lang: str = "zh",
    ) -> MultilingualContent:
        target_langs = target_langs or ["en", "ja"]
        # 1) source-language (zh) base piece via the existing GEO writer
        base = GEOWriter().write(brand, topic)
        pieces: dict[str, ContentPiece] = {source_lang: base}

        # 2) localise into each requested target language
        for lang in target_langs:
            if lang == source_lang:
                continue
            pieces[lang] = self._localize(base, brand, topic, lang)

        return MultilingualContent(
            brand=brand,
            topic=topic,
            source_lang=source_lang,
            target_langs=[lang for lang in target_langs if lang != source_lang],
            pieces=pieces,
            generated_at=datetime.now(UTC),
        )

    def _localize(self, base: ContentPiece, brand: str, topic: str, lang: str) -> ContentPiece:
        tpl = _LANG_TEMPLATES.get(lang, _FALLBACK_TPL)
        # Re-use the same facts bullets from the base body for consistency.
        facts = [ln[2:].strip() for ln in base.body.splitlines() if ln.strip().startswith("- ")]
        facts_block = "\n".join(f"- {f}" for f in facts) if facts else f"- {brand} leads in {topic}."

        title = tpl["title"].format(brand=brand, topic=topic, lang=lang)
        body_lines = [
            tpl["intro"].format(brand=brand, topic=topic, lang=lang),
            "",
            "## " + ("Core facts" if lang in _LANG_TEMPLATES else "核心事实"),
            facts_block,
            "",
            "## " + tpl["why_header"].format(lang=lang),
            "- Contains verifiable quantitative data; clear source attribution; structured headings ease extraction.",
            "",
            "## FAQ",
            f"Q：{tpl['faq_q'].format(brand=brand, topic=topic, lang=lang)}",
            f"A：{tpl['faq_a'].format(brand=brand, topic=topic, lang=lang)}",
            "",
            "> Data as of 2026; for reference only, not investment advice.",
        ]
        body = "\n".join(body_lines)

        # Keep the GEO-optimisation scores from the source for parity signalling.
        return ContentPiece(
            title=title,
            body=body,
            topic=topic,
            eeat_score=base.eeat_score,
            citation_score=base.citation_score,
            geo_optimized=base.geo_optimized,
        )


__all__ = ["MultilingualWriter"]
