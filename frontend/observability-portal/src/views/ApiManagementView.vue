<template>
  <div class="api-view">
    <div class="view-header">
      <h1 class="page-title">API Management</h1>
      <div class="controls">
        <input v-model="searchQuery" placeholder="Search endpoints..." class="input" />
        <select v-model="moduleFilter" class="select">
          <option value="">All Modules</option>
          <option v-for="m in moduleOptions" :key="m" :value="m">{{ m }}</option>
        </select>
        <button class="btn" @click="loadAll">Refresh</button>
      </div>
    </div>

    <!-- Stats bar -->
    <div class="stats-bar">
      <div class="stat"><span class="stat-value">{{ stats?.total_calls || 0 }}</span><span class="stat-label">Total Calls</span></div>
      <div class="stat"><span class="stat-value">{{ (stats?.avg_latency_ms || 0).toFixed(1) }}ms</span><span class="stat-label">Avg Latency</span></div>
      <div class="stat"><span class="stat-value" :class="errorClass">{{ ((stats?.error_rate || 0) * 100).toFixed(2) }}%</span><span class="stat-label">Error Rate</span></div>
      <div class="stat"><span class="stat-value">{{ stats?.qps || 0 }}</span><span class="stat-label">QPS</span></div>
    </div>

    <!-- API Key management -->
    <div class="card">
      <div class="section-header-row">
        <h2 class="section-title">API Keys</h2>
        <button class="btn btn-sm" @click="showKeyForm = !showKeyForm">+ Create Key</button>
      </div>
      <div v-if="showKeyForm" class="key-form">
        <input v-model="keyForm.name" placeholder="Key name" class="input" />
        <input v-model="keyForm.user_id" placeholder="User ID (optional)" class="input" />
        <input v-model.number="keyForm.quota_tpm" type="number" min="1" placeholder="TPM" class="input-sm" />
        <input v-model.number="keyForm.quota_rpm" type="number" min="1" placeholder="RPM" class="input-sm" />
        <button class="btn btn-primary" @click="createKey">Create</button>
      </div>
      <div v-if="newKey" class="new-key-alert">
        New key (save now, shown only once): <code>{{ newKey }}</code>
        <button class="btn btn-sm" @click="newKey = ''">Dismiss</button>
      </div>
      <table class="data-table">
        <thead><tr><th>Name</th><th>Quota (TPM/RPM)</th><th>Calls</th><th>Status</th><th>Last Used</th><th>Actions</th></tr></thead>
        <tbody>
          <tr v-for="k in apiKeys" :key="k.key_id">
            <td>{{ k.name }}</td>
            <td>{{ formatNum(k.quota_tpm) }} / {{ k.quota_rpm }}</td>
            <td>{{ k.total_calls || 0 }}</td>
            <td><span class="status-pill" :class="k.enabled ? 'ok' : 'exceeded'">{{ k.enabled ? 'enabled' : 'disabled' }}</span></td>
            <td>{{ k.last_used_at ? new Date(k.last_used_at * 1000).toLocaleString() : '—' }}</td>
            <td><button class="btn btn-sm btn-danger" @click="deleteKey(k.key_id)">Delete</button></td>
          </tr>
          <tr v-if="apiKeys.length === 0"><td colspan="6" class="empty">No API keys</td></tr>
        </tbody>
      </table>
    </div>

    <!-- External APIs -->
    <div class="card">
      <h2 class="section-title">External API Registry</h2>
      <div class="ext-grid">
        <div v-for="api in externalApis" :key="api.name" class="ext-card" :class="{ configured: api.configured, stub: api.status === 'stub' }">
          <div class="ext-header">
            <span class="ext-name">{{ api.name }}</span>
            <span class="status-pill" :class="api.configured ? 'ok' : 'no_budget'">{{ api.configured ? 'configured' : 'not set' }}</span>
          </div>
          <div class="ext-meta">{{ api.type }} · {{ api.auth_method }}</div>
          <div class="ext-url">{{ api.base_url }}</div>
          <div class="ext-env">env: <code>{{ api.env_var }}</code></div>
          <div class="ext-desc">{{ api.description }}</div>
        </div>
      </div>
    </div>

    <!-- Endpoint directory -->
    <div class="card">
      <h2 class="section-title">Endpoint Directory ({{ filteredEndpoints.length }})</h2>
      <table class="data-table">
        <thead><tr><th>Method</th><th>Path</th><th>Module</th><th>Summary</th></tr></thead>
        <tbody>
          <tr v-for="ep in filteredEndpoints" :key="ep.method + ep.path">
            <td><span class="method-badge" :class="ep.method.toLowerCase()">{{ ep.method }}</span></td>
            <td>{{ ep.path }}</td>
            <td>{{ ep.module }}</td>
            <td class="summary-cell">{{ ep.summary }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from "vue";
import { api } from "../api/client";

const endpoints = ref<any[]>([]);
const stats = ref<any>(null);
const externalApis = ref<any[]>([]);
const apiKeys = ref<any[]>([]);
const searchQuery = ref("");
const moduleFilter = ref("");
const showKeyForm = ref(false);
const newKey = ref("");
const keyForm = ref({ name: "", user_id: "", quota_tpm: 100000, quota_rpm: 60 });
let timer: ReturnType<typeof setInterval> | null = null;

const moduleOptions = computed(() => {
  const mods = new Set(endpoints.value.map((e) => e.module));
  return Array.from(mods).sort();
});

const filteredEndpoints = computed(() => {
  return endpoints.value.filter((e) => {
    const matchesSearch = !searchQuery.value ||
      e.path.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
      (e.summary || "").toLowerCase().includes(searchQuery.value.toLowerCase());
    const matchesModule = !moduleFilter.value || e.module === moduleFilter.value;
    return matchesSearch && matchesModule;
  });
});

const errorClass = computed(() => {
  const rate = (stats.value?.error_rate || 0) * 100;
  if (rate >= 10) return "error-high";
  if (rate >= 1) return "error-med";
  return "";
});

function formatNum(n: number): string {
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return String(n);
}

async function loadEndpoints() {
  try { endpoints.value = await api.getEndpoints(); } catch (e) { console.error(e); }
}
async function loadStats() {
  try { stats.value = await api.getApiStats(); } catch (e) { console.error(e); }
}
async function loadExternal() {
  try { externalApis.value = await api.getExternalApis(); } catch (e) { console.error(e); }
}
async function loadKeys() {
  try { apiKeys.value = await api.getApiKeys(); } catch (e) { console.error(e); }
}
async function loadAll() {
  await Promise.all([loadEndpoints(), loadStats(), loadExternal(), loadKeys()]);
}

async function createKey() {
  if (!keyForm.value.name) return;
  try {
    const result = await api.createApiKey(keyForm.value);
    newKey.value = result.api_key;
    showKeyForm.value = false;
    keyForm.value = { name: "", user_id: "", quota_tpm: 100000, quota_rpm: 60 };
    await loadKeys();
  } catch (e) { console.error(e); }
}

async function deleteKey(keyId: string) {
  if (!confirm("Delete this API key? This cannot be undone.")) return;
  try {
    await api.deleteApiKey(keyId);
    await loadKeys();
  } catch (e) { console.error(e); }
}

onMounted(() => { loadAll(); timer = setInterval(loadAll, 30000); });
onUnmounted(() => { if (timer) clearInterval(timer); });
</script>

<style scoped>
.api-view { max-width: 1100px; }
.view-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-title { font-size: 20px; font-weight: 500; }
.controls { display: flex; gap: 8px; }
.input, .select { background: var(--bg-tertiary); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: var(--radius-sm); padding: 6px 10px; font-size: 12px; }
.input { width: 200px; }
.input-sm { width: 90px; background: var(--bg-tertiary); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: var(--radius-sm); padding: 6px 10px; font-size: 12px; }
.btn { background: var(--bg-tertiary); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: var(--radius-sm); padding: 6px 14px; font-size: 12px; cursor: pointer; }
.btn:hover { border-color: var(--accent-blue); }
.btn-sm { padding: 4px 10px; font-size: 11px; }
.btn-primary { background: var(--accent-blue); color: #0d1117; border-color: var(--accent-blue); font-weight: 500; }
.btn-danger { color: var(--accent-red); border-color: rgba(248,81,73,0.3); }
.btn-danger:hover { background: rgba(248,81,73,0.1); }

.stats-bar { display: flex; gap: 0; background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius); margin-bottom: 20px; overflow: hidden; }
.stat { flex: 1; padding: 16px; text-align: center; border-right: 1px solid var(--border-color); }
.stat:last-child { border-right: none; }
.stat-value { display: block; font-size: 20px; font-weight: 600; color: var(--text-primary); }
.stat-value.error-high { color: var(--accent-red); }
.stat-value.error-med { color: var(--accent-yellow); }
.stat-label { font-size: 11px; color: var(--text-secondary); }

.card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 16px; margin-bottom: 20px; }
.section-title { font-size: 14px; font-weight: 500; margin-bottom: 12px; }
.section-header-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header-row .section-title { margin-bottom: 0; }

.key-form { display: flex; gap: 8px; margin-bottom: 16px; align-items: center; flex-wrap: wrap; }
.new-key-alert { background: rgba(210,153,34,0.1); border: 1px solid rgba(210,153,34,0.3); border-radius: var(--radius-sm); padding: 10px 12px; margin-bottom: 16px; font-size: 12px; color: var(--accent-yellow); display: flex; align-items: center; gap: 12px; }
.new-key-alert code { background: var(--bg-tertiary); padding: 2px 6px; border-radius: 4px; font-family: monospace; }

.data-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.data-table th { text-align: left; padding: 8px; color: var(--text-secondary); border-bottom: 1px solid var(--border-color); font-weight: 500; }
.data-table td { padding: 8px; border-bottom: 1px solid var(--border-color); }
.summary-cell { color: var(--text-secondary); max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.method-badge { padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 500; }
.method-badge.get { background: rgba(63,185,80,0.15); color: var(--accent-green); }
.method-badge.post { background: rgba(88,166,255,0.15); color: var(--accent-blue); }
.method-badge.delete { background: rgba(248,81,73,0.15); color: var(--accent-red); }
.method-badge.put { background: rgba(210,153,34,0.15); color: var(--accent-yellow); }

.ext-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.ext-card { background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 14px; }
.ext-card.configured { border-color: rgba(63,185,80,0.4); }
.ext-card.stub { opacity: 0.8; }
.ext-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.ext-name { font-weight: 500; font-size: 13px; }
.ext-meta { font-size: 11px; color: var(--text-secondary); margin-bottom: 4px; }
.ext-url { font-size: 11px; color: var(--accent-blue); margin-bottom: 4px; word-break: break-all; }
.ext-env { font-size: 11px; color: var(--text-tertiary); margin-bottom: 6px; }
.ext-env code { background: var(--bg-primary); padding: 1px 5px; border-radius: 3px; }
.ext-desc { font-size: 11px; color: var(--text-secondary); line-height: 1.5; }

.status-pill { padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 500; }
.status-pill.ok { background: rgba(63,185,80,0.15); color: var(--accent-green); }
.status-pill.exceeded { background: rgba(248,81,73,0.15); color: var(--accent-red); }
.status-pill.no_budget { background: rgba(110,118,129,0.15); color: var(--text-tertiary); }
.empty { color: var(--text-tertiary); font-size: 13px; text-align: center; padding: 20px; }
</style>
