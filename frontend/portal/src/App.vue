<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
const router = useRouter()
const loggedIn = computed(() => auth.isLoggedIn)

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="app-shell">
    <header v-if="loggedIn" class="topbar">
      <div class="brand">FDE 数据门户</div>
      <nav class="nav">
        <RouterLink to="/upload" class="nav-link">上传</RouterLink>
        <RouterLink to="/chat" class="nav-link">对话</RouterLink>
        <button class="link-btn" @click="logout">退出</button>
      </nav>
    </header>
    <main class="content">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  color: #1f2937;
  background: #f5f7fa;
}
.topbar {
  height: 56px;
  background: #1e3a8a;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
}
.brand {
  font-weight: 600;
  font-size: 16px;
  letter-spacing: 0.5px;
}
.nav {
  display: flex;
  align-items: center;
  gap: 16px;
}
.nav-link {
  color: #dbeafe;
  text-decoration: none;
  font-size: 14px;
  padding: 4px 8px;
  border-radius: 6px;
}
.nav-link:hover {
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
}
.link-btn {
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.4);
  color: #fff;
  font-size: 14px;
  padding: 4px 12px;
  border-radius: 6px;
  cursor: pointer;
}
.link-btn:hover {
  background: rgba(255, 255, 255, 0.12);
}
.content {
  flex: 1;
  padding: 24px;
  max-width: 960px;
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
}
</style>
