"""Ragas-based RAG quality evaluation.

Evaluates four core RAG metrics:
- faithfulness: answer grounded in retrieved context (anti-hallucination)
- answer_relevancy: answer relevance to the question
- context_precision: retrieval context precision
- context_recall: retrieval context coverage of ground truth
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from agents.governance_agent.eval.golden_dataset import GoldenDataset

logger = logging.getLogger(__name__)

# Default thresholds — scores below these values are considered failures
_DEFAULT_THRESHOLDS: dict[str, float] = {
    "faithfulness": 0.70,
    "answer_relevancy": 0.70,
    "context_precision": 0.60,
    "context_recall": 0.60,
}

_DEFAULT_METRICS: list[str] = list(_DEFAULT_THRESHOLDS.keys())


# ── Pydantic Models ─────────────────────────────────────────────────


class RagasEvalConfig(BaseModel):
    """Configuration for Ragas evaluation."""

    metrics: list[str] = Field(default_factory=lambda: list(_DEFAULT_METRICS))
    llm_model: str = Field(default="gpt-3.5-turbo", description="LLM model name for Ragas judge")
    llm_base_url: str = Field(
        default="http://localhost:8080/v1",
        description="OpenAI-compatible LLM endpoint (Router Agent)",
    )
    embedding_model: str = Field(
        default="text-embedding-ada-002",
        description="Embedding model name for Ragas",
    )
    embedding_base_url: str = Field(
        default="http://localhost:8080/v1",
        description="OpenAI-compatible embedding endpoint",
    )
    thresholds: dict[str, float] = Field(default_factory=lambda: dict(_DEFAULT_THRESHOLDS))


class RagasEvalResult(BaseModel):
    """Result for a single metric."""

    metric_name: str
    score: float = Field(..., ge=0.0, le=1.0)
    threshold: float = Field(..., ge=0.0, le=1.0)
    passed: bool
    details: list[dict[str, Any]] = Field(default_factory=list)


# ── Evaluator ────────────────────────────────────────────────────────


class RagasEvaluator:
    """Run Ragas evaluation against a GoldenDataset with model predictions."""

    def __init__(self, config: RagasEvalConfig | None = None) -> None:
        self.config = config or RagasEvalConfig()
        self._llm: Any = None
        self._embeddings: Any = None
        self._init_llm()

    def _init_llm(self) -> None:
        """Initialize the LLM backend via langchain_openai, pointing at Router Agent."""
        try:
            from langchain_openai import ChatOpenAI, OpenAIEmbeddings

            self._llm = ChatOpenAI(
                model=self.config.llm_model,
                base_url=self.config.llm_base_url,
                api_key="not-needed",  # Router Agent handles auth internally
                temperature=0,
            )
            self._embeddings = OpenAIEmbeddings(
                model=self.config.embedding_model,
                base_url=self.config.embedding_base_url,
                api_key="not-needed",
            )
            logger.info(
                "Ragas LLM initialised: %s @ %s", self.config.llm_model, self.config.llm_base_url
            )
        except Exception as exc:
            logger.warning(
                "Failed to initialise LLM for Ragas (%s). LLM-dependent metrics will be skipped.",
                exc,
            )
            self._llm = None
            self._embeddings = None

    def evaluate(
        self,
        dataset: GoldenDataset,
        predictions: list[str],
    ) -> list[RagasEvalResult]:
        """Evaluate RAG quality for the given dataset and predictions.

        Args:
            dataset: The golden dataset with ground truth.
            predictions: Model-generated answers, one per sample.

        Returns:
            A list of RagasEvalResult, one per configured metric.
        """
        if len(predictions) != len(dataset.samples):
            raise ValueError(
                f"Predictions count ({len(predictions)}) != samples count ({len(dataset.samples)})"
            )

        if not dataset.samples:
            logger.warning("Empty dataset — returning zero-score results")
            return [
                RagasEvalResult(
                    metric_name=m,
                    score=0.0,
                    threshold=self.config.thresholds.get(m, 0.7),
                    passed=False,
                )
                for m in self.config.metrics
            ]

        ragas_dataset = self._build_ragas_dataset(dataset, predictions)
        results: list[RagasEvalResult] = []

        for metric_name in self.config.metrics:
            result = self._compute_metric(metric_name, ragas_dataset)
            results.append(result)

        return results

    def _build_ragas_dataset(self, dataset: GoldenDataset, predictions: list[str]) -> Any:
        """Build a HuggingFace Dataset in the format Ragas expects."""
        try:
            from datasets import Dataset
        except ImportError as exc:
            raise ImportError(
                "The 'datasets' package is required. Install with: pip install fde-ai-platform[eval]"
            ) from exc

        data = {
            "question": [s.query for s in dataset.samples],
            "answer": predictions,
            "ground_truth": [s.expected_answer for s in dataset.samples],
            "contexts": [s.contexts if s.contexts else [""] for s in dataset.samples],
        }
        return Dataset.from_dict(data)

    def _compute_metric(self, metric_name: str, ragas_dataset: Any) -> RagasEvalResult:
        """Compute a single Ragas metric."""
        threshold = self.config.thresholds.get(metric_name, 0.7)

        if self._llm is None:
            logger.warning("LLM not available — skipping metric '%s'", metric_name)
            return RagasEvalResult(
                metric_name=metric_name,
                score=0.0,
                threshold=threshold,
                passed=False,
                details=[{"warning": "LLM not available, metric skipped"}],
            )

        try:
            from ragas import evaluate as ragas_evaluate
            from ragas.metrics import (
                answer_relevancy,
                context_precision,
                context_recall,
                faithfulness,
            )
        except ImportError as exc:
            raise ImportError(
                "The 'ragas' package is required. Install with: pip install fde-ai-platform[eval]"
            ) from exc

        metric_map = {
            "faithfulness": faithfulness,
            "answer_relevancy": answer_relevancy,
            "context_precision": context_precision,
            "context_recall": context_recall,
        }

        metric = metric_map.get(metric_name)
        if metric is None:
            logger.warning("Unknown metric '%s' — skipping", metric_name)
            return RagasEvalResult(
                metric_name=metric_name,
                score=0.0,
                threshold=threshold,
                passed=False,
                details=[{"warning": f"Unknown metric: {metric_name}"}],
            )

        try:
            ragas_result = ragas_evaluate(
                ragas_dataset,
                metrics=[metric],
                llm=self._llm,
                embeddings=self._embeddings,
            )
            score = float(ragas_result[metric_name])

            # Extract per-sample details
            details: list[dict[str, Any]] = []
            if hasattr(ragas_result, "to_pandas"):
                df = ragas_result.to_pandas()
                if metric_name in df.columns:
                    details = [{metric_name: float(v)} for v in df[metric_name].tolist()]

            return RagasEvalResult(
                metric_name=metric_name,
                score=score,
                threshold=threshold,
                passed=score >= threshold,
                details=details,
            )
        except Exception as exc:
            logger.error("Ragas metric '%s' failed: %s", metric_name, exc)
            return RagasEvalResult(
                metric_name=metric_name,
                score=0.0,
                threshold=threshold,
                passed=False,
                details=[{"error": str(exc)}],
            )

    def check_thresholds(self, results: list[RagasEvalResult]) -> bool:
        """Return True if all metrics meet their thresholds."""
        return all(r.passed for r in results)
