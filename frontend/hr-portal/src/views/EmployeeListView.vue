<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getEmployees, type EmployeeSummary } from '../api/client'

const router = useRouter()
const employees = ref<EmployeeSummary[]>([])
const loading = ref(true)
const search = ref('')

onMounted(async () => {
  try { employees.value = await getEmployees() }
  catch (e: any) { console.error(e) }
  finally { loading.value = false }
})

const filtered = () => employees.value.filter(e =>
  e.name.includes(search.value) || e.department.includes(search.value) || e.position.includes(search.value)
)
</script>

<template>
  <div class="panel">
    <div class="header">
      <h3>员工列表</h3>
      <input v-model="search" placeholder="搜索姓名/部门/职位..." class="search" />
    </div>
    <div v-if="loading" class="loading">加载中...</div>
    <table v-else>
      <thead><tr><th>工号</th><th>姓名</th><th>部门</th><th>职位</th><th>状态</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="e in filtered()" :key="e.employee_id">
          <td class="muted">{{ e.employee_id }}</td>
          <td>{{ e.name }}</td>
          <td>{{ e.department }}</td>
          <td>{{ e.position }}</td>
          <td><span :class="['tag', e.status]">{{ e.status }}</span></td>
          <td><button class="link-btn" @click="router.push('/employees/' + e.employee_id)">详情</button></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.panel { background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
h3 { font-size: 15px; color: #1e40af; margin: 0; }
.search { height: 34px; border: 1px solid #d1d5db; border-radius: 8px; padding: 0 12px; font-size: 14px; width: 260px; }
.loading { padding: 40px; text-align: center; color: #6b7280; }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; padding: 10px 12px; font-size: 12px; color: #6b7280; border-bottom: 2px solid #e5e7eb; }
td { padding: 10px 12px; font-size: 14px; border-bottom: 1px solid #f3f4f6; }
.muted { color: #9ca3af; font-size: 13px; }
.tag { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 12px; }
.tag.active { background: #dcfce7; color: #16a34a; }
.tag.probation { background: #fef3c7; color: #d97706; }
.tag.leave { background: #e0e7ff; color: #4f46e5; }
.tag.resigned { background: #fee2e2; color: #dc2626; }
.link-btn { background: #2563eb; color: #fff; border: none; border-radius: 6px; padding: 4px 14px; font-size: 13px; cursor: pointer; }
</style>
