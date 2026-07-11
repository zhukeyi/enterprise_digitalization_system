#!/bin/bash
# P7 Demo Script — FDE AI Platform v4 end-to-end walkthrough
# Usage: bash scripts/demo.sh [host]
# Default host: https://217.142.246.70:8443

set -euo pipefail
HOST="${1:-https://217.142.246.70:8443}"
CURL="curl -sk"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

step() { echo -e "\n${BLUE}=== $1 ===${NC}"; }
ok() { echo -e "${GREEN}  ✓ $1${NC}"; }
fail() { echo -e "${RED}  ✗ $1${NC}"; exit 1; }

echo "FDE AI Platform v4 — Demo Script"
echo "Host: $HOST"

# ══════════════════════════════════════════════════════════════════
# Demo 1: Sync upload + query
# ══════════════════════════════════════════════════════════════════

step "1. Sync upload (CSV)"

TMP=$(mktemp)
cat > "$TMP" <<'EOF'
名称,城市,行业,员工数
云深处,杭州,机器人,200
智谱AI,北京,大模型,800
科大讯飞,合肥,语音技术,12000
宇树科技,杭州,机器人,150
月之暗面,北京,大模型,300
EOF

RESP=$(mktemp)
$CURL -X POST "$HOST/fde-api/ingest/upload" \
  -F "file=@$TMP;filename=demo-data.csv" \
  -F "doc_type=demo" > "$RESP" 2>/dev/null

CANONICAL=$(python3 -c "import json; print(json.load(open('$RESP'))['canonical'])")
CHUNKS=$(python3 -c "import json; print(json.load(open('$RESP'))['chunks'])")
VECTORS=$(python3 -c "import json; print(json.load(open('$RESP'))['indexed_vectors'])")
STORAGE=$(python3 -c "import json; print(json.load(open('$RESP'))['storage_ref'])")

ok "canonical=$CANONICAL chunks=$CHUNKS vectors=$VECTORS"
ok "storage_ref=$STORAGE"
rm "$TMP" "$RESP"

# ══════════════════════════════════════════════════════════════════
# Demo 2: Semantic query
# ══════════════════════════════════════════════════════════════════

step "2. Semantic query (synced data)"

ask() {
  local q="$1" expect="$2"
  RESP=$(mktemp)
  $CURL -X POST "$HOST/fde-api/api/data/ask" \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"$q\",\"top_k\":3,\"doc_type\":\"demo\"}" > "$RESP" 2>/dev/null
  COUNT=$(python3 -c "import json; print(json.load(open('$RESP'))['count'])")
  ANSWER=$(python3 -c "import json; print(json.load(open('$RESP'))['answer'][:100])")
  if echo "$ANSWER" | grep -q "$expect"; then
    ok "\"$q\" → $expect ($COUNT results)"
  else
    fail "\"$q\" → expected '$expect' in answer, got: $ANSWER"
  fi
  rm "$RESP"
}

ask "杭州的机器人公司" "杭州"
ask "语音技术公司" "科大讯飞"
ask "大模型" "北京"

# ══════════════════════════════════════════════════════════════════
# Demo 3: Async upload
# ══════════════════════════════════════════════════════════════════

step "3. Async upload (non-blocking)"

TMP=$(mktemp)
cat > "$TMP" <<'EOF'
名称,产品,类别
DeepSeek,V3,大模型
Kimi,Moonshot,大模型
文心一言,ERNIE,大模型
EOF

RESP=$(mktemp)
$CURL -X POST "$HOST/fde-api/ingest/upload/async" \
  -F "file=@$TMP;filename=demo-ai.csv" \
  -F "doc_type=demo-ai" > "$RESP" 2>/dev/null

TASK_ID=$(python3 -c "import json; print(json.load(open('$RESP'))['task_id'])")
ok "task_id=$TASK_ID (returned immediately)"

# Poll for completion
for i in $(seq 1 10); do
  sleep 1
  STATUS=$(curl -sk "$HOST/fde-api/ingest/tasks/$TASK_ID" 2>/dev/null | python3 -c "import json; print(json.load(open('/dev/stdin'))['status'])")
  if [ "$STATUS" = "completed" ]; then
    ok "Task $TASK_ID → completed after ${i}s"
    break
  fi
  if [ "$i" -eq 10 ]; then
    fail "Task $TASK_ID still $STATUS after 10s"
  fi
done
rm "$TMP" "$RESP"

# ══════════════════════════════════════════════════════════════════
# Demo 4: Idempotency
# ══════════════════════════════════════════════════════════════════

step "4. Idempotency (re-upload same file)"

TMP=$(mktemp)
echo "名称,值" > "$TMP"
echo "测试,123" >> "$TMP"

# First upload
RESP1=$(mktemp)
$CURL -X POST "$HOST/fde-api/ingest/upload" \
  -F "file=@$TMP;filename=dup.csv" \
  -F "doc_type=dup-test" > "$RESP1" 2>/dev/null
C1=$(python3 -c "import json; print(json.load(open('$RESP1'))['canonical'])")
ok "first upload: canonical=$C1"

# Second upload (same file)
RESP2=$(mktemp)
$CURL -X POST "$HOST/fde-api/ingest/upload" \
  -F "file=@$TMP;filename=dup.csv" \
  -F "doc_type=dup-test" > "$RESP2" 2>/dev/null
DUP=$(python3 -c "import json; print(json.load(open('$RESP2')).get('duplicated', False))")
C2=$(python3 -c "import json; print(json.load(open('$RESP2'))['canonical'])")

if [ "$DUP" = "True" ] && [ "$C2" = "0" ]; then
  ok "re-upload: duplicated=true, canonical=0 (no ghost)"
else
  fail "re-upload: duplicated=$DUP canonical=$C2 (expected True/0)"
fi
rm "$TMP" "$RESP1" "$RESP2"

# ══════════════════════════════════════════════════════════════════
# Demo 5: Cache hit
# ══════════════════════════════════════════════════════════════════

step "5. Query cache"

# First query (cold)
RESP=$(mktemp)
$CURL -X POST "$HOST/fde-api/api/data/ask" \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"大模型公司\",\"top_k\":3,\"doc_type\":\"demo\"}" > "$RESP" 2>/dev/null
CACHED1=$(python3 -c "import json; print(json.load(open('$RESP'))['cached'])")
ok "cold query: cached=$CACHED1"

# Second query (hot — same params)
$CURL -X POST "$HOST/fde-api/api/data/ask" \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"大模型公司\",\"top_k\":3,\"doc_type\":\"demo\"}" > "$RESP" 2>/dev/null
CACHED2=$(python3 -c "import json; print(json.load(open('$RESP'))['cached'])")

if [ "$CACHED2" = "True" ]; then
  ok "hot query: cached=true (cache hit)"
else
  fail "hot query: cached=$CACHED2 (expected True)"
fi
rm "$RESP"

# ══════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════

echo ""
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo -e "${GREEN}  All 5 demo scenarios passed!${NC}"
echo -e "${GREEN}  1. Sync upload + query   ✅${NC}"
echo -e "${GREEN}  2. Semantic search        ✅${NC}"
echo -e "${GREEN}  3. Async upload           ✅${NC}"
echo -e "${GREEN}  4. Idempotency            ✅${NC}"
echo -e "${GREEN}  5. Query cache            ✅${NC}"
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo ""
echo "Demo data left in system:"
echo "  doc_type=demo (5 companies)"
echo "  doc_type=demo-ai (3 AI models)"
echo "  doc_type=dup-test (1 test row)"
echo ""
echo "To clean up, use sync upload with empty file (or DELETE /ingest/... when available)."