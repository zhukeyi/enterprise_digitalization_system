<template>
  <div class="health-view">
    <h1 class="page-title">Service Health</h1>
    <div class="probes-section">
      <div class="probe-card" v-for="probe in probes" :key="probe.name" :class="probe.status">
        <div class="probe-name">{{ probe.name }}</div>
        <div class="probe-status">{{ probe.status }}</div>
        <div class="probe-detail">{{ probe.detail }}</div>
      </div>
    </div>
    <h2 class="section-title">Component Matrix</h2>
    <table class="component-table">
      <thead>
        <tr><th>Component</th><th>Type</th><th>Status</th><th>Latency</th><th>Details</th></tr>
      </thead>
      <tbody>
        <tr v-for="comp in components" :key="comp.name" :class="comp.status">
          <td>{{ comp.name }}</td><td>{{ comp.type }}</td>
          <td><span class="status-dot"></span>{{ comp.status }}</td>
          <td>{{ comp.latency_ms }}ms</td>
          <td>{{ JSON.stringify(comp.details) }}</td>
        </tr>
      </tbody>
    </table>
    <h2 class="section-title">Service Map</h2>
    <div class="service-map">
      <div v-for="node in serviceNodes" :key="node.id" class="map-node" :class="node.status">
        {{ node.id }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";
import { api } from "../api/client";

const probes = ref([
  { name: "/healthz", status: "unknown", detail: "" },
  { name: "/readyz", status: "unknown", detail: "" },
  { name: "/livez", status: "unknown", detail: "" },
]);
const components = ref<any[]>([]);
const serviceNodes = ref<any[]>([]);
let timer: ReturnType<typeof setInterval> | null = null;

async function loadData() {
  try {
    const [hz, rz, lz, comps, sm] = await Promise.all([
      api.getHealthz(), api.getReadyz(), api.getLivez(), api.getComponents(), api.getServiceMap(),
    ]);
    probes.value[0].status = hz.status;
    probes.value[1].status = rz.status;
    probes.value[1].detail = `${rz.components?.length || 0} components`;
    probes.value[2].status = lz.status;
    probes.value[2].detail = `error_rate: ${lz.error_rate}`;
    components.value = comps.components || [];
    serviceNodes.value = sm.nodes || [];
  } catch (e) { console.error("Failed to load health:", e); }
}

onMounted(() => { loadData(); timer = setInterval(loadData, 60000); });
onUnmounted(() => { if (timer) clearInterval(timer); });
</script>

<style scoped>
.health-view { max-width: 900px; }
.page-title { font-size: 20px; font-weight: 500; margin-bottom: 24px; }
.probes-section { display: flex; gap: 16px; margin-bottom: 32px; }
.probe-card { flex: 1; background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 16px; }
.probe-card.healthy { border-color: var(--accent-green); }
.probe-card.degraded { border-color: var(--accent-yellow); }
.probe-card.unhealthy { border-color: var(--accent-red); }
.probe-name { font-size: 14px; font-weight: 500; margin-bottom: 8px; }
.probe-status { font-size: 12px; color: var(--text-secondary); margin-bottom: 4px; }
.probe-detail { font-size: 11px; color: var(--text-tertiary); }
.section-title { font-size: 15px; font-weight: 500; margin: 24px 0 12px; }
.component-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.component-table th { text-align: left; padding: 8px; color: var(--text-secondary); border-bottom: 1px solid var(--border-color); }
.component-table td { padding: 8px; border-bottom: 1px solid var(--border-color); }
.status-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 6px; }
tr.healthy .status-dot { background: var(--accent-green); }
tr.degraded .status-dot { background: var(--accent-yellow); }
tr.unhealthy .status-dot { background: var(--accent-red); }
.service-map { display: flex; flex-wrap: wrap; gap: 8px; }
.map-node { padding: 6px 12px; background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-sm); font-size: 12px; }
.map-node.online { border-color: var(--accent-green); }
.map-node.degraded { border-color: var(--accent-yellow); }
</style>
