#!/bin/bash
# P7 Demo Script — FDE AI Platform v4 end-to-end walkthrough
# Usage: bash scripts/demo.sh [host]
# Default host: https://217.142.246.70:8443

set -euo pipefail
HOST="${1:-https://217.142.246.70:8443}"
CURL="curl -sk"
DT="demo-$(date +%s)"  # unique doc_type per run

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

step() { echo -e "\n${BLUE}=== $1 ===${NC}"; }
ok() { echo -e "${GREEN}  ✓ $1${NC}"; }
fail() { echo -e "${RED}  ✗ $1${NC}"; exit 1; }

echo "FDE AI Platform v4 — Demo Script"
echo "Host: $HOST  doc_type: $DT"

# ════════════════════════════════════════════════════════════════
# 1. Sync upload
# ════════════════════════════════════════════════════════════════
step "1. Sync upload (CSV)"

TMP=$(mktemp)
cat > "$TMP" <<EOF
名称,城市,行业,员工数,run_id
云深处,杭州,机器人,200,$DT
智谱AI,北京,大模型,800,$DT
科大讯飞,合肥,语音技术,12000,$DT
宇树科技,杭州,机器人,150,$DT
月之暗面,北京,大模型,300,$DT
EOF

RESP=$(mktemp)
$CURL -X POST "$HOST/fde-api/ingest/upload" \
  -F "file=@$TMP;filename=demo-data.csv" \
  -F "doc_type=$DT" > "$RESP" 2>/dev/null

CANONICAL=$(python3 -c "import json; print(json.load(open('$RESP')).get('canonical',0))")
CHUNKS=$(python3 -c "import json; print(json.load(open('$RESP')).get('chunks',0))")
VECTORS=$(python3 -c "import json; print(json.load(open('$RESP')).get('indexed_vectors',0))")
STORAGE=$(python3 -c "import json; print(json.load(open('$RESP')).get('storage_ref','N/A'))")
DUP=$(python3 -c "import json; print(json.load(open('$RESP')).get('duplicated','N/A'))")

if [ "$DUP" = "True" ]; then
  ok "duplicated=true (already ingested, skipped)"
else
  ok "canonical=$CANONICAL chunks=$CHUNKS vectors=$VECTORS"
fi
[ "$STORAGE" != "N/A" ] && ok "storage_ref=$STORAGE"
rm "$TMP" "$RESP"

# ════════════════════════════════════════════════════════════════
# 2. Semantic query
# ════════════════════════════════════════════════════════════════
step "2. Semantic query"

ask() {
  local q="$1"
  RESP=$(mktemp)
  $CURL -X POST "$HOST/fde-api/api/data/ask" \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"$q\",\"top_k\":5,\"doc_type\":\"$DT\"}" > "$RESP" 2>/dev/null
  COUNT=$(python3 -c "import json; print(json.load(open('$RESP'))['count'])")
  ANSWER=$(python3 -c "import json; print(json.load(open('$RESP'))['answer'][:80])")
  [ "$COUNT" -gt 0 ] && ok "\"$q\" → $COUNT results: $ANSWER..." || fail "\"$q\" → 0 results"
  rm "$RESP"
}

ask "杭州的机器人公司"
ask "语音技术相关公司"
ask "大模型企业"

# ════════════════════════════════════════════════════════════════
# 3. Async upload
# ════════════════════════════════════════════════════════════════
step "3. Async upload"

ADT="${DT}-ai"
TMP=$(mktemp)
cat > "$TMP" <<EOF
名称,产品,类别
DeepSeek,V3,大模型
Moonshot,Kimi,大模型
EOF

RESP=$(mktemp)
$CURL -X POST "$HOST/fde-api/ingest/upload/async" \
  -F "file=@$TMP;filename=demo-ai.csv" \
  -F "doc_type=$ADT" > "$RESP" 2>/dev/null

TASK_ID=$(python3 -c "import json; print(json.load(open('$RESP'))['task_id'])")
ok "task_id=$TASK_ID (returned immediately)"

for i in $(seq 1 15); do
  sleep 1
  STATUS=$(curl -sk "$HOST/fde-api/ingest/tasks/$TASK_ID" 2>/dev/null | python3 -c "import json; print(json.load(open('/dev/stdin'))['status'])")
  [ "$STATUS" = "completed" ] && { ok "Task → completed after ${i}s"; break; }
  [ "$STATUS" = "failed" ] && fail "Task → failed"
  [ "$i" -eq 15 ] && fail "Task still $STATUS after 15s"
done
rm "$TMP" "$RESP"

# query async data
ask_adt() {
  local q="$1"
  RESP=$(mktemp)
  $CURL -X POST "$HOST/fde-api/api/data/ask" \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"$q\",\"top_k\":3,\"doc_type\":\"$ADT\"}" > "$RESP" 2>/dev/null
  COUNT=$(python3 -c "import json; print(json.load(open('$RESP'))['count'])")
  ANSWER=$(python3 -c "import json; print(json.load(open('$RESP'))['answer'][:80])")
  [ "$COUNT" -gt 0 ] && ok "async query \"$q\" → $COUNT results" || fail "async query \"$q\" → 0 results"
  rm "$RESP"
}
ask_adt "DeepSeek"

# ════════════════════════════════════════════════════════════════
# 4. Idempotency
# ════════════════════════════════════════════════════════════════
step "4. Idempotency"

IDT="${DT}-idem"
TMP=$(mktemp)
echo "名称,值,run_id" > "$TMP"
echo "测试,123,$IDT" >> "$TMP"

RESP1=$(mktemp)
$CURL -X POST "$HOST/fde-api/ingest/upload" \
  -F "file=@$TMP;filename=dup.csv" -F "doc_type=$IDT" > "$RESP1" 2>/dev/null

RESP2=$(mktemp)
$CURL -X POST "$HOST/fde-api/ingest/upload" \
  -F "file=@$TMP;filename=dup.csv" -F "doc_type=$IDT" > "$RESP2" 2>/dev/null

DUP2=$(python3 -c "import json;d=json.load(open('$RESP2'));print(d.get('duplicated','N/A'))")
C2=$(python3 -c "import json;d=json.load(open('$RESP2'));print(d.get('canonical','N/A'))")

[ "$DUP2" = "True" ] || [ "$C2" = "0" ] && ok "re-upload: duplicated=$DUP2 canonical=$C2 (idempotent)" || fail "re-upload: duplicated=$DUP2 canonical=$C2 (not idempotent)"
rm "$TMP" "$RESP1" "$RESP2"

# ════════════════════════════════════════════════════════════════
# 5. Cache
# ════════════════════════════════════════════════════════════════
step "5. Query cache"

RESP=$(mktemp)
$CURL -X POST "$HOST/fde-api/api/data/ask" \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"大模型\",\"top_k\":3,\"doc_type\":\"$DT\"}" > "$RESP" 2>/dev/null
C1=$(python3 -c "import json;d=json.load(open('$RESP'));print(d.get('cached',False))")
ok "cold: cached=$C1"

$CURL -X POST "$HOST/fde-api/api/data/ask" \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"大模型\",\"top_k\":3,\"doc_type\":\"$DT\"}" > "$RESP" 2>/dev/null
C2=$(python3 -c "import json;d=json.load(open('$RESP'));print(d.get('cached',False))")
[ "$C2" = "True" ] && ok "hot: cached=True (cache hit ✓)" || fail "hot: cached=$C2 (expected True)"
rm "$RESP"

# ════════════════════════════════════════════════════════════════
echo ""
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo -e "${GREEN}  All 5 demo scenarios passed!${NC}"
echo -e "${GREEN}═══════════════════════════════════════${NC}"