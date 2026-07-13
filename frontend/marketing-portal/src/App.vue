<script setup lang="ts">
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">
        <span class="logo-coin">◈</span>
        <span class="logo-text">FDE MARKETING</span>
        <span class="logo-sub">GEO 投放与增长引擎</span>
      </div>
      <nav class="nav-links">
        <RouterLink to="/">GEO 可见度</RouterLink>
        <RouterLink to="/content">内容工作室</RouterLink>
        <RouterLink to="/ads">广告投放</RouterLink>
        <RouterLink to="/roi">ROI 看板</RouterLink>
        <RouterLink to="/customs">海关定向</RouterLink>
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
