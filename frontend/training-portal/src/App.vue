<script setup lang="ts">
const courses = [
  { name: '数字化基础', desc: '企业信息化认知、数据资产与协同工具概览', hours: '2.0h', level: '入门' },
  { name: 'AI 工具实战', desc: '对话式 AI 与 RAG 知识库的日常使用', hours: '3.0h', level: '入门' },
  { name: '数据分析入门', desc: '指标体系搭建与经营看板解读', hours: '2.5h', level: '初级' },
  { name: 'Dify 工作流', desc: '低代码搭建业务自动化与智能体', hours: '3.0h', level: '初级' },
  { name: '情报与营销', desc: 'GEO 投放与外部情报采集方法', hours: '2.0h', level: '中级' },
  { name: '合规与安全', desc: '数据安全、权限治理与审计规范', hours: '1.5h', level: '中级' },
]

const certs = [
  { tier: '初级', title: '信息化应用专员', desc: '掌握平台基础操作与知识库使用' },
  { tier: '中级', title: 'AI 业务编排师', desc: '能独立搭建 Dify 工作流与看板' },
  { tier: '高级', title: '企业 AI 落地顾问', desc: '主导七步法落地与组织优化' },
]

const resources = [
  { name: '培训手册 (PDF)', note: '体系化教材，即将上线' },
  { name: '录播视频课程', note: '配套讲解，即将上线' },
  { name: '实操题库', note: '认证模拟，即将上线' },
]

const hubUrl = '/hub/'
</script>

<template>
  <div class="page">
    <header class="top">
      <div class="brand">
        <div class="logo">③</div>
        <div>
          <h1>培训与认证</h1>
          <p class="sub">FDE 企业信息化培训班 · 能力考证体系</p>
        </div>
      </div>
      <a class="hub-btn" :href="hubUrl">← 返回统一入口</a>
    </header>

    <section class="intro">
      <h2>培养目标</h2>
      <p>
        面向企业全员的信息化能力提升计划。通过体系化课程与分级认证，让业务团队真正用得起、
        用得好 AI 平台，把"七步法"转化为可落地的工作能力。
      </p>
    </section>

    <section>
      <h2>课程模块</h2>
      <div class="grid">
        <div v-for="c in courses" :key="c.name" class="card">
          <div class="card-head">
            <h3>{{ c.name }}</h3>
            <span class="tag">{{ c.level }}</span>
          </div>
          <p class="desc">{{ c.desc }}</p>
          <div class="meta">⏱ {{ c.hours }}</div>
        </div>
      </div>
    </section>

    <section>
      <h2>认证路径</h2>
      <div class="certs">
        <div v-for="(c, i) in certs" :key="c.tier" class="cert">
          <div class="cert-no">0{{ i + 1 }}</div>
          <div>
            <div class="cert-tier">{{ c.tier }}</div>
            <div class="cert-title">{{ c.title }}</div>
            <div class="cert-desc">{{ c.desc }}</div>
          </div>
        </div>
      </div>
    </section>

    <section>
      <h2>资料中心</h2>
      <div class="res-grid">
        <div v-for="r in resources" :key="r.name" class="res">
          <div class="res-name">{{ r.name }}</div>
          <div class="res-note">{{ r.note }}</div>
        </div>
      </div>
    </section>

    <footer class="footer">
      <span>FDE AI Platform · 培训与认证模块</span>
      <a :href="hubUrl">返回统一入口 ↗</a>
    </footer>
  </div>
</template>

<style scoped>
.page {
  max-width: 1080px;
  margin: 0 auto;
  padding: 32px 24px 56px;
}

.top {
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
  width: 50px;
  height: 50px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  font-size: 22px;
  font-weight: 800;
  color: #fff;
  background: linear-gradient(135deg, #8b5cf6, #4f7cff);
  box-shadow: 0 8px 22px rgba(139, 92, 246, 0.3);
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
}

.hub-btn {
  padding: 9px 15px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: #fff;
  font-size: 14px;
  font-weight: 600;
  color: var(--accent);
}

.hub-btn:hover {
  border-color: var(--accent);
}

section {
  margin-top: 36px;
}

h2 {
  font-size: 18px;
  font-weight: 700;
  margin: 0 0 16px;
  padding-left: 12px;
  border-left: 4px solid var(--accent);
}

.intro p {
  margin: 0;
  font-size: 15px;
  line-height: 1.7;
  color: var(--muted);
  max-width: 760px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 18px;
  transition: transform 0.16s ease, box-shadow 0.16s ease;
}

.card:hover {
  transform: translateY(-3px);
  box-shadow: 0 12px 28px rgba(20, 30, 60, 0.1);
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.card-head h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
}

.tag {
  font-size: 11px;
  padding: 3px 9px;
  border-radius: 999px;
  color: var(--accent);
  background: rgba(79, 124, 255, 0.12);
}

.desc {
  margin: 10px 0;
  font-size: 13.5px;
  color: var(--muted);
  line-height: 1.55;
}

.meta {
  font-size: 12.5px;
  color: #8a93ad;
}

.certs {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.cert {
  display: flex;
  gap: 14px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 18px;
}

.cert-no {
  flex: 0 0 auto;
  width: 42px;
  height: 42px;
  border-radius: 11px;
  display: grid;
  place-items: center;
  font-weight: 800;
  color: #fff;
  background: linear-gradient(135deg, #4f7cff, #8b5cf6);
}

.cert-tier {
  font-size: 12px;
  color: var(--accent);
  font-weight: 700;
}

.cert-title {
  font-size: 16px;
  font-weight: 700;
  margin: 2px 0;
}

.cert-desc {
  font-size: 13px;
  color: var(--muted);
  line-height: 1.5;
}

.res-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 14px;
}

.res {
  background: var(--card);
  border: 1px dashed var(--line);
  border-radius: 12px;
  padding: 16px;
}

.res-name {
  font-size: 14.5px;
  font-weight: 600;
}

.res-note {
  margin-top: 6px;
  font-size: 12.5px;
  color: #f0a020;
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
  color: var(--accent);
  font-weight: 600;
}

.footer a:hover {
  text-decoration: underline;
}
</style>
