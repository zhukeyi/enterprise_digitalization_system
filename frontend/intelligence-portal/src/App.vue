<script setup lang="ts">
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">
        <span class="logo-dot" />
        <span class="logo-text">FDE INTELLIGENCE</span>
        <span class="logo-sub">情报中心</span>
      </div>
      <div class="status-bar">
        <nav class="nav-links">
          <RouterLink to="/" class="nav-link">总览</RouterLink>
          <RouterLink to="/sources" class="nav-link">数据源</RouterLink>
          <RouterLink to="/trends" class="nav-link">趋势</RouterLink>
          <RouterLink to="/reports" class="nav-link">报告</RouterLink>
          <RouterLink to="/alerts" class="nav-link">预警</RouterLink>
        </nav>
        <span class="status-dot online" />
        <span class="status-text">LIVE</span>
        <span class="clock" id="clock">{{ clockText }}</span>
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
      const d = new Date()
      clockText.value = d.toLocaleTimeString('zh-CN', { hour12: false })
    }
    onMounted(() => { updateClock(); timer = setInterval(updateClock, 1000) })
    onUnmounted(() => { if (timer) clearInterval(timer) })
    return { clockText }
  }
}
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
}

.topbar {
  height: 60px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 32px;
  position: relative;
}
.topbar::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--accent), transparent);
  opacity: 0.5;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}
.logo-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--accent);
  animation: pulse-glow 2s ease-in-out infinite;
}
.logo-text {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 2px;
  color: var(--accent);
  text-shadow: 0 0 10px var(--accent-glow);
}
.logo-sub {
  font-size: 12px;
  color: var(--text-muted);
  letter-spacing: 1px;
}

.status-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.nav-links {
  display: flex;
  gap: 4px;
  margin-right: 16px;
}

.nav-link {
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 13px;
  padding: 4px 12px;
  border-radius: 6px;
  transition: all 0.2s;
}

.nav-link:hover {
  color: var(--accent);
  background: rgba(0, 212, 255, 0.08);
}

.nav-link.router-link-active {
  color: var(--accent);
  background: rgba(0, 212, 255, 0.12);
  text-shadow: 0 0 8px var(--accent-glow);
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.status-dot.online {
  background: var(--accent-green);
  box-shadow: 0 0 8px var(--accent-green);
  animation: pulse-glow 2s infinite;
}
.status-text {
  color: var(--accent-green);
  font-weight: 600;
  letter-spacing: 1px;
}
.clock {
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
  margin-left: 12px;
  padding-left: 12px;
  border-left: 1px solid var(--border);
}

.content {
  flex: 1;
  padding: 24px 32px;
  max-width: 1600px;
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
}
</style>
