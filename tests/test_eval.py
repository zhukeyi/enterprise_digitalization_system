"""Unit tests for the evaluation suite (agents.governance_agent.eval).

Covers:
- GoldenDatasetManager: load/save/validate/merge/summary (~11 tests)
- RagasEvaluator: config/build_dataset/thresholds (~5 tests, LLM mocked)
- PromptfooRunner: config generation/parse_output/is_available (~4 tests, subprocess mocked)
- EvalReportGenerator: to_markdown/to_json (~3 tests)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.governance_agent.eval.golden_dataset import (
    GoldenDataset,
    GoldenDatasetManager,
    GoldenSample,
)
from agents.governance_agent.eval.promptfoo_runner import (
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

# ── Fixtures ────────────────────────────────────────────────────────


def _make_sample(
    sid: str = "s001",
    query: str = "测试问题",
    answer: str = "测试答案",
    contexts: list[str] | None = None,
) -> GoldenSample:
    return GoldenSample(
        id=sid,
        query=query,
        expected_answer=answer,
        contexts=contexts or ["context1"],
        metadata={"category": "test"},
    )


def _make_dataset(
    samples: list[GoldenSample] | None = None,
    name: str = "test_ds",
) -> GoldenDataset:
    return GoldenDataset(
        id="test_ds",
        name=name,
        version="1.0",
        samples=samples if samples is not None else [_make_sample()],
        tags=["test"],
    )


@pytest.fixture
def sample_dataset() -> GoldenDataset:
    return _make_dataset(
        samples=[
            _make_sample("s001", "问题一", "答案一", ["上下文1"]),
            _make_sample("s002", "问题二", "答案二", ["上下文2"]),
            _make_sample("s003", "问题三", "答案三", ["上下文3a", "上下文3b"]),
        ]
    )


@pytest.fixture
def jsonl_file(sample_dataset: GoldenDataset, tmp_path: Path) -> Path:
    """Create a temporary JSONL file from the sample dataset."""
    path = tmp_path / "test_dataset.jsonl"
    GoldenDatasetManager.save(sample_dataset, str(path))
    return path


# ═══════════════════════════════════════════════════════════════════
# GoldenDatasetManager Tests
# ═══════════════════════════════════════════════════════════════════


class TestGoldenDatasetManagerLoad:
    def test_load_valid_dataset(self, jsonl_file: Path) -> None:
        ds = GoldenDatasetManager.load(str(jsonl_file))
        assert ds.id == "test_ds"
        assert ds.name == "test_ds"
        assert len(ds.samples) == 3
        assert ds.samples[0].query == "问题一"

    def test_load_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            GoldenDatasetManager.load("/nonexistent/path.jsonl")

    def test_load_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.jsonl"
        path.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="Empty dataset"):
            GoldenDatasetManager.load(str(path))


class TestGoldenDatasetManagerSave:
    def test_save_and_load_roundtrip(self, sample_dataset: GoldenDataset, tmp_path: Path) -> None:
        path = tmp_path / "roundtrip.jsonl"
        GoldenDatasetManager.save(sample_dataset, str(path))
        loaded = GoldenDatasetManager.load(str(path))
        assert len(loaded.samples) == len(sample_dataset.samples)
        assert loaded.samples[0].id == sample_dataset.samples[0].id

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "nested" / "ds.jsonl"
        ds = _make_dataset()
        GoldenDatasetManager.save(ds, str(path))
        assert path.exists()


class TestGoldenDatasetManagerAddSample:
    def test_add_sample_no_duplicate(self) -> None:
        ds = _make_dataset(samples=[_make_sample("s001", "原始问题")])
        new_sample = _make_sample("s002", "新问题")
        result = GoldenDatasetManager.add_sample(ds, new_sample)
        assert len(result.samples) == 2

    def test_add_sample_with_duplicate_query(self) -> None:
        ds = _make_dataset(samples=[_make_sample("s001", "重复问题")])
        dup_sample = _make_sample("s002", "重复问题")
        result = GoldenDatasetManager.add_sample(ds, dup_sample)
        assert len(result.samples) == 1  # duplicate skipped


class TestGoldenDatasetManagerMerge:
    def test_merge_datasets(self) -> None:
        ds_a = _make_dataset(
            samples=[_make_sample("s001", "问题A"), _make_sample("s002", "问题B")]
        )
        ds_b = GoldenDataset(
            id="ds_b",
            name="ds_b",
            version="1.0",
            samples=[
                _make_sample("s003", "问题C"),
                _make_sample("s004", "问题A"),  # duplicate with ds_a
            ],
            tags=["extra"],
        )
        merged = GoldenDatasetManager.merge(ds_a, ds_b)
        assert len(merged.samples) == 3  # s004 deduped
        assert "extra" in merged.tags


class TestGoldenDatasetManagerValidate:
    def test_validate_valid_dataset(self, sample_dataset: GoldenDataset) -> None:
        errors = GoldenDatasetManager.validate(sample_dataset)
        assert errors == []

    def test_validate_empty_dataset(self) -> None:
        ds = _make_dataset(samples=[])
        errors = GoldenDatasetManager.validate(ds)
        assert any("no samples" in e.lower() for e in errors)

    def test_validate_duplicate_ids(self) -> None:
        ds = _make_dataset(
            samples=[
                _make_sample("dup", "问题A"),
                _make_sample("dup", "问题B"),
            ]
        )
        errors = GoldenDatasetManager.validate(ds)
        assert any("Duplicate sample id" in e for e in errors)

    def test_validate_empty_query(self) -> None:
        ds = _make_dataset(samples=[_make_sample("s001", "  ")])
        errors = GoldenDatasetManager.validate(ds)
        assert any("empty query" in e for e in errors)


class TestGoldenDatasetManagerSummary:
    def test_summary(self, sample_dataset: GoldenDataset) -> None:
        summary = GoldenDatasetManager.summary(sample_dataset)
        assert summary["sample_count"] == 3
        assert summary["avg_query_length"] > 0
        assert "test" in summary["tags"]

    def test_summary_empty_dataset(self) -> None:
        ds = _make_dataset(samples=[])
        summary = GoldenDatasetManager.summary(ds)
        assert summary["sample_count"] == 0


# ═══════════════════════════════════════════════════════════════════
# RagasEvaluator Tests (LLM mocked)
# ═══════════════════════════════════════════════════════════════════


class TestRagasEvaluator:
    def test_config_defaults(self) -> None:
        config = RagasEvalConfig()
        assert "faithfulness" in config.metrics
        assert "answer_relevancy" in config.metrics
        assert config.thresholds["faithfulness"] == 0.70

    @patch("agents.governance_agent.eval.ragas_eval.RagasEvaluator._init_llm")
    def test_evaluate_mismatched_predictions(self, mock_init: MagicMock) -> None:
        evaluator = RagasEvaluator(RagasEvalConfig())
        ds = _make_dataset(samples=[_make_sample()])
        with pytest.raises(ValueError, match="Predictions count"):
            evaluator.evaluate(ds, ["a", "b"])  # 2 predictions for 1 sample

    @patch("agents.governance_agent.eval.ragas_eval.RagasEvaluator._init_llm")
    def test_evaluate_empty_dataset(self, mock_init: MagicMock) -> None:
        evaluator = RagasEvaluator(RagasEvalConfig())
        ds = _make_dataset(samples=[])
        results = evaluator.evaluate(ds, [])
        assert all(r.score == 0.0 for r in results)

    @patch("agents.governance_agent.eval.ragas_eval.RagasEvaluator._init_llm")
    def test_check_thresholds_all_pass(self, mock_init: MagicMock) -> None:
        evaluator = RagasEvaluator()
        results = [
            RagasEvalResult(metric_name="faithfulness", score=0.9, threshold=0.7, passed=True),
            RagasEvalResult(metric_name="answer_relevancy", score=0.8, threshold=0.7, passed=True),
        ]
        assert evaluator.check_thresholds(results) is True

    @patch("agents.governance_agent.eval.ragas_eval.RagasEvaluator._init_llm")
    def test_check_thresholds_one_fail(self, mock_init: MagicMock) -> None:
        evaluator = RagasEvaluator()
        results = [
            RagasEvalResult(metric_name="faithfulness", score=0.9, threshold=0.7, passed=True),
            RagasEvalResult(metric_name="context_recall", score=0.5, threshold=0.6, passed=False),
        ]
        assert evaluator.check_thresholds(results) is False


# ═══════════════════════════════════════════════════════════════════
# PromptfooRunner Tests (subprocess mocked)
# ═══════════════════════════════════════════════════════════════════


class TestPromptfooRunner:
    def test_is_available_no_npx(self) -> None:
        with patch("shutil.which", return_value=None):
            assert PromptfooRunner.is_available() is False

    def test_parse_output_valid(self) -> None:
        raw = json.dumps({
            "results": [
                {"success": True, "prompt": {"raw": "q1"}},
                {"success": False, "prompt": {"raw": "q2"}, "error": "assertion failed"},
            ]
        })
        result = PromptfooRunner.parse_output(raw, duration_ms=500)
        assert result.total == 2
        assert result.passed is False
        assert len(result.failures) == 1
        assert result.failures[0]["error"] == "assertion failed"

    def test_parse_output_empty(self) -> None:
        result = PromptfooRunner.parse_output("", duration_ms=0)
        assert result.passed is True
        assert result.total == 0

    def test_generate_config(self) -> None:
        ds = _make_dataset(
            samples=[_make_sample("s001", "测试问题", "测试答案")]
        )
        config = PromptfooRunner.generate_config(ds)
        assert "providers" in config
        assert "tests" in config
        assert len(config["tests"]) == 1

    def test_run_unavailable(self) -> None:
        with patch.object(PromptfooRunner, "is_available", return_value=False):
            runner = PromptfooRunner("/tmp/fake.yaml")
            result = runner.run()
            assert result.passed is True
            assert result.total == 0


# ═══════════════════════════════════════════════════════════════════
# EvalReportGenerator Tests
# ═══════════════════════════════════════════════════════════════════


class TestEvalReportGenerator:
    @pytest.fixture
    def report(self, sample_dataset: GoldenDataset) -> EvalReport:
        ragas_results = [
            RagasEvalResult(metric_name="faithfulness", score=0.85, threshold=0.70, passed=True),
            RagasEvalResult(metric_name="answer_relevancy", score=0.60, threshold=0.70, passed=False),
        ]
        pf_result = PromptfooResult(passed=True, total=5, failures=[], duration_ms=1200)
        return EvalReportGenerator.generate(ragas_results, pf_result, sample_dataset)

    def test_generate_report(self, report: EvalReport) -> None:
        assert report.overall_pass is False  # answer_relevancy failed
        assert len(report.ragas_results) == 2
        assert report.promptfoo_result.total == 5

    def test_to_markdown(self, report: EvalReport) -> None:
        md = EvalReportGenerator.to_markdown(report)
        assert "# FDE AI Platform 评测报告" in md
        assert "faithfulness" in md
        assert "FAIL" in md  # answer_relevancy failed
        assert "样本数: 3" in md

    def test_to_json(self, report: EvalReport) -> None:
        j = EvalReportGenerator.to_json(report)
        data = json.loads(j)
        assert data["overall_pass"] is False
        assert len(data["ragas_results"]) == 2

    def test_save(self, report: EvalReport, tmp_path: Path) -> None:
        paths = EvalReportGenerator.save(report, str(tmp_path))
        assert Path(paths["markdown"]).exists()
        assert Path(paths["json"]).exists()
        md_content = Path(paths["markdown"]).read_text(encoding="utf-8")
        assert "FDE AI Platform" in md_content
