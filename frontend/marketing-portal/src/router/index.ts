import { createRouter, createWebHistory } from 'vue-router'
import GEODashboard from '../views/GEODashboard.vue'
import ContentStudio from '../views/ContentStudio.vue'
import AdManager from '../views/AdManager.vue'
import ROIDashboard from '../views/ROIDashboard.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'geo', component: GEODashboard },
    { path: '/content', name: 'content', component: ContentStudio },
    { path: '/ads', name: 'ads', component: AdManager },
    { path: '/roi', name: 'roi', component: ROIDashboard },
  ],
})

export default router
