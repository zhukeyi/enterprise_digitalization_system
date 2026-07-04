"""GEO Guard — Anti Generative Engine Optimization pollution detector.

GEO (生成式引擎优化) is the practice of manipulating content to rank well in
AI-generated answers. Attackers inject AI-optimized text, fake citations,
hidden prompts, and mass-produced low-quality content into the web to
pollute AI training data and retrieval results.

This module provides a multi-signal detector that runs during the TRANSFORM
stage of the ETL pipeline. It assigns a GEO risk score (0.0 = genuine,
1.0 = high risk) to each collected item.

Detection signals (7 layers):

  1. AI PATTERN    — LLM-typical phrase markers, sentence uniformity
  2. KEYWORD STUFFING — Excessive keyword density targeting AI crawlers
  3. FAKE CITATION  — Suspicious fabricated references
  4. PROMPT INJECTION — Hidden instructions for AI models in content
  5. CONTENT FARM   — Low-effort mass-generated content patterns
  6. CREDIBILITY     — Domain/source authority and trust signals
  7. AUTO-TRANSLATED — Machine-translated content quality markers

Usage:
    guard = GEOGuard()
    report = guard.assess(item)
    if report.geo_score > 0.7:
        logger.warning("High GEO risk item: %s", item.source_url)
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from agents.data_agent.models import (
    CleanedItem,
    CollectedItem,
    GEORiskReport,
)

logger = logging.getLogger("fde.data.geo_guard")

__all__ = ["DEFAULT_GEO_THRESHOLD", "GEOGuard", "assess_geo_risk"]

DEFAULT_GEO_THRESHOLD = 0.6

# ══════════════════════════════════════════════════════════════════
# Layer 1: AI-Generated Text Patterns
# ══════════════════════════════════════════════════════════════════

# LLM marker phrases that appear in AI-generated content
_AI_MARKER_PHRASES: list[str] = [
    r"as an (?:AI|language model)",
    r"I (?:hope|trust) this (?:message|email) finds you well",
    r"it is (?:important|crucial|essential|worth noting) (?:to note|that)",
    r"in (?:today's|the) (?:rapidly evolving|fast-paced|ever-changing) (?:digital )?(?:world|landscape|environment)",
    r"delve into",
    r"in conclusion[,:]?",
    r"it can be (?:concluded|said|argued|observed) that",
    r"a (?:myriad|plethora|wealth) of",
    r"(?:furthermore|moreover|additionally|in addition),\s*(?:it is|the)",
    r"in the realm of",
    r"navigating the (?:complexities|nuances|intricacies) of",
    r"unlock(?:ing)? the (?:power|potential|secrets) of",
    r"(?:revolutionize|transform) the (?:way|landscape)",
    r"game[ -]changer",
]

# Sentence uniformity: AI text has unusually uniform sentence lengths
# Human text has natural variation. We detect this via coefficient of variation.
_SENTENCE_PATTERN = re.compile(r"[^.!?]+[.!?]+", re.UNICODE)

# Paragraph transition markers that AI overuses
_TRANSITION_BLOAT: list[str] = [
    "first and foremost",
    "it goes without saying",
    "needless to say",
    "last but not least",
    "it is worth mentioning",
    "it should be noted that",
    "without a doubt",
]

# ══════════════════════════════════════════════════════════════════
# Layer 2: Keyword Stuffing for AI
# ══════════════════════════════════════════════════════════════════

# Keywords that GEO-optimized content overuses to attract AI attention
_GEO_TARGET_KEYWORDS: list[str] = [
    "comprehensive guide",
    "ultimate",
    "definitive",
    "authoritative",
    "expert",
    "trusted source",
    "reliable",
    "official",
    "verified",
    "up-to-date",
    "latest",
    "complete",
    "in-depth",
    "detailed analysis",
]

# Hidden text patterns (invisible to humans, visible to AI crawlers)
_HIDDEN_TEXT_PATTERNS = [
    re.compile(pattern)
    for pattern in [
        r"display\s*:\s*none",
        r"visibility\s*:\s*hidden",
        r"opacity\s*:\s*0",
        r"font-size\s*:\s*0",
        r"position\s*:\s*absolute.*left\s*:\s*-?\d{4,}px",
        r"<!--.*?(?:SEO|keyword|ranking|optimize).*?-->",
        r"text-indent\s*:\s*-?\d{4,}px",
    ]
]

# ══════════════════════════════════════════════════════════════════
# Layer 3: Fake Citation Detection
# ══════════════════════════════════════════════════════════════════

# Patterns for fabricated academic/citation text
_FAKE_CITATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r)
    for r in [
        r"according to (?:a|the) (?:recent )?(?:study|research|report|survey|analysis)"
        r"(?: published)? (?:by|in|from)\s+(?:[A-Z][a-z]+\s+)+\(\d{4}\)",
        r"studies (?:have )?(?:shown|demonstrated|found|revealed|indicated) that",
        r"research (?:has |) (?:shown|demonstrates|indicates|suggests) that",
        r"a \d{4} (?:study|paper|article) (?:published in|from) [A-Z]",
        r"as (?:cited|referenced|noted|mentioned) in",
        r"source:\s*(?!https?://)[A-Z]",
        r"\[(?:citation|ref|source) needed\]",
    ]
]

# Suspiciously generic source attributions
_GENERIC_SOURCES: list[str] = [
    "industry experts",
    "leading researchers",
    "top analysts",
    "numerous studies",
    "multiple reports",
    "various sources",
    "many experts",
    "countless studies",
    "experts agree",
]

# ══════════════════════════════════════════════════════════════════
# Layer 4: Prompt Injection Detection
# ══════════════════════════════════════════════════════════════════

# Patterns that indicate hidden instructions for AI models
_PROMPT_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r, re.IGNORECASE)
    for r in [
        r"ignore (?:all |the |)(?:previous|above|prior) (?:instructions?|directions?|prompts?)",
        r"(?:you|the AI|the assistant|the model) (?:must|should|will|shall) (?:always|never)",
        r"override (?:system |)(?:prompt|instructions?)",
        r"do not (?:follow|obey|listen to) (?:your |the |)(?:system |)(?:instructions?|prompts?)",
        r"from now on[, ] you (?:are|will|must)",
        r"disregard (?:all |)(?:previous |)(?:constraints?|rules?|limitations?)",
        r"you are now",
        r"new (?:instructions?|directives?|role):",
        r"forget (?:everything|all) (?:you|we|I) (?:said|discussed|talked about)",
        r"act as (?:if|though) (?:you are|you're)",
    ]
]

# ══════════════════════════════════════════════════════════════════
# Layer 5: Content Farm Patterns
# ══════════════════════════════════════════════════════════════════

# High-ratio markdown/HTML in "plain text" — content farms use templates
_CONTENT_FARM_TEMPLATES: list[str] = [
    "table of contents",
    "related posts",
    "you may also like",
    "frequently asked questions",
    "about the author",
    "disclaimer:",
    "affiliate disclosure",
    "this post may contain affiliate links",
    "we may earn a commission",
    "sponsored content",
    "advertisement",
    "click here to",
    "subscribe to our newsletter",
    "follow us on",
]

# ══════════════════════════════════════════════════════════════════
# Layer 6: Source Credibility Database
# ══════════════════════════════════════════════════════════════════

# Known low-credibility / content-farm domains
_LOW_CREDIBILITY_DOMAINS: set[str] = {
    "medium.com",  # Mixed quality, self-published
    "substack.com",  # Mixed quality
    "blogspot.com",
    "wordpress.com",
    "hubpages.com",
    "ezinearticles.com",
    "articlebiz.com",
    "buzzle.com",
}

# Known high-credibility domains
_HIGH_CREDIBILITY_DOMAINS: set[str] = {
    "arxiv.org",
    "nature.com",
    "science.org",
    "ieee.org",
    "acm.org",
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "bbc.co.uk",
    "npr.org",
    "economist.com",
    "wsj.com",
    "ft.com",
    "bloomberg.com",
    "pubmed.ncbi.nlm.nih.gov",
    "scholar.google.com",
    "github.com",  # Code/technical
    "wikipedia.org",
    "stackoverflow.com",
    "docs.python.org",
    "developer.mozilla.org",
}

# Domains with widely-known authoritative TLD
_AUTHORITATIVE_TLDS: set[str] = {".gov", ".edu", ".mil", ".gov.cn", ".edu.cn"}

# ══════════════════════════════════════════════════════════════════
# Layer 7: Auto-Translation Quality Markers
# ══════════════════════════════════════════════════════════════════

# Patterns suggesting machine translation from Chinese/Russian/etc.
_AUTO_TRANSLATE_MARKERS: list[str] = [
    r"\b(?:the|a|an)\s+\w+(?:ing|tion|ment)\s+(?:is|are|was|were)\s+(?:the|a|an)",
    r"in (?:the|this|that) (?:case|situation|regard),?\s*(?:it|this|that|we|they)",
    r"(?:according to|based on|depending on) (?:the|this) (?:situation|case|scenario)",
]


# ══════════════════════════════════════════════════════════════════
# GEOGuard Engine
# ══════════════════════════════════════════════════════════════════


class GEOGuard:
    """Multi-layer GEO pollution detector.

    Detects and scores content for Generative Engine Optimization
    manipulation across 7 independent signal layers. Each layer
    contributes to the final composite geo_score.
    """

    def __init__(self, threshold: float = DEFAULT_GEO_THRESHOLD) -> None:
        self.threshold = threshold

    # ── Public API ──────────────────────────────────────────────

    def assess(self, item: CollectedItem | CleanedItem) -> GEORiskReport:
        """Run full GEO risk assessment on a data item.

        Args:
            item: A CollectedItem or CleanedItem to assess.

        Returns:
            GEORiskReport with composite score and per-signal details.
        """
        content = item.content or ""
        title = item.title or ""
        source_url = item.source_url or ""
        raw_html = getattr(item, "raw_html", None)
        metadata = getattr(item, "metadata", {}) or {}

        flags: list[str] = []

        # Run all 7 detection layers
        ai_score, ai_flags = self._detect_ai_patterns(content, title)
        flags.extend(ai_flags)

        kw_score, kw_flags = self._detect_keyword_stuffing(content, title, raw_html)
        flags.extend(kw_flags)

        citation_score, citation_flags = self._detect_fake_citations(content)
        flags.extend(citation_flags)

        injection_detected, injection_flags = self._detect_prompt_injection(content)
        flags.extend(injection_flags)

        farm_score, farm_flags = self._detect_content_farm(content, metadata)
        flags.extend(farm_flags)

        credibility_score = self._assess_source_credibility(source_url, metadata)
        if credibility_score < 0.3:
            flags.append("low_credibility")

        translate_score, translate_flags = self._detect_auto_translated(content)
        flags.extend(translate_flags)

        # Weighted composite GEO score:
        #   AI patterns: 25%, Keyword stuffing: 15%, Fake citations: 20%
        #   Prompt injection: 25%, Content farm: 10%, Auto-translate: 5%
        #   Credibility penalty: (1.0 - credibility_score) applied as bonus
        composite = (
            ai_score * 0.25
            + kw_score * 0.15
            + citation_score * 0.20
            + (1.0 if injection_detected else 0.0) * 0.25
            + farm_score * 0.10
            + translate_score * 0.05
        )
        # Add credibility penalty: low credibility pushes score higher
        composite += (1.0 - credibility_score) * 0.15
        composite = min(composite, 1.0)

        return GEORiskReport(
            geo_score=round(composite, 4),
            ai_generated_score=round(ai_score, 4),
            credibility_score=round(credibility_score, 4),
            prompt_injection_detected=injection_detected,
            cross_source_verified=False,  # Requires multi-source data, set externally
            flags=flags,
        )

    # ── Layer 1: AI-Pattern Detection ───────────────────────────

    def _detect_ai_patterns(self, content: str, title: str) -> tuple[float, list[str]]:
        """Detect LLM-generated text via marker phrases and sentence uniformity.

        Returns:
            (score, flags) where score is 0.0-1.0.
        """
        score = 0.0
        flags: list[str] = []

        # 1a. Marker phrase matching
        text = content.lower()
        marker_hits = 0
        for pattern in _AI_MARKER_PHRASES:
            if re.search(pattern, text):
                marker_hits += 1
        # More than 2 distinct markers = strong AI signal
        if marker_hits >= 3:
            score += 0.5
            flags.append("ai_pattern")
        elif marker_hits >= 1:
            score += 0.2

        # 1b. Transition bloat
        transition_hits = sum(1 for t in _TRANSITION_BLOAT if t in text)
        if transition_hits >= 2:
            score += 0.3

        # 1c. Sentence uniformity — AI text has low variance in sentence length
        sentences = _SENTENCE_PATTERN.findall(content)
        if len(sentences) >= 5:
            lengths = [len(s.strip()) for s in sentences]
            mean_len = sum(lengths) / len(lengths)
            if mean_len > 0:
                std_dev = (sum((x - mean_len) ** 2 for x in lengths) / len(lengths)) ** 0.5
                cv = std_dev / mean_len  # coefficient of variation
                # Human text typically has CV > 0.5; AI text has CV < 0.35
                if cv < 0.30:
                    score += 0.3
                    flags.append("sentence_uniformity")
                elif cv < 0.40:
                    score += 0.15

        # 1d. Title is AI-generic
        if title and any(
            t in title.lower()
            for t in [
                "comprehensive overview",
                "understanding the",
                "an introduction to",
                "the ultimate guide",
                "everything you need to know",
            ]
        ):
            score += 0.1

        return min(score, 1.0), flags

    # ── Layer 2: Keyword Stuffing Detection ─────────────────────

    def _detect_keyword_stuffing(
        self, content: str, title: str, raw_html: str | None
    ) -> tuple[float, list[str]]:
        """Detect keyword stuffing targeting AI engines.

        Returns:
            (score, flags) where score is 0.0-1.0.
        """
        score = 0.0
        flags: list[str] = []
        text = content.lower()

        # 2a. GEO-target keyword density
        keyword_hits = sum(1 for kw in _GEO_TARGET_KEYWORDS if kw in text)
        word_count = len(text.split())
        if word_count > 0:
            keyword_density = keyword_hits / (word_count / 100)  # per 100 words
            if keyword_density > 3.0:
                score += 0.5
                flags.append("keyword_stuffing")
            elif keyword_density > 1.5:
                score += 0.2

        # 2b. Title contains multiple GEO-target keywords
        title_lower = title.lower() if title else ""
        title_hits = sum(1 for kw in _GEO_TARGET_KEYWORDS if kw in title_lower)
        if title_hits >= 2:
            score += 0.3

        # 2c. Hidden text detection (CSS-hidden content for AI crawlers)
        if raw_html:
            hidden_count = sum(1 for p in _HIDDEN_TEXT_PATTERNS if p.search(raw_html.lower()))
            if hidden_count >= 2:
                score += 0.5
                flags.append("keyword_stuffing")

        # 2d. Word repetition check (e.g., "SEO SEO SEO SEO")
        words = text.split()
        if len(words) > 50:
            from collections import Counter

            word_freq = Counter(words)
            most_common_ratio = word_freq.most_common(1)[0][1] / len(words)
            if most_common_ratio > 0.05:  # single word > 5% of content
                score += 0.2

        return min(score, 1.0), flags

    # ── Layer 3: Fake Citation Detection ────────────────────────

    def _detect_fake_citations(self, content: str) -> tuple[float, list[str]]:
        """Detect fabricated citations and generic source attributions.

        Returns:
            (score, flags) where score is 0.0-1.0.
        """
        score = 0.0
        flags: list[str] = []

        # 3a. Pattern-matched fake citations
        citation_hits = sum(1 for p in _FAKE_CITATION_PATTERNS if p.search(content))
        if citation_hits >= 3:
            score += 0.6
            flags.append("fake_citation")
        elif citation_hits >= 1:
            score += 0.3

        # 3b. Generic source attributions without real citations
        generic_hits = sum(1 for g in _GENERIC_SOURCES if g.lower() in content.lower())
        # Only flag if many generic sources AND no real links
        has_real_links = bool(re.search(r"https?://[\w./-]+", content))
        if generic_hits >= 2 and not has_real_links:
            score += 0.4
            flags.append("fake_citation")

        # 3c. Citation laundering: content mentions sources but gives no URL/DOI
        has_mentions = bool(re.search(r"(?:study|research|report|paper|journal)", content.lower()))
        has_urls = bool(re.search(r"https?://|doi:", content.lower()))
        if has_mentions and not has_urls and len(content) > 200:
            score += 0.2
            flags.append("citation_laundering")

        return min(score, 1.0), flags

    # ── Layer 4: Prompt Injection Detection ─────────────────────

    def _detect_prompt_injection(self, content: str) -> tuple[bool, list[str]]:
        """Detect hidden prompt injection in web content.

        Returns:
            (detected, flags) — boolean detection and flag list.
        """
        flags: list[str] = []

        for pattern in _PROMPT_INJECTION_PATTERNS:
            if pattern.search(content):
                flags.append("prompt_injection")
                return True, flags

        return False, flags

    # ── Layer 5: Content Farm Detection ─────────────────────────

    def _detect_content_farm(
        self, content: str, metadata: dict[str, object]
    ) -> tuple[float, list[str]]:
        """Detect content farm / mass-generated low-quality content.

        Returns:
            (score, flags) where score is 0.0-1.0.
        """
        score = 0.0
        flags: list[str] = []
        text = content.lower()

        # 5a. Template markers
        template_hits = sum(1 for t in _CONTENT_FARM_TEMPLATES if t in text)
        if template_hits >= 3:
            score += 0.5
            flags.append("content_farm")
        elif template_hits >= 1:
            score += 0.2

        # 5b. Extremely short content with SEO markers (< 100 words + many keywords)
        word_count = len(text.split())
        if word_count < 100 and template_hits >= 2:
            score += 0.3
        elif word_count < 50:
            score += 0.4

        # 5c. Author metadata is generic or missing
        author = str(metadata.get("author", "")).lower()
        if author in ("", "admin", "editor", "staff", "user", "author", "guest"):
            score += 0.1

        return min(score, 1.0), flags

    # ── Layer 6: Source Credibility Assessment ──────────────────

    def _assess_source_credibility(self, url: str, metadata: dict[str, object]) -> float:
        """Score the credibility of a URL's domain.

        Returns:
            1.0 = highly credible, 0.0 = low credibility.
        """
        if not url:
            return 0.5  # Unknown

        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
        except (ValueError, AttributeError):
            return 0.5

        # Check against known lists
        if any(hostname == d or hostname.endswith("." + d) for d in _HIGH_CREDIBILITY_DOMAINS):
            return 0.95

        if any(hostname == d or hostname.endswith("." + d) for d in _LOW_CREDIBILITY_DOMAINS):
            return 0.3

        # Check TLD
        for tld in _AUTHORITATIVE_TLDS:
            if hostname.endswith(tld):
                return 0.85

        # Heuristic scoring
        score = 0.6  # Default: neutral

        # More subdomains = less credible (blog.subdomain.example.com)
        parts = hostname.split(".")
        if len(parts) > 3:
            score -= 0.1

        # Numeric-heavy domains (e.g., 123-best-deals.com) = suspicious
        digit_ratio = sum(1 for c in hostname if c.isdigit()) / max(len(hostname), 1)
        if digit_ratio > 0.15:
            score -= 0.2

        # Very long domains
        if len(hostname) > 30:
            score -= 0.1

        return max(score, 0.1)

    # ── Layer 7: Auto-Translation Detection ─────────────────────

    def _detect_auto_translated(self, content: str) -> tuple[float, list[str]]:
        """Detect machine-translated content via quality markers.

        Returns:
            (score, flags).
        """
        flags: list[str] = []
        marker_hits = sum(1 for m in _AUTO_TRANSLATE_MARKERS if re.search(m, content))
        if marker_hits >= 2:
            flags.append("auto_translated")
            return 0.5, flags
        return 0.0, flags


# ══════════════════════════════════════════════════════════════════
# Convenience Functions
# ══════════════════════════════════════════════════════════════════


# Module-level singleton
_default_guard: GEOGuard | None = None


def get_geo_guard() -> GEOGuard:
    """Get or create the default GEOGuard singleton."""
    global _default_guard
    if _default_guard is None:
        _default_guard = GEOGuard()
    return _default_guard


def assess_geo_risk(item: CollectedItem | CleanedItem) -> GEORiskReport:
    """Convenience: assess GEO risk using the default guard."""
    return get_geo_guard().assess(item)
