"""Conflict Detection, Resolution, and Response Generation (M2-T6).

Adds three nodes to the orchestrator graph:
1. ConflictDetector — scans worker outputs for contradictions
2. ConflictResolver — auto-resolves conflicts using rule-based strategies
3. ResponseGenerator — aggregates all worker outputs into a final response

All nodes are pure Python with zero external dependencies.

M2-T6 Review: Enterprise-grade hardening applied — see inline comments.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from langchain_core.messages import AIMessage

from agents.orchestrator.langgraph.state import (
    ConflictReport,
    ConflictResolution,
    OrchestratorState,
)

logger = logging.getLogger("fde.orchestrator.conflict")

# ── Configurable constants (extracted from magic numbers) ─────────

DEFAULT_NUMERIC_CONFLICT_THRESHOLD = 0.5  # 50% difference triggers conflict
DEFAULT_STATUS_EMPTY = "unknown"


def _check_high_risk(risk_workers: list[tuple[str, str]]) -> bool:
    """Check if any risk worker has a high/raw-critical value.

    Handles both string risk levels (e.g. 'high', 'critical') and
    numeric risk levels (e.g. 4, 5). String comparison is case-insensitive.
    """
    for _, risk_str in risk_workers:
        risk_lower = risk_str.lower().strip()
        if risk_lower in ("critical", "high", "4", "5"):
            return True
    return False


# ══════════════════════════════════════════════════════════════════
# Conflict Detector
# ══════════════════════════════════════════════════════════════════


class ConflictDetector:
    """Scans worker outputs for conflicting information.

    Detection rules:
    - Status conflicts: different status conclusions across workers
    - Numeric conflicts: same metric with divergent values (> threshold)
    - Coverage conflicts: one worker finds data, another returns empty
    - Risk conflicts: conflicting risk assessments

    All detection is deterministic — no LLM calls, no external services.
    """

    def __init__(
        self,
        numeric_threshold: float = DEFAULT_NUMERIC_CONFLICT_THRESHOLD,
    ) -> None:
        """Initialize with configurable thresholds.

        Args:
            numeric_threshold: Fraction (0.0-1.0) of max difference to
                trigger a numeric conflict. Default 0.5 = 50%.
        """
        self.numeric_threshold = numeric_threshold

    def __call__(self, state: OrchestratorState) -> dict[str, Any]:
        worker_outputs = state.worker_outputs

        if len(worker_outputs) < 2:
            logger.debug("Only %d worker(s) — skipping conflict detection", len(worker_outputs))
            return {"conflicts": []}

        conflicts: list[ConflictReport] = []

        # ── Rule 1: Status conflicts ────────────────────────────────
        conflicts.extend(self._detect_status_conflicts(worker_outputs))

        # ── Rule 2: Numeric value conflicts ─────────────────────────
        conflicts.extend(self._detect_numeric_conflicts(worker_outputs))

        # ── Rule 3: Data coverage conflicts (found vs not found) ────
        conflicts.extend(self._detect_coverage_conflicts(worker_outputs))

        # ── Rule 4: Risk/severity conflicts ─────────────────────────
        conflicts.extend(self._detect_risk_conflicts(worker_outputs))

        if conflicts:
            logger.info(
                "Detected %d conflicts among %d workers: %s",
                len(conflicts),
                len(worker_outputs),
                [c.description for c in conflicts],
            )
        else:
            logger.debug("No conflicts detected in worker outputs")

        return {"conflicts": conflicts}

    def _detect_status_conflicts(self, outputs: dict[str, Any]) -> list[ConflictReport]:
        """Detect conflicting status fields across workers.

        Uses is-not-None checks (not truthiness) to handle empty/zero status values.
        """
        worker_statuses: list[tuple[str, str]] = []

        for worker_name, output in outputs.items():
            if not isinstance(output, dict):
                continue
            # Use explicit None check, not truthiness (P0 fix)
            for key in ("overall_status", "status"):
                val = output.get(key)
                if val is not None and val != DEFAULT_STATUS_EMPTY:
                    worker_statuses.append((worker_name, str(val)))
                    break

        if len(worker_statuses) < 2:
            return []

        # Detect mismatches: all workers must have the same status
        unique_statuses = {status for _, status in worker_statuses}
        if len(unique_statuses) <= 1:
            return []

        source_workers = [w for w, _ in worker_statuses]
        status_map = dict(worker_statuses)

        return [
            ConflictReport(
                conflict_id=str(uuid.uuid4()),
                source_workers=list(dict.fromkeys(source_workers)),  # unique, order-preserving
                description=f"Conflicting status values: {status_map}",
                severity="medium",
                field="status",
                resolution_strategy="source_priority",
            )
        ]

    def _detect_numeric_conflicts(self, outputs: dict[str, Any]) -> list[ConflictReport]:
        """Detect significant numeric discrepancies across workers."""
        conflicts: list[ConflictReport] = []
        numeric_fields: dict[str, dict[str, float]] = {}

        for worker_name, output in outputs.items():
            if not isinstance(output, dict):
                continue
            for key, value in output.items():
                if isinstance(value, (int, float)) and not key.startswith("_"):
                    numeric_fields.setdefault(key, {})[worker_name] = float(value)

        for field_name, values in numeric_fields.items():
            if len(values) < 2:
                continue
            vals_list = list(values.values())
            min_v, max_v = min(vals_list), max(vals_list)

            # Skip if all values are zero (no meaningful conflict)
            if max_v == 0.0:
                continue

            diff_ratio = (max_v - min_v) / max_v
            if diff_ratio > self.numeric_threshold:
                conflicts.append(
                    ConflictReport(
                        conflict_id=str(uuid.uuid4()),
                        source_workers=list(values.keys()),
                        description=(
                            f"Numeric conflict in '{field_name}': "
                            f"values={values} (diff_ratio={diff_ratio:.2f})"
                        ),
                        severity="medium",
                        field=field_name,
                        resolution_strategy="highest_confidence",
                    )
                )

        return conflicts

    def _detect_coverage_conflicts(self, outputs: dict[str, Any]) -> list[ConflictReport]:
        """Detect when one worker finds data but another doesn't."""
        results_found: list[str] = []
        results_empty: list[str] = []

        for worker_name, output in outputs.items():
            if not isinstance(output, dict):
                continue
            count = self._extract_result_count(output)
            if count is not None:
                # bool is a subclass of int — exclude it explicitly
                if isinstance(count, (int, float)) and not isinstance(count, bool) and count > 0:
                    results_found.append(worker_name)
                else:
                    results_empty.append(worker_name)

        if results_found and results_empty:
            return [
                ConflictReport(
                    conflict_id=str(uuid.uuid4()),
                    source_workers=results_found + results_empty,
                    description=(
                        f"Coverage conflict: workers {results_found} found results "
                        f"but {results_empty} returned empty"
                    ),
                    severity="low",
                    field="total_results",
                    resolution_strategy="merge",
                )
            ]

        return []

    def _detect_risk_conflicts(self, outputs: dict[str, Any]) -> list[ConflictReport]:
        """Detect conflicting risk assessments.

        Uses is-not-None checks (not truthiness) for risk values.
        """
        risk_workers: list[tuple[str, str]] = []

        for worker_name, output in outputs.items():
            if not isinstance(output, dict):
                continue
            # P0 fix: use None check, not truthiness
            for key in ("risk_level", "overall_risk"):
                val = output.get(key)
                if val is not None:
                    risk_workers.append((worker_name, str(val)))
                    break

        if len(risk_workers) < 2:
            return []

        # Detect if risks differ
        unique_risks = {risk for _, risk in risk_workers}
        if len(unique_risks) <= 1:
            return []

        source_workers = [w for w, _ in risk_workers]
        risk_map = dict(risk_workers)

        return [
            ConflictReport(
                conflict_id=str(uuid.uuid4()),
                source_workers=list(dict.fromkeys(source_workers)),
                description=f"Risk level conflict: {risk_map}",
                severity=("high" if _check_high_risk(risk_workers) else "medium"),
                field="risk_level",
                resolution_strategy="highest_confidence",
            )
        ]

    @staticmethod
    def _extract_result_count(output: dict[str, Any]) -> int | float | None:
        """Extract the result count from a worker output dict.

        Tries multiple common key names. Returns None if no count field found.
        """
        for key in ("total_results", "count", "total_matched"):
            if key in output:
                val = output[key]
                if isinstance(val, (int, float)) and not isinstance(val, bool):
                    return val
                return None
        return None


# ══════════════════════════════════════════════════════════════════
# Conflict Resolver
# ══════════════════════════════════════════════════════════════════


class ConflictResolver:
    """Resolves detected conflicts using rule-based strategies.

    Resolution strategies (in priority order):
    1. source_priority — prefer specific workers (e.g., compliance > analysis)
    2. highest_confidence — choose the worker with higher confidence/score
    3. merge — combine results from both workers
    4. auto — pick the first non-empty result

    All strategies are deterministic — no LLM calls, no external services.
    """

    # Worker priority for source_priority strategy (higher = more trusted)
    WORKER_PRIORITY: dict[str, int] = {
        "compliance": 10,
        "governance": 9,
        "rag": 8,
        "data": 7,
        "analysis": 6,
        "hr": 5,
        "business_system": 4,
        "router": 3,
    }

    def __call__(self, state: OrchestratorState) -> dict[str, Any]:
        conflicts = state.conflicts
        if not conflicts:
            return {"conflict_resolutions": [], "conflict_resolved": True}

        resolutions: list[ConflictResolution] = []

        for conflict in conflicts:
            resolution = self._resolve(conflict, state.worker_outputs)
            resolutions.append(resolution)
            logger.debug(
                "Conflict '%s' resolved: strategy=%s chosen=%s",
                conflict.conflict_id[:8],
                conflict.resolution_strategy,
                resolution.chosen_worker,
            )

        return {
            "conflict_resolutions": resolutions,
            "conflict_resolved": all(r.resolved for r in resolutions),
        }

    def _resolve(
        self,
        conflict: ConflictReport,
        worker_outputs: dict[str, Any],
    ) -> ConflictResolution:
        strategy = conflict.resolution_strategy
        workers = conflict.source_workers

        # P0 fix: guard against empty workers list
        if not workers:
            return ConflictResolution(
                conflict_id=conflict.conflict_id,
                resolved=True,
                chosen_worker="",
                chosen_value=None,
                reasoning="No workers to resolve — empty source_workers list",
            )

        if strategy == "source_priority":
            return self._resolve_by_priority(conflict, workers, worker_outputs)
        elif strategy == "highest_confidence":
            return self._resolve_by_confidence(conflict, workers, worker_outputs)
        elif strategy == "merge":
            return self._resolve_by_merge(conflict, workers, worker_outputs)
        else:
            logger.warning(
                "Unknown resolution strategy '%s' for conflict %s — falling back to auto",
                strategy,
                conflict.conflict_id[:8],
            )
            return self._resolve_auto(conflict, workers, worker_outputs)

    def _resolve_by_priority(
        self,
        conflict: ConflictReport,
        workers: list[str],
        outputs: dict[str, Any],
    ) -> ConflictResolution:
        """Choose the highest-priority worker's output."""
        # P0 fix: workers list already validated by _resolve()
        ranked = sorted(
            workers,
            key=lambda w: self.WORKER_PRIORITY.get(w, 0),
            reverse=True,
        )
        chosen = ranked[0]
        chosen_output = outputs.get(chosen, {})
        value = (
            chosen_output.get(conflict.field)
            if conflict.field and isinstance(chosen_output, dict)
            else chosen_output
        )

        return ConflictResolution(
            conflict_id=conflict.conflict_id,
            resolved=True,
            chosen_worker=chosen,
            chosen_value=value,
            reasoning=f"Source priority: {chosen} (priority={self.WORKER_PRIORITY.get(chosen, 0)})",
        )

    def _resolve_by_confidence(
        self,
        conflict: ConflictReport,
        workers: list[str],
        outputs: dict[str, Any],
    ) -> ConflictResolution:
        """Choose the worker with the highest confidence score.

        If no worker has a confidence/score field, falls back to the
        first worker in the list (P1 fix: explicit fallback).
        """
        best_worker = None
        best_confidence = -1.0  # Start below 0 so any score wins

        for worker in workers:
            output = outputs.get(worker, {})
            if not isinstance(output, dict):
                continue
            conf = self._extract_confidence(output)
            if conf is not None and conf > best_confidence:
                best_confidence = conf
                best_worker = worker

        # P1 fix: explicit fallback when no confidence found
        if best_worker is None:
            best_worker = workers[0]
            chosen_output = outputs.get(best_worker, {})
            value = (
                chosen_output.get(conflict.field)
                if conflict.field and isinstance(chosen_output, dict)
                else chosen_output
            )
            return ConflictResolution(
                conflict_id=conflict.conflict_id,
                resolved=True,
                chosen_worker=best_worker,
                chosen_value=value,
                reasoning=f"No confidence scores found — fallback to first worker '{best_worker}'",
            )

        chosen_output = outputs.get(best_worker, {})
        value = (
            chosen_output.get(conflict.field)
            if conflict.field and isinstance(chosen_output, dict)
            else chosen_output
        )

        return ConflictResolution(
            conflict_id=conflict.conflict_id,
            resolved=True,
            chosen_worker=best_worker,
            chosen_value=value,
            reasoning=f"Highest confidence: {best_worker} (confidence={best_confidence:.2f})",
        )

    def _resolve_by_merge(
        self,
        conflict: ConflictReport,
        workers: list[str],
        outputs: dict[str, Any],
    ) -> ConflictResolution:
        """Merge results from all workers.

        P0 fix: deep-copy entries instead of mutating original dicts in-place.
        """
        merged: dict[str, Any] = {
            "sources": list(workers),
            "merged_items": [],
        }

        for worker in workers:
            output = outputs.get(worker, {})
            if not isinstance(output, dict):
                continue
            entries = self._extract_entries(output)
            if entries and isinstance(entries, list):
                # P0 fix: copy each entry instead of mutating the original
                for entry in entries:
                    tagged_entry = dict(entry) if isinstance(entry, dict) else entry
                    if isinstance(tagged_entry, dict):
                        tagged_entry["_source_worker"] = worker
                    merged["merged_items"].append(tagged_entry)

        merged["total_merged"] = len(merged["merged_items"])

        return ConflictResolution(
            conflict_id=conflict.conflict_id,
            resolved=True,
            chosen_worker=workers[0],
            chosen_value=merged,
            reasoning=f"Merged results from {len(workers)} workers",
        )

    def _resolve_auto(
        self,
        conflict: ConflictReport,
        workers: list[str],
        outputs: dict[str, Any],
    ) -> ConflictResolution:
        """Automatic resolution: pick first non-empty output."""
        for worker in workers:
            value = outputs.get(worker)
            if value is not None:
                return ConflictResolution(
                    conflict_id=conflict.conflict_id,
                    resolved=True,
                    chosen_worker=worker,
                    chosen_value=(
                        value.get(conflict.field)
                        if conflict.field and isinstance(value, dict)
                        else value
                    ),
                    reasoning=f"Auto: first non-empty result from '{worker}'",
                )

        return ConflictResolution(
            conflict_id=conflict.conflict_id,
            resolved=True,
            chosen_worker="",
            chosen_value=None,
            reasoning="Auto: all outputs are None/empty",
        )

    @staticmethod
    def _extract_confidence(output: dict[str, Any]) -> float | None:
        """Extract confidence score from worker output.

        Returns None if no confidence/score field found.
        """
        for key in ("confidence", "score"):
            val = output.get(key)
            if val is not None and isinstance(val, (int, float)):
                return float(val)
        return None

    @staticmethod
    def _extract_entries(output: dict[str, Any]) -> list[Any] | None:
        """Extract result entries from worker output.

        Tries multiple common key names.
        """
        for key in ("entries", "results", "sample"):
            val = output.get(key)
            if val is not None and isinstance(val, list):
                return val
        return None


# ══════════════════════════════════════════════════════════════════
# Response Generator
# ══════════════════════════════════════════════════════════════════


class ResponseGenerator:
    """Generates a natural language response from worker outputs + conflict resolutions.

    This is a deterministic, template-based aggregator. It produces a coherent
    final response without requiring an LLM call — fully local, zero QPS limit.
    """

    # Known healthy/positive status values for verdict classification
    HEALTHY_STATUSES: frozenset[str] = frozenset(
        {
            "healthy",
            "compliant",
            "pass",
            "completed",
            "ok",
            "success",
            "running",
        }
    )

    # Known warning/degraded values
    WARNING_STATUSES: frozenset[str] = frozenset(
        {
            "degraded",
            "warning",
            "partial",
        }
    )

    # Known critical/non-compliant values
    CRITICAL_STATUSES: frozenset[str] = frozenset(
        {
            "critical",
            "non_compliant",
            "error",
            "down",
            "failed",
        }
    )

    def __call__(self, state: OrchestratorState) -> dict[str, Any]:
        outputs = state.worker_outputs
        conflicts = state.conflicts
        resolutions = state.conflict_resolutions
        plan = state.plan

        parts: list[str] = []

        # ── Section 1: Summary of what was done ────────────────────
        if plan and plan.steps:
            parts.append(self._format_summary(plan, outputs))
        else:
            parts.append("已处理您的请求。")

        # ── Section 2: Worker results ──────────────────────────────
        if outputs:
            parts.append(self._format_results(outputs))

        # ── Section 3: Conflict notes (if any) ─────────────────────
        if conflicts and resolutions:
            parts.append(self._format_conflicts(conflicts, resolutions))

        # ── Section 4: Final verdict ───────────────────────────────
        parts.append(self._format_verdict(outputs))

        final_response = "\n\n".join(parts)

        # P0 fix: wrap in AIMessage instead of raw string
        return {
            "final_response": final_response,
            "messages": [AIMessage(content=final_response)],
        }

    def _format_summary(
        self,
        plan: Any,
        outputs: dict[str, Any],
    ) -> str:
        """Format the execution summary."""
        workers_called = list(outputs.keys())
        worker_names = ", ".join(workers_called) if workers_called else "无"
        return (
            f"**执行摘要**：调用了 {len(workers_called)} 个智能体（{worker_names}）处理您的请求。"
        )

    def _format_results(
        self,
        outputs: dict[str, Any],
    ) -> str:
        """Format individual worker results.

        P2 fix: removed unused `resolutions` parameter.
        """
        lines: list[str] = ["**各智能体输出**："]

        for worker_name, output in outputs.items():
            if not isinstance(output, dict):
                lines.append(f"- **{worker_name}**: {output}")
                continue

            main_content = self._describe_worker_output(output)
            lines.append(f"- **{worker_name}**: {main_content}")

        return "\n".join(lines)

    def _describe_worker_output(self, output: dict[str, Any]) -> str:
        """Produce a human-readable one-line summary of a worker's output."""
        if "note" in output:
            return self._extract_key_info(output)

        if "sample" in output:
            count = output.get("count")
            return f"查询到 {count if count is not None else '?'} 条记录"

        status = output.get("overall_status") or output.get("status")
        if status is not None:
            return f"状态: {status}"

        if "total_matched" in output:
            return f"匹配 {output.get('total_matched', 0)} 条记录"

        # Fallback: list keys
        keys = [k for k in output if not k.startswith("_") and k != "note"]
        return f"返回字段: {keys[:5]}" if keys else "已执行完成"

    @staticmethod
    def _extract_key_info(output: dict[str, Any]) -> str:
        """Extract the most informative field from a worker output."""
        for key in ("overall_status", "status", "message", "total_matched", "count"):
            val = output.get(key)
            if val is not None and val != "":
                return str(val)
        return "处理完成"

    def _format_conflicts(
        self,
        conflicts: list[ConflictReport],
        resolutions: list[ConflictResolution],
    ) -> str:
        """Format conflict resolution information."""
        lines: list[str] = [f"**冲突处理**（检测到 {len(conflicts)} 个冲突）："]

        for i, (conflict, resolution) in enumerate(zip(conflicts, resolutions, strict=True)):
            lines.append(
                f"{i + 1}. {conflict.description} → "
                f"采用 '{resolution.chosen_worker}' 的结果"
                f"（{resolution.reasoning}）"
            )

        return "\n".join(lines)

    def _format_verdict(self, outputs: dict[str, Any]) -> str:
        """Format the final verdict based on overall system status.

        P1 fix: uses pre-defined status sets instead of hardcoded lists
        for extensibility and correctness.
        """
        if not outputs:
            return "请求处理完成，当前无需调用智能体。如有进一步问题请继续提问。"

        statuses: list[str] = []
        for output in outputs.values():
            if not isinstance(output, dict):
                continue
            st = output.get("overall_status") or output.get("status")
            if st is not None and st != "":
                statuses.append(str(st))

        if not statuses:
            return "请求处理完成，请查看上述结果。如有疑问请继续提问。"

        if all(s in self.HEALTHY_STATUSES for s in statuses):
            return "✅ 所有检查均正常，系统运行良好。"
        if any(s in self.CRITICAL_STATUSES for s in statuses):
            return "⚠️ 检测到严重问题，建议立即查看上述详情并采取行动。"
        if any(s in self.WARNING_STATUSES for s in statuses):
            return "⚠️ 部分组件存在告警，请查看上述详情。"

        return "请求处理完成。"
