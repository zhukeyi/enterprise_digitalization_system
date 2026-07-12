<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { getProducts, getCompetitors, type ProductSummary, type CompetitorSnapshot } from '../api/client'

const products = ref<ProductSummary[]>([])
const selectedId = ref('')
const competitors = ref<CompetitorSnapshot | null>(null)
const loading = ref(true)
const analyzing = ref(false)
const error = ref('')

const chartRef = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

async function loadProducts() {
  loading.value = true
  error.value = ''
  try {
    products.value = await getProducts()
    if (products.value.length > 0) {
      selectedId.value = products.value[0].product_id
      await loadCompetitors()
    }
  } catch (e: any) {
    error.value = e?.message || '加载产品列表失败'
  } finally {
    loading.value = false
  }
}

async function loadCompetitors() {
  if (!selectedId.value) return
  analyzing.value = true
  competitors.value = null
  try {
    competitors.value = await getCompetitors(selectedId.value)
    await nextTick()
    renderChart()
  } catch (e: any) {
    error.value = e?.message || '竞品分析失败'
  } finally {
    analyzing.value = false
  }
}

function renderChart() {
  if (!chartRef.value || !competitors.value) return
  if (chart) chart.dispose()
  chart = echarts.init(chartRef.value)

  const c = competitors.value
  const allNames = ['本产品', ...c.competitors.map(x => x.competitor)]
  const allPrices = [c.own_price, ...c.competitors.map(x => x.price)]
  const colors = ['#00d4ff', '#a855f7', '#22c55e', '#f59e0b', '#ef4444', '#3b82f6']

  chart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 80, right: 40, top: 20, bottom: 40 },
    xAxis: { type: 'value', name: '价格', axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: '#1a2035' } } },
    yAxis: { type: 'category', data: allNames, axisLabel: { color: '#e2e8f0', fontSize: 13 } },
    series: [{
      type: 'bar',
      data: allPrices.map((v, i) => ({ value: v, itemStyle: { color: colors[i % colors.length], borderRadius: [0, 6, 6, 0] } })),
      barWidth: '50%',
      label: { show: true, position: 'right', formatter: '¥{c}', color: '#94a3b8', fontSize: 12 },
    }],
  })
}

function handleResize() { chart?.resize() }
onMounted(() => { loadProducts(); window.addEventListener('resize', handleResize) })
onUnmounted(() => { window.removeEventListener('resize', handleResize); chart?.dispose() })

function positionLabel(p: string): string {
  const map: Record<string, string> = {
    cheaper: '低于市场', parity: '接近市场', premium: '高于市场',
  }
  return map[p] || p
}

function positionClass(p: string): string {
  if (p === 'cheaper') return 'green'
  if (p === 'premium') return 'red'
  return 'blue'
}
</script>

<template>
  <div class="view">
    <div v-if="loading" class="loading">加载产品列表...</div>
    <template v-else>
      <div class="control-panel">
        <div class="control-group">
          <label class="control-label">选择产品</label>
          <select v-model="selectedId" class="select" @change="loadCompetitors">
            <option v-for="p in products" :key="p.product_id" :value="p.product_id">
              {{ p.name }}（¥{{ p.current_price }}）
            </option>
          </select>
        </div>
      </div>

      <div v-if="error" class="error">{{ error }}</div>

      <template v-if="competitors && !analyzing">
        <div class="kpi-row">
          <div class="kpi-card blue">
            <div class="kpi-val">¥{{ competitors.own_price.toFixed(2) }}</div>
            <div class="kpi-label">本产品价格</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-val">¥{{ competitors.avg_competitor.toFixed(2) }}</div>
            <div class="kpi-label">竞品均价</div>
          </div>
          <div class="kpi-card green">
            <div class="kpi-val">¥{{ competitors.min_competitor.toFixed(2) }}</div>
            <div class="kpi-label">最低竞品</div>
          </div>
          <div class="kpi-card red">
            <div class="kpi-val">¥{{ competitors.max_competitor.toFixed(2) }}</div>
            <div class="kpi-label">最高竞品</div>
          </div>
        </div>

        <div class="panel">
          <h3>竞品价格对比</h3>
          <div ref="chartRef" class="chart" />
        </div>

        <div class="panel">
          <h3>市场定位</h3>
          <div class="position-card" :class="positionClass(competitors.position)">
            <span class="position-label">{{ positionLabel(competitors.position) }}</span>
            <span class="position-detail">
              本产品价格 ¥{{ competitors.own_price.toFixed(2) }}
              vs 竞品均价 ¥{{ competitors.avg_competitor.toFixed(2) }}
             （价差 {{ ((competitors.own_price / competitors.avg_competitor - 1) * 100).toFixed(1) }}%）
            </span>
          </div>
        </div>

        <div class="panel">
          <h3>竞品明细</h3>
          <table>
            <thead>
              <tr><th>竞品</th><th>价格</th><th>与本品差</th></tr>
            </thead>
            <tbody>
              <tr v-for="c in competitors.competitors" :key="c.competitor">
                <td>{{ c.competitor }}</td>
                <td>¥{{ c.price.toFixed(2) }}</td>
                <td :class="c.price > competitors.own_price ? 'green' : 'red'">
                  {{ c.price > competitors.own_price ? '+' : '' }}{{ ((c.price / competitors.own_price - 1) * 100).toFixed(1) }}%
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
      <div v-else-if="analyzing" class="loading">分析竞品中...</div>
    </template>
  </div>
</template>

<style scoped>
.view { display: flex; flex-direction: column; gap: 20px; }
.loading { padding: 40px; text-align: center; color: #64748b; }
.error { padding: 16px; background: rgba(239,68,68,0.1); border-radius: 8px; color: #ef4444; font-size: 14px; }

.control-panel { background: #151c2e; border: 1px solid #2a3556; border-radius: 12px; padding: 20px; }
.control-group { flex: 1; }
.control-label { display: block; font-size: 13px; color: #94a3b8; margin-bottom: 6px; }
.select { width: 100%; max-width: 400px; padding: 10px 14px; background: #0a0e1a; border: 1px solid #2a3556; border-radius: 8px; color: #e2e8f0; font-size: 14px; outline: none; }
.select:focus { border-color: #00d4ff; }

.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.kpi-card { background: #151c2e; border: 1px solid #2a3556; border-radius: 12px; padding: 20px; border-left: 4px solid #64748b; }
.kpi-card.blue { border-color: #00d4ff; } .kpi-card.green { border-color: #22c55e; } .kpi-card.red { border-color: #ef4444; }
.kpi-val { font-size: 28px; font-weight: 800; color: #e2e8f0; }
.kpi-label { font-size: 13px; color: #94a3b8; margin-top: 4px; }

.panel { background: #151c2e; border: 1px solid #2a3556; border-radius: 12px; padding: 20px; }
.panel h3 { font-size: 15px; color: #00d4ff; margin: 0 0 12px; letter-spacing: 1px; }
.chart { width: 100%; height: 320px; }

.position-card { display: flex; align-items: center; gap: 16px; padding: 16px; border-radius: 8px; }
.position-card.blue { background: rgba(0,212,255,0.1); border: 1px solid rgba(0,212,255,0.3); }
.position-card.green { background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.3); }
.position-card.red { background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); }
.position-label { font-size: 18px; font-weight: 700; }
.position-card.blue .position-label { color: #00d4ff; }
.position-card.green .position-label { color: #22c55e; }
.position-card.red .position-label { color: #ef4444; }
.position-detail { font-size: 14px; color: #94a3b8; }

table { width: 100%; border-collapse: collapse; }
th { text-align: left; padding: 10px 12px; font-size: 12px; color: #64748b; border-bottom: 2px solid #2a3556; }
td { padding: 10px 12px; font-size: 14px; color: #e2e8f0; border-bottom: 1px solid #1a2035; }
td.green { color: #22c55e; } td.red { color: #ef4444; }
</style>
