<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import * as echarts from 'echarts'
import BaseChart from '../components/BaseChart.vue'
import { getDashboardStats, type DashboardStats } from '../api/client'

const stats = ref<DashboardStats | null>(null)
const loading = ref(true)
const error = ref('')

async function loadStats() {
  loading.value = true
  error.value = ''
  try {
    stats.value = await getDashboardStats()
  } catch (err: unknown) {
    const detail = (err as { response?: { data?: { detail?: string } }; message?: string })
      ?.response?.data?.detail
    error.value = detail || (err as { message?: string })?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

// Reusable chart options — now declared as plain data instead of inline echarts calls.
const dailyOption = computed<Record<string, unknown>>(() => {
  if (!stats.value) return {}
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: 'category',
      data: stats.value.daily_ingest.map((d) => d.date),
      axisLabel: { fontSize: 12, color: '#6b7280' },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { fontSize: 12, color: '#6b7280' },
    },
    series: [
      {
        type: 'bar',
        data: stats.value.daily_ingest.map((d) => d.count),
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#3b82f6' },
            { offset: 1, color: '#93c5fd' },
          ]),
          borderRadius: [4, 4, 0, 0],
        },
        barWidth: '50%',
      },
    ],
  }
})

const typeOption = computed<Record<string, unknown>>(() => {
  if (!stats.value) return {}
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: {
      orient: 'vertical',
      right: 10,
      top: 'center',
      textStyle: { fontSize: 12, color: '#374151' },
    },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['40%', '50%'],
        avoidLabelOverlap: false,
        label: { show: false },
        emphasis: {
          label: { show: true, fontSize: 14, fontWeight: 'bold' },
        },
        data: stats.value.doc_types.map((t) => ({ name: t.name, value: t.count })),
        color: ['#1e3a8a', '#3b82f6', '#60a5fa', '#93c5fd', '#bfdbfe', '#dbeafe', '#f59e0b', '#10b981'],
      },
    ],
  }
})

onMounted(loadStats)

function formatTime(iso: string | null): string {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch {
    return iso
  }
}
</script>

<template>
  <section class="dashboard">
    <!-- loading -->
    <div v-if="loading" class="loading">
      <div class="spinner" />
      <span>加载统计数据中…</span>
    </div>

    <!-- error -->
    <div v-else-if="error" class="error-banner">
      <span>{{ error }}</span>
      <button @click="loadStats">重试</button>
    </div>

    <!-- stats -->
    <template v-else-if="stats">
      <!-- KPI cards -->
      <div class="kpi-grid">
        <div class="kpi-card">
          <div class="kpi-icon doc" />
          <div class="kpi-body">
            <div class="kpi-value">{{ stats.total_documents }}</div>
            <div class="kpi-label">标准文档</div>
          </div>
        </div>
        <div class="kpi-card">
          <div class="kpi-icon chunk" />
          <div class="kpi-body">
            <div class="kpi-value">{{ stats.total_chunks }}</div>
            <div class="kpi-label">文档切片</div>
          </div>
        </div>
        <div class="kpi-card">
          <div class="kpi-icon raw" />
          <div class="kpi-body">
            <div class="kpi-value">{{ stats.total_raw }}</div>
            <div class="kpi-label">原始文件</div>
          </div>
        </div>
        <div class="kpi-card">
          <div class="kpi-icon type" />
          <div class="kpi-body">
            <div class="kpi-value">{{ stats.doc_types.length }}</div>
            <div class="kpi-label">数据类型</div>
          </div>
        </div>
      </div>

      <!-- charts -->
      <div class="chart-grid">
        <div class="chart-card">
          <h3>近 7 日入库趋势</h3>
          <BaseChart :option="dailyOption" />
        </div>
        <div class="chart-card">
          <h3>数据类型分布</h3>
          <BaseChart :option="typeOption" />
        </div>
      </div>

      <!-- recent uploads -->
      <div class="table-card">
        <h3>最近上传</h3>
        <table v-if="stats.recent_uploads.length > 0">
          <thead>
            <tr>
              <th>标题</th>
              <th>类型</th>
              <th>时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in stats.recent_uploads" :key="item.id">
              <td class="title-cell">{{ item.title }}</td>
              <td><span class="tag">{{ item.doc_type }}</span></td>
              <td class="time-cell">{{ formatTime(item.created_at) }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">暂无上传记录</div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* loading */
.loading {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 60px 0;
  justify-content: center;
  color: #6b7280;
  font-size: 14px;
}
.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid #e5e7eb;
  border-top-color: #1e3a8a;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

/* error */
.error-banner {
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  padding: 16px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #dc2626;
  font-size: 14px;
}
.error-banner button {
  background: #dc2626;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 4px 14px;
  font-size: 13px;
  cursor: pointer;
}

/* KPI cards */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
.kpi-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  transition: transform 0.15s;
}
.kpi-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
}
.kpi-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  flex-shrink: 0;
}
.kpi-icon.doc { background: linear-gradient(135deg, #3b82f6, #1e3a8a); }
.kpi-icon.chunk { background: linear-gradient(135deg, #60a5fa, #3b82f6); }
.kpi-icon.raw { background: linear-gradient(135deg, #93c5fd, #60a5fa); }
.kpi-icon.type { background: linear-gradient(135deg, #f59e0b, #d97706); }
.kpi-value {
  font-size: 28px;
  font-weight: 700;
  color: #1f2937;
  line-height: 1.2;
}
.kpi-label {
  font-size: 13px;
  color: #6b7280;
  margin-top: 2px;
}

/* charts */
.chart-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.chart-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}
.chart-card h3 {
  margin: 0 0 12px;
  font-size: 15px;
  color: #1e3a8a;
}
.chart-canvas {
  width: 100%;
  height: 280px;
}

/* table */
.table-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}
.table-card h3 {
  margin: 0 0 12px;
  font-size: 15px;
  color: #1e3a8a;
}
table {
  width: 100%;
  border-collapse: collapse;
}
th {
  text-align: left;
  padding: 10px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
  border-bottom: 2px solid #e5e7eb;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
td {
  padding: 10px 12px;
  font-size: 14px;
  color: #374151;
  border-bottom: 1px solid #f3f4f6;
}
td.title-cell {
  max-width: 360px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
td.time-cell {
  color: #9ca3af;
  font-size: 13px;
  white-space: nowrap;
}
.tag {
  display: inline-block;
  padding: 2px 10px;
  background: #eff6ff;
  color: #1e3a8a;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
}
.empty {
  padding: 32px 0;
  text-align: center;
  color: #9ca3af;
  font-size: 14px;
}

/* responsive */
@media (max-width: 768px) {
  .kpi-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .chart-grid {
    grid-template-columns: 1fr;
  }
}
</style>
