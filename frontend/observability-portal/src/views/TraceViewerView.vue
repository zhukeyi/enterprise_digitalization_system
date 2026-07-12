<template>
  <div class="trace-view">
    <h1 class="page-title">Trace Viewer</h1>
    <div class="placeholder">
      <p>Phase 3 will implement trace span storage and waterfall visualization.</p>
      <p>Current status: {{ traces?.note || "Loading..." }}</p>
    </div>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from "vue";
import { api } from "../api/client";
const traces = ref<any>(null);
onMounted(async () => { try { traces.value = await api.getTraces(); } catch (e) { console.error(e); } });
</script>
<style scoped>
.trace-view { max-width: 900px; }
.page-title { font-size: 20px; font-weight: 500; margin-bottom: 24px; }
.placeholder { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 32px; text-align: center; color: var(--text-secondary); }
</style>
