"""Conftest for RAG agent tests.

Injects mock modules for heavy optional dependencies (sentence_transformers)
so that tests can patch them without requiring the real packages.

Note: pymupdf is NOT stubbed globally because it pollutes sys.modules for
other test modules. Individual tests that need pymupdf mocking use
patch.dict locally.
"""

from __future__ import annotations

import sys
import types

# Inject a stub `sentence_transformers` module so that
# @patch("sentence_transformers.SentenceTransformer") works even when
# the real package is not installed.
if "sentence_transformers" not in sys.modules:
    st_stub = types.ModuleType("sentence_transformers")
    st_stub.SentenceTransformer = None  # type: ignore[attr-defined]
    sys.modules["sentence_transformers"] = st_stub
