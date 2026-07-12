<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getEmployeeDetail, getRiskAssessment } from '../api/client'

const props = defineProps<{ id: string }>()
const detail = ref<Record<string, any>>({})
const risk = ref<Record<string, any> | null>(null)
const loading = ref(true)
const riskLoading = ref(false)
const activeTab = ref('profile')

onMounted(async () => {
  try {
    detail.value = await getEmployeeDetail(props.id)
  } catch (e: any) { console.error(e) }
  finally { loading.value = false }
})

async function loadRisk() {
  if (risk.value) return
  riskLoading.value = true
  try { risk.value = await getRiskAssessment(props.id) }
  catch (e: any) { console.error(e) }
  finally { riskLoading.value = false }
}
</script>

<template>
  <div class="detail-page">
    <div v-if="loading" class="loading">加载中...</div>
    <template v-else-if="detail.employee">
      <div class="panel header-card">
        <div class="avatar">{{ detail.employee.name?.charAt(0) }}</div>
        <div class="info">
          <h2>{{ detail.employee.name }}</h2>
          <p class="meta">{{ detail.employee.title }} - {{ detail.employee.department_name }}</p>
          <p class="sub">{{ detail.employee.email }} | 工号: {{ detail.employee.employee_id }}</p>
        </div>
      </div>

      <div class="tabs">
        <button :class="{ active: activeTab === 'profile' }" @click="activeTab = 'profile'">AI 画像</button>
        <button :class="{ active: activeTab === 'risk' }" @click="activeTab = 'risk'; loadRisk()">风险评估</button>
      </div>

      <div v-if="activeTab === 'profile'" class="panel">
        <h3>能力画像</h3>
        <div v-if="detail.profile">
          <div class="profile-row" v-for="(val, key) in detail.profile" :key="key">
            <span class="profile-key">{{ key }}</span>
            <span class="profile-val">{{ typeof val === 'object' ? JSON.stringify(val).substring(0, 200) : val }}</span>
          </div>
        </div>
      </div>

      <div v-if="activeTab === 'risk'" class="panel">
        <div v-if="riskLoading" class="loading">评估中...</div>
        <template v-else-if="risk">
          <h3>风险评估结果</h3>
          <div class="risk-level" :class="risk.overall_risk_level">
            总体风险等级: <strong>{{ risk.overall_risk_level }}</strong>
          </div>
          <div v-if="risk.risk_dimensions" class="risk-dims">
            <div v-for="dim in risk.risk_dimensions" :key="dim.risk_type" class="risk-dim" :class="dim.level">
              <span class="dim-name">{{ dim.risk_type }}</span>
              <span class="dim-level">{{ dim.level }}</span>
              <span class="dim-score">{{ dim.score?.toFixed(1) }}</span>
            </div>
          </div>
          <div v-if="risk.recommendations" class="recs">
            <h4>建议</h4>
            <ul><li v-for="r in risk.recommendations" :key="r">{{ r }}</li></ul>
          </div>
        </template>
      </div>
    </template>
  </div>
</template>

<style scoped>
.detail-page { display: flex; flex-direction: column; gap: 16px; }
.loading { padding: 40px; text-align: center; color: #6b7280; }
.panel { background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); }
.header-card { display: flex; gap: 16px; align-items: center; }
.avatar { width: 56px; height: 56px; border-radius: 50%; background: #2563eb; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 24px; font-weight: 700; flex-shrink: 0; }
.info h2 { margin: 0; font-size: 18px; color: #1f2937; }
.meta { margin: 4px 0; font-size: 14px; color: #4b5563; }
.sub { margin: 0; font-size: 13px; color: #9ca3af; }
.tabs { display: flex; gap: 8px; }
.tabs button { padding: 8px 20px; border: 1px solid #d1d5db; background: #fff; border-radius: 8px; font-size: 14px; cursor: pointer; color: #6b7280; }
.tabs button.active { background: #2563eb; color: #fff; border-color: #2563eb; }
h3 { font-size: 15px; color: #1e40af; margin: 0 0 12px; }
h4 { font-size: 14px; color: #374151; margin: 16px 0 8px; }
.profile-row { display: flex; gap: 12px; padding: 8px 0; border-bottom: 1px solid #f3f4f6; }
.profile-key { font-size: 13px; color: #6b7280; min-width: 160px; font-weight: 500; }
.profile-val { font-size: 13px; color: #374151; flex: 1; }
.risk-level { padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; font-size: 14px; }
.risk-level.low { background: #dcfce7; color: #16a34a; }
.risk-level.medium { background: #fef3c7; color: #d97706; }
.risk-level.high { background: #fee2e2; color: #dc2626; }
.risk-level.critical { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
.risk-dims { display: flex; flex-direction: column; gap: 8px; }
.risk-dim { display: flex; gap: 16px; padding: 8px 12px; border-radius: 8px; align-items: center; }
.risk-dim.low { background: #f0fdf4; }
.risk-dim.medium { background: #fffbeb; }
.risk-dim.high { background: #fef2f2; }
.dim-name { flex: 1; font-size: 13px; font-weight: 500; }
.dim-level { font-size: 12px; padding: 2px 8px; border-radius: 20px; }
.dim-level.low { background: #22c55e; color: #fff; }
.dim-level.medium { background: #f59e0b; color: #fff; }
.dim-level.high { background: #ef4444; color: #fff; }
.dim-score { font-size: 14px; font-weight: 700; color: #374151; }
.recs ul { margin: 0; padding-left: 20px; }
.recs li { font-size: 13px; color: #4b5563; padding: 4px 0; }
</style>
