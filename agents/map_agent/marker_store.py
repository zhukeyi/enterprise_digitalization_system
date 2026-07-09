"""Marker persistence store — JSON file-based storage for map markers.

Stores markers in ~/.fde_markers.json, providing CRUD operations with
atomic writes (write to temp file, then rename) for crash safety.

Data volume is expected to be small (< 100 entries), so we load/save
the entire file on each operation. No database needed.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from collections import Counter
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from agents.map_agent.models import Marker, MarkerCreate, MarkerUpdate
from agents.map_agent.tag_extractor import extract_tags

logger = logging.getLogger("fde.map.store")

# Default storage location
_DEFAULT_PATH = Path(os.path.expanduser("~/.fde_markers.json"))


class MarkerStore:
    """JSON file-based marker storage with CRUD operations."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_PATH
        self._cache: list[Marker] | None = None

    @property
    def path(self) -> Path:
        return self._path

    # ══════════════════════════════════════════════════════════════════
    # Internal: load / save
    # ══════════════════════════════════════════════════════════════════

    def _load(self) -> list[Marker]:
        """Load all markers from the JSON file. Uses in-memory cache."""
        if self._cache is not None:
            return self._cache

        if not self._path.exists():
            self._cache = []
            return self._cache

        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw) if raw.strip() else []
            self._cache = [Marker(**item) for item in data]
        except (json.JSONDecodeError, TypeError) as e:
            logger.error("Failed to parse %s: %s — starting fresh", self._path, e)
            self._cache = []
        return self._cache

    def _save(self, markers: list[Marker]) -> None:
        """Atomically save markers to JSON file (temp + rename)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = [m.model_dump(mode="json") for m in markers]

        # Write to temp file in same directory, then rename (atomic on POSIX)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._path.parent),
            suffix=".tmp",
            prefix=".fde_markers_",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._path)
        except Exception:
            # Clean up temp file on failure
            with suppress(OSError):
                os.unlink(tmp_path)
            raise

        self._cache = markers

    def _invalidate_cache(self) -> None:
        """Force reload on next _load() call."""
        self._cache = None

    # ══════════════════════════════════════════════════════════════════
    # Public CRUD API
    # ══════════════════════════════════════════════════════════════════

    def list_all(self) -> list[Marker]:
        """Return all markers."""
        return self._load()

    def get(self, marker_id: str) -> Marker | None:
        """Get a single marker by ID."""
        return next((m for m in self._load() if m.id == marker_id), None)

    def create(self, data: MarkerCreate) -> Marker:
        """Create a new marker with auto-extracted tags."""
        tags = extract_tags(data.note) if data.note else []
        now = datetime.now(UTC)
        marker = Marker(
            id=str(uuid.uuid4()),
            name=data.name,
            lng=data.lng,
            lat=data.lat,
            note=data.note,
            tags=tags,
            created_at=now,
            updated_at=now,
        )
        markers = self._load()
        markers.append(marker)
        self._save(markers)
        logger.info("Created marker '%s' (%s) with tags: %s", marker.name, marker.id, tags)
        return marker

    def update(self, marker_id: str, data: MarkerUpdate) -> Marker | None:
        """Update a marker's name and/or note. Re-extracts tags if note changes."""
        markers = self._load()
        marker = next((m for m in markers if m.id == marker_id), None)
        if marker is None:
            return None

        changed = False
        if data.name is not None and data.name != marker.name:
            marker.name = data.name
            changed = True
        if data.note is not None and data.note != marker.note:
            marker.note = data.note
            marker.tags = extract_tags(data.note) if data.note else []
            changed = True

        if changed:
            marker.updated_at = datetime.now(UTC)
            self._save(markers)
            logger.info("Updated marker %s", marker_id)

        return marker

    def delete(self, marker_id: str) -> bool:
        """Delete a marker by ID. Returns True if found and deleted."""
        markers = self._load()
        before = len(markers)
        markers = [m for m in markers if m.id != marker_id]
        if len(markers) < before:
            self._save(markers)
            logger.info("Deleted marker %s", marker_id)
            return True
        return False

    def search(self, query: str) -> list[Marker]:
        """Search markers by name (case-insensitive substring match)."""
        if not query.strip():
            return self._load()
        q = query.lower()
        return [
            m for m in self._load()
            if q in m.name.lower() or q in m.note.lower()
        ]

    def filter_by_tag(self, tag: str) -> list[Marker]:
        """Filter markers that contain the given tag."""
        return [m for m in self._load() if tag in m.tags]

    def get_all_tags(self) -> list[tuple[str, int]]:
        """Return all tags with their counts, sorted by count descending."""
        counter: Counter[str] = Counter()
        for m in self._load():
            for t in m.tags:
                counter[t] += 1
        return sorted(counter.items(), key=lambda x: -x[1])


# ══════════════════════════════════════════════════════════════════
# Singleton accessor
# ══════════════════════════════════════════════════════════════════

_store: MarkerStore | None = None


def get_marker_store() -> MarkerStore:
    """Get the singleton MarkerStore instance."""
    global _store
    if _store is None:
        _store = MarkerStore()
    return _store
