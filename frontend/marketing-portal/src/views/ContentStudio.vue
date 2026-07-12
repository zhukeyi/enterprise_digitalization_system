<script setup lang="ts">
import { ref } from 'vue'
import { optimizeContent, generateGEO, generateSEO, type ContentScore, type ContentPiece } from '../api/client'

const title = ref('云栖智能 企业AI平台选型指南')
const body = ref('我们实测提效3倍，引用2026行业基准报告，数据经第三方审计。本文基于真实落地经验给出可验证结论。')
const score = ref<ContentScore | null>(null)
const scoring = ref(false)

const brand = ref('云栖智能')
const topic = ref('企业AI平台')
const geoPiece = ref<ContentPiece | null>(null)
const seoPiece = ref<ContentPiece | null>(null)
const generating = ref(false)

async function runScore() {
  scoring.value = true
  try {
    score.value = await optimizeContent({ title: title.value, body: body.value })
  } finally {
    scoring.value = false
  }
}

async function runGEO() {
  generating.value = true
  try {
    geoPiece.value = await generateGEO({ brand: brand.value, topic: topic.value })
  } finally {
    generating.value = false
  }
}

async function runSEO() {
  generating.value = true
  try {
    seoPiece.value = await generateSEO({ brand: brand.value, topic: topic.value })
  } finally {
    generating.value = false
  }
}

const fmt = (n: number, d = 1) => n.toFixed(d)
</script>

<template>
  <div class="fade-in">
    <div class="grid-2">
      <!-- Optimizer -->
      <div class="panel">
        <div class="panel-title"><span class="bar" /> 内容评分（E-E-A-T + 引用友好度）</div>
        <div class="field">
          <label>标题</label>
          <input v-model="title" class="input" placeholder="内容标题" />
        </div>
        <div class="field">
          <label>正文</label>
          <textarea v-model="body" rows="6" placeholder="粘贴内容正文…" />
        </div>
        <button class="btn" :disabled="scoring" @click="runScore">
          {{ scoring ? '评分中…' : '评分并给建议' }}
        </button>

        <div v-if="score" class="metric-row">
          <div class="metric"><div class="metric-label">E-E-A-T</div><div class="metric-value" style="color:var(--accent)">{{ fmt(score.eeat_score) }}</div></div>
          <div class="metric"><div class="metric-label">引用友好度</div><div class="metric-value" style="color:var(--accent-2)">{{ fmt(score.citation_score) }}</div></div>
          <div class="metric"><div class="metric-label">经验</div><div class="metric-value">{{ fmt(score.experience) }}</div></div>
          <div class="metric"><div class="metric-label">专业</div><div class="metric-value">{{ fmt(score.expertise) }}</div></div>
          <div class="metric"><div class="metric-label">权威</div><div class="metric-value">{{ fmt(score.authoritativeness) }}</div></div>
          <div class="metric"><div class="metric-label">可信</div><div class="metric-value">{{ fmt(score.trustworthiness) }}</div></div>
        </div>
        <ul v-if="score" class="sugg-list">
          <li v-for="(s, i) in score.suggestions" :key="i">{{ s }}</li>
        </ul>
      </div>

      <!-- Generator -->
      <div class="panel">
        <div class="panel-title"><span class="bar" /> GEO / SEO 内容生成</div>
        <div class="field">
          <label>品牌</label>
          <input v-model="brand" class="input" />
        </div>
        <div class="field">
          <label>主题 / 关键词</label>
          <input v-model="topic" class="input" />
        </div>
        <div style="display:flex;gap:10px">
          <button class="btn" :disabled="generating" @click="runGEO">生成 GEO 内容</button>
          <button class="btn btn-ghost" :disabled="generating" @click="runSEO">生成 SEO 文章</button>
        </div>

        <div v-if="geoPiece" class="variant-card" style="margin-top:16px">
          <div class="variant-head"><span class="variant-headline">{{ geoPiece.title }}</span><span class="tag tag-green">GEO 优化</span></div>
          <div class="variant-body" style="white-space:pre-wrap;max-height:220px;overflow:auto">{{ geoPiece.body }}</div>
          <div class="variant-foot">
            <span class="tag tag-violet">E-E-A-T {{ fmt(geoPiece.eeat_score) }}</span>
            <span class="tag tag-cyan">引用度 {{ fmt(geoPiece.citation_score) }}</span>
          </div>
        </div>
        <div v-if="seoPiece" class="variant-card" style="margin-top:12px">
          <div class="variant-head"><span class="variant-headline">{{ seoPiece.title }}</span><span class="tag tag-orange">SEO</span></div>
          <div class="variant-body" style="white-space:pre-wrap;max-height:220px;overflow:auto">{{ seoPiece.body }}</div>
        </div>
      </div>
    </div>
  </div>
</template>
