import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import SourceView from '../views/SourceView.vue'
import TrendView from '../views/TrendView.vue'
import ReportView from '../views/ReportView.vue'
import AlertView from '../views/AlertView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'dashboard', component: DashboardView },
    { path: '/sources', name: 'sources', component: SourceView },
    { path: '/trends', name: 'trends', component: TrendView },
    { path: '/reports', name: 'reports', component: ReportView },
    { path: '/alerts', name: 'alerts', component: AlertView },
  ],
})
export default router
