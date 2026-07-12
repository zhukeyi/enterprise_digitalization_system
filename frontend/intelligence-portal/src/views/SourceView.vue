<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getSources, type SourceInfo } from '../api/client'

const sources = ref<SourceInfo[]>([])
const loading = ref(true)
const error = ref('')

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    sources.value = await getSources()
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => loadData())
</script>

<template>
  <div class="view">
    <div v-if="loading" class="loading">扫描数据源...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <template v-else>
      <div class="header-row">
        <h2>数据源管理</h2>
        <span class="count">{{ sources.length }} 个活跃源</span>
      </div>
      <div class="grid">
        <div v-for="s in sources" :key="s.url" class="card" :class="{ active: s.active }">
          <div class="card-head">
            <span class="source-type" :class="s.source_type">{{ s.source_type.toUpperCase() }}</span>
            <span class="status-dot" :class="{ active: s.active }" />
          </div>
          <div class="source-label">{{ s.label }}</div>
          <div class="source-url">{{ s.url }}</div>
          <div class="source-meta">上限 {{ s.max_items }} 条/次</div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.view { display: flex; flex-direction: column; gap: 16px; }
.loading { padding: 40px; text-align: center; color: var(--text-muted); font-size: 14px; }
.error { padding: 20px; text-align: center; color: var(--accent-red); }

.header-row { display: flex; align-items: center; gap: 12px; }
.header-row h2 { font-size: 20px; font-weight: 700; color: var(--text-primary); margin: 0; }
.count { font-size: 13px; color: var(--text-muted); }

.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }

.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.card:hover { border-color: var(--accent); box-shadow: 0 0 20px var(--accent-glow); }

.card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }

.source-type {
  font-size: 11px; font-weight: 700; letter-spacing: 1px;
  padding: 3px 8px; border-radius: 4px;
  background: rgba(0, 212, 255, 0.15); color: var(--accent);
}
.source-type.http { background: rgba(168, 85, 247, 0.15); color: var(--accent-purple); }
.source-type.api { background: rgba(34, 197, 94, 0.15); color: var(--accent-green); }

.status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-muted); }
.status-dot.active { background: var(--accent-green); box-shadow: 0 0 8px var(--accent-green); animation: pulse-glow 2s infinite; }

.source-label { font-size: 15px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }
.source-url { font-size: 12px; color: var(--text-muted); font-family: 'SF Mono', monospace; word-break: break-all; margin-bottom: 8px; }
.source-meta { font-size: 12px; color: var(--text-secondary); }
</style>
