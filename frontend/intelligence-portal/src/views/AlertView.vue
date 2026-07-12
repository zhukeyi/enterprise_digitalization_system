<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getItems, collectIntelligence, type IntelItem } from '../api/client'

const items = ref<IntelItem[]>([])
const loading = ref(true)
const error = ref('')
const keywordInput = ref('')
const sourceType = ref('rss')
const collecting = ref(false)
const collectResult = ref('')

// Alert rules (local, demo)
const alertRules = ref([
  { id: 1, keyword: '竞品', sentiment: 'negative', enabled: true, triggered: 0 },
  { id: 2, keyword: '诉讼', sentiment: 'negative', enabled: true, triggered: 0 },
  { id: 3, keyword: '安全漏洞', sentiment: 'negative', enabled: true, triggered: 0 },
  { id: 4, keyword: '融资', sentiment: 'positive', enabled: false, triggered: 0 },
  { id: 5, keyword: '市场份额', sentiment: '', enabled: true, triggered: 0 },
])

const triggeredAlerts = ref<{ keyword: string; item: IntelItem }[]>([])

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    items.value = await getItems(200)
    checkAlerts()
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function checkAlerts() {
  triggeredAlerts.value = []
  for (const rule of alertRules.value) {
    if (!rule.enabled) continue
    const matches = items.value.filter(item => {
      const text = (item.title + ' ' + item.summary + ' ' + (item.keywords || []).join(' ')).toLowerCase()
      return text.includes(rule.keyword.toLowerCase())
    })
    rule.triggered = matches.length
    for (const m of matches.slice(0, 3)) {
      triggeredAlerts.value.push({ keyword: rule.keyword, item: m })
    }
  }
}

function toggleRule(id: number) {
  const rule = alertRules.value.find(r => r.id === id)
  if (rule) {
    rule.enabled = !rule.enabled
    checkAlerts()
  }
}

function addRule() {
  if (!keywordInput.value.trim()) return
  alertRules.value.push({
    id: Date.now(),
    keyword: keywordInput.value.trim(),
    sentiment: '',
    enabled: true,
    triggered: 0,
  })
  keywordInput.value = ''
  checkAlerts()
}

function removeRule(id: number) {
  alertRules.value = alertRules.value.filter(r => r.id !== id)
  checkAlerts()
}

async function triggerCollect() {
  collecting.value = true
  collectResult.value = ''
  try {
    const res = await collectIntelligence({ source_type: sourceType.value, max_items: 10 })
    collectResult.value = res.success ? `采集成功，新增 ${res.items_collected} 条` : `采集失败: ${res.error || '未知错误'}`
    await loadData()
  } catch (e: any) {
    collectResult.value = e?.message || '采集请求失败'
  } finally {
    collecting.value = false
  }
}

onMounted(() => loadData())
</script>

<template>
  <div class="view">
    <div v-if="loading" class="loading">扫描预警规则...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <template v-else>
      <h2>预警管理</h2>

      <div class="panel">
        <h3>手动采集</h3>
        <div class="collect-row">
          <select v-model="sourceType" class="select">
            <option value="rss">RSS</option>
            <option value="http">HTTP</option>
            <option value="api">API</option>
          </select>
          <button class="btn-collect" :disabled="collecting" @click="triggerCollect">
            {{ collecting ? '采集中...' : '触发采集' }}
          </button>
          <span v-if="collectResult" class="collect-result">{{ collectResult }}</span>
        </div>
      </div>

      <div class="panel">
        <h3>预警规则</h3>
        <div class="rule-list">
          <div v-for="rule in alertRules" :key="rule.id" class="rule-item">
            <div class="rule-info">
              <span class="rule-kw">{{ rule.keyword }}</span>
              <span v-if="rule.sentiment" class="rule-sentiment" :class="rule.sentiment">{{ rule.sentiment }}</span>
              <span class="rule-triggered">触发 {{ rule.triggered }} 次</span>
            </div>
            <div class="rule-actions">
              <button class="btn-toggle" :class="{ on: rule.enabled }" @click="toggleRule(rule.id)">
                {{ rule.enabled ? '已启用' : '已禁用' }}
              </button>
              <button class="btn-remove" @click="removeRule(rule.id)">删除</button>
            </div>
          </div>
        </div>
        <div class="add-rule">
          <input v-model="keywordInput" class="input" placeholder="输入关键词..." @keyup.enter="addRule" />
          <button class="btn-add" @click="addRule">添加规则</button>
        </div>
      </div>

      <div class="panel">
        <h3>近期预警触发 ({{ triggeredAlerts.length }})</h3>
        <div v-if="triggeredAlerts.length === 0" class="empty">暂无预警触发</div>
        <div v-else class="alert-list">
          <div v-for="(a, i) in triggeredAlerts.slice(0, 20)" :key="i" class="alert-item">
            <span class="alert-kw">{{ a.keyword }}</span>
            <span class="alert-title">{{ a.item.title }}</span>
            <span class="alert-date">{{ a.item.collected_at?.slice(0, 10) || '—' }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.view { display: flex; flex-direction: column; gap: 16px; }
.loading { padding: 40px; text-align: center; color: var(--text-muted); }
.error { padding: 20px; text-align: center; color: var(--accent-red); }
h2 { font-size: 20px; font-weight: 700; color: var(--text-primary); margin: 0; }
h3 { font-size: 14px; color: var(--accent); margin: 0 0 12px; letter-spacing: 1px; }

.panel { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 18px; }

.collect-row { display: flex; align-items: center; gap: 12px; }
.select {
  padding: 8px 12px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-primary); font-size: 13px;
}
.btn-collect {
  padding: 8px 16px; background: transparent; border: 1px solid var(--accent); border-radius: 6px;
  color: var(--accent); font-size: 13px; font-weight: 600; cursor: pointer;
}
.btn-collect:hover { background: rgba(0,212,255,0.1); }
.btn-collect:disabled { opacity: 0.4; cursor: not-allowed; }
.collect-result { font-size: 13px; color: var(--accent-green); }

.rule-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }
.rule-item { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; background: var(--bg-secondary); border-radius: 8px; }
.rule-info { display: flex; align-items: center; gap: 10px; }
.rule-kw { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.rule-sentiment { font-size: 11px; padding: 2px 6px; border-radius: 4px; }
.rule-sentiment.positive { background: rgba(34,197,94,0.2); color: var(--accent-green); }
.rule-sentiment.negative { background: rgba(239,68,68,0.2); color: var(--accent-red); }
.rule-triggered { font-size: 12px; color: var(--text-muted); }
.rule-actions { display: flex; gap: 8px; }
.btn-toggle { padding: 4px 10px; border: 1px solid var(--border); border-radius: 6px; font-size: 12px; cursor: pointer; background: transparent; color: var(--text-muted); }
.btn-toggle.on { border-color: var(--accent-green); color: var(--accent-green); background: rgba(34,197,94,0.1); }
.btn-remove { padding: 4px 10px; border: 1px solid var(--accent-red); border-radius: 6px; font-size: 12px; cursor: pointer; background: transparent; color: var(--accent-red); }

.add-rule { display: flex; gap: 8px; }
.input { flex: 1; padding: 8px 12px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 13px; outline: none; }
.input:focus { border-color: var(--accent); }
.btn-add { padding: 8px 16px; background: var(--accent); border: none; border-radius: 6px; color: #0a0e1a; font-size: 13px; font-weight: 600; cursor: pointer; }

.empty { color: var(--text-muted); font-size: 14px; padding: 16px 0; }
.alert-list { display: flex; flex-direction: column; gap: 6px; max-height: 400px; overflow-y: auto; }
.alert-item { display: flex; align-items: center; gap: 12px; padding: 8px 12px; background: var(--bg-secondary); border-radius: 6px; }
.alert-kw { font-size: 12px; padding: 2px 8px; border-radius: 4px; background: rgba(245,158,11,0.2); color: var(--accent-yellow); white-space: nowrap; }
.alert-title { flex: 1; font-size: 13px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.alert-date { font-size: 11px; color: var(--text-muted); font-family: 'SF Mono', monospace; }
</style>
