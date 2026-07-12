<template>
  <div class="audit-view">
    <h1 class="page-title">Audit Trail</h1>
    <div class="placeholder">
      <p>Phase 4 will implement audit log query and export.</p>
      <p>Current status: {{ logs?.note || "Loading..." }}</p>
    </div>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from "vue";
import { api } from "../api/client";
const logs = ref<any>(null);
onMounted(async () => { try { logs.value = await api.getAuditLogs(); } catch (e) { console.error(e); } });
</script>
<style scoped>
.audit-view { max-width: 900px; }
.page-title { font-size: 20px; font-weight: 500; margin-bottom: 24px; }
.placeholder { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 32px; text-align: center; color: var(--text-secondary); }
</style>
