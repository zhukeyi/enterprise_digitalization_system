"""Evaluation report generation (Markdown and JSON).

Aggregates Ragas and Promptfoo results into a unified EvalReport
with Markdown and JSON export capabilities.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agents.governance_agent.eval.golden_dataset import GoldenDataset
from agents.governance_agent.eval.promptfoo_runner import PromptfooResult
from agents.governance_agent.eval.ragas_eval import RagasEvalResult

logger = logging.getLogger(__name__)


# ── Pydantic Models ─────────────────────────────────────────────────


class EvalReport(BaseModel):
    """Aggregated evaluation report."""

    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO-8601 report generation timestamp",
    )
    ragas_results: list[RagasEvalResult] = Field(default_factory=list)
    promptfoo_result: PromptfooResult = Field(
        default_factory=lambda: PromptfooResult(passed=True, total=0)
    )
    dataset_summary: dict[str, Any] = Field(default_factory=dict)
    overall_pass: bool = Field(default=False, description="True if all evaluations passed")


# ── Report Generator ────────────────────────────────────────────────


class EvalReportGenerator:
    """Generate evaluation reports from Ragas and Promptfoo results."""

    @staticmethod
    def generate(
        ragas_results: list[RagasEvalResult],
        promptfoo_result: PromptfooResult,
        dataset: GoldenDataset,
    ) -> EvalReport:
        """Aggregate results into a unified EvalReport.

        Overall pass = all Ragas metrics pass AND promptfoo pass.
        """
        from agents.governance_agent.eval.golden_dataset import GoldenDatasetManager

        ragas_pass = all(r.passed for r in ragas_results)
        promptfoo_pass = promptfoo_result.passed

        summary = GoldenDatasetManager.summary(dataset)

        return EvalReport(
            ragas_results=ragas_results,
            promptfoo_result=promptfoo_result,
            dataset_summary=summary,
            overall_pass=ragas_pass and promptfoo_pass,
        )

    @staticmethod
    def to_markdown(report: EvalReport) -> str:
        """Render the report as a Markdown document."""
        status = "PASS ✅" if report.overall_pass else "FAIL ❌"
        lines = [
            "# FDE AI Platform 评测报告",
            f"> 生成时间: {report.timestamp}",
            "",
            f"## 总体结论: {status}",
            "",
        ]

        # Ragas section
        if report.ragas_results:
            lines.append("## Ragas 评测 (RAG 质量)")
            lines.append("")
            lines.append("| 指标 | 得分 | 阈值 | 状态 |")
            lines.append("|------|------|------|------|")
            for r in report.ragas_results:
                mark = "PASS ✅" if r.passed else "FAIL ❌"
                lines.append(f"| {r.metric_name} | {r.score:.2f} | {r.threshold:.2f} | {mark} |")
            lines.append("")
        else:
            lines.append("## Ragas 评测 (RAG 质量)")
            lines.append("")
            lines.append("*No Ragas results available.*")
            lines.append("")

        # Promptfoo section
        pf = report.promptfoo_result
        lines.append("## Promptfoo 评测 (端到端)")
        lines.append("")
        if pf.total > 0:
            pf_status = "PASS ✅" if pf.passed else "FAIL ❌"
            lines.append(f"- **状态**: {pf_status}")
            lines.append(
                f"- Total: {pf.total}, Passed: {pf.total - len(pf.failures)}, Failed: {len(pf.failures)}"
            )
            lines.append(f"- Duration: {pf.duration_ms}ms")
            if pf.failures:
                lines.append("")
                lines.append("### 失败详情")
                lines.append("")
                for i, fail in enumerate(pf.failures, 1):
                    prompt = fail.get("prompt", "N/A")
                    error = fail.get("error", "N/A")
                    lines.append(f"{i}. **Prompt**: {prompt[:80]}")
                    lines.append(f"   - Error: {error}")
            lines.append("")
        else:
            lines.append("*Promptfoo not available or no tests executed.*")
            lines.append("")

        # Dataset summary
        lines.append("## 数据集概况")
        lines.append("")
        summary = report.dataset_summary
        lines.append(f"- 样本数: {summary.get('sample_count', 0)}")
        lines.append(f"- 版本: {summary.get('version', 'N/A')}")
        lines.append(f"- 平均 query 长度: {summary.get('avg_query_length', 0)} 字符")
        lines.append(f"- 平均 answer 长度: {summary.get('avg_answer_length', 0)} 字符")
        if summary.get("tags"):
            lines.append(f"- 标签: {', '.join(summary['tags'])}")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def to_json(report: EvalReport) -> str:
        """Render the report as a JSON string."""
        return report.model_dump_json(indent=2)

    @staticmethod
    def save(report: EvalReport, output_dir: str) -> dict[str, str]:
        """Save both Markdown and JSON reports to output_dir.

        Returns a dict mapping format name to file path.
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        md_path = out / "eval_report.md"
        json_path = out / "eval_report.json"

        md_path.write_text(EvalReportGenerator.to_markdown(report), encoding="utf-8")
        json_path.write_text(EvalReportGenerator.to_json(report), encoding="utf-8")

        logger.info("Reports saved: %s, %s", md_path, json_path)
        return {"markdown": str(md_path), "json": str(json_path)}
