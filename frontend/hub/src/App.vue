<script setup lang="ts">
const platform = {
  name: 'FDE 企业 AI 平台',
  sub: 'Enterprise AI Platform',
}

const modules = [
  { step: '①', name: '基础信息化', desc: '企业数字化基建与 RAG 知识中枢', path: '/portal/', tag: 'V4 基石', accent: '#4f7cff' },
  { step: '②', name: '交付驾驶舱', desc: '定制 Dify 工作流 + 经营驾驶舱', path: '/portal/dashboard', tag: 'Dashboard', accent: '#22d3ee' },
  { step: '③', name: '培训与认证', desc: '信息化培训班 + 能力考证体系', path: '/training/', tag: '新建', accent: '#a78bfa' },
  { step: '④', name: '情报增幅器', desc: '外部情报采集与竞争洞察', path: '/intel/', tag: 'Insight', accent: '#34d399' },
  { step: '⑤', name: 'GEO 营销', desc: '生成式引擎优化与增长投放', path: '/marketing/', tag: 'Growth', accent: '#f472b6' },
  { step: '⑥', name: '智能裁员评估', desc: '人岗匹配与组织优化模拟', path: '/hr/', tag: 'HR', accent: '#fbbf24' },
  { step: '⑦', name: '动态定价引擎', desc: '需求预测与弹性定价优化', path: '/pricing/', tag: 'Pricing', accent: '#fb7185' },
]

const difyUrl = '/'
</script>

<template>
  <div class="page">
    <header class="hero">
      <div class="hero-inner">
        <div class="brand">
          <div class="logo">FDE</div>
          <div>
            <h1>{{ platform.name }}</h1>
            <p class="sub">{{ platform.sub }} · 统一入口</p>
          </div>
        </div>
        <a class="dify-btn" :href="difyUrl">智能体工作台 (Dify) ↗</a>
      </div>
      <h2 class="slogan">企业落地七步法 · 一站式导航</h2>
      <p class="lead">
        从信息化基建到动态定价，七大能力模块统一编排，助力企业完成 AI 落地闭环。
      </p>
    </header>

    <main class="grid">
      <a
        v-for="m in modules"
        :key="m.step"
        class="card"
        :href="m.path"
        :style="{ '--accent': m.accent }"
      >
        <div class="step">{{ m.step }}</div>
        <div class="card-body">
          <div class="card-head">
            <h3>{{ m.name }}</h3>
            <span class="badge">● 已上线</span>
          </div>
          <p class="desc">{{ m.desc }}</p>
          <div class="foot">
            <span class="tag">{{ m.tag }}</span>
            <span class="enter">进入 →</span>
          </div>
        </div>
      </a>
    </main>

    <footer class="footer">
      <span>FDE AI Platform · V5 企业落地七步法</span>
      <a href="/hub/">返回统一入口</a>
    </footer>
  </div>
</template>

<style scoped>
.page {
  max-width: 1180px;
  margin: 0 auto;
  padding: 36px 24px 56px;
}

.hero {
  margin-bottom: 32px;
}

.hero-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.brand {
  display: flex;
  align-items: center;
  gap: 14px;
}

.logo {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  font-weight: 800;
  letter-spacing: 0.5px;
  color: #fff;
  background: linear-gradient(135deg, #4f7cff, #8b5cf6);
  box-shadow: 0 8px 24px rgba(79, 124, 255, 0.35);
}

.brand h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
}

.sub {
  margin: 2px 0 0;
  font-size: 13px;
  color: var(--muted);
  letter-spacing: 0.4px;
}

.dify-btn {
  padding: 10px 16px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.04);
  font-size: 14px;
  font-weight: 600;
  transition: all 0.18s ease;
}

.dify-btn:hover {
  border-color: #4f7cff;
  background: rgba(79, 124, 255, 0.12);
}

.slogan {
  margin: 28px 0 8px;
  font-size: 26px;
  font-weight: 800;
  background: linear-gradient(90deg, #fff, #b9c6ff);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.lead {
  margin: 0;
  max-width: 640px;
  color: var(--muted);
  font-size: 15px;
  line-height: 1.6;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 18px;
}

.card {
  position: relative;
  display: flex;
  gap: 14px;
  padding: 20px;
  border-radius: 16px;
  background: var(--card);
  border: 1px solid var(--line);
  overflow: hidden;
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}

.card::before {
  content: '';
  position: absolute;
  inset: 0 0 auto 0;
  height: 3px;
  background: var(--accent);
  opacity: 0.9;
}

.card:hover {
  transform: translateY(-4px);
  border-color: var(--accent);
  box-shadow: 0 14px 34px rgba(0, 0, 0, 0.35);
}

.step {
  flex: 0 0 auto;
  width: 46px;
  height: 46px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  font-size: 20px;
  font-weight: 800;
  color: #fff;
  background: color-mix(in srgb, var(--accent) 22%, #0c1222);
  border: 1px solid color-mix(in srgb, var(--accent) 45%, transparent);
}

.card-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.card-head h3 {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
}

.badge {
  font-size: 11px;
  color: #34d399;
  white-space: nowrap;
}

.desc {
  margin: 0;
  font-size: 13.5px;
  color: var(--muted);
  line-height: 1.55;
}

.foot {
  margin-top: auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.tag {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 999px;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
}

.enter {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  opacity: 0.75;
  transition: opacity 0.18s ease;
}

.card:hover .enter {
  opacity: 1;
}

.footer {
  margin-top: 40px;
  padding-top: 18px;
  border-top: 1px solid var(--line);
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  color: var(--muted);
}

.footer a {
  color: #8ea2ff;
}

.footer a:hover {
  text-decoration: underline;
}
</style>
