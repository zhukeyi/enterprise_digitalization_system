import { createRouter, createWebHistory } from 'vue-router'
import PricingDashboard from '../views/PricingDashboard.vue'
import SimulatorView from '../views/SimulatorView.vue'
import StrategyView from '../views/StrategyView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'dashboard', component: PricingDashboard },
    { path: '/simulator', name: 'simulator', component: SimulatorView },
    { path: '/strategy', name: 'strategy', component: StrategyView },
  ],
})

export default router
