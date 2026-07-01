"""Configurable chunking strategies for document splitting.

M1-T10: Multiple chunking strategies:
- FixedSizeChunker: Token/character-aware fixed-size chunks
- SemanticChunker: Paragraph/sentence boundary-based chunks
- RecursiveChunker: Hierarchical separator-based splitting

All strategies support configurable chunk size, overlap, and token counting.

Document model: Reuses document_parser.Document (Pydantic BaseModel) to avoid
the dual-model problem. A lightweight adapter converts ParsedDocument fields
to the chunker's expected interface.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from agents.rag_agent.document_parser import Document

logger = logging.getLogger("fde.rag.chunking")

# ══════════════════════════════════════════════════════════════════
# Data Models
# ══════════════════════════════════════════════════════════════════


class Chunk:
    """A single chunk produced by a chunker."""

    def __init__(
        self,
        content: str = "",
        metadata: dict[str, Any] | None = None,
        source: str = "",
        mime_type: str = "text/plain",
        chunk_id: str = "",
        chunk_index: int = 0,
        chunk_strategy: str = "",
        parent_document_id: str = "",
        page_number: int | None = None,
    ) -> None:
        self.content = content
        self.metadata = metadata or {}
        self.source = source
        self.mime_type = mime_type
        self.chunk_id = chunk_id
        self.chunk_index = chunk_index
        self.chunk_strategy = chunk_strategy
        self.parent_document_id = parent_document_id
        self.page_number = page_number


# Re-export Document so chunking consumers don't need to import from document_parser
__all__ = [
    "BaseChunker",
    "Chunk",
    "ChunkerFactory",
    "Document",
    "FixedSizeChunker",
    "RecursiveChunker",
    "SemanticChunker",
    "chunk_documents",
]


# ══════════════════════════════════════════════════════════════════
# Shared Helpers
# ══════════════════════════════════════════════════════════════════


def _count_tokens(text: str) -> int:
    """Count approximate tokens in text (~2 chars per token for CJK/English)."""
    if not text:
        return 0
    return max(1, len(text) // 2)


def _generate_chunk_id(doc_id: str, index: int) -> str:
    """Generate a unique chunk ID."""
    return f"{doc_id}:chunk:{index:05d}"


# ══════════════════════════════════════════════════════════════════
# Abstract Base Chunker
# ══════════════════════════════════════════════════════════════════


class BaseChunker(ABC):
    """Abstract base for all chunking strategies."""

    name: str = "base"

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        use_token_count: bool = False,
    ) -> None:
        if chunk_overlap >= chunk_size:
            raise ValueError(f"chunk_overlap ({chunk_overlap}) must be < chunk_size ({chunk_size})")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.use_token_count = use_token_count

    @abstractmethod
    def chunk_text(self, text: str) -> list[str]:
        """Split a single text into chunk strings."""

    def chunk_document(self, document: Document) -> list[Chunk]:
        """Split a Document into Chunks with metadata."""
        text_parts = self.chunk_text(document.content)
        chunks: list[Chunk] = []

        for i, part in enumerate(text_parts):
            part = part.strip()
            if not part:
                continue

            meta = dict(document.metadata)
            meta["chunk_size"] = self.chunk_size
            meta["chunk_overlap"] = self.chunk_overlap
            meta["chunk_strategy"] = self.name
            meta["chunk_token_count"] = _count_tokens(part)

            chunks.append(
                Chunk(
                    chunk_id=_generate_chunk_id(document.id or document.source, i),
                    chunk_index=i,
                    chunk_strategy=self.name,
                    parent_document_id=document.id or document.source,
                    content=part,
                    metadata=meta,
                    source=document.source,
                    mime_type=document.mime_type,
                )
            )

        return chunks

    def _measure(self, text: str) -> int:
        """Measure size of text based on configured method."""
        if self.use_token_count:
            return _count_tokens(text)
        return len(text)


# ══════════════════════════════════════════════════════════════════
# 1. Fixed-Size Chunker
# ══════════════════════════════════════════════════════════════════


class FixedSizeChunker(BaseChunker):
    """Split text into fixed-size chunks with configurable overlap.

    Splits by exact character/token count, breaking at word boundaries
    when possible (space-aware for CJK-friendly splitting).
    """

    name = "fixed_size"

    def chunk_text(self, text: str) -> list[str]:
        if not text.strip():
            return []

        chunks: list[str] = []
        start = 0
        text_len = len(text)

        while start < text_len:
            if self.use_token_count:
                content = self._grow_by_tokens(text, start, self.chunk_size)
            else:
                content = text[start : start + self.chunk_size]

            if not content:
                break

            chunks.append(content)
            content_len = len(content)

            # If this chunk consumed the rest of the text, we're done
            if start + content_len >= text_len:
                break

            # Advance: chunk_size - overlap, at least 1 char
            advance = content_len - self.chunk_overlap
            if advance <= 0:
                advance = 1

            start += advance
            # Clamp to not overshoot
            if start >= text_len:
                break
            start = min(start, text_len)

        return chunks

    def _grow_by_tokens(self, text: str, start: int, target_tokens: int) -> str:
        """Grow content from start until we reach target_tokens."""
        # Binary search-like approach
        low = start
        high = min(start + target_tokens * 4, len(text))  # 4 chars per token estimate

        while low < high:
            mid = (low + high + 1) // 2
            tokens = _count_tokens(text[start:mid])
            if tokens <= target_tokens:
                low = mid
            else:
                high = mid - 1

        return text[start:low]


# ══════════════════════════════════════════════════════════════════
# 2. Semantic Chunker
# ══════════════════════════════════════════════════════════════════


class SemanticChunker(BaseChunker):
    """Split text at semantic boundaries (paragraphs, sentences).

    Preserves natural text structure by splitting at:
    1. Double newlines (paragraphs)
    2. Single newlines
    3. Sentence endings (.!? followed by space)
    4. Last resort: character position
    """

    name = "semantic"

    # Separator priority: highest = most preferred
    SEPARATORS: list[str] = [
        "\n\n",  # Paragraph break
        "\n",  # Line break
        "。",  # Chinese period
        "！",  # Chinese exclamation
        "？",  # Chinese question mark
        ". ",  # English period + space
        "! ",  # English exclamation + space
        "? ",  # English question mark + space
        "；",  # Chinese semicolon
        "；\n",  # Chinese semicolon + newline
    ]

    def chunk_text(self, text: str) -> list[str]:
        if not text.strip():
            return []

        # First split into semantic units (sentences/paragraphs)
        units = self._split_into_units(text)
        if not units:
            return []

        # Merge units into chunks respecting chunk_size
        chunks: list[str] = []
        current_chunk: list[str] = []

        def _flush() -> None:
            merged = "".join(current_chunk)
            if merged.strip():
                chunks.append(merged)
            current_chunk.clear()

        for unit in units:
            unit_stripped = unit.strip()
            if not unit_stripped:
                continue

            candidate = "".join(current_chunk) + unit

            if self._measure(candidate) > self.chunk_size and current_chunk:
                # Flush current, start new with overlap
                overflow = self._compute_overlap(current_chunk)
                _flush()
                current_chunk.extend(overflow)

            current_chunk.append(unit)

        if current_chunk:
            _flush()

        return chunks

    def _split_into_units(self, text: str) -> list[str]:
        """Split text into smallest semantic units."""
        units: list[str] = [text]

        for sep in self.SEPARATORS:
            new_units: list[str] = []
            for unit in units:
                if self._measure(unit) > self.chunk_size * 1.5:
                    split = self._split_by(unit, sep)
                    new_units.extend(split)
                else:
                    new_units.append(unit)
            units = new_units

        return units

    @staticmethod
    def _split_by(text: str, separator: str) -> list[str]:
        """Split text by separator, keeping the separator with the part."""
        if not separator:
            return [text]

        parts = text.split(separator)
        result: list[str] = []

        for i, part in enumerate(parts):
            if not part:
                continue
            if i < len(parts) - 1:
                result.append(part + separator)
            else:
                result.append(part)

        return result

    def _compute_overlap(self, units: list[str]) -> list[str]:
        """Extract trailing content for overlap."""
        if self.chunk_overlap <= 0:
            return []

        overlap_tokens = 0
        overlap_units: list[str] = []

        for unit in reversed(units):
            unit_tokens = self._measure(unit)
            if overlap_tokens + unit_tokens > self.chunk_overlap:
                break
            overlap_units.insert(0, unit)
            overlap_tokens += unit_tokens

        return overlap_units


# ══════════════════════════════════════════════════════════════════
# 3. Recursive Chunker
# ══════════════════════════════════════════════════════════════════


class RecursiveChunker(BaseChunker):
    """Split text recursively using a hierarchy of separators.

    Tries larger separators first, falls back to smaller ones
    when chunks are still too large.

    Separator hierarchy:
        1. "\n\n"   (paragraphs)
        2. "\n"     (lines)
        3. ". "     (sentences)
        4. ""       (characters — last resort)
    """

    name = "recursive"

    SEPARATORS: list[str] = [
        "\n\n",
        "\n",
        ". ",
        "。",
        "! ",
        "？",
        "",
    ]

    def chunk_text(self, text: str) -> list[str]:
        return self._chunk_recursive(text, self.SEPARATORS)

    def _chunk_recursive(self, text: str, separators: list[str]) -> list[str]:
        """Recursively split text using the hierarchy of separators."""
        final_chunks: list[str] = []

        # Base case: text is small enough
        if self._measure(text) <= self.chunk_size:
            return [text] if text.strip() else []

        # No more separators — split by fixed size
        if not separators:
            logger.debug("No more separators, falling back to fixed-size split")
            fixed = FixedSizeChunker(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                use_token_count=self.use_token_count,
            )
            return fixed.chunk_text(text)

        separator = separators[0]

        if separator:
            splits = text.split(separator)
        else:
            # Character-level split (last resort)
            splits = list(text)

        # Merge small splits
        merged: list[str] = []
        buffer = ""

        for split in splits:
            if not split:
                continue

            candidate = buffer + (separator if buffer else "") + split

            if self._measure(candidate) <= self.chunk_size:
                buffer = candidate
            else:
                if buffer:
                    merged.append(buffer)
                buffer = split

        if buffer:
            merged.append(buffer)

        # Recursively split large chunks with next separator level
        for part in merged:
            if self._measure(part) <= self.chunk_size:
                if part.strip():
                    final_chunks.append(part)
            else:
                sub_chunks = self._chunk_recursive(part, separators[1:])
                final_chunks.extend(sub_chunks)

        return final_chunks


# ══════════════════════════════════════════════════════════════════
# Chunker Factory
# ══════════════════════════════════════════════════════════════════


class ChunkerFactory:
    """Factory for creating chunkers by name.

    Usage:
        factory = ChunkerFactory()
        chunker = factory.create("fixed_size", chunk_size=512)
        chunker = factory.create("recursive", chunk_size=256, chunk_overlap=32)
        chunks = chunker.chunk_document(doc)
    """

    STRATEGIES: dict[str, type[BaseChunker]] = {
        "fixed_size": FixedSizeChunker,
        "semantic": SemanticChunker,
        "recursive": RecursiveChunker,
    }

    def create(
        self,
        strategy: str = "recursive",
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        use_token_count: bool = False,
    ) -> BaseChunker:
        """Create a chunker by strategy name.

        Args:
            strategy: One of "fixed_size", "semantic", "recursive"
            chunk_size: Maximum chunk size (tokens or chars)
            chunk_overlap: Overlap between consecutive chunks
            use_token_count: If True, measure by tokens; else by chars

        Returns:
            A BaseChunker instance.

        Raises:
            ValueError: If strategy name is unknown.
        """
        cls = self.STRATEGIES.get(strategy)
        if cls is None:
            raise ValueError(
                f"Unknown chunking strategy '{strategy}'. "
                f"Available: {', '.join(self.STRATEGIES)}"
            )
        return cls(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            use_token_count=use_token_count,
        )

    def list_strategies(self) -> list[str]:
        """List available chunking strategy names."""
        return list(self.STRATEGIES.keys())


# ══════════════════════════════════════════════════════════════════
# Batch Chunking
# ══════════════════════════════════════════════════════════════════


def chunk_documents(
    documents: list[Document],
    strategy: str = "recursive",
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    use_token_count: bool = False,
    **kwargs: Any,
) -> list[Chunk]:
    """Convenience function: chunk multiple documents at once.

    Args:
        documents: List of Document objects.
        strategy: Chunking strategy name.
        chunk_size: Maximum chunk size.
        chunk_overlap: Overlap size.
        **kwargs: Additional options passed to chunker constructor.

    Returns:
        Flattened list of Chunks from all documents.
    """
    factory = ChunkerFactory()
    chunker = factory.create(
        strategy=strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        **kwargs,
    )

    all_chunks: list[Chunk] = []
    for doc in documents:
        chunks = chunker.chunk_document(doc)
        all_chunks.extend(chunks)

    logger.info(
        "Chunked %d documents into %d chunks (strategy=%s)",
        len(documents),
        len(all_chunks),
        strategy,
    )
    return all_chunks
