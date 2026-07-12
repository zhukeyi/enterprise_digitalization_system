<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import {
  getProducts,
  getStrategies,
  optimize,
  type ProductSummary,
  type StrategyPreset,
  type OptimizationResult,
} from '../api/client'

const products = ref<ProductSummary[]>([])
const strategies = ref<StrategyPreset[]>([])
const selected = ref<string>('')
const strategy = ref<string>('rl_optimal')
const result = ref<OptimizationResult | null>(null)
const loading = ref(false)
const error = ref('')
const rlEl = ref<HTMLElement | null>(null)
let rlChart: echarts.ECharts | null = null

onMounted(async () => {
  try {
    const [ps, st] = await Promise.all([getProducts(), getStrategies()])
    products.value = ps
    strategies.value = st
    if (ps.length) selected.value = ps[0].product_id
  } catch (e: any) { error.value = e?.message || '加载失败' }
})

async function runOptimize() {
  if (!selected.value) return
  loading.value = true
  error.value = ''
  try {
    result.value = await optimize(selected.value, strategy.value)
    renderRL()
  } catch (e: any) { error.value = e?.message || '优化失败' }
  finally { loading.value = false }
}

function renderRL() {
  if (!rlEl.value || !result.value?.rl_log) return
  if (!rlChart) rlChart = echarts.init(rlEl.value)
  const log = result.value.rl_log
  rlChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { data: ['每轮利润', '尝试价格'], textStyle: { color: '#8fbf9f' }, top: 0 },
    grid: { left: 60, right: 60, top: 36, bottom: 40 },
    xAxis: { type: 'category', data: log.episodes.map((_, i) => i + 1), axisLine: { lineStyle: { color: '#5d8369' } }, axisLabel: { color: '#8fbf9f' } },
    yAxis: [
      { type: 'value', name: '利润', axisLine: { lineStyle: { color: '#5d8369' } }, splitLine: { lineStyle: { color: '#16331f' } }, axisLabel: { color: '#8fbf9f' } },
      { type: 'value', name: '价格', axisLine: { lineStyle: { color: '#ffc107' } }, axisLabel: { color: '#ffc107' } },
    ],
    series: [
      { name: '每轮利润', type: 'line', data: log.episodes, showSymbol: false, lineStyle: { color: '#00e676', width: 1.5 }, itemStyle: { color: '#00e676' } },
      { name: '尝试价格', type: 'line', yAxisIndex: 1, data: log.prices, showSymbol: false, lineStyle: { color: '#ffc107', width: 1.2, type: 'dashed' }, itemStyle: { color: '#ffc107' } },
    ],
  })
}

onUnmounted(() => { rlChart?.dispose(); window.removeEventListener('resize', onResize) })
function onResize() { rlChart?.resize() }
onMounted(() => window.addEventListener('resize', onResize))
</script>

<template>
  <div class="fade-in">
    <h2 class="section-title">定价策略优化</h2>
    <div v-if="error" class="error-banner">{{ error }}</div>

    <div class="card">
      <div class="form-row">
        <div class="field">
          <label>选择商品</label>
          <select v-model="selected">
            <option v-for="p in products" :key="p.product_id" :value="p.product_id">{{ p.name }}</option>
          </select>
        </div>
        <div class="field">
          <label>优化策略</label>
          <select v-model="strategy">
            <option v-for="s in strategies" :key="s.key" :value="s.key">{{ s.name }} — {{ s.desc }}</option>
          </select>
        </div>
        <button class="btn" :disabled="loading" @click="runOptimize">{{ loading ? '优化中…' : '运行优化' }}</button>
      </div>
    </div>

    <div v-if="result" class="fade-in">
      <div class="kpi-grid">
        <div class="kpi-card">
          <div class="kpi-label">当前价 → 建议价</div>
          <div class="kpi-value kpi-accent-1">{{ result.current_price }} → {{ result.recommended_price }}</div>
          <div class="kpi-sub">{{ ((result.recommended_price - result.current_price) / result.current_price * 100).toFixed(1) }}%</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">预计利润变化</div>
          <div class="kpi-value" :class="result.expected_delta_profit_pct >= 0 ? 'kpi-accent-1' : 'kpi-accent-2'">{{ result.expected_delta_profit_pct }}%</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">预计营收变化</div>
          <div class="kpi-value" :class="result.expected_delta_revenue_pct >= 0 ? 'kpi-accent-1' : 'kpi-accent-2'">{{ result.expected_delta_revenue_pct }}%</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">置信度</div>
          <div class="kpi-value kpi-accent-3">{{ (result.confidence * 100).toFixed(0) }}%</div>
        </div>
      </div>

      <div class="rec-box">
        <div class="rec-price">建议价 ¥{{ result.recommended_price }}</div>
        <div class="rec-reason">{{ result.rationale }}</div>
        <div v-if="result.elasticity" class="muted" style="font-size: 12px; margin-top: 10px;">
          弹性 β = {{ result.elasticity.elasticity }} ｜ 竞品定位：{{ result.competitors.position }}（均价 ¥{{ result.competitors.avg_competitor }}）
        </div>
      </div>

      <div v-if="result.rl_log" class="card" style="margin-top: 20px;">
        <h3>强化学习训练轨迹（PPO 风格策略梯度 · {{ result.rl_log.iterations }} 轮）</h3>
        <div ref="rlEl" class="chart-box" />
        <p class="muted" style="font-size: 12px; margin-top: 8px;">
          最优价收敛至 ¥{{ result.rl_log.best_price }}，最终策略均值 ¥{{ result.rl_log.final_policy_mean }}。
        </p>
      </div>
    </div>
  </div>
</template>
