<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">FDE HR 智能评估</div>
      <nav class="nav">
        <RouterLink to="/" class="nav-link">总览</RouterLink>
        <RouterLink to="/employees" class="nav-link">员工</RouterLink>
      </nav>
    </header>
    <main class="content"><RouterView /></main>
  </div>
</template>

<style scoped>
.app-shell { min-height: 100vh; display: flex; flex-direction: column; }
.topbar { height: 56px; background: #1e40af; color: #fff; display: flex; align-items: center; justify-content: space-between; padding: 0 24px; }
.brand { font-weight: 600; font-size: 16px; }
.nav { display: flex; gap: 16px; }
.nav-link { color: #dbeafe; text-decoration: none; font-size: 14px; padding: 4px 12px; border-radius: 6px; }
.nav-link:hover, .nav-link.router-link-active { background: rgba(255,255,255,0.15); color: #fff; }
.content { flex: 1; padding: 24px; max-width: 1200px; margin: 0 auto; width: 100%; box-sizing: border-box; }
</style>
