"""Permission-aware RAG search filter (M2-T2).

Filters hybrid search results based on user RBAC/ABAC permissions.
This is a backend hard filter — permission enforcement does NOT rely on LLM prompts.

Filtering logic:
1. User with "admin" role → all results pass (no filtering)
2. User has explicit ABAC Permission entries → filter by resource IDs
3. No permission entries → no results returned (deny by default)

Usage:
    from agents.rag_agent.auth_filter import filter_by_permission

    user = get_current_user(...)
    raw_results = engine.search("query")
    filtered = await filter_by_permission(raw_results, user, db_session)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.governance_agent.database.models import Permission

if TYPE_CHECKING:
    from agents.governance_agent.database.models import User

logger = logging.getLogger("fde.rag.auth_filter")

# ── Resource type constants ────────────────────────────────────────

RESOURCE_KNOWLEDGE_BASE = "knowledge_base"
RESOURCE_DOCUMENT = "document"
RESOURCE_PARAGRAPH = "paragraph"
RESOURCE_COLLECTION = "collection"

# ── Filter result keys used in SearchResult metadata ───────────────

METADATA_COLLECTION_KEY = "collection_id"
METADATA_DOCUMENT_KEY = "document_id"
METADATA_KB_KEY = "kb_id"


# ══════════════════════════════════════════════════════════════════
# Core filter function
# ══════════════════════════════════════════════════════════════════


async def filter_by_permission(
    results: list[dict[str, Any]],
    user: User,
    session: AsyncSession,
) -> list[dict[str, Any]]:
    """Filter search results by user permissions (hard filter).

    Args:
        results: Raw search results from hybrid engine, each dict with at least
                 "source" and optionally "metadata" keys.
        user: The authenticated user (from get_current_user dependency).
        session: Active database session for permission queries.

    Returns:
        Filtered list of results the user is authorized to see.
    """
    if not results:
        return []

    # Admin bypass — no filtering needed
    user_roles: set[str] = set(user.roles or [])
    if "admin" in user_roles:
        logger.debug("Admin user — skipping permission filter")
        return results

    # Collect all resource identifiers from results
    resource_ids = _extract_resource_ids(results)

    if not resource_ids:
        # No identifiable resources in results — deny by default
        logger.warning(
            "No resource IDs found in search results for user=%s, returning empty",
            user.id,
        )
        return []

    # Query user + role permissions for these resources
    permitted_ids = await _get_permitted_resource_ids(
        user_id=user.id,
        roles=user_roles,
        resource_ids=resource_ids,
        session=session,
    )

    if not permitted_ids:
        logger.info("User=%s has no read permissions for current results", user.id)
        return []

    # Filter results
    filtered = _apply_filter(results, permitted_ids)

    logger.debug(
        "Permission filter: %d → %d results (user=%s)",
        len(results),
        len(filtered),
        user.id,
    )
    return filtered


# ══════════════════════════════════════════════════════════════════
# Internal helpers
# ══════════════════════════════════════════════════════════════════


def _extract_resource_ids(results: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Extract (resource_type, resource_id) tuples from search results.

    Scans result metadata for collection_id, document_id, kb_id, or source.
    """
    ids: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for r in results:
        metadata = r.get("metadata", {}) if isinstance(r.get("metadata"), dict) else {}
        source = r.get("source", "")

        # Try metadata keys first
        for meta_key, resource_type in [
            (METADATA_COLLECTION_KEY, RESOURCE_COLLECTION),
            (METADATA_DOCUMENT_KEY, RESOURCE_DOCUMENT),
            (METADATA_KB_KEY, RESOURCE_KNOWLEDGE_BASE),
        ]:
            if meta_key in metadata:
                rid = str(metadata[meta_key])
                pair = (resource_type, rid)
                if pair not in seen:
                    ids.append(pair)
                    seen.add(pair)

        # Fallback: use source as document_id
        if source and source not in ("unknown", ""):
            pair = (RESOURCE_DOCUMENT, source)
            if pair not in seen:
                ids.append(pair)
                seen.add(pair)

    return ids


async def _get_permitted_resource_ids(
    user_id: str,
    roles: set[str],
    resource_ids: list[tuple[str, str]],
    session: AsyncSession,
) -> set[tuple[str, str]]:
    """Query the permissions table for granted resource access.

    Checks:
    - Direct user permissions (subject_type="user", subject_id=user_id)
    - Role-based permissions (subject_type="role", subject_id in roles)
    - All for action="read"
    """
    if not resource_ids:
        return set()

    # Build permission subjects to check
    subjects: list[tuple[str, str]] = [("user", user_id)]
    for role in roles:
        subjects.append(("role", role))

    # Build OR conditions for all (subject_type, subject_id) pairs
    subject_conditions = [
        (Permission.subject_type == st) & (Permission.subject_id == sid) for st, sid in subjects
    ]

    # Build OR conditions for all (resource_type, resource_id) pairs
    resource_conditions = [
        (Permission.resource_type == rt) & (Permission.resource_id == rid)
        for rt, rid in resource_ids
    ]

    if not subject_conditions or not resource_conditions:
        return set()

    # Query: any subject x any resource where action="read"
    result = await session.execute(
        select(Permission.resource_type, Permission.resource_id).where(
            or_(*subject_conditions),
            or_(*resource_conditions),
            Permission.action == "read",
        )
    )
    rows = result.all()

    permitted: set[tuple[str, str]] = set()
    for row in rows:
        permitted.add((row.resource_type, row.resource_id))

    return permitted


def _apply_filter(
    results: list[dict[str, Any]],
    permitted_ids: set[tuple[str, str]],
) -> list[dict[str, Any]]:
    """Filter results to only those with permitted resource IDs."""
    filtered: list[dict[str, Any]] = []

    for r in results:
        metadata = r.get("metadata", {}) if isinstance(r.get("metadata"), dict) else {}
        source = r.get("source", "")

        is_permitted = False

        # Check metadata keys
        for meta_key, resource_type in [
            (METADATA_COLLECTION_KEY, RESOURCE_COLLECTION),
            (METADATA_DOCUMENT_KEY, RESOURCE_DOCUMENT),
            (METADATA_KB_KEY, RESOURCE_KNOWLEDGE_BASE),
        ]:
            if (
                meta_key in metadata
                and (
                    resource_type,
                    str(metadata[meta_key]),
                )
                in permitted_ids
            ):
                is_permitted = True
                break

        # Check source
        if not is_permitted and source and (RESOURCE_DOCUMENT, source) in permitted_ids:
            is_permitted = True

        if is_permitted:
            filtered.append(r)

    return filtered
