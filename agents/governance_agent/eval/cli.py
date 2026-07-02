"""CLI entry point for the FDE evaluation suite.

Usage:
    python -m agents.governance_agent.eval.cli [OPTIONS]

Options:
    --dataset PATH        Path to golden dataset JSONL (default: tests/golden_datasets/rag_basic.jsonl)
    --promptfoo PATH      Path to promptfoo.yaml config (default: tests/promptfoo/promptfoo.yaml)
    --output-dir PATH     Directory for report output (default: eval_reports/)
    --skip-ragas          Skip Ragas evaluation
    --skip-promptfoo      Skip Promptfoo evaluation
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _resolve_path(relative: str) -> str:
    """Resolve a path relative to the project root."""
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    candidate = project_root / relative
    if candidate.exists():
        return str(candidate)
    return relative


def run_eval_suite(
    dataset_path: str | None = None,
    promptfoo_config: str | None = None,
    output_dir: str = "eval_reports",
    skip_ragas: bool = False,
    skip_promptfoo: bool = False,
) -> int:
    """Run the full evaluation suite and return exit code (0=pass, 1=fail)."""
    from agents.governance_agent.eval.golden_dataset import GoldenDatasetManager
    from agents.governance_agent.eval.promptfoo_runner import PromptfooResult, PromptfooRunner
    from agents.governance_agent.eval.ragas_eval import (
        RagasEvalConfig,
        RagasEvalResult,
        RagasEvaluator,
    )
    from agents.governance_agent.eval.report import EvalReportGenerator

    # Resolve defaults
    if dataset_path is None:
        dataset_path = _resolve_path("tests/golden_datasets/rag_basic.jsonl")
    if promptfoo_config is None:
        promptfoo_config = _resolve_path("tests/promptfoo/promptfoo.yaml")

    logger.info("=== FDE AI Platform Evaluation Suite ===")
    logger.info("Dataset: %s", dataset_path)

    # 1. Load dataset
    try:
        dataset = GoldenDatasetManager.load(dataset_path)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Failed to load dataset: %s", exc)
        return 1

    summary = GoldenDatasetManager.summary(dataset)
    logger.info("Loaded %d samples (v%s)", summary["sample_count"], summary["version"])

    errors = GoldenDatasetManager.validate(dataset)
    if errors:
        logger.warning("Dataset validation issues: %s", errors)

    # 2. Ragas evaluation
    ragas_results: list[RagasEvalResult] = []
    if not skip_ragas:
        logger.info("--- Running Ragas evaluation ---")
        config = RagasEvalConfig()
        evaluator = RagasEvaluator(config)

        # Generate mock predictions for dry-run (in production, these come from the RAG pipeline)
        predictions = [s.expected_answer for s in dataset.samples]
        ragas_results = evaluator.evaluate(dataset, predictions)

        for r in ragas_results:
            status = "PASS" if r.passed else "FAIL"
            logger.info(
                "  %s: %.2f (threshold %.2f) [%s]", r.metric_name, r.score, r.threshold, status
            )
    else:
        logger.info("--- Skipping Ragas evaluation ---")

    # 3. Promptfoo evaluation
    promptfoo_result: PromptfooResult = PromptfooResult(passed=True, total=0)
    if not skip_promptfoo:
        logger.info("--- Running Promptfoo evaluation ---")
        runner = PromptfooRunner(promptfoo_config)
        promptfoo_result = runner.run()
        logger.info(
            "  Promptfoo: total=%d, passed=%d, failures=%d",
            promptfoo_result.total,
            promptfoo_result.total - len(promptfoo_result.failures),
            len(promptfoo_result.failures),
        )
    else:
        logger.info("--- Skipping Promptfoo evaluation ---")

    # 4. Generate report
    logger.info("--- Generating report ---")
    report = EvalReportGenerator.generate(ragas_results, promptfoo_result, dataset)
    paths = EvalReportGenerator.save(report, output_dir)
    logger.info("Reports saved to: %s", paths)

    # 5. Summary
    overall = "PASS ✅" if report.overall_pass else "FAIL ❌"
    logger.info("=== Overall: %s ===", overall)

    # Print markdown report to stdout
    print(EvalReportGenerator.to_markdown(report))

    return 0 if report.overall_pass else 1


def main() -> None:
    """CLI argument parser."""
    parser = argparse.ArgumentParser(description="FDE AI Platform Evaluation Suite")
    parser.add_argument("--dataset", type=str, default=None, help="Path to golden dataset JSONL")
    parser.add_argument("--promptfoo", type=str, default=None, help="Path to promptfoo.yaml config")
    parser.add_argument(
        "--output-dir", type=str, default="eval_reports", help="Output directory for reports"
    )
    parser.add_argument("--skip-ragas", action="store_true", help="Skip Ragas evaluation")
    parser.add_argument("--skip-promptfoo", action="store_true", help="Skip Promptfoo evaluation")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    exit_code = run_eval_suite(
        dataset_path=args.dataset,
        promptfoo_config=args.promptfoo,
        output_dir=args.output_dir,
        skip_ragas=args.skip_ragas,
        skip_promptfoo=args.skip_promptfoo,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
