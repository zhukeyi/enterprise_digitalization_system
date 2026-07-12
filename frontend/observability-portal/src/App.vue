<template>
  <div class="app-layout">
    <nav class="sidebar">
      <div class="logo">
        <span class="logo-icon">&#9889;</span>
        <span class="logo-text">FDE Observability</span>
      </div>
      <ul class="nav-links">
        <li v-for="item in navItems" :key="item.path">
          <router-link :to="item.path" class="nav-link" active-class="active">
            <span class="nav-icon">{{ item.icon }}</span>
            <span>{{ item.label }}</span>
          </router-link>
        </li>
      </ul>
      <div class="sidebar-footer">
        <a href="/hub/" class="back-link">&#8592; Back to Hub</a>
      </div>
    </nav>
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
const navItems = [
  { path: "/", label: "Overview", icon: "\u25A0" },
  { path: "/health", label: "Service Health", icon: "\u25CF" },
  { path: "/tokens", label: "Token Router", icon: "\u25B2" },
  { path: "/api", label: "API Management", icon: "\u25C6" },
  { path: "/rag", label: "RAG Inspector", icon: "\u25C8" },
  { path: "/traces", label: "Trace Viewer", icon: "\u25CB" },
  { path: "/audit", label: "Audit Trail", icon: "\u25A3" },
  { path: "/alerts", label: "Alerts & Drift", icon: "\u26A1" },
];
</script>

<style scoped>
.app-layout {
  display: flex;
  min-height: 100vh;
}
.sidebar {
  width: 220px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}
.logo {
  padding: 20px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  border-bottom: 1px solid var(--border-color);
}
.logo-icon {
  font-size: 20px;
}
.logo-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}
.nav-links {
  list-style: none;
  padding: 8px 0;
  flex: 1;
}
.nav-link {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  color: var(--text-secondary);
  font-size: 13px;
  transition: background 0.15s, color 0.15s;
}
.nav-link:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  text-decoration: none;
}
.nav-link.active {
  background: var(--bg-tertiary);
  color: var(--accent-blue);
  border-left: 2px solid var(--accent-blue);
}
.nav-icon {
  font-size: 10px;
  width: 14px;
}
.sidebar-footer {
  padding: 12px 16px;
  border-top: 1px solid var(--border-color);
}
.back-link {
  font-size: 12px;
  color: var(--text-tertiary);
}
.main-content {
  flex: 1;
  padding: 24px 32px;
  overflow-y: auto;
}
</style>
