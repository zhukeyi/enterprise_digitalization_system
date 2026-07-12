<template>
  <div class="trace-view">
    <div class="view-header">
      <h1 class="page-title">Trace Viewer</h1>
      <div class="controls">
        <select v-model="statusFilter" @change="loadTraces" class="select">
          <option value="">All statuses</option>
          <option value="ok">OK</option>
          <option value="error">Error</option>
        </select>
        <button class="btn" @click="loadAll">Refresh</button>
      </div>
    </div>

    <!-- Summary cards -->
    <div class="summary-grid">
      <div class="summary-card"><div class="summary-label">Total Spans</div><div class="summary-value">{{ stats.total_spans || 0 }}</div></div>
      <div class="summary-card"><div class="summary-label">P50 (ms)</div><div class="summary-value">{{ stats.p50_ms || 0 }}</div></div>
      <div class="summary-card"><div class="summary-label">P95 (ms)</div><div class="summary-value">{{ stats.p95_ms || 0 }}</div></div>
      <div class="summary-card"><div class="summary-label">P99 (ms)</div><div class="summary-value">{{ stats.p99_ms || 0 }}</div></div>
      <div class="summary-card">
        <div class="summary-label">Error Rate</div>
        <div class="summary-value" :class="errorHigh ? 'bad' : 'good'">{{ ((stats.error_rate || 0) * 100).toFixed(1) }}%</div>
      </div>
    </div>

    <div class="two-column">
      <!-- Span types -->
      <div class="chart-card">
        <h2 class="section-title">Span Types</h2>
        <div ref="typeChart" class="chart-sm"></div>
      </div>
      <!-- Hot paths -->
      <div class="chart-card">
        <h2 class="section-title">Hot Paths (by avg duration)</h2>
        <table class="data-table" v-if="stats.hot_paths?.length">
          <thead><tr><th>Path</th><th>Avg</th><th>Max</th><th>Count</th></tr></thead>
          <tbody>
            <tr v-for="h in stats.hot_paths" :key="h.name">
              <td class="path">{{ h.name }}</td>
              <td>{{ h.avg_ms }} ms</td>
              <td>{{ h.max_ms }} ms</td>
              <td>{{ h.count }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">No spans recorded yet</div>
      </div>
    </div>

    <!-- Trace list -->
    <div class="chart-card">
      <h2 class="section-title">Traces</h2>
      <div v-if="traceLoading" class="loading">Loading…</div>
      <table v-else class="data-table">
        <thead><tr><th>Trace ID</th><th>Root</th><th>Spans</th><th>Duration</th><th>Status</th><th></th></tr></thead>
        <tbody>
          <tr v-for="t in traceList" :key="t.trace_id" class="trace-row" :class="{ selected: selectedTrace?.trace_id === t.trace_id }" @click="selectTrace(t)">
            <td class="mono">{{ shortId(t.trace_id) }}</td>
            <td>{{ t.root_name }}</td>
            <td>{{ t.span_count }}</td>
            <td>{{ t.total_duration_ms }} ms</td>
            <td><span class="status-pill" :class="t.status">{{ t.status }}</span></td>
            <td><span class="link">View →</span></td>
          </tr>
          <tr v-if="traceList.length === 0"><td colspan="6" class="empty">No traces</td></tr>
        </tbody>
      </table>
    </div>

    <!-- Waterfall -->
    <div class="chart-card" v-if="selectedTrace">
      <div class="section-header-row">
        <h2 class="section-title">Waterfall — {{ shortId(selectedTrace.trace_id) }}</h2>
        <span class="meta-tag">{{ selectedTrace.span_count }} spans · {{ selectedTrace.total_duration_ms }} ms</span>
      </div>
      <div class="waterfall">
        <div v-for="(s, i) in treeSpans" :key="s.span_id" class="wf-row" :style="{ marginLeft: s.depth * 18 + 'px' }">
          <div class="wf-label">
            <span class="wf-name">{{ s.name }}</span>
            <span class="wf-type">{{ s.span_type }}</span>
          </div>
          <div class="wf-track">
            <div class="wf-bar" :class="s.status" :style="{ left: s.offsetPct + '%', width: Math.max(s.widthPct, 1) + '%' }"></div>
            <span class="wf-dur">{{ s.duration_ms }} ms</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from "vue";
import * as echarts from "echarts";
import { api } from "../api/client";

const stats = ref<any>({});
const statusFilter = ref("");
const traces = ref<any>(null);
const traceList = computed(() => traces.value?.data || []);
const traceLoading = ref(false);
const selectedTrace = ref<any>(null);
const typeChart = ref<HTMLElement>();
let chart: echarts.ECharts | null = null;
let timer: ReturnType<typeof setInterval> | null = null;

const errorHigh = computed(() => (stats.value.error_rate || 0) >= 0.1);

function shortId(id?: string) { return id ? id.slice(0, 8) : "—"; }

async function loadStats() {
  try { stats.value = await api.getTraceStats(); renderTypeChart(); }
  catch (e) { console.error(e); }
}

async function loadTraces() {
  traceLoading.value = true;
  try { traces.value = await api.getTraces(1, 20, undefined, statusFilter.value || undefined); }
  catch (e) { console.error(e); traces.value = { data: [] }; }
  traceLoading.value = false;
}

async function selectTrace(t: any) {
  try {
    selectedTrace.value = await api.getTraceDetail(t.trace_id);
  } catch (e) { console.error(e); }
}

// Build a depth-ordered, offset/width-computed span list for the waterfall
const treeSpans = computed(() => {
  const tr = selectedTrace.value;
  if (!tr?.spans?.length) return [];
  const spans = tr.spans;
  const minStart = Math.min(...spans.map((s: any) => s.start_time));
  const maxEnd = Math.max(...spans.map((s: any) => s.end_time ?? s.start_time));
  const total = Math.max(maxEnd - minStart, 0.001);

  const byId: Record<string, any> = {};
  spans.forEach((s: any) => (byId[s.span_id] = s));
  const children: Record<string, any[]> = {};
  spans.forEach((s: any) => {
    const p = s.parent_span_id || "__root__";
    (children[p] = children[p] || []).push(s);
  });

  const ordered: any[] = [];
  const walk = (pid: string, depth: number) => {
    (children[pid] || []).forEach((s: any) => {
      const start = s.start_time - minStart;
      s.depth = depth;
      s.offsetPct = (start / total) * 100;
      s.widthPct = (s.duration_ms / total) * 100;
      ordered.push(s);
      walk(s.span_id, depth + 1);
    });
  };
  walk("__root__", 0);
  // Fallback: include any orphan spans not reached
  if (ordered.length < spans.length) {
    spans.forEach((s: any) => {
      if (!ordered.includes(s)) { s.depth = 0; s.offsetPct = 0; s.widthPct = (s.duration_ms / total) * 100; ordered.push(s); }
    });
  }
  return ordered;
});

function renderTypeChart() {
  if (!typeChart.value) return;
  const types = stats.value.span_types || {};
  const data = Object.entries(types).map(([k, v]) => ({ name: k, value: v as number }));
  if (chart) chart.dispose();
  chart = echarts.init(typeChart.value);
  chart.setOption({
    tooltip: { trigger: "axis" },
    grid: { left: 60, right: 20, top: 20, bottom: 20 },
    xAxis: { type: "value", axisLabel: { color: "#8b949e" }, splitLine: { lineStyle: { color: "#21262d" } } },
    yAxis: { type: "category", data: data.map((d) => d.name), axisLabel: { color: "#8b949e" } },
    series: [{ type: "bar", data: data.map((d) => d.value), itemStyle: { color: "#39d2c0" }, barWidth: "55%" }],
  });
}

async function loadAll() { await Promise.all([loadStats(), loadTraces()]); }

function resize() { chart?.resize(); }
window.addEventListener("resize", resize);

onMounted(() => { loadAll(); timer = setInterval(loadAll, 30000); });
onUnmounted(() => {
  if (timer) clearInterval(timer);
  chart?.dispose();
  window.removeEventListener("resize", resize);
});
</script>

<style scoped>
.trace-view { max-width: 1100px; }
.view-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-title { font-size: 20px; font-weight: 500; }
.controls { display: flex; gap: 8px; }
.select { background: var(--bg-tertiary); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: var(--radius-sm); padding: 6px 10px; font-size: 12px; }
.btn { background: var(--bg-tertiary); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: var(--radius-sm); padding: 6px 14px; font-size: 12px; cursor: pointer; }
.btn:hover { border-color: var(--accent-blue); }

.summary-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 20px; }
.summary-card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 16px; }
.summary-label { font-size: 11px; color: var(--text-secondary); margin-bottom: 8px; }
.summary-value { font-size: 22px; font-weight: 600; }
.summary-value.good { color: var(--accent-green); }
.summary-value.bad { color: var(--accent-red); }

.chart-card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 16px; margin-bottom: 20px; }
.two-column { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.section-title { font-size: 14px; font-weight: 500; margin-bottom: 12px; }
.section-header-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header-row .section-title { margin-bottom: 0; }
.chart-sm { height: 240px; }

.data-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.data-table th { text-align: left; padding: 8px; color: var(--text-secondary); border-bottom: 1px solid var(--border-color); }
.data-table td { padding: 8px; border-bottom: 1px solid var(--border-color); }
.trace-row { cursor: pointer; }
.trace-row:hover { background: var(--bg-tertiary); }
.trace-row.selected { background: rgba(88,166,255,0.1); }
.mono { font-family: monospace; color: var(--accent-cyan); }
.path { color: var(--text-primary); }
.link { color: var(--accent-blue); font-size: 11px; }
.loading { color: var(--text-secondary); font-size: 13px; padding: 12px 0; }
.empty { color: var(--text-tertiary); font-size: 13px; text-align: center; padding: 20px; }
.meta-tag { background: var(--bg-tertiary); border-radius: 8px; padding: 2px 8px; font-size: 10px; color: var(--text-secondary); }

.status-pill { padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 500; }
.status-pill.ok { background: rgba(63,185,80,0.15); color: var(--accent-green); }
.status-pill.error { background: rgba(248,81,73,0.15); color: var(--accent-red); }

.waterfall { display: flex; flex-direction: column; gap: 6px; }
.wf-row { display: flex; align-items: center; gap: 10px; }
.wf-label { width: 200px; flex-shrink: 0; display: flex; flex-direction: column; }
.wf-name { font-size: 12px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wf-type { font-size: 10px; color: var(--text-tertiary); }
.wf-track { position: relative; flex: 1; height: 22px; background: var(--bg-tertiary); border-radius: 4px; overflow: hidden; }
.wf-bar { position: absolute; top: 3px; height: 16px; border-radius: 3px; background: var(--accent-blue); opacity: 0.85; }
.wf-bar.ok { background: var(--accent-green); }
.wf-bar.error { background: var(--accent-red); }
.wf-dur { position: absolute; right: 6px; top: 3px; font-size: 10px; color: var(--text-secondary); }
</style>
