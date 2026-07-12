<script setup lang="ts">
import { ref, onMounted } from 'vue'
import * as echarts from 'echarts'
import {
  getBrands, getPerformance, predictROI,
  type Brand, type PlatformPerformanceAgg, type ROIPrediction,
} from '../api/client'

const brands = ref<Brand[]>([])
const brandId = ref('')
const brandName = ref('')
const perf = ref<PlatformPerformanceAgg | null>(null)

const spend = ref(80000)
const pred = ref<ROIPrediction | null>(null)
const predLoading = ref(false)

const perfChart = ref<HTMLElement | null>(null)
const roiChart = ref<HTMLElement | null>(null)
let perfInst: echarts.ECharts | null = null
let roiInst: echarts.ECharts | null = null

const fmt = (n: number, d = 1) => n.toLocaleString('zh-CN', { maximumFractionDigits: d })
const money = (n: number) => '¥' + n.toLocaleString('zh-CN', { maximumFractionDigits: 0 })

async function loadPerf() {
  if (!brandId.value) return
  const b = brands.value.find((x) => x.brand_id === brandId.value)
  brandName.value = b?.name ?? ''
  perf.value = await getPerformance(brandId.value)
  renderPerfChart()
}

async function runPred() {
  if (!brandId.value) return
  predLoading.value = true
  try {
    pred.value = await predictROI({ brand_id: brandId.value, spend: spend.value })
    renderRoiChart()
  } finally {
    predLoading.value = false
  }
}

function renderPerfChart() {
  if (!perfChart.value || !perf.value) return
  perfInst = echarts.init(perfChart.value, 'dark')
  const r = perf.value.ranking
  perfInst.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 70, right: 30, top: 20, bottom: 24 },
    xAxis: { type: 'category', data: r.map((x) => x.platform), axisLabel: { color: '#b9a8e8' } },
    yAxis: { type: 'value', name: 'ROAS', axisLabel: { color: '#b9a8e8' } },
    series: [{
      type: 'bar', data: r.map((x) => x.roas),
      itemStyle: {
        borderRadius: [6, 6, 0, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: '#22d3ee' }, { offset: 1, color: '#a855f7' },
        ]),
      },
      label: { show: true, position: 'top', color: '#f1ecff', formatter: '{c}×' },
    }],
  })
}

function renderRoiChart() {
  if (!roiChart.value || !pred.value) return
  roiInst = echarts.init(roiChart.value, 'dark')
  const s = pred.value.spend
  const slope = pred.value.slope
  const base = pred.value.predicted_revenue - slope * s
  const xs = [s * 0.4, s * 0.7, s, s * 1.3, s * 1.6]
  roiInst.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', formatter: (p: any) => `投入 ¥${fmt(p[0].value, 0)}<br/>预测营收 ¥${fmt(p[0].data.y, 0)}` },
    grid: { left: 70, right: 24, top: 20, bottom: 36 },
    xAxis: { type: 'value', name: '投入', axisLabel: { color: '#b9a8e8', formatter: (v: number) => '¥' + (v / 1000) + 'k' } },
    yAxis: { type: 'value', name: '营收', axisLabel: { color: '#b9a8e8', formatter: (v: number) => '¥' + (v / 1000) + 'k' } },
    series: [{
      type: 'line', smooth: true, symbol: 'circle',
      data: xs.map((x) => ({ x, y: base + slope * x })),
      lineStyle: { color: '#fb923c', width: 3 },
      itemStyle: { color: '#a855f7' },
      markPoint: {
        data: [{ coord: [s, pred.value!.predicted_revenue], value: '当前' }],
        itemStyle: { color: '#22d3ee' },
      },
    }],
  })
}

onMounted(async () => {
  brands.value = await getBrands()
  if (brands.value.length) {
    brandId.value = brands.value[0].brand_id
    await loadPerf()
  }
})
</script>

<template>
  <div class="fade-in">
    <div class="panel">
      <div class="panel-title">
        <span class="bar" /> 多平台效果聚合
        <select v-model="brandId" class="select" style="width:auto;margin-left:auto;padding:5px 10px" @change="loadPerf">
          <option v-for="b in brands" :key="b.brand_id" :value="b.brand_id">{{ b.name }}</option>
        </select>
      </div>
      <div v-if="perf" class="kpi-grid">
        <div class="kpi-card" style="--glow:rgba(251,146,60,0.18)"><div class="kpi-label">综合 ROAS</div><div class="kpi-value">{{ perf.blended_roas }}<span class="kpi-unit">×</span></div></div>
        <div class="kpi-card" style="--glow:rgba(34,211,238,0.16)"><div class="kpi-label">总曝光</div><div class="kpi-value">{{ fmt(perf.total_impressions / 1000, 0) }}<span class="kpi-unit">k</span></div></div>
        <div class="kpi-card" style="--glow:rgba(168,85,247,0.16)"><div class="kpi-label">总点击</div><div class="kpi-value">{{ fmt(perf.total_clicks / 1000, 1) }}<span class="kpi-unit">k</span></div></div>
        <div class="kpi-card" style="--glow:rgba(52,211,153,0.16)"><div class="kpi-label">总转化</div><div class="kpi-value">{{ perf.total_conversions }}</div></div>
        <div class="kpi-card" style="--glow:rgba(244,63,94,0.14)"><div class="kpi-label">总投入</div><div class="kpi-value">{{ money(perf.total_spend) }}</div></div>
        <div class="kpi-card" style="--glow:rgba(251,146,60,0.16)"><div class="kpi-label">总营收</div><div class="kpi-value">{{ money(perf.total_revenue) }}</div></div>
      </div>
      <div ref="perfChart" class="chart" />
    </div>

    <div class="panel">
      <div class="panel-title"><span class="bar" /> ROI 预测（OLS 回归，投入→营收）</div>
      <div class="field" style="max-width:240px"><label>计划投入（¥）</label><input v-model.number="spend" type="number" class="input" /></div>
      <button class="btn" :disabled="predLoading" @click="runPred">{{ predLoading ? '预测中…' : '预测 ROI' }}</button>

      <div v-if="pred" class="metric-row" style="margin-top:14px">
        <div class="metric"><div class="metric-label">预测营收</div><div class="metric-value" style="color:var(--accent-2)">{{ money(pred.predicted_revenue) }}</div></div>
        <div class="metric"><div class="metric-label">预测 ROAS</div><div class="metric-value" style="color:var(--accent-3)">{{ pred.predicted_roas }}×</div></div>
        <div class="metric"><div class="metric-label">预测利润</div><div class="metric-value kpi-up">{{ money(pred.predicted_profit) }}</div></div>
        <div class="metric"><div class="metric-label">置信度</div><div class="metric-value">{{ (pred.confidence * 100).toFixed(0) }}%</div></div>
        <div class="metric"><div class="metric-label">拟合 R²</div><div class="metric-value">{{ pred.fit_r_squared }}</div></div>
        <div class="metric"><div class="metric-label">边际收入/元</div><div class="metric-value">{{ pred.slope.toFixed(3) }}</div></div>
      </div>
      <div ref="roiChart" class="chart" style="margin-top:14px" />
    </div>
  </div>
</template>
