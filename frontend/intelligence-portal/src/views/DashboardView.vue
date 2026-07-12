<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { getOverview, type OverviewStats } from '../api/client'

const stats = ref<OverviewStats | null>(null)
const loading = ref(true)
const error = ref('')

const trendChartRef = ref<HTMLElement | null>(null)
const sentimentChartRef = ref<HTMLElement | null>(null)
const sourceChartRef = ref<HTMLElement | null>(null)
let trendChart: echarts.ECharts | null = null
let sentimentChart: echarts.ECharts | null = null
let sourceChart: echarts.ECharts | null = null

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    stats.value = await getOverview()
    await nextTick()
    renderCharts()
  } catch (err: unknown) {
    error.value = (err as { message?: string })?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function renderCharts() {
  if (!stats.value) return
  const darkAxis = { axisLabel: { color: '#94a3b8', fontSize: 11 }, axisLine: { lineStyle: { color: '#2a3556' } } }

  if (trendChartRef.value) {
    if (trendChart) trendChart.dispose()
    trendChart = echarts.init(trendChartRef.value, 'dark')
    trendChart.setOption({
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis' },
      grid: { left: 40, right: 20, top: 30, bottom: 30 },
      xAxis: { type: 'category', data: stats.value.daily_collection.map(d => d.date), ...darkAxis },
      yAxis: { type: 'value', minInterval: 1, ...darkAxis },
      series: [{
        type: 'line',
        data: stats.value.daily_collection.map(d => d.count),
        smooth: true, symbol: 'circle', symbolSize: 8,
        lineStyle: { width: 3, color: '#00d4ff', shadowColor: 'rgba(0,212,255,0.5)', shadowBlur: 10 },
        itemStyle: { color: '#00d4ff', borderColor: '#0a0e1a', borderWidth: 2 },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(0,212,255,0.3)' }, { offset: 1, color: 'rgba(0,212,255,0.02)' },
        ]) },
      }],
    })
  }

  if (sentimentChartRef.value) {
    if (sentimentChart) sentimentChart.dispose()
    sentimentChart = echarts.init(sentimentChartRef.value, 'dark')
    const sd = stats.value.sentiment_distribution
    const total = sd.positive + sd.neutral + sd.negative || 1
    const posPct = Math.round((sd.positive / total) * 100)
    sentimentChart.setOption({
      backgroundColor: 'transparent',
      series: [{
        type: 'gauge', startAngle: 180, endAngle: 0, min: 0, max: 100,
        radius: '90%', center: ['50%', '75%'],
        progress: { show: true, width: 14, roundCap: true,
          itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: '#ef4444' }, { offset: 0.5, color: '#f59e0b' }, { offset: 1, color: '#22c55e' },
          ]) } },
        axisLine: { lineStyle: { width: 14, color: [[1, '#1a2035']] } },
        pointer: { show: false }, axisTick: { show: false },
        splitLine: { show: false }, axisLabel: { show: false },
        detail: { valueAnimation: true, formatter: '{value}%', color: '#e2e8f0', fontSize: 28, fontWeight: 'bold', offsetCenter: [0, -20] },
        title: { show: true, offsetCenter: [0, 20], color: '#94a3b8', fontSize: 12 },
        data: [{ value: posPct, name: '正向情绪' }],
      }],
    })
  }

  if (sourceChartRef.value) {
    if (sourceChart) sourceChart.dispose()
    sourceChart = echarts.init(sourceChartRef.value, 'dark')
    sourceChart.setOption({
      backgroundColor: 'transparent',
      tooltip: { trigger: 'item' },
      legend: { bottom: 10, textStyle: { color: '#94a3b8', fontSize: 12 } },
      series: [{
        type: 'pie', radius: ['45%', '70%'], center: ['50%', '45%'],
        label: { show: false },
        emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold', color: '#e2e8f0' } },
        data: stats.value.source_types.map((s, i) => ({
          name: s.name, value: s.count,
          itemStyle: { color: ['#00d4ff', '#a855f7', '#22c55e'][i % 3] },
        })),
      }],
    })
  }
}

function handleResize() { trendChart?.resize(); sentimentChart?.resize(); sourceChart?.resize() }
onMounted(() => { loadData(); window.addEventListener('resize', handleResize) })
onUnmounted(() => { window.removeEventListener('resize', handleResize); trendChart?.dispose(); sentimentChart?.dispose(); sourceChart?.dispose() })

function fmtTime(iso: string): string {
  if (!iso) return '-'
  try { const d = new Date(iso); return d.getMonth()+1 + '/' + d.getDate() + ' ' + String(d.getHours()).padStart(2,'0') + ':' + String(d.getMinutes()).padStart(2,'0') } catch { return iso }
}
function sentimentColor(s: string): string { return s === 'positive' ? 'var(--accent-green)' : s === 'negative' ? 'var(--accent-red)' : 'var(--text-muted)' }
function sentimentLabel(s: string): string { return s === 'positive' ? '正向' : s === 'negative' ? '负向' : '中性' }
</script>

<template>
  <div class="dashboard">
    <div v-if="loading" class="loading">
      <div class="scan-line" />
      <span>INITIALIZING INTELLIGENCE GRID...</span>
    </div>
    <div v-else-if="error" class="error-banner">
      <span>{{ error }}</span><button @click="loadData">RETRY</button>
    </div>
    <template v-else-if="stats">
      <div class="kpi-row">
        <div class="kpi-card cyan"><div class="kpi-label">TOTAL INTEL</div><div class="kpi-value">{{ stats.total_items }}</div><div class="kpi-sub">情报条目</div></div>
        <div class="kpi-card purple"><div class="kpi-label">DATA SOURCES</div><div class="kpi-value">{{ stats.total_sources }}</div><div class="kpi-sub">数据源</div></div>
        <div class="kpi-card green"><div class="kpi-label">POSITIVE</div><div class="kpi-value">{{ stats.sentiment_distribution.positive }}</div><div class="kpi-sub">正向情报</div></div>
        <div class="kpi-card red"><div class="kpi-label">NEGATIVE</div><div class="kpi-value">{{ stats.sentiment_distribution.negative }}</div><div class="kpi-sub">负向情报</div></div>
      </div>
      <div class="chart-row">
        <div class="panel chart-panel wide">
          <div class="panel-header"><span class="panel-title">采集趋势 / COLLECTION TREND</span><span class="panel-badge">7D</span></div>
          <div ref="trendChartRef" class="chart-canvas" />
        </div>
        <div class="panel chart-panel">
          <div class="panel-header"><span class="panel-title">情绪分布 / SENTIMENT</span></div>
          <div ref="sentimentChartRef" class="chart-canvas" />
        </div>
        <div class="panel chart-panel">
          <div class="panel-header"><span class="panel-title">数据源 / SOURCES</span></div>
          <div ref="sourceChartRef" class="chart-canvas" />
        </div>
      </div>
      <div class="panel feed-panel">
        <div class="panel-header"><span class="panel-title">情报流 / INTEL FEED</span><span class="panel-badge live">LIVE</span></div>
        <div class="feed-list">
          <div v-for="(item, idx) in stats.recent_items" :key="item.id" class="feed-item" :style="{ animationDelay: idx * 0.08 + 's' }">
            <div class="feed-sentiment" :style="{ background: sentimentColor(item.sentiment) }" />
            <div class="feed-body">
              <div class="feed-title">{{ item.title }}</div>
              <div class="feed-meta">
                <span class="feed-source">{{ item.source }}</span>
                <span class="feed-time">{{ fmtTime(item.collected_at) }}</span>
                <span class="feed-sentiment-tag" :style="{ color: sentimentColor(item.sentiment) }">{{ sentimentLabel(item.sentiment) }}</span>
              </div>
              <div class="feed-summary">{{ item.summary }}</div>
              <div class="feed-keywords"><span v-for="kw in item.keywords" :key="kw" class="keyword-tag">{{ kw }}</span></div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.dashboard { display: flex; flex-direction: column; gap: 20px; }
.loading { display: flex; align-items: center; justify-content: center; height: 60vh; position: relative; overflow: hidden; color: var(--accent); font-size: 14px; letter-spacing: 3px; }
.scan-line { position: absolute; left: 0; right: 0; height: 2px; background: linear-gradient(90deg, transparent, var(--accent), transparent); animation: scan-line 2s linear infinite; }
.error-banner { background: rgba(239,68,68,0.1); border: 1px solid var(--accent-red); border-radius: 8px; padding: 16px 20px; display: flex; justify-content: space-between; align-items: center; color: var(--accent-red); font-size: 14px; }
.error-banner button { background: var(--accent-red); color: #fff; border: none; border-radius: 6px; padding: 4px 14px; cursor: pointer; }
.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.kpi-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; position: relative; overflow: hidden; animation: fade-in-up 0.5s ease-out; }
.kpi-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; }
.kpi-card.cyan::before { background: var(--gradient-cyan); }
.kpi-card.purple::before { background: var(--gradient-purple); }
.kpi-card.green::before { background: var(--gradient-green); }
.kpi-card.red::before { background: var(--gradient-red); }
.kpi-label { font-size: 11px; letter-spacing: 1.5px; color: var(--text-muted); font-weight: 600; }
.kpi-value { font-size: 36px; font-weight: 800; margin-top: 8px; color: var(--text-primary); font-variant-numeric: tabular-nums; }
.kpi-card.cyan .kpi-value { color: var(--accent); text-shadow: 0 0 12px var(--accent-glow); }
.kpi-card.purple .kpi-value { color: var(--accent-purple); }
.kpi-card.green .kpi-value { color: var(--accent-green); }
.kpi-card.red .kpi-value { color: var(--accent-red); }
.kpi-sub { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
.panel { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
.panel-header { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
.panel-title { font-size: 13px; font-weight: 600; color: var(--text-secondary); letter-spacing: 1px; }
.panel-badge { font-size: 10px; padding: 2px 8px; border-radius: 20px; background: var(--bg-secondary); color: var(--text-muted); letter-spacing: 1px; }
.panel-badge.live { color: var(--accent-green); border: 1px solid rgba(34,197,94,0.3); }
.panel-badge.live::before { content: ''; display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: var(--accent-green); margin-right: 4px; animation: pulse-glow 1.5s infinite; }
.chart-row { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 16px; }
.chart-canvas { width: 100%; height: 300px; }
.feed-list { display: flex; flex-direction: column; gap: 0; max-height: 600px; overflow-y: auto; }
.feed-item { display: flex; gap: 16px; padding: 16px 0; border-bottom: 1px solid var(--border); animation: fade-in-up 0.4s ease-out both; }
.feed-item:last-child { border-bottom: none; }
.feed-sentiment { width: 4px; border-radius: 2px; flex-shrink: 0; }
.feed-body { flex: 1; min-width: 0; }
.feed-title { font-size: 15px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }
.feed-meta { display: flex; gap: 12px; font-size: 12px; color: var(--text-muted); margin-bottom: 6px; }
.feed-source { color: var(--accent); }
.feed-sentiment-tag { font-weight: 600; }
.feed-summary { font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 8px; }
.feed-keywords { display: flex; gap: 6px; flex-wrap: wrap; }
.keyword-tag { font-size: 11px; padding: 2px 8px; border-radius: 4px; background: rgba(0,212,255,0.1); color: var(--accent); border: 1px solid rgba(0,212,255,0.2); }
@media (max-width: 1024px) { .kpi-row { grid-template-columns: repeat(2, 1fr); } .chart-row { grid-template-columns: 1fr; } }
</style>
