"""Data cleaning pipeline — TRANSFORM stage (M3-T1).

Four-step cleaning pipeline:
  1. Dedup (content hash)
  2. Normalize (strip HTML, trim, field mapping)
  3. PII masking (phone, email, ID card)
  4. Quality scoring (completeness + length + validity)

Each step is a pure method, independently testable.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from agents.data_agent.models import CleanedItem, CollectedItem
from shared.utils.hashing import hash_content

logger = logging.getLogger("fde.data.cleaning")

__all__ = ["CleaningPipeline"]

# ══════════════════════════════════════════════════════════════════
# PII Masking Patterns
# ══════════════════════════════════════════════════════════════════

# Chinese mobile phone: 1[3-9]XXXXXXXXX
_PHONE_PATTERN = re.compile(r"1[3-9]\d{9}")
# Email
_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
# Chinese ID card (18 digits, last may be X)
_ID_CARD_PATTERN = re.compile(r"\d{17}[\dXx]")
# HTML tags
_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


def _mask_phone(text: str) -> tuple[str, bool]:
    """Mask Chinese mobile phone numbers: 13812345678 → 138****5678."""
    masked = False

    def _replace(match: re.Match[str]) -> str:
        nonlocal masked
        masked = True
        phone = match.group()
        return phone[:3] + "****" + phone[7:]

    return _PHONE_PATTERN.sub(_replace, text), masked


def _mask_email(text: str) -> tuple[str, bool]:
    """Mask email addresses: user@example.com → us***@example.com."""
    masked = False

    def _replace(match: re.Match[str]) -> str:
        nonlocal masked
        masked = True
        email = match.group()
        at_idx = email.index("@")
        if at_idx <= 2:
            return email[:1] + "***" + email[at_idx:]
        return email[:2] + "***" + email[at_idx:]

    return _EMAIL_PATTERN.sub(_replace, text), masked


def _mask_id_card(text: str) -> tuple[str, bool]:
    """Mask Chinese ID card numbers: 110101199001011234 → 110101********1234."""
    masked = False

    def _replace(match: re.Match[str]) -> str:
        nonlocal masked
        masked = True
        id_card = match.group()
        return id_card[:6] + "********" + id_card[14:]

    return _ID_CARD_PATTERN.sub(_replace, text), masked


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    return _HTML_TAG_PATTERN.sub("", text).strip()


# ══════════════════════════════════════════════════════════════════
# Quality Scoring
# ══════════════════════════════════════════════════════════════════

# Quality score below which items are discarded
_MIN_QUALITY_THRESHOLD = 0.3

# Quality score weights
_W_COMPLETENESS = 0.4
_W_LENGTH = 0.3
_W_VALIDITY = 0.3

# Expected minimum metadata fields for full validity score
_EXPECTED_METADATA_FIELDS = 5
# Optimal content length range
_OPTIMAL_MIN_LENGTH = 50
_OPTIMAL_MAX_LENGTH = 500


def _assess_quality(title: str, content: str, metadata: dict[str, Any]) -> float:
    """Compute a quality score (0.0-1.0) for a cleaned item.

    Score = completeness (40%) + content length (30%) + validity (30%).

    Args:
        title: Normalized title.
        content: Normalized content.
        metadata: Normalized metadata.

    Returns:
        Quality score between 0.0 and 1.0.
    """
    # Completeness: title and content present
    has_title = 1.0 if title else 0.0
    content_len = len(content)
    has_content = 1.0 if content_len > _OPTIMAL_MIN_LENGTH else content_len / _OPTIMAL_MIN_LENGTH
    completeness = (has_title + has_content) / 2

    # Content length score: optimal range is 50-500 chars
    if content_len < _OPTIMAL_MIN_LENGTH:
        length_score = content_len / _OPTIMAL_MIN_LENGTH * 0.1  # Very short → low score
    elif content_len <= _OPTIMAL_MAX_LENGTH:
        length_score = 1.0
    else:
        # Long content: slight penalty but still good
        length_score = max(0.7, 1.0 - (content_len - _OPTIMAL_MAX_LENGTH) / 5000)

    # Validity: metadata field count
    non_none_count = sum(1 for v in metadata.values() if v is not None and v != "")
    validity = min(non_none_count / _EXPECTED_METADATA_FIELDS, 1.0)

    return round(
        completeness * _W_COMPLETENESS + length_score * _W_LENGTH + validity * _W_VALIDITY, 4
    )


# ══════════════════════════════════════════════════════════════════
# Cleaning Pipeline
# ══════════════════════════════════════════════════════════════════


class CleaningPipeline:
    """Data cleaning pipeline — dedup → normalize → PII mask → quality score.

    Usage:
        pipeline = CleaningPipeline()
        cleaned = pipeline.run(raw_items)
        print(pipeline.duplicate_count)
    """

    def __init__(self) -> None:
        self._seen_hashes: set[str] = set()
        self._duplicate_count: int = 0
        self._pii_masked_count: int = 0

    @property
    def duplicate_count(self) -> int:
        """Number of duplicates removed during the last run."""
        return self._duplicate_count

    @property
    def pii_masked_count(self) -> int:
        """Number of items with PII masked during the last run."""
        return self._pii_masked_count

    def run(self, items: list[CollectedItem]) -> list[CleanedItem]:
        """Execute the full cleaning pipeline.

        Args:
            items: Raw collected items from the EXTRACT stage.

        Returns:
            Cleaned items (may be fewer than input due to dedup and quality filtering).
        """
        self._seen_hashes.clear()
        self._duplicate_count = 0
        self._pii_masked_count = 0

        cleaned: list[CleanedItem] = []

        for item in items:
            # Step 1: Dedup
            if self._is_duplicate(item):
                continue

            # Step 2: Normalize
            title, content, metadata = self._normalize(item)

            # Step 3: PII masking
            content, pii_masked = self._mask_pii(content)
            title, title_masked = self._mask_pii(title)
            item_pii_masked = pii_masked or title_masked
            if item_pii_masked:
                self._pii_masked_count += 1

            # Step 4: Quality scoring
            quality_score = _assess_quality(title, content, metadata)
            if quality_score < _MIN_QUALITY_THRESHOLD:
                logger.warning("Item %s quality too low (%.2f), skipping", item.id, quality_score)
                continue

            cleaned.append(
                CleanedItem(
                    id=item.id,
                    source=item.source,
                    source_url=item.source_url,
                    title=title,
                    content=content,
                    metadata=metadata,
                    quality_score=quality_score,
                    pii_masked=item_pii_masked,
                )
            )

        logger.info(
            "CleaningPipeline: %d input → %d output (duplicates: %d, low quality dropped: %d)",
            len(items),
            len(cleaned),
            self._duplicate_count,
            len(items) - len(cleaned) - self._duplicate_count,
        )
        return cleaned

    def _is_duplicate(self, item: CollectedItem) -> bool:
        """Check if item content has been seen before (hash-based dedup).

        Args:
            item: Collected item to check.

        Returns:
            True if duplicate, False otherwise.
        """
        if not item.content:
            return False
        h = hash_content(item.content)
        if h in self._seen_hashes:
            self._duplicate_count += 1
            return True
        self._seen_hashes.add(h)
        return False

    def _normalize(self, item: CollectedItem) -> tuple[str, str, dict[str, Any]]:
        """Normalize item fields: strip HTML, trim whitespace, filter None values.

        Args:
            item: Collected item to normalize.

        Returns:
            Tuple of (title, content, metadata).
        """
        # Title: trim whitespace
        title = item.title.strip()

        # Content: strip HTML tags if raw_html present, then trim
        if item.raw_html:
            content = _strip_html(item.content)
        else:
            content = item.content.strip()

        # Metadata: remove None and empty string values
        metadata = {str(k): v for k, v in item.metadata.items() if v is not None and v != ""}

        return title, content, metadata

    def _mask_pii(self, text: str) -> tuple[str, bool]:
        """Mask PII in text: phone numbers, emails, ID card numbers.

        Args:
            text: Text to mask.

        Returns:
            Tuple of (masked_text, was_masked).
        """
        if not text:
            return text, False

        masked = False
        text, phone_found = _mask_phone(text)
        masked = masked or phone_found
        text, email_found = _mask_email(text)
        masked = masked or email_found
        text, id_found = _mask_id_card(text)
        masked = masked or id_found

        return text, masked
