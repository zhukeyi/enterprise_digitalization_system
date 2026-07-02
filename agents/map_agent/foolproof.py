"""MapAgent foolproof — validation for analysis requests (M3-T11).

Provides pre-flight validation for map analysis operations:
1. Empty entity check: reject analysis with zero entities
2. Minimum entity check: require at least 2 entities for correlation
3. Permission check: verify user has analysis permission
4. Voice input fallback: handle speech recognition failures gracefully
5. Duplicate entity check: warn on duplicate entity IDs

Usage:
    from agents.map_agent.foolproof import validate_analysis_request
    result = validate_analysis_request(entity_ids=["e1", "e2"], user_id="u1")
    if not result.ok:
        raise HTTPException(400, result.message)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("fde.map.foolproof")

__all__ = [
    "FoolproofResult",
    "validate_analysis_request",
    "validate_entity_ids",
    "validate_voice_input",
]


# ══════════════════════════════════════════════════════════════════
# Result Model
# ══════════════════════════════════════════════════════════════════


@dataclass
class FoolproofResult:
    """Result of a foolproof validation check.

    Attributes:
        ok: Whether the validation passed.
        message: Error or warning message (empty if ok).
        severity: 'error' (block), 'warning' (proceed with caution).
        code: Machine-readable error code.
    """

    ok: bool
    message: str = ""
    severity: str = "error"
    code: str = ""


# ══════════════════════════════════════════════════════════════════
# Validators
# ══════════════════════════════════════════════════════════════════


def validate_entity_ids(entity_ids: list[str]) -> FoolproofResult:
    """Validate a list of entity IDs for analysis.

    Checks:
    - Not empty
    - At least 2 entities (for correlation)
    - No duplicates
    - All IDs are non-empty strings
    """
    if not entity_ids:
        return FoolproofResult(
            ok=False,
            message="实体列表为空，请先在地图上标记实体",
            code="EMPTY_ENTITIES",
        )

    if len(entity_ids) < 2:
        return FoolproofResult(
            ok=False,
            message=f"至少需要 2 个实体才能进行关联分析（当前: {len(entity_ids)}）",
            code="INSUFFICIENT_ENTITIES",
        )

    # Check for empty string IDs
    empty_ids = [i for i, eid in enumerate(entity_ids) if not eid or not eid.strip()]
    if empty_ids:
        return FoolproofResult(
            ok=False,
            message=f"存在空的实体 ID（位置: {empty_ids}）",
            code="INVALID_ENTITY_ID",
        )

    # Check for duplicates
    seen: set[str] = set()
    duplicates: list[str] = []
    for eid in entity_ids:
        if eid in seen:
            duplicates.append(eid)
        seen.add(eid)

    if duplicates:
        return FoolproofResult(
            ok=True,
            message=f"存在重复的实体: {duplicates}（将自动去重）",
            severity="warning",
            code="DUPLICATE_ENTITIES",
        )

    return FoolproofResult(ok=True)


def validate_analysis_request(
    entity_ids: list[str],
    user_id: str | None = None,
    user_permissions: list[str] | None = None,
) -> FoolproofResult:
    """Full pre-flight validation for an analysis request.

    Combines entity validation with permission checks.

    Args:
        entity_ids: List of entity IDs to analyze.
        user_id: Optional user ID for permission check.
        user_permissions: Optional list of user permissions.

    Returns:
        FoolproofResult with ok=True if all checks pass.
    """
    # Entity validation
    entity_result = validate_entity_ids(entity_ids)
    if not entity_result.ok:
        return entity_result

    # Permission check (if auth is enabled)
    if (
        user_id is not None
        and user_permissions is not None
        and "map:analysis" not in user_permissions
        and "admin" not in user_permissions
    ):
        return FoolproofResult(
            ok=False,
            message=f"用户 '{user_id}' 没有 map:analysis 权限",
            code="PERMISSION_DENIED",
        )

    # Log warning if we got a warning from entity validation
    if entity_result.severity == "warning":
        logger.warning("Analysis request warning: %s", entity_result.message)

    return entity_result


def validate_voice_input(transcript: str) -> FoolproofResult:
    """Validate voice input transcript before using it as analysis query.

    Handles cases where speech recognition fails or returns garbage.

    Args:
        transcript: The transcribed text from voice input.

    Returns:
        FoolproofResult with ok=True if transcript is usable.
    """
    if not transcript or not transcript.strip():
        return FoolproofResult(
            ok=False,
            message="语音输入为空，请使用文本输入或重新录音",
            code="EMPTY_VOICE_INPUT",
        )

    # Very short transcripts are likely noise
    if len(transcript.strip()) < 2:
        return FoolproofResult(
            ok=False,
            message="语音输入过短，无法识别有效指令",
            code="VOICE_INPUT_TOO_SHORT",
        )

    # Check for repeated characters (common speech recognition artifact)
    stripped = transcript.strip()
    if len(set(stripped)) == 1 and len(stripped) > 3:
        return FoolproofResult(
            ok=False,
            message="语音输入似乎包含重复噪声，请重新录音",
            code="VOICE_INPUT_NOISE",
        )

    return FoolproofResult(ok=True)
