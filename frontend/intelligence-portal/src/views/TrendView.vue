<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { getTrends, type TrendItem } from '../api/client'

const trends = ref<TrendItem[]>([])
const loading = ref(true)
const error = ref('')
const chartRef = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

const allKeywords = ref<{ word: string; weight: number }[]>([])

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    trends.value = await getTrends(14)
    const kwMap: Record<string, number> = {}
    for (const t of trends.value) {
      for (const kw of t.keywords || []) {
        kwMap[kw] = (kwMap[kw] || 0) + t.count
      }
    }
    allKeywords.value = Object.entries(kwMap)
      .map(([word, weight]) => ({ word, weight }))
      .sort((a, b) => b.weight - a.weight)
      .slice(0, 40)
    await nextTick()
    renderChart()
  } catch (e: any) {
    error.value = e?.message || '加载趋势数据失败'
  } finally {
    loading.value = false
  }
}

function renderChart() {
  if (!chartRef.value || trends.value.length === 0) return
  if (chart) chart.dispose()
  chart = echarts.init(chartRef.value)

  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 30, top: 30, bottom: 40 },
    xAxis: {
      type: 'category',
      data: trends.value.map(t => t.date.slice(5)),
      axisLabel: { color: '#94a3b8', fontSize: 11 },
      axisLine: { lineStyle: { color: '#2a3556' } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#94a3b8' },
      splitLine: { lineStyle: { color: '#1a2035' } },
    },
    series: [{
      type: 'line',
      data: trends.value.map(t => t.count),
      smooth: true,
      symbol: 'circle',
      symbolSize: 8,
      lineStyle: { color: '#00d4ff', width: 3, shadowColor: 'rgba(0,212,255,0.4)', shadowBlur: 10 },
      itemStyle: { color: '#00d4ff', borderColor: '#0a0e1a', borderWidth: 2 },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(0,212,255,0.25)' },
          { offset: 1, color: 'rgba(0,212,255,0.02)' },
        ]),
      },
    }],
  })
}

function handleResize() { chart?.resize() }
onMounted(() => { loadData(); window.addEventListener('resize', handleResize) })
onUnmounted(() => { window.removeEventListener('resize', handleResize); chart?.dispose() })
</script>

<template>
  <div class="view">
    <div v-if="loading" class="loading">分析趋势中...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <template v-else>
      <h2>趋势分析</h2>

      <div class="panel">
        <h3>14 日情报采集趋势</h3>
        <div ref="chartRef" class="chart" />
      </div>

      <div class="panel">
        <h3>热门关键词</h3>
        <div class="keyword-cloud">
          <span
            v-for="kw in allKeywords"
            :key="kw.word"
            class="kw-tag"
            :style="{ fontSize: Math.min(28, 12 + kw.weight * 0.5) + 'px', opacity: Math.min(1, 0.4 + kw.weight * 0.04) }"
          >
            {{ kw.word }}
          </span>
          <span v-if="allKeywords.length === 0" class="empty">暂无关键词数据</span>
        </div>
      </div>

      <div class="panel">
        <h3>每日关键词明细</h3>
        <div class="timeline">
          <div v-for="t in trends.slice().reverse()" :key="t.date" class="tl-item">
            <div class="tl-date">{{ t.date.slice(5) }}</div>
            <div class="tl-count">{{ t.count }} 条</div>
            <div class="tl-kws">
              <span v-for="kw in (t.keywords || []).slice(0, 5)" :key="kw" class="kw-mini">{{ kw }}</span>
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
h2 { font-size: 20px; font-weight: 700; color: var(--text-primary); margin: 0; }
h3 { font-size: 14px; color: var(--accent); margin: 0 0 12px; letter-spacing: 1px; }

.panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
}
.chart { width: 100%; height: 320px; }

.keyword-cloud { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; }
.kw-tag { color: var(--accent); text-shadow: 0 0 8px var(--accent-glow); font-weight: 600; transition: all 0.2s; cursor: default; }
.kw-tag:hover { color: #fff; text-shadow: 0 0 16px var(--accent); }
.empty { color: var(--text-muted); font-size: 14px; }

.timeline { display: flex; flex-direction: column; gap: 8px; max-height: 400px; overflow-y: auto; }
.tl-item { display: flex; align-items: center; gap: 16px; padding: 10px 14px; background: var(--bg-secondary); border-radius: 8px; }
.tl-date { font-size: 13px; color: var(--accent); font-family: 'SF Mono', monospace; min-width: 50px; }
.tl-count { font-size: 13px; color: var(--text-secondary); min-width: 60px; }
.tl-kws { display: flex; flex-wrap: wrap; gap: 6px; }
.kw-mini { font-size: 11px; padding: 2px 8px; border-radius: 4px; background: rgba(0,212,255,0.1); color: var(--accent); }
</style>
