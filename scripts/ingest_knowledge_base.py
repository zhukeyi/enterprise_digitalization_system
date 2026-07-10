"""Ingest FDE platform documentation into the RAG knowledge base.

One-shot admin script (not part of the running service). Builds a
self-documenting knowledge base from the project's own docs so that
rag_search / rag_answer return real, grounded results.

Usage:
    ./venv/bin/python scripts/ingest_knowledge_base.py [collection_name]
"""

from __future__ import annotations

import asyncio
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ensure the package is importable when run directly on the server
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from agents.rag_agent.integration import _rag_ingest_handler  # noqa: E402
from agents.rag_agent import integration as rag_integration  # noqa: E402
from agents.rag_agent.embeddings import EmbeddingConfig, EmbeddingModel  # noqa: E402

# ARM server has few cores; a larger batch size keeps them busy and
# cuts total embedding time significantly. Upserts are idempotent by
# chunk UUID, so re-running is safe.
rag_integration._embedding_model_instance = EmbeddingModel(EmbeddingConfig(batch_size=32))

# High-value, substantive docs only (skip stale "待开发" agent READMEs)
DOC_PATTERNS = [
    os.path.join(ROOT, "docs", "*.md"),
    os.path.join(ROOT, "README.md"),
    os.path.join(ROOT, "frontend", "map-ai", "INTEGRATION.md"),
]


def collect_documents() -> list[dict[str, str]]:
    docs: list[dict[str, str]] = []
    seen: set[str] = set()
    for pattern in DOC_PATTERNS:
        for path in sorted(glob.glob(pattern)):
            abspath = os.path.abspath(path)
            if abspath in seen:
                continue
            seen.add(abspath)
            # Skip empty / placeholder docs
            try:
                if os.path.getsize(abspath) < 50:
                    continue
            except OSError:
                continue
            docs.append({"path": abspath, "format": "auto"})
    return docs


async def main() -> None:
    collection = sys.argv[1] if len(sys.argv) > 1 else "fde_knowledge"
    docs = collect_documents()
    print(f"[ingest] Found {len(docs)} documents for collection '{collection}'")
    for d in docs:
        print("  -", os.path.relpath(d["path"], ROOT))

    result = await _rag_ingest_handler(docs, collection_name=collection)
    print("[ingest] RESULT:", result)


if __name__ == "__main__":
    asyncio.run(main())
