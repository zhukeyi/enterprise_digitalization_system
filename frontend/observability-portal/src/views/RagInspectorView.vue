<template>
  <div class="rag-view">
    <h1 class="page-title">RAG Inspector</h1>
    <div class="placeholder">
      <p>Phase 3 will implement chunk inspection, retrieval replay, and document management.</p>
      <p>Current status: {{ docs?.note || "Loading..." }}</p>
    </div>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from "vue";
import { api } from "../api/client";
const docs = ref<any>(null);
onMounted(async () => { try { docs.value = await api.getRagDocs(); } catch (e) { console.error(e); } });
</script>
<style scoped>
.rag-view { max-width: 900px; }
.page-title { font-size: 20px; font-weight: 500; margin-bottom: 24px; }
.placeholder { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 32px; text-align: center; color: var(--text-secondary); }
</style>
