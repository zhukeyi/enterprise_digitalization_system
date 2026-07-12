<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { getOverview, type HROverview } from '../api/client'

const stats = ref<HROverview | null>(null)
const loading = ref(true)
const error = ref('')
const riskChartRef = ref<HTMLElement | null>(null)
const deptChartRef = ref<HTMLElement | null>(null)
let riskChart: echarts.ECharts | null = null
let deptChart: echarts.ECharts | null = null

async function loadData() {
  loading.value = true; error.value = ''
  try {
    stats.value = await getOverview()
    await nextTick(); renderCharts()
  } catch (e: any) { error.value = e?.message || '加载失败' }
  finally { loading.value = false }
}

function renderCharts() {
  if (!stats.value) return
  if (riskChartRef.value) {
    if (riskChart) riskChart.dispose()
    riskChart = echarts.init(riskChartRef.value)
    const rd = stats.value.risk_distribution
    riskChart.setOption({
      tooltip: { trigger: 'item' },
      legend: { bottom: 10, textStyle: { fontSize: 12 } },
      series: [{
        type: 'pie', radius: ['40%', '70%'], center: ['50%', '45%'],
        label: { show: false },
        data: [
          { name: '低风险', value: rd.low, itemStyle: { color: '#22c55e' } },
          { name: '中风险', value: rd.medium, itemStyle: { color: '#f59e0b' } },
          { name: '高风险', value: rd.high, itemStyle: { color: '#ef4444' } },
          { name: ' critical', value: rd.critical, itemStyle: { color: '#991b1b' } },
        ],
      }],
    })
  }
  if (deptChartRef.value) {
    if (deptChart) deptChart.dispose()
    deptChart = echarts.init(deptChartRef.value)
    deptChart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 100, right: 20, top: 10, bottom: 30 },
      xAxis: { type: 'value', minInterval: 1 },
      yAxis: { type: 'category', data: stats.value.departments.map(d => d.name) },
      series: [{
        type: 'bar', data: stats.value.departments.map(d => d.count),
        itemStyle: { color: '#3b82f6', borderRadius: [0, 4, 4, 0] },
        barWidth: '60%',
      }],
    })
  }
}

function handleResize() { riskChart?.resize(); deptChart?.resize() }
onMounted(() => { loadData(); window.addEventListener('resize', handleResize) })
onUnmounted(() => { window.removeEventListener('resize', handleResize); riskChart?.dispose(); deptChart?.dispose() })
</script>

<template>
  <div class="dashboard">
    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="error" class="error">{{ error }} <button @click="loadData">重试</button></div>
    <template v-else-if="stats">
      <div class="kpi-row">
        <div class="kpi-card blue"><div class="kpi-val">{{ stats.total_employees }}</div><div class="kpi-label">员工总数</div></div>
        <div class="kpi-card green"><div class="kpi-val">{{ stats.active_count }}</div><div class="kpi-label">在职人数</div></div>
        <div class="kpi-card purple"><div class="kpi-val">{{ stats.departments.length }}</div><div class="kpi-label">部门数量</div></div>
        <div class="kpi-card red"><div class="kpi-val">{{ stats.risk_distribution.high + stats.risk_distribution.critical }}</div><div class="kpi-label">高风险人数</div></div>
      </div>
      <div class="chart-row">
        <div class="panel"><h3>风险分布</h3><div ref="riskChartRef" class="chart" /></div>
        <div class="panel"><h3>部门人数</h3><div ref="deptChartRef" class="chart" /></div>
      </div>
      <div class="panel">
        <h3>最近入职</h3>
        <table><thead><tr><th>姓名</th><th>部门</th><th>职位</th><th>入职日期</th></tr></thead>
        <tbody>
          <tr v-for="h in stats.recent_hires" :key="h.id">
            <td>{{ h.name }}</td><td>{{ h.department }}</td><td>{{ h.position }}</td><td class="muted">{{ h.hire_date.split('T')[0] }}</td>
          </tr>
        </tbody></table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.dashboard { display: flex; flex-direction: column; gap: 20px; }
.loading, .error { padding: 40px; text-align: center; color: #6b7280; }
.error button { background: #2563eb; color: #fff; border: none; border-radius: 6px; padding: 4px 14px; cursor: pointer; margin-left: 12px; }
.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.kpi-card { background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); border-left: 4px solid; }
.kpi-card.blue { border-color: #3b82f6; } .kpi-card.green { border-color: #22c55e; }
.kpi-card.purple { border-color: #a855f7; } .kpi-card.red { border-color: #ef4444; }
.kpi-val { font-size: 32px; font-weight: 700; color: #1f2937; }
.kpi-label { font-size: 13px; color: #6b7280; margin-top: 4px; }
.chart-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.panel { background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); }
.panel h3 { font-size: 15px; color: #1e40af; margin: 0 0 12px; }
.chart { width: 100%; height: 280px; }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; padding: 10px 12px; font-size: 12px; color: #6b7280; border-bottom: 2px solid #e5e7eb; }
td { padding: 10px 12px; font-size: 14px; border-bottom: 1px solid #f3f4f6; }
.muted { color: #9ca3af; font-size: 13px; }
@media (max-width: 768px) { .kpi-row { grid-template-columns: repeat(2, 1fr); } .chart-row { grid-template-columns: 1fr; } }
</style>
