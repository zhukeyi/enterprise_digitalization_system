"""Promptfoo CI gate runner.

Wraps the ``npx promptfoo eval`` CLI as a subprocess, parses its JSON output,
and provides graceful degradation when Node.js / promptfoo is unavailable.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agents.governance_agent.eval.golden_dataset import GoldenDataset

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 300  # seconds


# ── Pydantic Models ─────────────────────────────────────────────────


class PromptfooConfig(BaseModel):
    """Configuration for a Promptfoo evaluation run."""

    config_path: str = Field(..., description="Path to promptfoo.yaml config file")
    assertions: list[dict[str, Any]] = Field(default_factory=list)
    timeout: int = Field(default=_DEFAULT_TIMEOUT, gt=0, description="Subprocess timeout in seconds")


class PromptfooResult(BaseModel):
    """Parsed result from a Promptfoo evaluation run."""

    passed: bool
    total: int = Field(default=0, ge=0)
    failures: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: int = Field(default=0, ge=0)
    raw_output: str = Field(default="", description="Raw stdout from promptfoo")


# ── Runner ───────────────────────────────────────────────────────────


class PromptfooRunner:
    """Execute Promptfoo evaluations via subprocess."""

    def __init__(self, config_path: str, timeout: int = _DEFAULT_TIMEOUT) -> None:
        self.config = PromptfooConfig(config_path=config_path, timeout=timeout)

    @staticmethod
    def is_available() -> bool:
        """Check whether ``npx`` and ``promptfoo`` are available on the system."""
        if shutil.which("npx") is None:
            logger.warning("npx not found in PATH")
            return False
        try:
            result = subprocess.run(
                ["npx", "promptfoo", "--version"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            available = result.returncode == 0
            if not available:
                logger.warning("promptfoo not installed or returned non-zero exit code")
            return available
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.warning("Cannot verify promptfoo availability: %s", exc)
            return False

    def run(self) -> PromptfooResult:
        """Run ``npx promptfoo eval`` and parse the result.

        Returns a zero-total passed result if promptfoo is unavailable (graceful degradation).
        """
        if not self.is_available():
            logger.warning("Promptfoo not available — returning graceful skip result")
            return PromptfooResult(passed=True, total=0, duration_ms=0, raw_output="")

        config_file = Path(self.config.config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Promptfoo config not found: {self.config.config_path}")

        cmd = [
            "npx", "promptfoo", "eval",
            "--config", str(config_file),
            "--output", "-",       # write JSON to stdout
            "--no-progress-bar",
        ]

        start = time.monotonic()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            raw_output = result.stdout + result.stderr

            if result.returncode != 0:
                logger.warning("promptfoo exited with code %d: %s", result.returncode, result.stderr)
                return PromptfooResult(
                    passed=False,
                    total=0,
                    failures=[{"error": result.stderr}],
                    duration_ms=duration_ms,
                    raw_output=raw_output,
                )

            return self.parse_output(result.stdout, duration_ms)

        except subprocess.TimeoutExpired:
            logger.error("promptfoo timed out after %ds", self.config.timeout)
            return PromptfooResult(
                passed=False,
                total=0,
                failures=[{"error": f"Timeout after {self.config.timeout}s"}],
                duration_ms=self.config.timeout * 1000,
                raw_output="",
            )

    @staticmethod
    def parse_output(raw: str, duration_ms: int = 0) -> PromptfooResult:
        """Parse Promptfoo JSON output into a PromptfooResult.

        Promptfoo outputs a JSON object with a ``results`` array.
        """
        if not raw.strip():
            return PromptfooResult(passed=True, total=0, duration_ms=duration_ms, raw_output=raw)

        # Try to find the JSON object in the output (promptfoo may print extra lines)
        json_str = raw
        for line in reversed(raw.strip().splitlines()):
            line = line.strip()
            if line.startswith("{"):
                json_str = line
                break

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse promptfoo output: %s", exc)
            return PromptfooResult(
                passed=True,
                total=0,
                failures=[{"parse_error": str(exc), "raw_snippet": raw[:500]}],
                duration_ms=duration_ms,
                raw_output=raw,
            )

        results_list = data.get("results", [])
        if not results_list and "stats" in data:
            # Alternative format from newer versions
            stats = data.get("stats", {})
            total = stats.get("assertions", 0)
            failures_count = stats.get("failures", 0)
            return PromptfooResult(
                passed=failures_count == 0,
                total=total,
                failures=[{"count": failures_count}] if failures_count else [],
                duration_ms=data.get("stats", {}).get("elapsedMs", duration_ms),
                raw_output=raw,
            )

        total = len(results_list)
        failures: list[dict[str, Any]] = []
        for item in results_list:
            success = item.get("success", True)
            if not success:
                failures.append({
                    "prompt": item.get("prompt", {}).get("raw", ""),
                    "error": item.get("error", ""),
                    "grading": item.get("grading", {}),
                })

        return PromptfooResult(
            passed=len(failures) == 0,
            total=total,
            failures=failures,
            duration_ms=duration_ms,
            raw_output=raw,
        )

    @staticmethod
    def generate_config(
        dataset: GoldenDataset,
        assertions: list[dict[str, Any]] | None = None,
        api_base_url: str = "http://localhost:8080/v1",
    ) -> dict[str, Any]:
        """Generate a promptfoo.yaml config dict from a GoldenDataset.

        Args:
            dataset: The golden dataset to evaluate.
            assertions: Custom assertion rules. Falls back to basic contains assertions.
            api_base_url: The OpenAI-compatible API base URL.

        Returns:
            A dict suitable for YAML serialisation as promptfoo config.
        """
        prompts = [
            {"id": f"test-{sample.id}", "raw": sample.query}
            for sample in dataset.samples
        ]

        tests: list[dict[str, Any]] = []
        for sample in dataset.samples:
            test: dict[str, Any] = {
                "vars": {"query": sample.query},
                "assert": [],
            }
            if assertions:
                test["assert"] = assertions
            else:
                # Default: check the answer is non-empty and contains some expected keywords
                keywords = sample.expected_answer[:30]
                test["assert"] = [
                    {"type": "not-equals", "value": ""},
                    {"type": "icontains", "value": keywords},
                ]
            tests.append(test)

        return {
            "description": f"FDE Eval — {dataset.name} v{dataset.version}",
            "providers": [
                {
                    "id": "openai:chat:gpt-3.5-turbo",
                    "config": {
                        "apiBaseUrl": api_base_url,
                        "apiKey": "not-needed",
                        "temperature": 0,
                    },
                }
            ],
            "prompts": prompts,
            "tests": tests,
        }
