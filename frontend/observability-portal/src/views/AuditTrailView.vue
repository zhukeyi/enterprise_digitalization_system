<template>
  <div class="audit-view">
    <div class="view-header">
      <h1 class="page-title">Audit Trail</h1>
      <div class="controls">
        <button class="btn" @click="loadAll">Refresh</button>
        <button class="btn btn-primary" @click="exportCsv">Export CSV</button>
      </div>
    </div>

    <!-- Filters -->
    <div class="filter-bar">
      <input v-model="filters.actor" class="input" placeholder="Actor" />
      <input v-model="filters.action" class="input" placeholder="Action (e.g. api_key.create)" />
      <input v-model="filters.resource_type" class="input" placeholder="Resource type" />
      <select v-model="filters.status" class="select">
        <option value="">Any status</option>
        <option value="ok">OK</option>
        <option value="failed">Failed</option>
      </select>
      <button class="btn" @click="loadAll">Apply</button>
    </div>

    <!-- Summary -->
    <div class="summary-grid">
      <div class="summary-card"><div class="summary-label">Total Events</div><div class="summary-value">{{ logs?.total || 0 }}</div></div>
      <div class="summary-card"><div class="summary-label">Page</div><div class="summary-value">{{ logs?.page || 0 }} / {{ logs?.total_pages || 0 }}</div></div>
      <div class="summary-card"><div class="summary-label">Failed</div><div class="summary-value bad">{{ failedCount }}</div></div>
      <div class="summary-card"><div class="summary-label">Distinct Actors</div><div class="summary-value">{{ actorCount }}</div></div>
    </div>

    <!-- Table -->
    <div class="chart-card">
      <div v-if="loading" class="loading">Loading…</div>
      <table v-else class="data-table">
        <thead>
          <tr><th>Time</th><th>Actor</th><th>Action</th><th>Resource</th><th>Status</th><th>Detail</th></tr>
        </thead>
        <tbody>
          <tr v-for="e in logList" :key="e.event_id">
            <td class="mono">{{ shortTime(e.timestamp) }}</td>
            <td>{{ e.actor }}</td>
            <td><span class="action-pill">{{ e.action }}</span></td>
            <td class="res">{{ e.resource_type }}<span v-if="e.resource_id"> #{{ shortId(e.resource_id) }}</span></td>
            <td><span class="status-pill" :class="e.status">{{ e.status }}</span></td>
            <td class="detail">{{ e.detail || '—' }}</td>
          </tr>
          <tr v-if="logList.length === 0"><td colspan="6" class="empty">No audit events</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue";
import { api } from "../api/client";

const logs = ref<any>(null);
const logList = computed(() => logs.value?.data || []);
const loading = ref(false);
const filters = ref({ actor: "", action: "", resource_type: "", status: "" });
let timer: ReturnType<typeof setInterval> | null = null;

const failedCount = computed(() => logList.value.filter((e: any) => e.status !== "ok").length);
const actorCount = computed(() => new Set(logList.value.map((e: any) => e.actor)).size);

function shortId(id?: string) { return id ? id.slice(0, 8) : "—"; }
function shortTime(ts?: string) { return ts ? ts.slice(11, 19) : "—"; }

async function loadAll() {
  loading.value = true;
  try {
    logs.value = await api.getAuditLogs(1, 50, { ...filters.value });
  } catch (e) { console.error(e); logs.value = { data: [], total: 0, total_pages: 0 }; }
  loading.value = false;
}

async function exportCsv() {
  try {
    const csv = await api.exportAudit({ ...filters.value });
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `fde-audit-${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) { console.error(e); }
}

onMounted(() => { loadAll(); timer = setInterval(loadAll, 30000); });
onUnmounted(() => { if (timer) clearInterval(timer); });
</script>

<style scoped>
.audit-view { max-width: 1100px; }
.view-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-title { font-size: 20px; font-weight: 500; }
.controls { display: flex; gap: 8px; }
.btn { background: var(--bg-tertiary); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: var(--radius-sm); padding: 6px 14px; font-size: 12px; cursor: pointer; }
.btn:hover { border-color: var(--accent-blue); }
.btn-primary { background: var(--accent-blue); color: #0d1117; border-color: var(--accent-blue); font-weight: 500; }

.filter-bar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.input, .select { background: var(--bg-tertiary); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: var(--radius-sm); padding: 6px 10px; font-size: 12px; }
.input { width: 180px; }

.summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
.summary-card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 16px; }
.summary-label { font-size: 11px; color: var(--text-secondary); margin-bottom: 8px; }
.summary-value { font-size: 22px; font-weight: 600; }
.summary-value.bad { color: var(--accent-red); }

.chart-card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 16px; }
.data-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.data-table th { text-align: left; padding: 8px; color: var(--text-secondary); border-bottom: 1px solid var(--border-color); }
.data-table td { padding: 8px; border-bottom: 1px solid var(--border-color); vertical-align: top; }
.mono { font-family: monospace; color: var(--text-tertiary); white-space: nowrap; }
.res { color: var(--text-primary); }
.detail { color: var(--text-secondary); max-width: 320px; }
.loading { color: var(--text-secondary); font-size: 13px; padding: 12px 0; }
.empty { color: var(--text-tertiary); font-size: 13px; text-align: center; padding: 20px; }

.action-pill { background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: 10px; padding: 1px 8px; font-size: 10px; color: var(--accent-purple); }
.status-pill { padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 500; }
.status-pill.ok { background: rgba(63,185,80,0.15); color: var(--accent-green); }
.status-pill.failed { background: rgba(248,81,73,0.15); color: var(--accent-red); }
</style>
