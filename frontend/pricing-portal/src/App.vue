<script setup lang="ts">
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">
        <span class="logo-coin">¥</span>
        <span class="logo-text">FDE PRICING</span>
        <span class="logo-sub">动态定价引擎</span>
      </div>
      <nav class="nav-links">
        <RouterLink to="/">总览</RouterLink>
        <RouterLink to="/simulator">What-if 模拟</RouterLink>
        <RouterLink to="/strategy">策略优化</RouterLink>
        <RouterLink to="/elasticity">弹性分析</RouterLink>
        <RouterLink to="/competitors">竞品监控</RouterLink>
      </nav>
      <div class="status-bar">
        <span class="status-dot" />
        <span class="status-text">LIVE</span>
        <span class="clock">{{ clockText }}</span>
      </div>
    </header>
    <main class="content">
      <RouterView />
    </main>
  </div>
</template>

<script lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

export default {
  setup() {
    const clockText = ref('')
    let timer: number | undefined
    const updateClock = () => {
      clockText.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    }
    onMounted(() => { updateClock(); timer = setInterval(updateClock, 1000) as unknown as number })
    onUnmounted(() => { if (timer) clearInterval(timer) })
    return { clockText }
  }
}
</script>
