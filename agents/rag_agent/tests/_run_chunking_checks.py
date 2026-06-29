"""Standalone chunking logic checker (avoids heavy module imports)."""
import importlib.util
import sys

# Load module in isolation
spec = importlib.util.spec_from_file_location(
    "chk", "agents/rag_agent/chunking.py"
)
mod = importlib.util.module_from_spec(spec)

class Stub:
    pass

sys.modules["agents"] = Stub()
sys.modules["agents.rag_agent"] = Stub()
spec.loader.exec_module(mod)

FS = mod.FixedSizeChunker
SC = mod.SemanticChunker
RC = mod.RecursiveChunker
D = mod.Document
F = mod.ChunkerFactory
from_chunks = mod.chunk_documents

errors = []

def check(name, condition, msg=""):
    if condition:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}: {msg}")
        errors.append(name)

print("=== FixedSizeChunker ===")
c = FS(100, 20, False)
check("short text single chunk", len(c.chunk_text("Hi")) == 1)
check("long text multiple chunks", len(c.chunk_text("A" * 200)) >= 3)
check("empty text no chunks", c.chunk_text("") == [])
check("whitespace no chunks", c.chunk_text("   ") == [])
check("single char chunking", len(c.chunk_text("ABC")) == 3)

# chunk_document
doc = D(id="t1", content="Hello " * 50, source="/path/test.txt")
chunks = c.chunk_document(doc)
check("chunk_document produces chunks", len(chunks) >= 1)
check("chunk_strategy inherited", chunks[0].chunk_strategy == "fixed_size")
check("parent_document_id set", chunks[0].parent_document_id == "t1")

print("\n=== SemanticChunker ===")
check("paragraph boundary", len(SC(500, 50, False).chunk_text("A.\n\nB.\n\nC.")) >= 2)
check("chinese boundary", len(SC(500, 50, False).chunk_text("一。二。三。")) >= 1)
check("small text single chunk", len(SC(1000).chunk_text("Short.")) == 1)

print("\n=== RecursiveChunker ===")
check("paragraph split", len(RC(500, 50, False).chunk_text("\n\n".join([f"P{i}." for i in range(10)]))) >= 2)
check("fits in one chunk", len(RC(1000).chunk_text("Short doc.")) == 1)
check("long text split", len(RC(50, 10, False).chunk_text("A" * 200)) >= 3)
check("char fallback", len(RC(10, 0, False).chunk_text("ABCDEFGHIJKLMNOPQRSTUVWXYZ")) >= 2)

print("\n=== ChunkerFactory ===")
f = F()
check("create fixed_size", isinstance(f.create("fixed_size"), FS))
check("create semantic", isinstance(f.create("semantic"), SC))
check("create recursive", isinstance(f.create("recursive"), RC))
try:
    f.create("bad")
    check("invalid raises ValueError", False)
except ValueError:
    check("invalid raises ValueError", True)
check("list_strategies contains fixed_size", "fixed_size" in f.list_strategies())
check("list_strategies contains semantic", "semantic" in f.list_strategies())
check("list_strategies contains recursive", "recursive" in f.list_strategies())
c2 = f.create("recursive", 256, 32)
check("chunk_size param honored", c2.chunk_size == 256)
check("chunk_overlap param honored", c2.chunk_overlap == 32)

print("\n=== chunk_documents ===")
chunks = from_chunks([D(id="d1", content="Hello world. " * 20)], "fixed_size", 50, 10, False)
check("single doc produces chunks", len(chunks) >= 2)
chunks2 = from_chunks(
    [D(id="d1", content="A " * 50), D(id="d2", content="B " * 50)],
    "recursive", 100, 20, False
)
check("multiple docs produce chunks", len(chunks2) >= 2)

doc_m = D(id="md", content="Test " * 20)
doc_m.metadata["custom"] = "value"
chunks3 = from_chunks([doc_m], "fixed_size", 100, 0, False)
check("metadata preserved", chunks3[0].metadata.get("custom") == "value")

print("\n=== Validation ===")
try:
    FS(100, 100)
    check("overlap >= size raises ValueError", False)
except ValueError:
    check("overlap >= size raises ValueError", True)

try:
    SC(100, 100)
    check("semantic overlap validation", False)
except ValueError:
    check("semantic overlap validation", True)

try:
    RC(100, 100)
    check("recursive overlap validation", False)
except ValueError:
    check("recursive overlap validation", True)

# Count tokens
ct = mod._count_tokens
check("count_tokens > 0 for text", ct("hello world") > 0)
check("count_tokens == 0 for empty", ct("") == 0)

print(f"\n{'='*30}")
if errors:
    print(f"❌ {len(errors)} failures: {', '.join(errors)}")
    sys.exit(1)
else:
    print("✅ ALL CHECKS PASSED")