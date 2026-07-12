<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import * as echarts from 'echarts'
import { getProducts, getElasticity, type ProductSummary, type ElasticityResult } from '../api/client'

const products = ref<ProductSummary[]>([])
const selectedId = ref('')
const elasticity = ref<ElasticityResult | null>(null)
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
      await loadElasticity()
    }
  } catch (e: any) {
    error.value = e?.message || '加载产品列表失败'
  } finally {
    loading.value = false
  }
}

async function loadElasticity() {
  if (!selectedId.value) return
  analyzing.value = true
  elasticity.value = null
  try {
    elasticity.value = await getElasticity(selectedId.value)
    await nextTick()
    renderChart()
  } catch (e: any) {
    error.value = e?.message || '弹性分析失败'
  } finally {
    analyzing.value = false
  }
}

function renderChart() {
  if (!chartRef.value || !elasticity.value) return
  if (chart) chart.dispose()
  chart = echarts.init(chartRef.value)

  const el = elasticity.value
  const e = el.elasticity
  // Generate demand curve based on elasticity
  const product = products.value.find(p => p.product_id === selectedId.value)
  const basePrice = product?.current_price || 100
  const prices: number[] = []
  const demands: number[] = []
  for (let i = -30; i <= 30; i += 2) {
    const p = basePrice * (1 + i / 100)
    const demand = 100 * Math.pow(p / basePrice, e)
    prices.push(Number(p.toFixed(2)))
    demands.push(Number(demand.toFixed(1)))
  }

  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['需求曲线'], bottom: 5, textStyle: { color: '#94a3b8' } },
    grid: { left: 60, right: 40, top: 30, bottom: 50 },
    xAxis: {
      type: 'category',
      name: '价格',
      data: prices,
      axisLabel: { color: '#94a3b8', fontSize: 11 },
      axisLine: { lineStyle: { color: '#2a3556' } },
    },
    yAxis: {
      type: 'value',
      name: '相对需求',
      axisLabel: { color: '#94a3b8' },
      splitLine: { lineStyle: { color: '#1a2035' } },
    },
    series: [{
      name: '需求曲线',
      type: 'line',
      data: demands,
      smooth: true,
      symbol: 'none',
      lineStyle: { color: '#f59e0b', width: 3 },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(245,158,11,0.2)' },
          { offset: 1, color: 'rgba(245,158,11,0.01)' },
        ]),
      },
      markLine: {
        data: [{ xAxis: 15, label: { formatter: '当前价格', color: '#00d4ff' }, lineStyle: { color: '#00d4ff', type: 'dashed' } }],
      },
    }],
  })
}

function handleResize() { chart?.resize() }
onMounted(() => { loadProducts(); window.addEventListener('resize', handleResize) })
onUnmounted(() => { window.removeEventListener('resize', handleResize); chart?.dispose() })
</script>

<template>
  <div class="view">
    <div v-if="loading" class="loading">加载产品列表...</div>
    <template v-else>
      <div class="control-panel">
        <div class="control-group">
          <label class="control-label">选择产品</label>
          <select v-model="selectedId" class="select" @change="loadElasticity">
            <option v-for="p in products" :key="p.product_id" :value="p.product_id">
              {{ p.name }}（¥{{ p.current_price }}）
            </option>
          </select>
        </div>
      </div>

      <div v-if="error" class="error">{{ error }}</div>

      <template v-if="elasticity && !analyzing">
        <div class="kpi-row">
          <div class="kpi-card" :class="elasticity.is_elastic ? 'red' : 'green'">
            <div class="kpi-val">{{ elasticity.elasticity.toFixed(3) }}</div>
            <div class="kpi-label">价格弹性系数</div>
          </div>
          <div class="kpi-card blue">
            <div class="kpi-val">{{ (elasticity.r_squared * 100).toFixed(1) }}%</div>
            <div class="kpi-label">R² 拟合优度</div>
          </div>
          <div class="kpi-card" :class="elasticity.is_elastic ? 'red' : 'green'">
            <div class="kpi-val">{{ elasticity.is_elastic ? '富有弹性' : '缺乏弹性' }}</div>
            <div class="kpi-label">弹性类型</div>
          </div>
        </div>

        <div class="panel">
          <h3>需求价格弹性曲线</h3>
          <div ref="chartRef" class="chart" />
        </div>

        <div class="panel">
          <h3>分析说明</h3>
          <p class="interpretation">{{ elasticity.interpretation }}</p>
        </div>
      </template>
      <div v-else-if="analyzing" class="loading">计算弹性中...</div>
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

.kpi-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.kpi-card { background: #151c2e; border: 1px solid #2a3556; border-radius: 12px; padding: 20px; border-left: 4px solid; }
.kpi-card.blue { border-color: #00d4ff; } .kpi-card.green { border-color: #22c55e; } .kpi-card.red { border-color: #ef4444; }
.kpi-val { font-size: 30px; font-weight: 800; color: #e2e8f0; }
.kpi-label { font-size: 13px; color: #94a3b8; margin-top: 4px; }

.panel { background: #151c2e; border: 1px solid #2a3556; border-radius: 12px; padding: 20px; }
.panel h3 { font-size: 15px; color: #00d4ff; margin: 0 0 12px; letter-spacing: 1px; }
.chart { width: 100%; height: 340px; }
.interpretation { font-size: 14px; color: #94a3b8; line-height: 1.7; margin: 0; }
</style>
