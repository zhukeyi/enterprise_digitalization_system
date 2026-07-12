<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getOverview, getItems, type OverviewStats, type IntelItem } from '../api/client'

const overview = ref<OverviewStats | null>(null)
const items = ref<IntelItem[]>([])
const loading = ref(true)
const error = ref('')
const sentimentFilter = ref('')

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const [ov, it] = await Promise.all([getOverview(), getItems(100)])
    overview.value = ov
    items.value = it
  } catch (e: any) {
    error.value = e?.message || '加载情报数据失败'
  } finally {
    loading.value = false
  }
}

function filteredItems(): IntelItem[] {
  if (!sentimentFilter.value) return items.value
  return items.value.filter(i => i.sentiment === sentimentFilter.value)
}

function sentimentLabel(s: string): string {
  const map: Record<string, string> = { positive: '正向', neutral: '中性', negative: '负向' }
  return map[s] || s
}

function exportReport() {
  if (!overview.value) return
  const ov = overview.value
  const lines = [
    `# FDE 情报报告`,
    `生成时间: ${new Date().toLocaleString('zh-CN')}`,
    '',
    `## 总览`,
    `- 情报条目总数: ${ov.total_items}`,
    `- 数据源数: ${ov.total_sources}`,
    `- 情感分布: 正向 ${ov.sentiment_distribution.positive} / 中性 ${ov.sentiment_distribution.neutral} / 负向 ${ov.sentiment_distribution.negative}`,
    '',
    `## 数据源类型分布`,
    ...ov.source_types.map(s => `- ${s.name}: ${s.count} 条`),
    '',
    `## 近期情报摘要`,
    ...ov.recent_items.slice(0, 10).map((item, i) => `### ${i + 1}. ${item.title}\n- 来源: ${item.source}\n- 情感: ${sentimentLabel(item.sentiment)}\n- 摘要: ${item.summary}\n- 关键词: ${(item.keywords || []).join(', ')}\n`),
  ]
  const blob = new Blob([lines.join('\n')], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `intel-report-${Date.now()}.md`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(() => loadData())
</script>

<template>
  <div class="view">
    <div v-if="loading" class="loading">生成报告中...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <template v-else-if="overview">
      <div class="header-row">
        <h2>情报报告</h2>
        <button class="btn-export" @click="exportReport">导出 Markdown</button>
      </div>

      <div class="report-grid">
        <div class="panel">
          <h3>条目总数</h3>
          <div class="big-num cyan">{{ overview.total_items }}</div>
        </div>
        <div class="panel">
          <h3>数据源</h3>
          <div class="big-num purple">{{ overview.total_sources }}</div>
        </div>
        <div class="panel">
          <h3>正向情报</h3>
          <div class="big-num green">{{ overview.sentiment_distribution.positive }}</div>
        </div>
        <div class="panel">
          <h3>负向情报</h3>
          <div class="big-num red">{{ overview.sentiment_distribution.negative }}</div>
        </div>
      </div>

      <div class="panel">
        <h3>数据源类型分布</h3>
        <div class="dist-list">
          <div v-for="s in overview.source_types" :key="s.name" class="dist-item">
            <span class="dist-name">{{ s.name }}</span>
            <div class="dist-bar-bg">
              <div class="dist-bar" :style="{ width: (s.count / overview.total_items * 100) + '%' }" />
            </div>
            <span class="dist-count">{{ s.count }}</span>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="filter-row">
          <h3>情报条目列表</h3>
          <div class="filters">
            <button :class="['filter-btn', { active: sentimentFilter === '' }]" @click="sentimentFilter = ''">全部</button>
            <button :class="['filter-btn', { active: sentimentFilter === 'positive' }]" @click="sentimentFilter = 'positive'">正向</button>
            <button :class="['filter-btn', { active: sentimentFilter === 'neutral' }]" @click="sentimentFilter = 'neutral'">中性</button>
            <button :class="['filter-btn', { active: sentimentFilter === 'negative' }]" @click="sentimentFilter = 'negative'">负向</button>
          </div>
        </div>
        <div class="item-list">
          <div v-for="item in filteredItems().slice(0, 30)" :key="item.id" class="item-card">
            <div class="item-head">
              <span class="item-title">{{ item.title }}</span>
              <span class="sentiment-badge" :class="item.sentiment">{{ sentimentLabel(item.sentiment) }}</span>
            </div>
            <div class="item-summary">{{ item.summary }}</div>
            <div class="item-meta">
              <span class="meta-src">{{ item.source }}</span>
              <span class="meta-date">{{ item.collected_at?.slice(0, 10) || '—' }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.view { display: flex; flex-direction: column; gap: 16px; }
.loading { padding: 40px; text-align: center; color: var(--text-muted); }
.error { padding: 20px; text-align: center; color: var(--accent-red); }

.header-row { display: flex; align-items: center; justify-content: space-between; }
h2 { font-size: 20px; font-weight: 700; color: var(--text-primary); margin: 0; }
h3 { font-size: 14px; color: var(--accent); margin: 0; letter-spacing: 1px; }

.btn-export {
  padding: 8px 16px; background: transparent; border: 1px solid var(--accent); border-radius: 8px;
  color: var(--accent); font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.2s;
}
.btn-export:hover { background: rgba(0,212,255,0.1); box-shadow: 0 0 12px var(--accent-glow); }

.report-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.panel { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 18px; }
.big-num { font-size: 36px; font-weight: 800; margin-top: 8px; }
.big-num.cyan { color: var(--accent); text-shadow: 0 0 12px var(--accent-glow); }
.big-num.purple { color: var(--accent-purple); }
.big-num.green { color: var(--accent-green); }
.big-num.red { color: var(--accent-red); }

.dist-list { display: flex; flex-direction: column; gap: 10px; }
.dist-item { display: flex; align-items: center; gap: 12px; }
.dist-name { font-size: 13px; color: var(--text-secondary); min-width: 80px; }
.dist-bar-bg { flex: 1; height: 8px; background: var(--bg-secondary); border-radius: 4px; overflow: hidden; }
.dist-bar { height: 100%; background: var(--gradient-cyan); border-radius: 4px; transition: width 0.3s; }
.dist-count { font-size: 13px; color: var(--text-primary); font-weight: 600; min-width: 40px; text-align: right; }

.filter-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.filters { display: flex; gap: 6px; }
.filter-btn {
  padding: 5px 12px; background: transparent; border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-muted); font-size: 12px; cursor: pointer;
}
.filter-btn.active { border-color: var(--accent); color: var(--accent); background: rgba(0,212,255,0.1); }

.item-list { display: flex; flex-direction: column; gap: 10px; max-height: 600px; overflow-y: auto; }
.item-card { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px; padding: 14px; }
.item-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
.item-title { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.sentiment-badge { font-size: 11px; padding: 2px 8px; border-radius: 4px; white-space: nowrap; }
.sentiment-badge.positive { background: rgba(34,197,94,0.2); color: var(--accent-green); }
.sentiment-badge.neutral { background: rgba(148,163,184,0.2); color: var(--text-secondary); }
.sentiment-badge.negative { background: rgba(239,68,68,0.2); color: var(--accent-red); }
.item-summary { font-size: 13px; color: var(--text-secondary); line-height: 1.5; margin-bottom: 8px; }
.item-meta { display: flex; gap: 12px; font-size: 11px; color: var(--text-muted); }
</style>
