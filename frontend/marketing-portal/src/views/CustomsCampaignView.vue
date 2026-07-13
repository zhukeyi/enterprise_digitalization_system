<script setup lang="ts">
import { onMounted, ref, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import {
  getCampaignOverview, getCampaignSegments, generateCampaignContent, pushCampaign, attributeCampaignROI,
  type CustomsOverview, type CustomsSegment, type CustomsContent, type CustomsPushResult, type CustomsROI,
} from '../api/client'

const overview = ref<CustomsOverview | null>(null)
const segments = ref<CustomsSegment[]>([])
const loading = ref(true)

const selectedSegment = ref<CustomsSegment | null>(null)
const brand = ref('云栖智能')

// content
const content = ref<CustomsContent | null>(null)
const contentLoading = ref(false)
const contentLangs = ref<string[]>(['en', 'ja', 'ko'])

// push
const pushChannel = ref<'portal' | 'webhook' | 'email'>('portal')
const pushAddress = ref('')
const pushEmail = ref('')
const pushConsent = ref(true)
const pushUnsub = ref('https://fde.local/unsubscribe')
const pushResult = ref<CustomsPushResult | null>(null)
const pushLoading = ref(false)

// roi
const totalBudget = ref<number>(80000)
const roi = ref<CustomsROI | null>(null)
const roiLoading = ref(false)
const roiChart = ref<HTMLElement | null>(null)
let roiInst: echarts.ECharts | null = null

const fmt = (n: number, d = 1) => n.toLocaleString('zh-CN', { maximumFractionDigits: d })
const fmtMoney = (n: number) => '$' + n.toLocaleString('zh-CN', { maximumFractionDigits: 0 })

const statusTag = (s: string) =>
  s === 'passed' ? 'tag-green' : s === 'partial' ? 'tag-orange' : s === 'blocked' ? 'tag-red' : 'tag-violet'

async function loadAll() {
  overview.value = await getCampaignOverview()
  segments.value = await getCampaignSegments()
  if (segments.value.length && !selectedSegment.value) selectedSegment.value = segments.value[0]
}

async function genContent() {
  if (!selectedSegment.value) return
  contentLoading.value = true
  try {
    content.value = await generateCampaignContent({
      segment_id: selectedSegment.value.segment_id,
      brand: brand.value,
      target_langs: contentLangs.value,
    })
  } finally {
    contentLoading.value = false
  }
}

async function doPush() {
  if (!selectedSegment.value) return
  pushLoading.value = true
  pushResult.value = null
  try {
    pushResult.value = await pushCampaign({
      segment_id: selectedSegment.value.segment_id,
      channel: pushChannel.value,
      address: pushAddress.value,
      brand: brand.value,
      email: pushChannel.value === 'email' ? pushEmail.value : null,
      consent: pushChannel.value === 'email' ? pushConsent.value : null,
      unsubscribe_url: pushChannel.value === 'email' ? pushUnsub.value : null,
    })
  } finally {
    pushLoading.value = false
  }
}

async function doROI() {
  roiLoading.value = true
  try {
    roi.value = await attributeCampaignROI({ total_budget: totalBudget.value })
    await nextTick()
    renderRoiChart()
  } finally {
    roiLoading.value = false
  }
}

function renderRoiChart() {
  if (!roiChart.value || !roi.value) return
  roiInst = echarts.init(roiChart.value, 'dark')
  const r = roi.value.ranking
  roiInst.setOption({
    backgroundColor: 'transparent',
    grid: { left: 130, right: 24, top: 16, bottom: 24 },
    tooltip: { trigger: 'axis', valueFormatter: (v: number) => fmt(v, 2) + '×' },
    xAxis: { type: 'value', axisLabel: { color: '#b9a8e8', formatter: '{value}×' } },
    yAxis: { type: 'category', data: r.map((x) => x.platform), axisLabel: { color: '#b9a8e8' } },
    series: [{
      type: 'bar', data: r.map((x) => x.roas),
      itemStyle: {
        borderRadius: [0, 6, 6, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
          { offset: 0, color: '#22d3ee' }, { offset: 1, color: '#a855f7' },
        ]),
      },
      label: { show: true, position: 'right', color: '#f1ecff', formatter: '{c}×' },
    }],
  })
}

watch(selectedSegment, () => { content.value = null; pushResult.value = null })

onMounted(async () => {
  try { await loadAll() } finally { loading.value = false }
})
</script>

<template>
  <div class="fade-in">
    <div v-if="loading" class="loading"><div class="spinner" /><span>加载海关定向数据…</span></div>
    <template v-else-if="overview">
      <!-- KPI -->
      <div class="kpi-grid">
        <div class="kpi-card" style="--glow:rgba(34,211,238,0.18)">
          <div class="kpi-label">受众分群</div>
          <div class="kpi-value">{{ overview.total_segments }}<span class="kpi-unit">个</span></div>
          <div class="kpi-sub">可触达 {{ overview.outreach_ready }}</div>
        </div>
        <div class="kpi-card" style="--glow:rgba(52,211,153,0.16)">
          <div class="kpi-label">可触达买家</div>
          <div class="kpi-value">{{ overview.total_deliverable_buyers }}<span class="kpi-unit">家</span></div>
          <div class="kpi-sub kpi-up">衍生画像（非原始 BOL）</div>
        </div>
        <div class="kpi-card" style="--glow:rgba(244,63,94,0.16)">
          <div class="kpi-label">制裁拦截买家</div>
          <div class="kpi-value">{{ overview.total_blocked_buyers }}<span class="kpi-unit">家</span></div>
          <div class="kpi-sub" style="color:var(--danger)">{{ overview.blocked_segments }} 个分群全拦截</div>
        </div>
        <div class="kpi-card" style="--glow:rgba(251,146,60,0.18)">
          <div class="kpi-label">合计进口额</div>
          <div class="kpi-value" style="font-size:22px">{{ fmtMoney(overview.total_deliverable_value_usd) }}</div>
          <div class="kpi-sub">可触达买家合计</div>
        </div>
      </div>

      <!-- Segment table -->
      <div class="panel">
        <div class="panel-title"><span class="bar" /> 海关受众分群（品类 × 港口 × 频次 × 增长）</div>
        <table class="table">
          <thead>
            <tr>
              <th>品类</th><th>港口</th><th>频次</th><th>增长</th>
              <th class="num">可触达</th><th class="num">拦截</th><th class="num">进口额</th><th>合规</th><th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in segments" :key="s.segment_id"
                :class="{ 'row-active': selectedSegment && selectedSegment.segment_id === s.segment_id }"
                @click="selectedSegment = s" style="cursor:pointer">
              <td>{{ s.category }}</td>
              <td>{{ s.port }}</td>
              <td><span class="tag tag-cyan">{{ s.frequency_tier }}</span></td>
              <td><span class="tag tag-violet">{{ s.growth_tier }}</span></td>
              <td class="num">{{ s.deliverable_count }}</td>
              <td class="num" style="color:var(--danger)">{{ s.blocked_count }}</td>
              <td class="num">{{ fmtMoney(s.total_value_usd) }}</td>
              <td><span class="tag" :class="statusTag(s.compliance_status)">{{ s.compliance_status }}</span></td>
              <td class="num"><b style="color:var(--accent-2)">选择</b></td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="selectedSegment" class="grid-2">
        <!-- Content + Push -->
        <div>
          <div class="panel">
            <div class="panel-title"><span class="bar" /> 定向 GEO 内容（{{ selectedSegment.name }}）</div>
            <div class="field">
              <label>推广品牌</label>
              <input class="input" v-model="brand" />
            </div>
            <div class="field">
              <label>多语言版本（逗号分隔，如 en,ja,ko）</label>
              <input class="input" v-model="contentLangs" placeholder="en,ja,ko" />
            </div>
            <button class="btn" :disabled="contentLoading" @click="genContent">
              {{ contentLoading ? '生成中…' : '生成 GEO 内容' }}
            </button>

            <div v-if="content" class="fade-in" style="margin-top:14px">
              <div class="variant-card">
                <div class="variant-headline">{{ content.geo_piece.title }}</div>
                <div class="variant-foot">
                  <span>EEAT {{ fmt(content.geo_piece.eeat_score) }}</span>
                  <span>引用友好 {{ fmt(content.geo_piece.citation_score) }}</span>
                  <span class="tag tag-green" v-if="content.geo_piece.geo_optimized">GEO</span>
                </div>
                <pre class="raw-body">{{ content.geo_piece.body }}</pre>
              </div>
              <div class="panel-title" style="margin-top:6px"><span class="bar" /> 多语言版本</div>
              <div v-for="(piece, lang) in content.multilingual.pieces" :key="lang" class="variant-card">
                <div class="variant-head"><span class="variant-headline">[{{ lang }}] {{ piece.title }}</span></div>
              </div>
              <div class="panel-title" style="margin-top:6px"><span class="bar" /> 衍生关键词机会</div>
              <table class="table">
                <thead><tr><th>关键词</th><th>意图</th><th class="num">月量</th><th class="num">机会分</th></tr></thead>
                <tbody>
                  <tr v-for="k in content.keywords.slice(0, 6)" :key="k.term">
                    <td>{{ k.term }}</td><td><span class="tag tag-cyan">{{ k.intent }}</span></td>
                    <td class="num">{{ k.monthly_volume.toLocaleString() }}</td>
                    <td class="num"><b style="color:var(--accent-3)">{{ fmt(k.opportunity_score) }}</b></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="panel">
            <div class="panel-title"><span class="bar" /> 合规推送</div>
            <div class="field">
              <label>渠道</label>
              <select class="select" v-model="pushChannel">
                <option value="portal">Portal（企业内网，无需 PII）</option>
                <option value="webhook">Webhook（企业系统）</option>
                <option value="email">Email（需企业域名+同意+退订）</option>
              </select>
            </div>
            <div class="field">
              <label>地址（Portal/Webhook URL 或 邮箱）</label>
              <input class="input" v-model="pushAddress" :placeholder="pushChannel === 'email' ? 'marketing@公司域名.com' : 'https://…'" />
            </div>
            <template v-if="pushChannel === 'email'">
              <div class="field">
                <label>企业邮箱</label>
                <input class="input" v-model="pushEmail" placeholder="marketing@corp.com" />
              </div>
              <div class="field" style="display:flex;gap:12px;align-items:center">
                <label style="margin:0">明示同意</label>
                <input type="checkbox" v-model="pushConsent" />
                <label style="margin:0">退订链接</label>
                <input class="input" style="width:auto;flex:1" v-model="pushUnsub" />
              </div>
            </template>
            <button class="btn" :disabled="pushLoading" @click="doPush">
              {{ pushLoading ? '推送中…' : '推送分群' }}
            </button>
            <div v-if="pushResult" class="fade-in" style="margin-top:12px">
              <div class="variant-card" :style="{ borderColor: pushResult.success ? 'var(--up)' : 'var(--danger)' }">
                <div class="variant-headline" :style="{ color: pushResult.success ? 'var(--up)' : 'var(--danger)' }">
                  {{ pushResult.success ? '✓ 推送成功' : '✕ 已拒绝' }}
                </div>
                <div class="variant-body">{{ pushResult.message }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- ROI -->
        <div class="panel">
          <div class="panel-title"><span class="bar" /> ROI 归因（分群即渠道）</div>
          <div class="field">
            <label>计划总预算（USD）</label>
            <input class="input" type="number" v-model.number="totalBudget" />
          </div>
          <button class="btn" :disabled="roiLoading" @click="doROI">
            {{ roiLoading ? '归因中…' : '测算 ROI' }}
          </button>
          <div v-if="roi" class="fade-in" style="margin-top:14px">
            <div class="metric-row">
              <div class="metric"><div class="metric-label">混合 ROAS</div><div class="metric-value" style="color:var(--accent-2)">{{ fmt(roi.blended_roas, 2) }}×</div></div>
              <div class="metric"><div class="metric-label">总花费</div><div class="metric-value">{{ fmtMoney(roi.total_spend) }}</div></div>
              <div class="metric"><div class="metric-label">总营收</div><div class="metric-value" style="color:var(--up)">{{ fmtMoney(roi.total_revenue) }}</div></div>
            </div>
            <div ref="roiChart" class="chart" style="height:260px;margin-top:12px" />
            <div v-if="roi.roi_prediction" class="variant-card" style="margin-top:12px">
              <div class="variant-headline">预测（预算 {{ fmtMoney(roi.roi_prediction.spend) }}）</div>
              <div class="metric-row">
                <div class="metric"><div class="metric-label">预测营收</div><div class="metric-value" style="color:var(--up)">{{ fmtMoney(roi.roi_prediction.predicted_revenue) }}</div></div>
                <div class="metric"><div class="metric-label">预测 ROAS</div><div class="metric-value">{{ fmt(roi.roi_prediction.predicted_roas, 2) }}×</div></div>
                <div class="metric"><div class="metric-label">预测利润</div><div class="metric-value">{{ fmtMoney(roi.roi_prediction.predicted_profit) }}</div></div>
                <div class="metric"><div class="metric-label">拟合 R²</div><div class="metric-value">{{ fmt(roi.roi_prediction.fit_r_squared, 3) }}</div></div>
              </div>
            </div>
            <div v-else class="kpi-sub" style="margin-top:8px">可触达分群不足 2 个，未触发 OLS 预测。</div>
          </div>
        </div>
      </div>

      <div v-else class="panel"><div class="kpi-sub">请选择一个受众分群以生成内容与归因。</div></div>
    </template>
  </div>
</template>

<style scoped>
.raw-body {
  white-space: pre-wrap; word-break: break-word; font-size: 12px; line-height: 1.6;
  background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px;
  padding: 12px; margin-top: 10px; color: var(--text-secondary); max-height: 240px; overflow: auto;
}
.row-active { background: rgba(34, 211, 238, 0.08); }
.row-active td:first-child { box-shadow: inset 3px 0 0 var(--accent-2); }
</style>
