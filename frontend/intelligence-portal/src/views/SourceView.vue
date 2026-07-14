<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import {
  getSources,
  getSourceTypes,
  getRSSHubRoutes,
  collectIntelligence,
  type SourceInfo,
  type SourceTypeOption,
  type RSSHubRouteCategory,
} from '../api/client'

// ── State ──────────────────────────────────────────────────────────
const sources = ref<SourceInfo[]>([])
const sourceTypes = ref<SourceTypeOption[]>([])
const rsshubRoutes = ref<RSSHubRouteCategory>({})
const loading = ref(true)
const error = ref('')

// ── Collect dialog ─────────────────────────────────────────────────
const showCollect = ref(false)
const collectForm = ref({
  source_type: 'rsshub',
  url: '',
  max_items: 20,
})
const collectResult = ref<{ success: boolean; count: number; error: string } | null>(null)
const collectLoading = ref(false)

// ── RSSHub route browser ───────────────────────────────────────────
const activeCategory = ref('news_global')
const rsshubRoutesExpanded = ref(false)

const categories = computed(() => Object.keys(rsshubRoutes.value))
const currentRoutes = computed(() => rsshubRoutes.value[activeCategory.value] || [])

// ── Methods ────────────────────────────────────────────────────────
async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const [srcs, types, routes] = await Promise.all([
      getSources(),
      getSourceTypes().catch(() => []),
      getRSSHubRoutes().catch(() => ({})),
    ])
    sources.value = srcs
    sourceTypes.value = types
    rsshubRoutes.value = routes
  } catch (e: any) {
    error.value = e?.message || 'Load failed'
  } finally {
    loading.value = false
  }
}

function openCollect(route?: string) {
  if (route) {
    collectForm.value.url = route
    collectForm.value.source_type = 'rsshub'
  }
  collectResult.value = null
  showCollect.value = true
}

async function doCollect() {
  collectLoading.value = true
  collectResult.value = null
  try {
    const result = await collectIntelligence({
      source_type: collectForm.value.source_type,
      url: collectForm.value.url,
      max_items: collectForm.value.max_items,
    })
    collectResult.value = {
      success: result.success,
      count: result.items_collected,
      error: result.error || '',
    }
  } catch (e: any) {
    collectResult.value = {
      success: false,
      count: 0,
      error: e?.message || 'Collection failed',
    }
  } finally {
    collectLoading.value = false
  }
}

function sourceTypeClass(type: string): string {
  return type.toLowerCase()
}

function sourceTypeLabel(type: string): string {
  const found = sourceTypes.value.find((t) => t.type === type)
  return found ? found.label : type.toUpperCase()
}

onMounted(() => loadData())
</script>

<template>
  <div class="view">
    <div v-if="loading" class="loading">Scanning data sources...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <template v-else>
      <!-- Header -->
      <div class="header-row">
        <h2>Data Sources</h2>
        <span class="count">{{ sources.length }} active sources</span>
        <button class="btn-primary" @click="openCollect()">+ Trigger Collection</button>
      </div>

      <!-- Source type legend -->
      <div v-if="sourceTypes.length" class="type-legend">
        <div v-for="t in sourceTypes" :key="t.type" class="type-badge" :class="t.type">
          <span class="type-name">{{ t.label }}</span>
          <span class="type-desc">{{ t.description }}</span>
        </div>
      </div>

      <!-- Source cards -->
      <div class="section-title">Configured Sources</div>
      <div class="grid">
        <div v-for="s in sources" :key="s.url" class="card" :class="{ active: s.active }">
          <div class="card-head">
            <span class="source-type" :class="sourceTypeClass(s.source_type)">{{ sourceTypeLabel(s.source_type) }}</span>
            <span class="status-dot" :class="{ active: s.active }" />
          </div>
          <div class="source-label">{{ s.label }}</div>
          <div class="source-url">{{ s.url }}</div>
          <div class="source-meta">Max {{ s.max_items }} items/run</div>
        </div>
      </div>

      <!-- RSSHub route browser -->
      <div v-if="categories.length" class="rsshub-section">
        <div class="section-title" @click="rsshubRoutesExpanded = !rsshubRoutesExpanded">
          RSSHub Predefined Routes
          <span class="expand-toggle">{{ rsshubRoutesExpanded ? '[Collapse]' : '[Expand]' }}</span>
        </div>
        <div v-if="rsshubRoutesExpanded" class="rsshub-browser">
          <div class="category-tabs">
            <button
              v-for="cat in categories"
              :key="cat"
              class="cat-tab"
              :class="{ active: cat === activeCategory }"
              @click="activeCategory = cat"
            >
              {{ cat }}
            </button>
          </div>
          <div class="route-list">
            <div v-for="route in currentRoutes" :key="route" class="route-item">
              <span class="route-path">{{ route }}</span>
              <button class="btn-mini" @click="openCollect(route)">Collect</button>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Collect Dialog -->
    <div v-if="showCollect" class="modal-overlay" @click.self="showCollect = false">
      <div class="modal">
        <h3>Trigger Collection</h3>
        <div class="form-group">
          <label>Source Type</label>
          <select v-model="collectForm.source_type">
            <option v-for="t in sourceTypes" :key="t.type" :value="t.type">{{ t.label }}</option>
            <option value="rss">RSS/Atom Feed</option>
            <option value="web">Web Page (HTTP)</option>
          </select>
        </div>
        <div class="form-group">
          <label>URL / Route</label>
          <input v-model="collectForm.url" placeholder="/reuters/business or https://..." />
        </div>
        <div class="form-group">
          <label>Max Items</label>
          <input v-model.number="collectForm.max_items" type="number" min="1" max="500" />
        </div>
        <div v-if="collectResult" class="result" :class="{ ok: collectResult.success, err: !collectResult.success }">
          <template v-if="collectResult.success">Collected {{ collectResult.count }} items.</template>
          <template v-else>Failed: {{ collectResult.error }}</template>
        </div>
        <div class="modal-actions">
          <button class="btn-secondary" @click="showCollect = false">Close</button>
          <button class="btn-primary" :disabled="collectLoading" @click="doCollect">
            {{ collectLoading ? 'Collecting...' : 'Collect' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.view { display: flex; flex-direction: column; gap: 16px; }
.loading { padding: 40px; text-align: center; color: var(--text-muted); font-size: 14px; }
.error { padding: 20px; text-align: center; color: var(--accent-red); }

.header-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.header-row h2 { font-size: 20px; font-weight: 700; color: var(--text-primary); margin: 0; }
.count { font-size: 13px; color: var(--text-muted); flex: 1; }

.btn-primary {
  background: var(--accent); color: #fff; border: none; border-radius: 8px;
  padding: 8px 16px; font-size: 13px; font-weight: 600; cursor: pointer;
  transition: opacity 0.2s;
}
.btn-primary:hover { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-secondary {
  background: transparent; color: var(--text-secondary); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 16px; font-size: 13px; cursor: pointer;
}
.btn-secondary:hover { border-color: var(--accent); }

.btn-mini {
  background: transparent; color: var(--accent); border: 1px solid var(--accent);
  border-radius: 4px; padding: 2px 8px; font-size: 11px; cursor: pointer;
}
.btn-mini:hover { background: rgba(0, 212, 255, 0.1); }

/* Type legend */
.type-legend { display: flex; flex-wrap: wrap; gap: 8px; }
.type-badge {
  display: flex; flex-direction: column; padding: 6px 12px; border-radius: 8px;
  border: 1px solid var(--border); background: var(--bg-card);
}
.type-name { font-size: 12px; font-weight: 700; }
.type-desc { font-size: 10px; color: var(--text-muted); }

/* Source grid */
.section-title {
  font-size: 14px; font-weight: 600; color: var(--text-secondary);
  margin-top: 8px; cursor: pointer;
}
.expand-toggle { font-size: 11px; color: var(--accent); margin-left: 8px; }

.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }

.card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 12px; padding: 18px;
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
.source-type.rsshub { background: rgba(251, 146, 60, 0.15); color: #fb923c; }
.source-type.crawl4ai { background: rgba(244, 114, 182, 0.15); color: #f472b6; }
.source-type.customs { background: rgba(96, 165, 250, 0.15); color: #60a5fa; }

.status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-muted); }
.status-dot.active { background: var(--accent-green); box-shadow: 0 0 8px var(--accent-green); }

.source-label { font-size: 15px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }
.source-url { font-size: 12px; color: var(--text-muted); font-family: 'SF Mono', monospace; word-break: break-all; margin-bottom: 8px; }
.source-meta { font-size: 12px; color: var(--text-secondary); }

/* RSSHub browser */
.rsshub-section { margin-top: 8px; }
.rsshub-browser { margin-top: 8px; }
.category-tabs { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 12px; }
.cat-tab {
  background: transparent; border: 1px solid var(--border); border-radius: 6px;
  padding: 4px 12px; font-size: 12px; color: var(--text-secondary); cursor: pointer;
}
.cat-tab.active { background: var(--accent); color: #fff; border-color: var(--accent); }

.route-list { display: flex; flex-direction: column; gap: 4px; }
.route-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px; background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 6px;
}
.route-path { font-family: 'SF Mono', monospace; font-size: 13px; color: var(--text-secondary); }

/* Modal */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.6);
  display: flex; align-items: center; justify-content: center; z-index: 1000;
}
.modal {
  background: var(--bg-card); border-radius: 16px; padding: 24px;
  min-width: 400px; max-width: 500px; border: 1px solid var(--border);
}
.modal h3 { margin: 0 0 16px; font-size: 18px; color: var(--text-primary); }

.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 12px; color: var(--text-muted); margin-bottom: 4px; }
.form-group input, .form-group select {
  width: 100%; padding: 8px 12px; border: 1px solid var(--border);
  border-radius: 8px; background: var(--bg-primary); color: var(--text-primary);
  font-size: 14px;
}
.form-group input:focus, .form-group select:focus { border-color: var(--accent); outline: none; }

.result { padding: 10px 12px; border-radius: 8px; font-size: 13px; margin-bottom: 12px; }
.result.ok { background: rgba(34, 197, 94, 0.1); color: var(--accent-green); }
.result.err { background: rgba(239, 68, 68, 0.1); color: var(--accent-red); }

.modal-actions { display: flex; justify-content: flex-end; gap: 8px; }
</style>
