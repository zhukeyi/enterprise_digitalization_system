<template>
  <div class="rag-view">
    <div class="view-header">
      <h1 class="page-title">RAG Inspector</h1>
      <div class="controls">
        <select v-model="docTypeFilter" @change="loadDocs" class="select">
          <option value="">All types</option>
          <option value="pdf">PDF</option>
          <option value="docx">DOCX</option>
          <option value="txt">TXT</option>
          <option value="md">Markdown</option>
          <option value="html">HTML</option>
          <option value="web">Web</option>
        </select>
        <button class="btn" @click="loadAll">Refresh</button>
      </div>
    </div>

    <!-- Summary cards -->
    <div class="summary-grid">
      <div class="summary-card">
        <div class="summary-label">Documents</div>
        <div class="summary-value">{{ docs?.total || 0 }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Total Chunks</div>
        <div class="summary-value">{{ totalChunks }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Store Status</div>
        <div class="summary-value" :class="dbAvailable ? 'ok' : 'warn'">
          {{ dbAvailable ? "Connected" : "Unavailable" }}
        </div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Page</div>
        <div class="summary-value">{{ docs?.page || 0 }} / {{ docs?.total_pages || 0 }}</div>
      </div>
    </div>

    <div class="two-column">
      <!-- Document list -->
      <div class="chart-card">
        <h2 class="section-title">Documents</h2>
        <div v-if="docLoading" class="loading">Loading…</div>
        <table v-else class="data-table">
          <thead><tr><th>Title</th><th>Type</th><th>Chunks</th><th></th></tr></thead>
          <tbody>
            <tr
              v-for="d in docList"
              :key="d.doc_id"
              class="doc-row"
              :class="{ selected: selectedDoc?.doc_id === d.doc_id }"
              @click="selectDoc(d)"
            >
              <td class="doc-title">{{ d.title || d.doc_id }}</td>
              <td><span class="type-pill">{{ d.doc_type }}</span></td>
              <td>{{ d.chunk_count }}</td>
              <td><span class="link">View →</span></td>
            </tr>
            <tr v-if="docList.length === 0"><td colspan="4" class="empty">No documents</td></tr>
          </tbody>
        </table>
      </div>

      <!-- Chunk detail / doc actions -->
      <div class="chart-card">
        <div class="section-header-row" v-if="selectedDoc">
          <h2 class="section-title">Chunks — {{ selectedDoc.title || selectedDoc.doc_id }}</h2>
          <div class="actions">
            <button class="btn btn-sm" @click="reindex(selectedDoc.doc_id)" :disabled="busy">Reindex</button>
            <button class="btn btn-sm btn-danger" @click="remove(selectedDoc.doc_id)" :disabled="busy">Delete</button>
          </div>
        </div>
        <h2 class="section-title" v-else>Document Detail</h2>

        <div v-if="chunkLoading" class="loading">Loading chunks…</div>
        <div v-else-if="selectedChunk" class="chunk-detail">
          <div class="kv"><span>Chunk #{{ selectedChunk.chunk_index }}</span><button class="btn btn-sm" @click="selectedChunk = null">← Back</button></div>
          <div class="meta-row">
            <span class="meta-tag">tokens: {{ selectedChunk.token_count }}</span>
            <span class="meta-tag">type: {{ selectedChunk.metadata?.block_kind || 'text' }}</span>
            <span class="meta-tag" v-if="selectedChunk.parent_chunk_id">parent: {{ shortId(selectedChunk.parent_chunk_id) }}</span>
          </div>
          <div class="field-label">Content</div>
          <pre class="chunk-text">{{ selectedChunk.content }}</pre>
          <template v-if="selectedChunk.parent_text">
            <div class="field-label">Parent Text</div>
            <pre class="chunk-text parent">{{ selectedChunk.parent_text }}</pre>
          </template>
          <template v-if="selectedChunk.vector_preview?.length">
            <div class="field-label">Vector Preview (first 10 dims)</div>
            <div class="vector">{{ selectedChunk.vector_preview.join(', ') }}</div>
          </template>
        </div>
        <div v-else-if="chunks?.data?.length">
          <table class="data-table">
            <thead><tr><th>#</th><th>Tokens</th><th>Preview</th><th></th></tr></thead>
            <tbody>
              <tr v-for="c in chunks.data" :key="c.chunk_id" class="chunk-row" @click="openChunk(c.chunk_id)">
                <td>{{ c.chunk_index }}</td>
                <td>{{ c.token_count }}</td>
                <td class="preview">{{ truncate(c.content) }}</td>
                <td><span class="link">Open →</span></td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty">Select a document to inspect its chunks.</div>
      </div>
    </div>

    <!-- Debug retrieve -->
    <div class="chart-card">
      <h2 class="section-title">Debug Retrieve — Query Replay</h2>
      <div class="debug-form">
        <input v-model="query" class="input wide" placeholder="Enter a query to replay retrieval…" @keyup.enter="runRetrieve" />
        <select v-model="retrieveType" class="select">
          <option value="">All types</option>
          <option value="pdf">PDF</option>
          <option value="web">Web</option>
          <option value="txt">TXT</option>
        </select>
        <input v-model.number="topK" type="number" min="1" max="20" class="input narrow" />
        <button class="btn btn-primary" @click="runRetrieve" :disabled="retrieving || !query">Run</button>
      </div>
      <div v-if="retrieveError" class="error-msg">{{ retrieveError }}</div>
      <div v-if="retrieveResult" class="retrieve-result">
        <div class="retrieve-meta">
          <span>rewritten: <em>{{ retrieveResult.rewritten_query }}</em></span>
          <span>latency: {{ retrieveResult.latency_ms }} ms</span>
          <span>candidates: {{ retrieveResult.candidate_count }}</span>
        </div>
        <table class="data-table" v-if="retrieveResult.chunks?.length">
          <thead><tr><th>Rank</th><th>Score</th><th>Title</th><th>Text</th></tr></thead>
          <tbody>
            <tr v-for="r in retrieveResult.chunks" :key="r.id">
              <td>{{ r.rank }}</td>
              <td><span class="score">{{ r.score }}</span></td>
              <td class="doc-title">{{ r.title || '—' }}</td>
              <td class="preview">{{ truncate(r.text) }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">No chunks returned (store may be empty).</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue";
import { api } from "../api/client";

const docTypeFilter = ref("");
const docs = ref<any>(null);
const docList = computed(() => docs.value?.data || []);
const totalChunks = computed(() => docList.value.reduce((s: number, d: any) => s + (d.chunk_count || 0), 0));
const dbAvailable = computed(() => docs.value?.db_available !== false);
const docLoading = ref(false);

const selectedDoc = ref<any>(null);
const chunks = ref<any>(null);
const chunkLoading = ref(false);
const selectedChunk = ref<any>(null);
const busy = ref(false);

const query = ref("");
const retrieveType = ref("");
const topK = ref(5);
const retrieveResult = ref<any>(null);
const retrieveError = ref("");
const retrieving = ref(false);

let timer: ReturnType<typeof setInterval> | null = null;

function shortId(id?: string) { return id ? id.slice(0, 8) : "—"; }
function truncate(s: string) { return s.length > 80 ? s.slice(0, 80) + "…" : s; }

async function loadDocs() {
  docLoading.value = true;
  try {
    docs.value = await api.getRagDocs(1, 20, docTypeFilter.value || undefined);
  } catch (e: any) { console.error(e); docs.value = { data: [], total: 0, total_pages: 0, db_available: false }; }
  docLoading.value = false;
}

async function selectDoc(d: any) {
  selectedDoc.value = d;
  selectedChunk.value = null;
  chunkLoading.value = true;
  chunks.value = null;
  try {
    chunks.value = await api.getRagDocChunks(d.doc_id, 1, 50);
  } catch (e) { console.error(e); chunks.value = { data: [] }; }
  chunkLoading.value = false;
}

async function openChunk(chunkId: string) {
  try {
    selectedChunk.value = await api.getRagChunkDetail(chunkId);
  } catch (e) { console.error(e); }
}

async function reindex(docId: string) {
  busy.value = true;
  try {
    await api.reindexRagDoc(docId);
    await selectDoc(selectedDoc.value);
  } catch (e) { console.error(e); }
  busy.value = false;
}

async function remove(docId: string) {
  if (!confirm(`Delete document ${docId}? This removes Qdrant points and Postgres rows.`)) return;
  busy.value = true;
  try {
    await api.deleteRagDoc(docId);
    selectedDoc.value = null;
    chunks.value = null;
    await loadDocs();
  } catch (e) { console.error(e); }
  busy.value = false;
}

async function runRetrieve() {
  if (!query.value) return;
  retrieving.value = true;
  retrieveError.value = "";
  try {
    retrieveResult.value = await api.retrieveRag(query.value, topK.value, retrieveType.value || undefined);
  } catch (e: any) {
    retrieveError.value = e?.message || "Retrieve failed (Qdrant/embedding may be unavailable)";
    retrieveResult.value = null;
  }
  retrieving.value = false;
}

async function loadAll() { await loadDocs(); }

onMounted(() => { loadAll(); timer = setInterval(loadAll, 30000); });
onUnmounted(() => { if (timer) clearInterval(timer); });
</script>

<style scoped>
.rag-view { max-width: 1100px; }
.view-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-title { font-size: 20px; font-weight: 500; }
.controls { display: flex; gap: 8px; }
.select, .input { background: var(--bg-tertiary); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: var(--radius-sm); padding: 6px 10px; font-size: 12px; }
.input.wide { flex: 1; min-width: 240px; }
.input.narrow { width: 64px; }
.btn { background: var(--bg-tertiary); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: var(--radius-sm); padding: 6px 14px; font-size: 12px; cursor: pointer; }
.btn:hover { border-color: var(--accent-blue); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-sm { padding: 4px 10px; font-size: 11px; }
.btn-primary { background: var(--accent-blue); color: #0d1117; border-color: var(--accent-blue); font-weight: 500; }
.btn-danger { color: var(--accent-red); border-color: var(--accent-red); }
.section-title { font-size: 14px; font-weight: 500; margin-bottom: 12px; }
.section-header-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header-row .section-title { margin-bottom: 0; }
.actions { display: flex; gap: 6px; }

.summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
.summary-card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 16px; }
.summary-label { font-size: 11px; color: var(--text-secondary); margin-bottom: 8px; }
.summary-value { font-size: 22px; font-weight: 600; }
.summary-value.ok { color: var(--accent-green); }
.summary-value.warn { color: var(--accent-yellow); }

.chart-card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 16px; margin-bottom: 20px; }
.two-column { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }

.data-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.data-table th { text-align: left; padding: 8px; color: var(--text-secondary); border-bottom: 1px solid var(--border-color); }
.data-table td { padding: 8px; border-bottom: 1px solid var(--border-color); vertical-align: top; }
.doc-row { cursor: pointer; }
.doc-row:hover, .chunk-row:hover { background: var(--bg-tertiary); }
.doc-row.selected { background: rgba(88,166,255,0.1); }
.doc-title { color: var(--text-primary); max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.type-pill { background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: 10px; padding: 1px 8px; font-size: 10px; color: var(--text-secondary); }
.link { color: var(--accent-blue); font-size: 11px; }
.preview { color: var(--text-secondary); max-width: 280px; }
.loading { color: var(--text-secondary); font-size: 13px; padding: 12px 0; }
.empty { color: var(--text-tertiary); font-size: 13px; text-align: center; padding: 20px; }

.kv { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; font-size: 12px; color: var(--text-secondary); }
.meta-row { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
.meta-tag { background: var(--bg-tertiary); border-radius: 8px; padding: 2px 8px; font-size: 10px; color: var(--text-secondary); }
.field-label { font-size: 11px; color: var(--text-secondary); margin: 12px 0 6px; text-transform: uppercase; letter-spacing: 0.4px; }
.chunk-text { background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 12px; font-size: 12px; line-height: 1.6; white-space: pre-wrap; max-height: 260px; overflow: auto; color: var(--text-primary); }
.chunk-text.parent { color: var(--text-secondary); }
.vector { font-size: 11px; color: var(--accent-cyan); font-family: monospace; word-break: break-all; }

.debug-form { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; }
.retrieve-meta { display: flex; gap: 16px; font-size: 11px; color: var(--text-secondary); margin-bottom: 10px; flex-wrap: wrap; }
.retrieve-meta em { color: var(--accent-purple); font-style: normal; }
.score { color: var(--accent-cyan); font-weight: 600; }
.error-msg { color: var(--accent-red); font-size: 12px; padding: 8px 0; }
</style>
