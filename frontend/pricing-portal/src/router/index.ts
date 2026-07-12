import { createRouter, createWebHistory } from 'vue-router'
import PricingDashboard from '../views/PricingDashboard.vue'
import SimulatorView from '../views/SimulatorView.vue'
import StrategyView from '../views/StrategyView.vue'
import ElasticityView from '../views/ElasticityView.vue'
import CompetitorView from '../views/CompetitorView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'dashboard', component: PricingDashboard },
    { path: '/simulator', name: 'simulator', component: SimulatorView },
    { path: '/strategy', name: 'strategy', component: StrategyView },
    { path: '/elasticity', name: 'elasticity', component: ElasticityView },
    { path: '/competitors', name: 'competitors', component: CompetitorView },
  ],
})
export default router
