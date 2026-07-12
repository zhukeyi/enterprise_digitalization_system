<template>
  <div class="token-view">
    <div class="view-header">
      <h1 class="page-title">Token Router & Cost</h1>
      <div class="controls">
        <select v-model="groupBy" @change="loadUsage" class="select">
          <option value="model">By Model</option>
          <option value="agent">By Agent</option>
          <option value="user">By User</option>
          <option value="hour">By Hour</option>
        </select>
        <select v-model="hours" @change="loadUsage" class="select">
          <option :value="6">Last 6h</option>
          <option :value="24">Last 24h</option>
          <option :value="72">Last 72h</option>
          <option :value="168">Last 7d</option>
        </select>
        <button class="btn" @click="loadAll">Refresh</button>
      </div>
    </div>

    <!-- Summary cards -->
    <div class="summary-grid">
      <div class="summary-card">
        <div class="summary-label">Total Calls</div>
        <div class="summary-value">{{ summary.total_calls || 0 }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Total Tokens</div>
        <div class="summary-value">{{ formatNum(summary.total_tokens || 0) }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Total Cost</div>
        <div class="summary-value">${{ (summary.total_cost_usd || 0).toFixed(2) }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Tokens / Hour</div>
        <div class="summary-value">{{ formatNum(summary.tokens_per_hour || 0) }}</div>
      </div>
    </div>

    <!-- Usage chart -->
    <div class="chart-card">
      <h2 class="section-title">Token Usage by {{ groupByLabel }}</h2>
      <div ref="usageChart" class="chart"></div>
    </div>

    <!-- Routing distribution + cost report -->
    <div class="two-column">
      <div class="chart-card">
        <h2 class="section-title">Model Routing Distribution</h2>
        <div ref="routingChart" class="chart-sm"></div>
      </div>
      <div class="chart-card">
        <h2 class="section-title">Cost Report ({{ costPeriod }})</h2>
        <div ref="costChart" class="chart-sm"></div>
      </div>
    </div>

    <!-- Pricing table -->
    <div class="chart-card">
      <h2 class="section-title">Model Pricing (USD / 1K tokens)</h2>
      <table class="data-table">
        <thead><tr><th>Model</th><th>Input</th><th>Output</th></tr></thead>
        <tbody>
          <tr v-for="p in pricing" :key="p.model">
            <td>{{ p.model }}</td>
            <td>${{ p.prompt_price_per_1k.toFixed(4) }}</td>
            <td>${{ p.completion_price_per_1k.toFixed(4) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Budget (Cost Canary) -->
    <div class="chart-card">
      <div class="section-header-row">
        <h2 class="section-title">Cost Canary — Agent Budgets</h2>
        <button class="btn btn-sm" @click="showBudgetForm = !showBudgetForm">+ Set Budget</button>
      </div>
      <div v-if="showBudgetForm" class="budget-form">
        <select v-model="budgetForm.agent" class="select">
          <option v-for="a in agentModules" :key="a" :value="a">{{ a }}</option>
        </select>
        <input v-model.number="budgetForm.limit" type="number" step="0.01" min="0.01" placeholder="Daily limit USD" class="input" />
        <button class="btn btn-primary" @click="setBudget">Save</button>
      </div>
      <div v-if="budgetLoading" class="loading">Loading budgets...</div>
      <table v-else class="data-table">
        <thead><tr><th>Agent</th><th>Daily Limit</th><th>Spend</th><th>Usage</th><th>Status</th></tr></thead>
        <tbody>
          <tr v-for="b in budgets" :key="b.agent_module">
            <td>{{ b.agent_module }}</td>
            <td>${{ (b.daily_limit_usd || 0).toFixed(2) }}</td>
            <td>${{ (b.current_spend_usd || 0).toFixed(4) }}</td>
            <td>
              <div class="progress-bar">
                <div class="progress-fill" :class="b.status" :style="{ width: Math.min(b.percentage || 0, 100) + '%' }"></div>
              </div>
              <span class="progress-label">{{ b.percentage || 0 }}%</span>
            </td>
            <td><span class="status-pill" :class="b.status">{{ b.status }}</span></td>
          </tr>
          <tr v-if="budgets.length === 0"><td colspan="5" class="empty">No budgets set</td></tr>
        </tbody>
      </table>
    </div>

    <!-- Failover events -->
    <div class="chart-card">
      <h2 class="section-title">Failover Events</h2>
      <div v-if="failover.length === 0" class="empty">No failover events recorded</div>
      <ul v-else class="event-list">
        <li v-for="(e, i) in failover" :key="i" class="event-item">
          {{ e.type }} — {{ e.model }} → {{ e.degraded_to }}
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from "vue";
import * as echarts from "echarts";
import { api } from "../api/client";

const groupBy = ref("model");
const hours = ref(24);
const costPeriod = ref("daily");
const summary = ref<any>({});
const usageData = ref<any[]>([]);
const pricing = ref<any[]>([]);
const budgets = ref<any[]>([]);
const budgetLoading = ref(false);
const failover = ref<any[]>([]);
const showBudgetForm = ref(false);
const budgetForm = ref({ agent: "router_agent", limit: 1.0 });
const agentModules = [
  "router_agent", "orchestrator", "rag_agent", "hr_agent", "data_agent",
  "analysis_agent", "pricing_agent", "marketing_agent", "map_agent", "im_agent",
];

const groupByLabel = computed(() => ({ model: "Model", agent: "Agent", user: "User", hour: "Hour" }[groupBy.value]));

const usageChart = ref<HTMLElement>();
const routingChart = ref<HTMLElement>();
const costChart = ref<HTMLElement>();
let charts: echarts.ECharts[] = [];
let timer: ReturnType<typeof setInterval> | null = null;

function formatNum(n: number): string {
  if (n >= 1e6) return (n / 1e6).toFixed(2) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(2) + "K";
  return String(n);
}

async function loadUsage() {
  try {
    const data = await api.getTokenUsage(groupBy.value, hours.value);
    summary.value = data.summary || {};
    usageData.value = data.data || [];
    renderUsageChart();
  } catch (e) { console.error(e); }
}

async function loadRouting() {
  try {
    const data = await api.getTokenRouting();
    pricing.value = data.pricing || [];
    renderRoutingChart(data.distribution || []);
  } catch (e) { console.error(e); }
}

async function loadCost() {
  try {
    const data = await api.getTokenCost(costPeriod.value);
    renderCostChart(data.data || []);
  } catch (e) { console.error(e); }
}

async function loadBudget() {
  budgetLoading.value = true;
  try {
    const data = await api.getBudget();
    budgets.value = data.budgets || [];
  } catch (e) { console.error(e); }
  budgetLoading.value = false;
}

async function loadFailover() {
  try {
    const data = await api.getTokenFailover();
    failover.value = data.events || [];
  } catch (e) { console.error(e); }
}

async function loadAll() {
  await Promise.all([loadUsage(), loadRouting(), loadCost(), loadBudget(), loadFailover()]);
}

async function setBudget() {
  try {
    await api.setBudget(budgetForm.value.agent, budgetForm.value.limit);
    showBudgetForm.value = false;
    await loadBudget();
  } catch (e) { console.error(e); }
}

function renderUsageChart() {
  if (!usageChart.value) return;
  const chart = echarts.init(usageChart.value);
  const labels = usageData.value.map((d) => d.group_value);
  const tokens = usageData.value.map((d) => d.total_tokens);
  const costs = usageData.value.map((d) => d.total_cost);
  chart.setOption({
    tooltip: { trigger: "axis" },
    legend: { data: ["Tokens", "Cost (USD)"], textStyle: { color: "#8b949e" } },
    grid: { left: 60, right: 60, top: 40, bottom: 30 },
    xAxis: { type: "category", data: labels, axisLabel: { color: "#8b949e", rotate: labels.length > 8 ? 30 : 0 } },
    yAxis: [
      { type: "value", name: "Tokens", axisLabel: { color: "#8b949e" }, splitLine: { lineStyle: { color: "#21262d" } } },
      { type: "value", name: "USD", axisLabel: { color: "#8b949e" }, splitLine: { show: false } },
    ],
    series: [
      { name: "Tokens", type: "bar", data: tokens, itemStyle: { color: "#58a6ff" } },
      { name: "Cost (USD)", type: "line", yAxisIndex: 1, data: costs, itemStyle: { color: "#d29922" }, smooth: true },
    ],
  });
  charts.push(chart);
}

function renderRoutingChart(dist: any[]) {
  if (!routingChart.value || dist.length === 0) return;
  const chart = echarts.init(routingChart.value);
  chart.setOption({
    tooltip: { trigger: "item" },
    series: [{
      type: "pie",
      radius: ["40%", "70%"],
      data: dist.map((d) => ({ name: d.model, value: d.count })),
      label: { color: "#e6edf3", fontSize: 11 },
      color: ["#58a6ff", "#3fb950", "#d29922", "#bc8cff", "#39d2c0", "#f85149"],
    }],
  });
  charts.push(chart);
}

function renderCostChart(data: any[]) {
  if (!costChart.value) return;
  const chart = echarts.init(costChart.value);
  const labels = data.map((d) => d.period_label);
  const costs = data.map((d) => d.total_cost);
  const tokens = data.map((d) => d.total_tokens);
  chart.setOption({
    tooltip: { trigger: "axis" },
    legend: { data: ["Cost (USD)", "Tokens"], textStyle: { color: "#8b949e" } },
    grid: { left: 60, right: 60, top: 40, bottom: 30 },
    xAxis: { type: "category", data: labels, axisLabel: { color: "#8b949e" } },
    yAxis: [
      { type: "value", name: "USD", axisLabel: { color: "#8b949e" }, splitLine: { lineStyle: { color: "#21262d" } } },
      { type: "value", name: "Tokens", axisLabel: { color: "#8b949e" }, splitLine: { show: false } },
    ],
    series: [
      { name: "Cost (USD)", type: "bar", data: costs, itemStyle: { color: "#d29922" } },
      { name: "Tokens", type: "line", yAxisIndex: 1, data: tokens, itemStyle: { color: "#58a6ff" }, smooth: true },
    ],
  });
  charts.push(chart);
}

function resizeCharts() { charts.forEach((c) => c.resize()); }
window.addEventListener("resize", resizeCharts);

onMounted(() => { loadAll(); timer = setInterval(loadAll, 30000); });
onUnmounted(() => { if (timer) clearInterval(timer); charts.forEach((c) => c.dispose()); window.removeEventListener("resize", resizeCharts); });
</script>

<style scoped>
.token-view { max-width: 1100px; }
.view-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-title { font-size: 20px; font-weight: 500; }
.controls { display: flex; gap: 8px; }
.select, .input { background: var(--bg-tertiary); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: var(--radius-sm); padding: 6px 10px; font-size: 12px; }
.input { width: 140px; }
.btn { background: var(--bg-tertiary); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: var(--radius-sm); padding: 6px 14px; font-size: 12px; cursor: pointer; }
.btn:hover { border-color: var(--accent-blue); }
.btn-sm { padding: 4px 10px; font-size: 11px; }
.btn-primary { background: var(--accent-blue); color: #0d1117; border-color: var(--accent-blue); font-weight: 500; }
.section-title { font-size: 14px; font-weight: 500; margin-bottom: 12px; }
.section-header-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header-row .section-title { margin-bottom: 0; }

.summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
.summary-card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 16px; }
.summary-label { font-size: 11px; color: var(--text-secondary); margin-bottom: 8px; }
.summary-value { font-size: 22px; font-weight: 600; color: var(--text-primary); }

.chart-card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 16px; margin-bottom: 20px; }
.chart { height: 300px; }
.chart-sm { height: 240px; }
.two-column { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }

.data-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.data-table th { text-align: left; padding: 8px; color: var(--text-secondary); border-bottom: 1px solid var(--border-color); }
.data-table td { padding: 8px; border-bottom: 1px solid var(--border-color); }

.budget-form { display: flex; gap: 8px; margin-bottom: 16px; align-items: center; }
.loading { color: var(--text-secondary); font-size: 13px; padding: 12px 0; }
.empty { color: var(--text-tertiary); font-size: 13px; text-align: center; padding: 20px; }

.progress-bar { display: inline-block; width: 80px; height: 6px; background: var(--bg-tertiary); border-radius: 3px; overflow: hidden; vertical-align: middle; margin-right: 8px; }
.progress-fill { height: 100%; transition: width 0.3s; }
.progress-fill.ok { background: var(--accent-green); }
.progress-fill.warning { background: var(--accent-yellow); }
.progress-fill.exceeded { background: var(--accent-red); }
.progress-label { font-size: 11px; color: var(--text-secondary); }
.status-pill { padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 500; }
.status-pill.ok { background: rgba(63,185,80,0.15); color: var(--accent-green); }
.status-pill.warning { background: rgba(210,153,34,0.15); color: var(--accent-yellow); }
.status-pill.exceeded { background: rgba(248,81,73,0.15); color: var(--accent-red); }
.status-pill.no_budget { background: rgba(110,118,129,0.15); color: var(--text-tertiary); }

.event-list { list-style: none; }
.event-item { padding: 8px 0; border-bottom: 1px solid var(--border-color); font-size: 12px; color: var(--text-secondary); }
</style>
