<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import {
  getOverview, getBrands, getVisibility, getKeywords,
  type MarketingOverview, type Brand, type BrandVisibility, type KeywordOpportunity,
} from '../api/client'

const overview = ref<MarketingOverview | null>(null)
const brands = ref<Brand[]>([])
const selectedBrand = ref('')
const visibility = ref<BrandVisibility | null>(null)
const keywords = ref<KeywordOpportunity[]>([])
const loading = ref(true)

const engineChart = ref<HTMLElement | null>(null)
const visChart = ref<HTMLElement | null>(null)
let engineInst: echarts.ECharts | null = null
let visInst: echarts.ECharts | null = null

const fmt = (n: number, d = 1) => n.toLocaleString('zh-CN', { maximumFractionDigits: d })
const fmtMoney = (n: number) => '¥' + n.toLocaleString('zh-CN', { maximumFractionDigits: 0 })

async function loadOverview() {
  overview.value = await getOverview()
  brands.value = await getBrands()
  if (brands.value.length && !selectedBrand.value) selectedBrand.value = brands.value[0].brand_id
  await loadBrand()
  renderEngineChart()
}

async function loadBrand() {
  if (!selectedBrand.value) return
  visibility.value = await getVisibility(selectedBrand.value)
  keywords.value = await getKeywords(selectedBrand.value)
  renderVisChart()
}

function renderEngineChart() {
  if (!engineChart.value || !overview.value) return
  engineInst = echarts.init(engineChart.value, 'dark')
  const eb = overview.value.engine_breakdown
  engineInst.setOption({
    backgroundColor: 'transparent',
    grid: { left: 90, right: 24, top: 16, bottom: 24 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'value', max: 100, axisLabel: { color: '#b9a8e8' } },
    yAxis: { type: 'category', data: eb.map((e) => e.engine), axisLabel: { color: '#b9a8e8' } },
    series: [{
      type: 'bar', data: eb.map((e) => e.avg_score),
      itemStyle: {
        borderRadius: [0, 6, 6, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
          { offset: 0, color: '#a855f7' }, { offset: 1, color: '#22d3ee' },
        ]),
      },
      label: { show: true, position: 'right', color: '#f1ecff', formatter: '{c}' },
    }],
  })
}

function renderVisChart() {
  if (!visChart.value || !visibility.value) return
  visInst = echarts.init(visChart.value, 'dark')
  const ens = visibility.value.engines
  visInst.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    radar: {
      indicator: ens.map((e) => ({ name: e.engine, max: 100 })),
      axisName: { color: '#b9a8e8' },
      splitLine: { lineStyle: { color: '#34256b' } },
      splitArea: { areaStyle: { color: ['rgba(34,211,238,0.04)', 'rgba(168,85,247,0.04)'] } },
    },
    series: [{
      type: 'radar',
      data: [{ value: ens.map((e) => e.score), name: '可见度' }],
      lineStyle: { color: '#a855f7' },
      areaStyle: { color: 'rgba(168,85,247,0.30)' },
      itemStyle: { color: '#22d3ee' },
    }],
  })
}

function brandName(id: string) {
  return brands.value.find((b) => b.brand_id === id)?.name ?? id
}

onMounted(async () => {
  try {
    await loadOverview()
  } finally {
    loading.value = false
  }
})

watch(selectedBrand, () => { loadBrand() })

defineExpose({
  beforeUnmount() { engineInst?.dispose(); visInst?.dispose() },
})
</script>

<template>
  <div class="fade-in">
    <div v-if="loading" class="loading"><div class="spinner" /><span>加载 GEO 可见度数据…</span></div>
    <template v-else-if="overview">
      <!-- KPI -->
      <div class="kpi-grid">
        <div class="kpi-card" style="--glow:rgba(168,85,247,0.20)">
          <div class="kpi-label">平均 GEO 可见度</div>
          <div class="kpi-value">{{ fmt(overview.avg_geo_index) }}<span class="kpi-unit">/100</span></div>
          <div class="kpi-sub kpi-up">分 5 个 AI 引擎综合</div>
        </div>
        <div class="kpi-card" style="--glow:rgba(34,211,238,0.18)">
          <div class="kpi-label">监测品牌</div>
          <div class="kpi-value">{{ overview.total_brands }}<span class="kpi-unit">个</span></div>
          <div class="kpi-sub">覆盖 {{ overview.tracked_engines }} 个 AI 引擎</div>
        </div>
        <div class="kpi-card" style="--glow:rgba(251,146,60,0.18)">
          <div class="kpi-label">跨平台综合 ROAS</div>
          <div class="kpi-value">{{ fmt(overview.blended_roas, 2) }}<span class="kpi-unit">×</span></div>
          <div class="kpi-sub kpi-up">广告支出回报</div>
        </div>
        <div class="kpi-card" style="--glow:rgba(52,211,153,0.16)">
          <div class="kpi-label">平均 E-E-A-T</div>
          <div class="kpi-value">{{ fmt(overview.avg_eeat) }}<span class="kpi-unit">/100</span></div>
          <div class="kpi-sub">内容权威度（{{ overview.total_content }} 篇）</div>
        </div>
      </div>

      <!-- Engine breakdown + Visibility per brand -->
      <div class="grid-2">
        <div class="panel">
          <div class="panel-title"><span class="bar" /> 各 AI 引擎平均可见度</div>
          <div ref="engineChart" class="chart" />
        </div>
        <div class="panel">
          <div class="panel-title">
            <span class="bar" /> 品牌可见度（雷达）
            <select v-model="selectedBrand" class="select" style="width:auto;margin-left:auto;padding:5px 10px">
              <option v-for="b in brands" :key="b.brand_id" :value="b.brand_id">{{ b.name }}</option>
            </select>
          </div>
          <div ref="visChart" class="chart" />
          <div v-if="visibility" class="metric-row">
            <div class="metric"><div class="metric-label">GEO 指数</div><div class="metric-value">{{ fmt(visibility.geo_index) }}</div></div>
            <div class="metric"><div class="metric-label">被引用关键词</div><div class="metric-value">{{ visibility.cited_keywords }}/{{ visibility.total_keywords }}</div></div>
            <div class="metric"><div class="metric-label">30天趋势</div><div class="metric-value" :class="visibility.trend_30d >= 0 ? 'kpi-up' : 'kpi-down'">{{ visibility.trend_30d >= 0 ? '+' : '' }}{{ fmt(visibility.trend_30d) }}</div></div>
          </div>
        </div>
      </div>

      <!-- Top opportunities -->
      <div class="panel">
        <div class="panel-title"><span class="bar" /> 高机会关键词（GEO 投放优先）</div>
        <table class="table">
          <thead><tr><th>品牌</th><th>关键词</th><th>意图</th><th class="num">月搜索量</th><th class="num">难度</th><th class="num">机会分</th></tr></thead>
          <tbody>
            <tr v-for="o in overview.top_opportunities" :key="o.brand_id + o.keyword">
              <td>{{ o.brand }}</td>
              <td>{{ o.keyword }}</td>
              <td><span class="tag tag-violet">{{ o.monthly_volume ? '商业' : '信息' }}</span></td>
              <td class="num">{{ o.monthly_volume.toLocaleString() }}</td>
              <td class="num">{{ fmt(o.difficulty) }}</td>
              <td class="num"><b style="color:var(--accent-3)">{{ fmt(o.opportunity_score) }}</b></td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Keywords for selected brand -->
      <div class="panel">
        <div class="panel-title"><span class="bar" /> {{ brandName(selectedBrand) }} · 关键词机会排序</div>
        <table class="table">
          <thead><tr><th>关键词</th><th>意图</th><th class="num">月搜索量</th><th class="num">难度</th><th class="num">当前位次</th><th class="num">机会分</th></tr></thead>
          <tbody>
            <tr v-for="k in keywords" :key="k.term">
              <td>{{ k.term }}</td>
              <td><span class="tag tag-cyan">{{ k.intent }}</span></td>
              <td class="num">{{ k.monthly_volume.toLocaleString() }}</td>
              <td class="num">{{ fmt(k.difficulty) }}</td>
              <td class="num">{{ fmt(k.current_position) }}</td>
              <td class="num"><b>{{ fmt(k.opportunity_score) }}</b></td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
