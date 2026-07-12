<template>
  <div class="alerts-view">
    <div class="view-header">
      <h1 class="page-title">Alerts & Drift</h1>
      <div class="controls">
        <button class="btn btn-primary" @click="evaluate">Evaluate Now</button>
        <button class="btn" @click="loadAll">Refresh</button>
      </div>
    </div>

    <!-- Metric snapshot -->
    <div class="summary-grid" v-if="evalResult">
      <div class="summary-card"><div class="summary-label">Error Rate</div><div class="summary-value" :class="errHigh ? 'bad' : 'good'">{{ pct(evalResult.metrics.error_rate) }}</div></div>
      <div class="summary-card"><div class="summary-label">P95 Latency</div><div class="summary-value">{{ evalResult.metrics.p95_ms }} ms</div></div>
      <div class="summary-card"><div class="summary-label">Daily Cost</div><div class="summary-value">${{ evalResult.metrics.daily_cost_usd.toFixed(2) }}</div></div>
      <div class="summary-card"><div class="summary-label">Triggered Rules</div><div class="summary-value" :class="triggeredCount ? 'bad' : 'good'">{{ triggeredCount }}</div></div>
    </div>

    <!-- Active alerts -->
    <div class="chart-card">
      <h2 class="section-title">Active Alerts</h2>
      <div v-if="alertLoading" class="loading">Loading…</div>
      <ul v-else-if="alertList.length" class="alert-list">
        <li v-for="a in alertList" :key="a.alert_id" class="alert-item" :class="a.severity">
          <span class="sev-pill" :class="a.severity">{{ a.severity }}</span>
          <span class="alert-msg">{{ a.message || a.rule_id }}</span>
          <span class="alert-val">{{ fmtVal(a.metric, a.value) }} / thr {{ a.threshold }}</span>
          <span class="alert-time mono">{{ shortTime(a.timestamp) }}</span>
        </li>
      </ul>
      <div v-else class="empty">No active alerts — all systems nominal</div>
    </div>

    <!-- Drift -->
    <div class="chart-card">
      <div class="section-header-row">
        <h2 class="section-title">Metric Drift</h2>
        <span class="status-pill" :class="driftStatusClass">{{ drift.status }}</span>
      </div>
      <table class="data-table" v-if="driftMetrics">
        <thead><tr><th>Metric</th><th>Baseline</th><th>Current</th><th>Δ%</th></tr></thead>
        <tbody>
          <tr v-for="(v, k) in driftMetrics" :key="k">
            <td>{{ k }}</td>
            <td>{{ v.baseline_mean }}</td>
            <td>{{ v.current }}</td>
            <td :class="Math.abs(v.pct_change) >= 50 ? 'bad' : ''">{{ v.pct_change }}%</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty">Collecting baseline… (need ~{{ baselineNeed }} snapshots)</div>
    </div>

    <!-- Alert rules -->
    <div class="chart-card">
      <div class="section-header-row">
        <h2 class="section-title">Alert Rules</h2>
        <button class="btn btn-sm" @click="showRuleForm = !showRuleForm">+ Add Rule</button>
      </div>
      <div v-if="showRuleForm" class="rule-form">
        <select v-model="ruleForm.metric" class="select">
          <option value="error_rate">error_rate</option>
          <option value="p95_ms">p95_ms</option>
          <option value="daily_cost_usd">daily_cost_usd</option>
          <option value="budget_exceeded">budget_exceeded</option>
        </select>
        <select v-model="ruleForm.operator" class="select">
          <option value="gt">&gt;</option>
          <option value="gte">≥</option>
          <option value="lt">&lt;</option>
          <option value="lte">≤</option>
        </select>
        <input v-model.number="ruleForm.threshold" type="number" step="0.01" class="input narrow" />
        <select v-model="ruleForm.severity" class="select">
          <option value="info">info</option>
          <option value="warning">warning</option>
          <option value="critical">critical</option>
        </select>
        <button class="btn btn-primary" @click="addRule">Add</button>
      </div>
      <table class="data-table">
        <thead><tr><th>Rule</th><th>Metric</th><th>Cond</th><th>Severity</th><th></th></tr></thead>
        <tbody>
          <tr v-for="r in ruleList" :key="r.id">
            <td class="mono">{{ r.id }}</td>
            <td>{{ r.metric }}</td>
            <td>{{ r.operator }} {{ r.threshold }}</td>
            <td><span class="status-pill" :class="r.severity">{{ r.severity }}</span></td>
            <td><button class="btn btn-sm btn-danger" @click="removeRule(r.id)">Del</button></td>
          </tr>
          <tr v-if="ruleList.length === 0"><td colspan="5" class="empty">No rules</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue";
import { api } from "../api/client";

const evalResult = ref<any>(null);
const alertList = ref<any[]>([]);
const alertLoading = ref(false);
const drift = ref<any>({});
const ruleList = ref<any[]>([]);
const showRuleForm = ref(false);
const ruleForm = ref({ metric: "error_rate", operator: "gt", threshold: 0.1, severity: "warning" });
const baselineNeed = 31;
let timer: ReturnType<typeof setInterval> | null = null;

const errHigh = computed(() => (evalResult.value?.metrics?.error_rate || 0) >= 0.1);
const triggeredCount = computed(() => evalResult.value?.triggered?.length || 0);
const driftMetrics = computed(() => drift.value?.metrics || null);
const driftStatusClass = computed(() => drift.value?.status === "drift_detected" ? "warning" : "ok");

function pct(v: number) { return ((v || 0) * 100).toFixed(1) + "%"; }
function fmtVal(metric: string, v: number) {
  if (metric === "daily_cost_usd") return "$" + (v || 0).toFixed(2);
  if (metric === "p95_ms") return (v || 0) + " ms";
  if (metric === "budget_exceeded") return String(v || 0);
  return pct(v);
}
function shortTime(ts?: string) { return ts ? ts.slice(11, 19) : "—"; }

async function evaluate() {
  try { evalResult.value = await api.evaluateAlerts(); }
  catch (e) { console.error(e); }
  await Promise.all([loadAlerts(), loadDrift(), loadRules()]);
}

async function loadAlerts() {
  alertLoading.value = true;
  try { alertList.value = (await api.getAlerts(1, 50)).data || []; }
  catch (e) { console.error(e); alertList.value = []; }
  alertLoading.value = false;
}
async function loadDrift() {
  try { drift.value = await api.getDrift(); } catch (e) { console.error(e); }
}
async function loadRules() {
  try { ruleList.value = await api.getAlertRules(); } catch (e) { console.error(e); ruleList.value = []; }
}
async function addRule() {
  try { await api.setAlertRule({ ...ruleForm.value }); showRuleForm.value = false; await loadRules(); }
  catch (e) { console.error(e); }
}
async function removeRule(id: string) {
  try { await api.deleteAlertRule(id); await loadRules(); } catch (e) { console.error(e); }
}

async function loadAll() { await evaluate(); }

onMounted(() => { loadAll(); timer = setInterval(loadAll, 30000); });
onUnmounted(() => { if (timer) clearInterval(timer); });
</script>

<style scoped>
.alerts-view { max-width: 1100px; }
.view-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-title { font-size: 20px; font-weight: 500; }
.controls { display: flex; gap: 8px; }
.btn { background: var(--bg-tertiary); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: var(--radius-sm); padding: 6px 14px; font-size: 12px; cursor: pointer; }
.btn:hover { border-color: var(--accent-blue); }
.btn-sm { padding: 4px 10px; font-size: 11px; }
.btn-primary { background: var(--accent-blue); color: #0d1117; border-color: var(--accent-blue); font-weight: 500; }
.btn-danger { color: var(--accent-red); border-color: var(--accent-red); }

.summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
.summary-card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 16px; }
.summary-label { font-size: 11px; color: var(--text-secondary); margin-bottom: 8px; }
.summary-value { font-size: 22px; font-weight: 600; }
.summary-value.good { color: var(--accent-green); }
.summary-value.bad { color: var(--accent-red); }

.chart-card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 16px; margin-bottom: 20px; }
.section-title { font-size: 14px; font-weight: 500; margin-bottom: 12px; }
.section-header-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header-row .section-title { margin-bottom: 0; }

.alert-list { list-style: none; }
.alert-item { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--border-color); font-size: 12px; }
.alert-msg { flex: 1; color: var(--text-primary); }
.alert-val { color: var(--text-secondary); font-family: monospace; }
.alert-time { color: var(--text-tertiary); white-space: nowrap; }
.sev-pill { padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 500; }
.sev-pill.info { background: rgba(57,210,192,0.15); color: var(--accent-cyan); }
.sev-pill.warning { background: rgba(210,153,34,0.15); color: var(--accent-yellow); }
.sev-pill.critical { background: rgba(248,81,73,0.15); color: var(--accent-red); }

.loading { color: var(--text-secondary); font-size: 13px; padding: 12px 0; }
.empty { color: var(--text-tertiary); font-size: 13px; text-align: center; padding: 20px; }
.mono { font-family: monospace; color: var(--text-tertiary); }
.bad { color: var(--accent-red); }

.data-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.data-table th { text-align: left; padding: 8px; color: var(--text-secondary); border-bottom: 1px solid var(--border-color); }
.data-table td { padding: 8px; border-bottom: 1px solid var(--border-color); }

.rule-form { display: flex; gap: 8px; margin-bottom: 16px; align-items: center; flex-wrap: wrap; }
.select, .input { background: var(--bg-tertiary); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: var(--radius-sm); padding: 6px 10px; font-size: 12px; }
.input.narrow { width: 90px; }

.status-pill { padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 500; }
.status-pill.ok { background: rgba(63,185,80,0.15); color: var(--accent-green); }
.status-pill.warning { background: rgba(210,153,34,0.15); color: var(--accent-yellow); }
.status-pill.critical { background: rgba(248,81,73,0.15); color: var(--accent-red); }
.status-pill.info { background: rgba(57,210,192,0.15); color: var(--accent-cyan); }
</style>
