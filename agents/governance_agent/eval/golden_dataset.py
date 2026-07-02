"""Golden Dataset management for RAG evaluation.

Provides Pydantic models and a manager class for loading, saving, validating,
merging and converting golden datasets in JSONL format.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Pydantic Models ─────────────────────────────────────────────────


class GoldenSample(BaseModel):
    """A single evaluation sample."""

    id: str = Field(..., description="Unique sample identifier")
    query: str = Field(..., min_length=1, description="User question / query")
    expected_answer: str = Field(..., min_length=1, description="Ground-truth answer")
    contexts: list[str] = Field(default_factory=list, description="Retrieval contexts")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")


class GoldenDataset(BaseModel):
    """A versioned collection of golden samples."""

    id: str = Field(..., description="Dataset identifier")
    name: str = Field(..., description="Human-readable name")
    version: str = Field(default="1.0", description="Semantic version")
    samples: list[GoldenSample] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO-8601 creation timestamp",
    )
    tags: list[str] = Field(default_factory=list, description="Classification tags")


# ── Manager ──────────────────────────────────────────────────────────


class GoldenDatasetManager:
    """CRUD operations for golden datasets stored as JSONL."""

    @staticmethod
    def load(path: str) -> GoldenDataset:
        """Load a dataset from a JSONL file.

        The first line is the dataset header (id, name, version, tags).
        Subsequent lines are individual samples.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Dataset file not found: {path}")

        lines = file_path.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            raise ValueError(f"Empty dataset file: {path}")

        # First line = dataset header
        header = json.loads(lines[0])
        samples: list[GoldenSample] = []
        for idx, line in enumerate(lines[1:], start=2):
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(GoldenSample.model_validate_json(line))
            except Exception as exc:
                logger.warning("Skipping malformed line %d in %s: %s", idx, path, exc)

        dataset = GoldenDataset(
            id=header.get("id", file_path.stem),
            name=header.get("name", file_path.stem),
            version=header.get("version", "1.0"),
            samples=samples,
            created_at=header.get("created_at", datetime.now(UTC).isoformat()),
            tags=header.get("tags", []),
        )
        return dataset

    @staticmethod
    def save(dataset: GoldenDataset, path: str) -> None:
        """Save a dataset to a JSONL file (header + samples)."""
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        header = {
            "id": dataset.id,
            "name": dataset.name,
            "version": dataset.version,
            "created_at": dataset.created_at,
            "tags": dataset.tags,
        }

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(header, ensure_ascii=False) + "\n")
            for sample in dataset.samples:
                f.write(sample.model_dump_json() + "\n")

    @staticmethod
    def add_sample(dataset: GoldenDataset, sample: GoldenSample) -> GoldenDataset:
        """Add a sample with deduplication based on query hash."""
        existing_hashes = {hashlib.sha256(s.query.encode()).hexdigest() for s in dataset.samples}
        new_hash = hashlib.sha256(sample.query.encode()).hexdigest()

        if new_hash in existing_hashes:
            logger.info("Duplicate query detected, skipping sample %s", sample.id)
            return dataset

        dataset.samples.append(sample)
        return dataset

    @staticmethod
    def merge(dataset_a: GoldenDataset, dataset_b: GoldenDataset) -> GoldenDataset:
        """Merge two datasets, deduplicating by query hash."""
        merged = GoldenDataset(
            id=f"{dataset_a.id}+{dataset_b.id}",
            name=f"{dataset_a.name} (merged)",
            version="1.0",
            samples=list(dataset_a.samples),
            tags=list(set(dataset_a.tags + dataset_b.tags)),
        )

        existing_hashes = {hashlib.sha256(s.query.encode()).hexdigest() for s in merged.samples}

        for sample in dataset_b.samples:
            h = hashlib.sha256(sample.query.encode()).hexdigest()
            if h not in existing_hashes:
                merged.samples.append(sample)
                existing_hashes.add(h)

        return merged

    @staticmethod
    def validate(dataset: GoldenDataset) -> list[str]:
        """Validate dataset integrity. Returns a list of error messages (empty = valid)."""
        errors: list[str] = []

        if not dataset.samples:
            errors.append("Dataset contains no samples")

        seen_ids: set[str] = set()
        seen_queries: set[str] = set()

        for idx, sample in enumerate(dataset.samples):
            # Duplicate ID check
            if sample.id in seen_ids:
                errors.append(f"Duplicate sample id '{sample.id}' at index {idx}")
            seen_ids.add(sample.id)

            # Empty field checks
            if not sample.query.strip():
                errors.append(f"Sample '{sample.id}' has empty query")
            if not sample.expected_answer.strip():
                errors.append(f"Sample '{sample.id}' has empty expected_answer")

            # Duplicate query check
            query_hash = hashlib.sha256(sample.query.encode()).hexdigest()
            if query_hash in seen_queries:
                errors.append(f"Duplicate query in sample '{sample.id}' at index {idx}")
            seen_queries.add(query_hash)

        return errors

    @staticmethod
    def to_ragas_dataset(dataset: GoldenDataset) -> Any:
        """Convert to a HuggingFace Dataset suitable for Ragas evaluation.

        Returns a ``datasets.Dataset`` with columns:
        - question, ground_truth, contexts, answer
        """
        try:
            from datasets import Dataset
        except ImportError as exc:
            raise ImportError(
                "The 'datasets' package is required. Install with: pip install fde-ai-platform[eval]"
            ) from exc

        data = {
            "question": [s.query for s in dataset.samples],
            "ground_truth": [s.expected_answer for s in dataset.samples],
            "contexts": [s.contexts if s.contexts else [""] for s in dataset.samples],
        }
        return Dataset.from_dict(data)

    @staticmethod
    def summary(dataset: GoldenDataset) -> dict[str, Any]:
        """Return statistical summary of the dataset."""
        if not dataset.samples:
            return {
                "sample_count": 0,
                "avg_query_length": 0,
                "avg_answer_length": 0,
                "tags": dataset.tags,
                "version": dataset.version,
            }

        query_lengths = [len(s.query) for s in dataset.samples]
        answer_lengths = [len(s.expected_answer) for s in dataset.samples]

        return {
            "sample_count": len(dataset.samples),
            "avg_query_length": round(sum(query_lengths) / len(query_lengths), 1),
            "avg_answer_length": round(sum(answer_lengths) / len(answer_lengths), 1),
            "min_query_length": min(query_lengths),
            "max_query_length": max(query_lengths),
            "tags": dataset.tags,
            "version": dataset.version,
        }
