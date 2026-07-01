"""Governance Agent — Evaluation Suite.

Provides RAG quality evaluation via Ragas and Promptfoo integration.

Modules:
- golden_dataset: Golden dataset management (load/save/validate/merge)
- ragas_eval: Ragas-based RAG quality evaluation
- promptfoo_runner: Promptfoo CI gate runner
- report: Evaluation report generation (Markdown/JSON)
- cli: CLI entry point for running the full evaluation suite
"""

from agents.governance_agent.eval.golden_dataset import (
    GoldenDataset,
    GoldenDatasetManager,
    GoldenSample,
)
from agents.governance_agent.eval.promptfoo_runner import (
    PromptfooConfig,
    PromptfooResult,
    PromptfooRunner,
)
from agents.governance_agent.eval.ragas_eval import (
    RagasEvalConfig,
    RagasEvalResult,
    RagasEvaluator,
)
from agents.governance_agent.eval.report import (
    EvalReport,
    EvalReportGenerator,
)

__all__ = [
    "EvalReport",
    "EvalReportGenerator",
    "GoldenDataset",
    "GoldenDatasetManager",
    "GoldenSample",
    "PromptfooConfig",
    "PromptfooResult",
    "PromptfooRunner",
    "RagasEvalConfig",
    "RagasEvalResult",
    "RagasEvaluator",
]
