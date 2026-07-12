<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'
import {
  getOverview,
  getProducts,
  forecast as apiForecast,
  getElasticity,
  getCompetitors,
  type PricingOverview,
  type ProductSummary,
  type DemandForecast,
  type ElasticityResult,
  type CompetitorSnapshot,
} from '../api/client'

const overview = ref<PricingOverview | null>(null)
const products = ref<ProductSummary[]>([])
const selected = ref<string>('')
const fc = ref<DemandForecast | null>(null)
const elasticity = ref<ElasticityResult | null>(null)
const competitors = ref<CompetitorSnapshot | null>(null)
const loading = ref(true)
const error = ref('')

const forecastEl = ref<HTMLElement | null>(null)
const categoryEl = ref<HTMLElement | null>(null)
const competitorEl = ref<HTMLElement | null>(null)
let fcChart: echarts.ECharts | null = null
let catChart: echarts.ECharts | null = null
let compChart: echarts.ECharts | null = null

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [ov, ps] = await Promise.all([getOverview(), getProducts()])
    overview.value = ov
    products.value = ps
    if (ps.length) {
      selected.value = ps[0].product_id
      await loadProduct(selected.value)
    }
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function loadProduct(pid: string) {
  try {
    const [f, el, comp] = await Promise.all([apiForecast(pid, 14), getElasticity(pid), getCompetitors(pid)])
    fc.value = f
    elasticity.value = el
    competitors.value = comp
    renderForecast()
    renderCompetitor()
  } catch (e: any) {
    error.value = e?.message || '商品数据加载失败'
  }
}

function renderCategory() {
  if (!categoryEl.value || !overview.value) return
  if (!catChart) catChart = echarts.init(categoryEl.value)
  const dist = overview.value.category_distribution
  catChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 60, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'value', axisLine: { lineStyle: { color: '#5d8369' } }, splitLine: { lineStyle: { color: '#16331f' } } },
    yAxis: { type: 'category', data: dist.map((d) => d.category), axisLine: { lineStyle: { color: '#5d8369' } }, axisLabel: { color: '#8fbf9f' } },
    series: [
      {
        type: 'bar', data: dist.map((d) => d.count),
        itemStyle: { color: '#00e676', borderRadius: [0, 6, 6, 0] },
        label: { show: true, position: 'right', color: '#e8f5ec' },
      },
    ],
  })
}

function renderForecast() {
  if (!forecastEl.value || !fc.value) return
  if (!fcChart) fcChart = echarts.init(forecastEl.value)
  const f = fc.value
  const histX = f.history.map((h) => h.t)
  const fcX = f.forecast.map((x) => x.t)
  const allX = [...histX, ...fcX]
  fcChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { data: ['实际销量', '预测销量', '预测区间'], textStyle: { color: '#8fbf9f' }, top: 0 },
    grid: { left: 50, right: 20, top: 36, bottom: 30 },
    xAxis: { type: 'category', data: allX, axisLine: { lineStyle: { color: '#5d8369' } }, axisLabel: { color: '#8fbf9f' } },
    yAxis: { type: 'value', axisLine: { lineStyle: { color: '#5d8369' } }, splitLine: { lineStyle: { color: '#16331f' } } },
    series: [
      {
        name: '实际销量', type: 'line', data: [...f.history.map((h) => h.actual), ...fcX.map(() => null)],
        showSymbol: false, lineStyle: { color: '#29b6f6', width: 2 }, itemStyle: { color: '#29b6f6' },
      },
      {
        name: '预测区间', type: 'line', data: [...histX.map(() => null), ...f.forecast.map((x) => x.upper)],
        showSymbol: false, lineStyle: { opacity: 0 }, areaStyle: { color: 'rgba(0,230,118,0.10)' }, stack: 'band',
      },
      {
        name: '预测区间', type: 'line', data: [...histX.map(() => null), ...f.forecast.map((x) => x.lower)],
        showSymbol: false, lineStyle: { opacity: 0 }, areaStyle: { color: 'transparent' }, stack: 'band',
      },
      {
        name: '预测销量', type: 'line', data: [...histX.map(() => null), ...f.forecast.map((x) => x.value)],
        showSymbol: false, lineStyle: { color: '#00e676', width: 2, type: 'dashed' }, itemStyle: { color: '#00e676' },
      },
    ],
  })
}

function renderCompetitor() {
  if (!competitorEl.value || !competitors.value) return
  if (!compChart) compChart = echarts.init(competitorEl.value)
  const c = competitors.value
  const names = ['本商品', ...c.competitors.map((x) => x.competitor)]
  const vals = [c.own_price, ...c.competitors.map((x) => x.price)]
  const colors = ['#00e676', ...c.competitors.map(() => '#ffc107')]
  compChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 60, right: 20, top: 20, bottom: 60 },
    xAxis: { type: 'category', data: names, axisLine: { lineStyle: { color: '#5d8369' } }, axisLabel: { color: '#8fbf9f', interval: 0, rotate: 12 } },
    yAxis: { type: 'value', axisLine: { lineStyle: { color: '#5d8369' } }, splitLine: { lineStyle: { color: '#16331f' } } },
    series: [
      {
        type: 'bar', data: vals.map((v, i) => ({ value: v, itemStyle: { color: colors[i], borderRadius: [6, 6, 0, 0] } })),
        label: { show: true, position: 'top', color: '#e8f5ec', formatter: '¥{c}' },
      },
    ],
  })
}

const positionText: Record<string, string> = { cheaper: '低于竞品', parity: '与竞品持平', premium: '高于竞品' }

watch(selected, (v) => { if (v) loadProduct(v) })

onMounted(async () => {
  await loadAll()
  renderCategory()
  window.addEventListener('resize', onResize)
})
onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  fcChart?.dispose(); catChart?.dispose(); compChart?.dispose()
})
function onResize() { fcChart?.resize(); catChart?.resize(); compChart?.resize() }
</script>

<template>
  <div class="fade-in">
    <h2 class="section-title">定价总览</h2>

    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-if="loading" class="loading">加载定价数据…</div>

    <template v-if="overview && !loading">
      <div class="kpi-grid">
        <div class="kpi-card">
          <div class="kpi-label">在管商品</div>
          <div class="kpi-value kpi-accent-1">{{ overview.total_products }}</div>
          <div class="kpi-sub">覆盖 {{ overview.category_distribution.length }} 个品类</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">平均毛利率</div>
          <div class="kpi-value kpi-accent-2">{{ overview.avg_margin_pct }}%</div>
          <div class="kpi-sub">加权测算</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">预估日营收</div>
          <div class="kpi-value kpi-accent-3">¥{{ overview.total_est_revenue.toLocaleString() }}</div>
          <div class="kpi-sub">基于当前价 × 历史销量</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">定价优化机会</div>
          <div class="kpi-value" :class="overview.opportunity_count > 0 ? 'kpi-accent-1' : ''">{{ overview.opportunity_count }}</div>
          <div class="kpi-sub">偏离最优价 > 3% 的商品</div>
        </div>
      </div>

      <div class="chart-row">
        <div class="card">
          <h3>品类分布</h3>
          <div ref="categoryEl" class="chart-box" />
        </div>
        <div class="card">
          <h3>价格弹性与定位</h3>
          <div v-if="elasticity" class="elasticity-box">
            <div class="el-main">
              <span class="el-num" :class="elasticity.is_elastic ? 'pos' : 'neg'">{{ elasticity.elasticity }}</span>
              <span class="pill" :class="elasticity.is_elastic ? 'green' : 'amber'">{{ elasticity.is_elastic ? '富有弹性' : '缺乏弹性' }}</span>
            </div>
            <p class="muted" style="font-size: 13px; line-height: 1.6; margin: 10px 0;">{{ elasticity.interpretation }}</p>
            <div class="el-meta">R² = {{ elasticity.r_squared }} ｜ 样本 {{ elasticity.price_range[0] }}~{{ elasticity.price_range[1] }} 元</div>
            <div v-if="competitors" class="el-pos pill" :class="competitors.position === 'cheaper' ? 'green' : competitors.position === 'premium' ? 'red' : 'blue'" style="margin-top: 10px;">
              竞品定位：{{ positionText[competitors.position] }}（均价 ¥{{ competitors.avg_competitor }}）
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="form-row" style="justify-content: space-between; align-items: center;">
          <h3 style="margin: 0;">需求预测（季节 + 趋势模型）</h3>
          <div class="field">
            <select v-model="selected">
              <option v-for="p in products" :key="p.product_id" :value="p.product_id">{{ p.name }}</option>
            </select>
          </div>
        </div>
        <div ref="forecastEl" class="chart-box" />
      </div>

      <div class="card">
        <h3>竞品价格监控</h3>
        <div ref="competitorEl" class="chart-box" />
      </div>

      <div class="card">
        <h3>定价机会 Top 5</h3>
        <table class="table">
          <thead>
            <tr><th>商品</th><th>品类</th><th>当前价</th><th>建议价</th><th>利润变化</th><th>营收变化</th><th>销量变化</th></tr>
          </thead>
          <tbody>
            <tr v-for="o in overview.top_opportunities" :key="o.product_id">
              <td>{{ o.name }}</td>
              <td>{{ o.category }}</td>
              <td>¥{{ o.current_price }}</td>
              <td class="pos">¥{{ o.recommended_price }}</td>
              <td :class="o.expected_delta_profit_pct >= 0 ? 'up' : 'down'">{{ o.expected_delta_profit_pct }}%</td>
              <td :class="o.expected_delta_revenue_pct >= 0 ? 'up' : 'down'">{{ o.expected_delta_revenue_pct }}%</td>
              <td :class="o.expected_delta_volume_pct >= 0 ? 'up' : 'down'">{{ o.expected_delta_volume_pct }}%</td>
            </tr>
            <tr v-if="!overview.top_opportunities.length"><td colspan="7" class="muted">暂无显著定价机会</td></tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.elasticity-box { padding: 6px 2px; }
.el-main { display: flex; align-items: center; gap: 14px; }
.el-num { font-size: 40px; font-weight: 800; font-variant-numeric: tabular-nums; }
.el-meta { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
</style>
