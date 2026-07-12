<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { getDepartments, getRedundancy, type DepartmentInfo } from '../api/client'
import FoolproofDialog from '../components/FoolproofDialog.vue'

const departments = ref<DepartmentInfo[]>([])
const selectedDept = ref<string>('')
const loading = ref(true)
const error = ref('')
const analysisResult = ref<Record<string, any> | null>(null)
const analyzing = ref(false)
const dialogVisible = ref(false)
const confirmed = ref(false)

const chartRef = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

async function loadDepartments() {
  loading.value = true
  error.value = ''
  try {
    departments.value = await getDepartments()
    if (departments.value.length > 0) {
      selectedDept.value = departments.value[0].dept_id
      await runAnalysis()
    }
  } catch (e: any) {
    error.value = e?.message || '加载部门列表失败'
  } finally {
    loading.value = false
  }
}

async function runAnalysis() {
  if (!selectedDept.value) return
  analyzing.value = true
  confirmed.value = false
  analysisResult.value = null
  try {
    const result = await getRedundancy(selectedDept.value)
    analysisResult.value = result
    await nextTick()
    renderChart()
  } catch (e: any) {
    error.value = e?.message || '冗余分析失败'
  } finally {
    analyzing.value = false
  }
}

function renderChart() {
  if (!chartRef.value || !analysisResult.value) return
  if (chart) chart.dispose()
  chart = echarts.init(chartRef.value)

  const r = analysisResult.value
  const positions = r.optimizable_positions || r.positions || []
  const names = positions.map((p: any) => p.position || p.title || p.name || '—')
  const redundancyRates = positions.map((p: any) => p.redundancy_rate || p.score || 0)
  const headcounts = positions.map((p: any) => p.headcount || p.count || 0)

  chart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['冗余率 %', '人数'], bottom: 5, textStyle: { fontSize: 12, color: '#6b7280' } },
    grid: { left: 120, right: 60, top: 20, bottom: 50 },
    xAxis: { type: 'value', axisLabel: { color: '#6b7280' } },
    yAxis: { type: 'category', data: names, axisLabel: { color: '#374151', fontSize: 13 } },
    series: [
      {
        name: '冗余率 %',
        type: 'bar',
        data: redundancyRates,
        itemStyle: { color: '#f59e0b', borderRadius: [0, 4, 4, 0] },
        barWidth: '35%',
      },
      {
        name: '人数',
        type: 'bar',
        data: headcounts,
        itemStyle: { color: '#3b82f6', borderRadius: [0, 4, 4, 0] },
        barWidth: '35%',
      },
    ],
  })
}

function openDialog() {
  dialogVisible.value = true
}

function onConfirmed() {
  confirmed.value = true
  dialogVisible.value = false
}

function handleResize() { chart?.resize() }
onMounted(() => { loadDepartments(); window.addEventListener('resize', handleResize) })
onUnmounted(() => { window.removeEventListener('resize', handleResize); chart?.dispose() })
</script>

<template>
  <div class="simulator">
    <div v-if="loading" class="loading">加载中...</div>
    <template v-else>
      <div class="control-panel">
        <div class="control-group">
          <label class="control-label">选择部门</label>
          <select v-model="selectedDept" class="select" @change="runAnalysis">
            <option v-for="d in departments" :key="d.dept_id" :value="d.dept_id">
              {{ d.name }}（{{ d.head_count }}人）
            </option>
          </select>
        </div>
        <button class="btn-analyze" :disabled="analyzing" @click="runAnalysis">
          {{ analyzing ? '分析中...' : '重新分析' }}
        </button>
      </div>

      <div v-if="error" class="error">{{ error }}</div>

      <template v-if="analysisResult && !analyzing">
        <div class="kpi-row">
          <div class="kpi-card amber">
            <div class="kpi-val">{{ ((analysisResult.redundancy_rate || 0) * 100).toFixed(1) }}%</div>
            <div class="kpi-label">冗余率</div>
          </div>
          <div class="kpi-card blue">
            <div class="kpi-val">{{ analysisResult.affected_count || analysisResult.headcount || '—' }}</div>
            <div class="kpi-label">涉及人数</div>
          </div>
          <div class="kpi-card green">
            <div class="kpi-val">¥{{ ((analysisResult.estimated_savings || 0) / 10000).toFixed(1) }}万</div>
            <div class="kpi-label">预计年节省</div>
          </div>
          <div class="kpi-card" :class="{
            red: analysisResult.risk_level === 'high',
            amber: analysisResult.risk_level === 'medium',
            green: analysisResult.risk_level === 'low',
          }">
            <div class="kpi-val">{{ analysisResult.risk_level || '—' }}</div>
            <div class="kpi-label">风险等级</div>
          </div>
        </div>

        <div class="panel">
          <h3>岗位冗余分析</h3>
          <div ref="chartRef" class="chart" />
        </div>

        <div class="panel">
          <h3>可优化岗位清单</h3>
          <table>
            <thead>
              <tr>
                <th>岗位</th>
                <th>人数</th>
                <th>冗余率</th>
                <th>建议</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(p, i) in (analysisResult.optimizable_positions || analysisResult.positions || [])" :key="i">
                <td>{{ p.position || p.title || p.name || '—' }}</td>
                <td>{{ p.headcount || p.count || '—' }}</td>
                <td>{{ ((p.redundancy_rate || p.score || 0)).toFixed(1) }}%</td>
                <td class="muted">{{ p.recommendation || p.suggestion || '可优化' }}</td>
              </tr>
              <tr v-if="(analysisResult.optimizable_positions || analysisResult.positions || []).length === 0">
                <td colspan="4" class="empty">暂无可优化岗位数据</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="action-bar">
          <div v-if="confirmed" class="confirmed-banner">
            ✓ 裁员方案已确认执行，快照已存档
          </div>
          <button v-else class="btn-execute" @click="openDialog">
            执行裁员模拟（防呆确认）
          </button>
        </div>
      </template>
    </template>

    <FoolproofDialog
      :visible="dialogVisible"
      :department-name="departments.find(d => d.dept_id === selectedDept)?.name || ''"
      :analysis-result="analysisResult"
      @close="dialogVisible = false"
      @confirm="onConfirmed"
    />
  </div>
</template>

<style scoped>
.simulator { display: flex; flex-direction: column; gap: 20px; }
.loading { padding: 40px; text-align: center; color: #6b7280; }
.error { padding: 16px; background: #fef2f2; border-radius: 8px; color: #991b1b; font-size: 14px; }

.control-panel {
  display: flex;
  gap: 16px;
  align-items: flex-end;
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.06);
}
.control-group { flex: 1; }
.control-label { display: block; font-size: 13px; color: #6b7280; margin-bottom: 6px; }
.select {
  width: 100%; padding: 10px 14px; border: 1px solid #d1d5db; border-radius: 8px;
  font-size: 14px; color: #1f2937; background: #fff; outline: none;
}
.select:focus { border-color: #2563eb; }
.btn-analyze {
  padding: 10px 20px; background: #2563eb; color: #fff; border: none; border-radius: 8px;
  font-size: 14px; font-weight: 600; cursor: pointer; white-space: nowrap;
}
.btn-analyze:hover { background: #1d4ed8; }
.btn-analyze:disabled { opacity: 0.5; cursor: not-allowed; }

.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.kpi-card { background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); border-left: 4px solid; }
.kpi-card.blue { border-color: #3b82f6; } .kpi-card.green { border-color: #22c55e; }
.kpi-card.amber { border-color: #f59e0b; } .kpi-card.red { border-color: #ef4444; }
.kpi-val { font-size: 28px; font-weight: 700; color: #1f2937; }
.kpi-label { font-size: 13px; color: #6b7280; margin-top: 4px; }

.panel { background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); }
.panel h3 { font-size: 15px; color: #1e40af; margin: 0 0 12px; }
.chart { width: 100%; height: 300px; }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; padding: 10px 12px; font-size: 12px; color: #6b7280; border-bottom: 2px solid #e5e7eb; }
td { padding: 10px 12px; font-size: 14px; border-bottom: 1px solid #f3f4f6; }
.muted { color: #9ca3af; }
.empty { text-align: center; color: #9ca3af; padding: 20px; }

.action-bar { display: flex; justify-content: center; padding: 8px 0; }
.btn-execute {
  padding: 14px 36px; background: #dc2626; color: #fff; border: none; border-radius: 10px;
  font-size: 16px; font-weight: 700; cursor: pointer; transition: background 0.15s;
}
.btn-execute:hover { background: #b91c1c; }
.confirmed-banner {
  padding: 14px 28px; background: #dcfce7; border: 1px solid #86efac; border-radius: 10px;
  color: #166534; font-size: 15px; font-weight: 600;
}

@media (max-width: 768px) {
  .kpi-row { grid-template-columns: repeat(2, 1fr); }
  .control-panel { flex-direction: column; }
}
</style>
