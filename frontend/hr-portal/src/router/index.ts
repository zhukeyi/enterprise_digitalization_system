import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import EmployeeListView from '../views/EmployeeListView.vue'
import EmployeeDetailView from '../views/EmployeeDetailView.vue'
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'dashboard', component: DashboardView },
    { path: '/employees', name: 'employees', component: EmployeeListView },
    { path: '/employees/:id', name: 'employee-detail', component: EmployeeDetailView, props: true },
  ],
})
export default router
