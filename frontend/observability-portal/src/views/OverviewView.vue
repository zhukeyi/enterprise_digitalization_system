<template>
  <div class="overview">
    <h1 class="page-title">Platform Overview</h1>
    <div class="health-score-section">
      <div ref="gaugeEl" class="gauge-chart"></div>
      <div class="health-status">
        <span class="status-badge" :class="healthStatusClass">{{ healthStatusText }}</span>
        <span class="last-updated">Updated {{ lastUpdated }}</span>
      </div>
    </div>
    <div class="kpi-grid">
      <div v-for="kpi in kpis" :key="kpi.label" class="kpi-card">
        <div class="kpi-label">{{ kpi.label }}</div>
        <div class="kpi-value">{{ kpi.value }}<span class="kpi-unit">{{ kpi.unit }}</span></div>
      </div>
    </div>
    <div class="modules-section">
      <h2 class="section-title">Agent Modules</h2>
      <div class="modules-grid">
        <div v-for="mod in modules" :key="mod.name" class="module-card" :class="mod.status">
          <span class="module-status-dot"></span>
          <span class="module-name">{{ mod.name }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from "vue";
import * as echarts from "echarts";
import { api } from "../api/client";

const gaugeEl = ref<HTMLElement>();
let chart: echarts.ECharts | null = null;
let timer: ReturnType<typeof setInterval> | null = null;
const healthScore = ref(100);
const kpis = ref<any[]>([]);
const modules = ref<any[]>([]);
const lastUpdated = ref("");

const healthStatusClass = computed(() => {
  if (healthScore.value >= 80) return "healthy";
  if (healthScore.value >= 50) return "degraded";
  return "unhealthy";
});
const healthStatusText = computed(() => {
  if (healthScore.value >= 80) return "Healthy";
  if (healthScore.value >= 50) return "Degraded";
  return "Unhealthy";
});

async function loadData() {
  try {
    const data = await api.getOverview();
    healthScore.value = data.health_score;
    kpis.value = data.kpis || [];
    modules.value = data.modules || [];
    lastUpdated.value = new Date().toLocaleTimeString();
    renderGauge();
  } catch (e) { console.error("Failed to load overview:", e); }
}

function renderGauge() {
  if (!gaugeEl.value) return;
  if (!chart) chart = echarts.init(gaugeEl.value);
  chart.setOption({
    series: [{
      type: "gauge", startAngle: 200, endAngle: -20, min: 0, max: 100, radius: "90%",
      progress: { show: true, width: 14 },
      axisLine: { lineStyle: { width: 14 } },
      axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false }, pointer: { show: false },
      detail: { valueAnimation: true, fontSize: 36, fontWeight: 500, color: "#e6edf3", offsetCenter: [0, "10%"], formatter: "{value}" },
      data: [{ value: healthScore.value }],
    }],
  });
}

onMounted(() => { loadData(); timer = setInterval(loadData, 30000); });
onUnmounted(() => { if (timer) clearInterval(timer); if (chart) chart.dispose(); });
</script>

<style scoped>
.overview { max-width: 900px; }
.page-title { font-size: 20px; font-weight: 500; margin-bottom: 24px; }
.health-score-section { display: flex; align-items: center; gap: 32px; margin-bottom: 32px; }
.gauge-chart { width: 200px; height: 160px; }
.health-status { display: flex; flex-direction: column; gap: 8px; }
.status-badge { padding: 4px 12px; border-radius: 20px; font-size: 13px; font-weight: 500; }
.status-badge.healthy { background: rgba(63,185,80,0.15); color: var(--accent-green); }
.status-badge.degraded { background: rgba(210,153,34,0.15); color: var(--accent-yellow); }
.status-badge.unhealthy { background: rgba(248,81,73,0.15); color: var(--accent-red); }
.last-updated { font-size: 12px; color: var(--text-tertiary); }
.kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 32px; }
.kpi-card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 16px; }
.kpi-label { font-size: 12px; color: var(--text-secondary); margin-bottom: 8px; }
.kpi-value { font-size: 28px; font-weight: 500; }
.kpi-unit { font-size: 14px; color: var(--text-tertiary); margin-left: 4px; }
.section-title { font-size: 15px; font-weight: 500; margin-bottom: 16px; }
.modules-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 8px; }
.module-card { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-sm); font-size: 12px; }
.module-status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.module-card.online .module-status-dot { background: var(--accent-green); }
.module-card.degraded .module-status-dot { background: var(--accent-yellow); }
.module-card.offline .module-status-dot { background: var(--accent-red); }
.module-name { color: var(--text-secondary); }
</style>
