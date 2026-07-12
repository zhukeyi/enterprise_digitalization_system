<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import {
  getProducts,
  simulate,
  type ProductSummary,
  type SimulatorResult,
} from '../api/client'

const products = ref<ProductSummary[]>([])
const selected = ref<string>('')
const newPrice = ref<number>(0)
const result = ref<SimulatorResult | null>(null)
const loading = ref(false)
const error = ref('')
const chartEl = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

onMounted(async () => {
  try {
    products.value = await getProducts()
    if (products.value.length) {
      selected.value = products.value[0].product_id
      newPrice.value = products.value[0].current_price
    }
  } catch (e: any) { error.value = e?.message || '加载失败' }
})

async function runSim() {
  if (!selected.value) return
  loading.value = true
  error.value = ''
  try {
    result.value = await simulate({ product_id: selected.value, new_price: newPrice.value })
    renderChart()
  } catch (e: any) { error.value = e?.message || '模拟失败' }
  finally { loading.value = false }
}

function onChangeProduct() {
  const p = products.value.find((x) => x.product_id === selected.value)
  if (p) { newPrice.value = p.current_price; result.value = null }
}

function renderChart() {
  if (!chartEl.value || !result.value) return
  if (!chart) chart = echarts.init(chartEl.value)
  const r = result.value
  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['当前', '模拟后'], textStyle: { color: '#8fbf9f' }, top: 0 },
    grid: { left: 60, right: 20, top: 36, bottom: 30 },
    xAxis: { type: 'category', data: ['销量', '营收', '利润'], axisLine: { lineStyle: { color: '#5d8369' } }, axisLabel: { color: '#8fbf9f' } },
    yAxis: { type: 'value', axisLine: { lineStyle: { color: '#5d8369' } }, splitLine: { lineStyle: { color: '#16331f' } } },
    series: [
      { name: '当前', type: 'bar', data: [r.current_volume, r.current_revenue, r.current_profit], itemStyle: { color: '#5d8369', borderRadius: [6, 6, 0, 0] } },
      { name: '模拟后', type: 'bar', data: [r.projected_volume, r.projected_revenue, r.projected_profit], itemStyle: { color: '#00e676', borderRadius: [6, 6, 0, 0] } },
    ],
  })
}

onUnmounted(() => { chart?.dispose(); window.removeEventListener('resize', onResize) })
function onResize() { chart?.resize() }
onMounted(() => window.addEventListener('resize', onResize))
</script>

<template>
  <div class="fade-in">
    <h2 class="section-title">What-if 定价模拟</h2>
    <div v-if="error" class="error-banner">{{ error }}</div>

    <div class="card">
      <div class="form-row">
        <div class="field">
          <label>选择商品</label>
          <select v-model="selected" @change="onChangeProduct">
            <option v-for="p in products" :key="p.product_id" :value="p.product_id">{{ p.name }}（¥{{ p.current_price }}）</option>
          </select>
        </div>
        <div class="field">
          <label>模拟售价（元）</label>
          <input type="number" v-model.number="newPrice" step="1" />
        </div>
        <button class="btn" :disabled="loading" @click="runSim">{{ loading ? '计算中…' : '运行模拟' }}</button>
      </div>
      <p class="muted" style="font-size: 12px;">提示：拖动/输入新价格，查看销量、营收、利润的预计变化（基于该商品历史价格弹性）。</p>
    </div>

    <div v-if="result" class="fade-in">
      <div class="kpi-grid">
        <div class="kpi-card">
          <div class="kpi-label">价格变动</div>
          <div class="kpi-value">{{ result.current_price }} → {{ result.new_price }}</div>
          <div class="kpi-sub" :class="result.new_price >= result.current_price ? 'pos' : 'neg'">
            {{ ((result.new_price - result.current_price) / result.current_price * 100).toFixed(1) }}%
          </div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">销量变化</div>
          <div class="kpi-value" :class="result.delta_volume_pct >= 0 ? 'kpi-accent-1' : 'kpi-accent-2'">{{ result.delta_volume_pct }}%</div>
          <div class="kpi-sub">{{ result.current_volume }} → {{ result.projected_volume }}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">营收变化</div>
          <div class="kpi-value" :class="result.delta_revenue_pct >= 0 ? 'kpi-accent-1' : 'kpi-accent-2'">{{ result.delta_revenue_pct }}%</div>
          <div class="kpi-sub">¥{{ result.current_revenue.toLocaleString() }} → ¥{{ result.projected_revenue.toLocaleString() }}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">利润变化</div>
          <div class="kpi-value" :class="result.delta_profit_pct >= 0 ? 'kpi-accent-1' : 'kpi-accent-2'">{{ result.delta_profit_pct }}%</div>
          <div class="kpi-sub">¥{{ result.current_profit.toLocaleString() }} → ¥{{ result.projected_profit.toLocaleString() }}</div>
        </div>
      </div>
      <div class="card">
        <h3>当前 vs 模拟后</h3>
        <div ref="chartEl" class="chart-box" />
      </div>
    </div>
  </div>
</template>
