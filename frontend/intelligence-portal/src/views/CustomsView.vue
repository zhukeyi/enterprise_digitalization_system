<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import {
  getCustomsOverview,
  getTradeRecords,
  getBuyers,
  getCustomsTrends,
  ingestCustoms,
  type CustomsOverview,
  type TradeRecord,
  type BuyerEntity,
  type IngestRequest,
} from '../api/client'

const overview = ref<CustomsOverview | null>(null)
const tradeRecords = ref<TradeRecord[]>([])
const buyers = ref<BuyerEntity[]>([])
const loading = ref(false)
const error = ref('')

// Search filters
const filters = ref({ hsCode: '', reporter: '', partner: '', port: '', limit: 50 })

// Ingest form
const ingestForm = ref<IngestRequest & { url: string }>({
  provider: 'un_comtrade',
  url: '',
  reporter: '842',
  partner: 'all',
  year: '2023',
  hs_code: 'ALL',
  max_items: 50,
})
const ingesting = ref(false)
const ingestMsg = ref('')

const trendChartRef = ref<HTMLElement | null>(null)
let trendChart: echarts.ECharts | null = null

async function loadOverview() {
  try {
    overview.value = await getCustomsOverview()
  } catch {
    /* overview is best-effort */
  }
}

async function search() {
  loading.value = true
  error.value = ''
  try {
    const f = filters.value
    tradeRecords.value = await getTradeRecords({
      hs_code: f.hsCode || undefined,
      reporter_country: f.reporter || undefined,
      partner_country: f.partner || undefined,
      port: f.port || undefined,
      limit: f.limit,
    })
    await loadBuyers()
    if (f.hsCode) await loadTrends(f.hsCode)
  } catch (err: unknown) {
    error.value = (err as { message?: string })?.message || '查询失败'
  } finally {
    loading.value = false
  }
}

async function loadBuyers() {
  try {
    buyers.value = await getBuyers({ limit: 50 })
  } catch {
    buyers.value = []
  }
}

async function loadTrends(hsCode: string) {
  const pts = await getCustomsTrends(hsCode, 'period')
  await nextTick()
  renderTrend(pts)
}

function renderTrend(pts: { bucket: string; value_usd: number }[]) {
  if (!trendChartRef.value) return
  if (trendChart) trendChart.dispose()
  trendChart = echarts.init(trendChartRef.value, 'dark')
  const darkAxis = {
    axisLabel: { color: '#94a3b8', fontSize: 11 },
    axisLine: { lineStyle: { color: '#2a3556' } },
  }
  trendChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', formatter: (p: unknown) => {
      const arr = p as Array<{ name: string; value: number }>
      return `${arr[0].name}<br/>贸易额: $${Number(arr[0].value).toLocaleString()}`
    } },
    grid: { left: 60, right: 20, top: 30, bottom: 40 },
    xAxis: { type: 'category', data: pts.map((d) => d.bucket), ...darkAxis },
    yAxis: { type: 'value', ...darkAxis },
    series: [{
      type: 'bar',
      data: pts.map((d) => d.value_usd),
      barWidth: '55%',
      itemStyle: {
        borderRadius: [4, 4, 0, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: '#a855f7' },
          { offset: 1, color: 'rgba(168,85,247,0.15)' },
        ]),
        shadowColor: 'rgba(168,85,247,0.4)',
        shadowBlur: 12,
      },
    }],
  })
}

async function ingest() {
  ingesting.value = true
  ingestMsg.value = ''
  try {
    const res = await ingestCustoms(ingestForm.value)
    if (res.error) {
      ingestMsg.value = `采集失败: ${res.error}`
    } else {
      ingestMsg.value = `已入库 ${res.stored} 条 (tier=${res.tier})`
      await loadOverview()
      await search()
    }
  } catch (err: unknown) {
    ingestMsg.value = `采集异常: ${(err as { message?: string })?.message || '未知错误'}`
  } finally {
    ingesting.value = false
  }
}

function fmtUsd(v: number): string {
  if (!v) return '-'
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`
  if (v >= 1e3) return `$${(v / 1e3).toFixed(1)}K`
  return `$${v.toFixed(0)}`
}

function handleResize() {
  trendChart?.resize()
}

onMounted(async () => {
  await loadOverview()
  await search()
  window.addEventListener('resize', handleResize)
})
onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  trendChart?.dispose()
})
</script>

<template>
  <div class="customs">
    <div v-if="error" class="error-banner">
      <span>{{ error }}</span><button @click="search">RETRY</button>
    </div>

    <!-- KPI row -->
    <div class="kpi-row">
      <div class="kpi-card purple">
        <div class="kpi-label">TRADE RECORDS</div>
        <div class="kpi-value">{{ overview?.trade_record_count ?? '—' }}</div>
        <div class="kpi-sub">进口品类记录 (Tier-1)</div>
      </div>
      <div class="kpi-card cyan">
        <div class="kpi-label">BUYER ENTITIES</div>
        <div class="kpi-value">{{ overview?.buyer_count ?? '—' }}</div>
        <div class="kpi-sub">采购商实体 (Tier-2)</div>
      </div>
      <div class="kpi-card green">
        <div class="kpi-label">TIER-1 STATS</div>
        <div class="kpi-value">{{ overview?.tier1_available ? 'ON' : 'OFF' }}</div>
        <div class="kpi-sub">官方统计披露</div>
      </div>
      <div class="kpi-card red">
        <div class="kpi-label">TIER-2 BOL</div>
        <div class="kpi-value">{{ overview?.tier2_available ? 'ON' : 'OFF' }}</div>
        <div class="kpi-sub">提单采购商</div>
      </div>
    </div>

    <!-- Search + trend -->
    <div class="panel-row">
      <div class="panel search-panel">
        <div class="panel-header"><span class="panel-title">检索 / QUERY</span></div>
        <div class="search-grid">
          <label>HS 编码<input v-model="filters.hsCode" placeholder="如 8517" /></label>
          <label>报告国<input v-model="filters.reporter" placeholder="如 United States" /></label>
          <label>伙伴国<input v-model="filters.partner" placeholder="如 China" /></label>
          <label>港口<input v-model="filters.port" placeholder="如 Los Angeles" /></label>
          <label>数量<input v-model.number="filters.limit" type="number" min="1" max="500" /></label>
        </div>
        <button class="primary-btn" :disabled="loading" @click="search">
          {{ loading ? '查询中…' : '查询海关数据' }}
        </button>
        <div class="hint">输入 HS 编码可同时查看贸易额趋势图。</div>
      </div>
      <div class="panel chart-panel">
        <div class="panel-header"><span class="panel-title">贸易额趋势 / TRADE VALUE</span><span class="panel-badge">BY PERIOD</span></div>
        <div ref="trendChartRef" class="chart-canvas" />
      </div>
    </div>

    <!-- Trade records table -->
    <div class="panel">
      <div class="panel-header">
        <span class="panel-title">进口品类 / TRADE RECORDS</span>
        <span class="panel-badge">{{ tradeRecords.length }} ROWS</span>
      </div>
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>HS</th><th>描述</th><th>报告国→伙伴国</th><th>流向</th>
              <th class="num">贸易额</th><th>年份</th><th>港口</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in tradeRecords" :key="r.id">
              <td class="mono">{{ r.hs_code }}</td>
              <td class="desc">{{ r.hs_description || '—' }}</td>
              <td>{{ r.reporter_country || '—' }} → {{ r.partner_country || '—' }}</td>
              <td><span class="tag" :class="r.trade_flow === 'import' ? 'imp' : 'exp'">{{ r.trade_flow === 'import' ? '进口' : '出口' }}</span></td>
              <td class="num">{{ fmtUsd(r.value_usd) }}</td>
              <td>{{ r.year || '—' }}</td>
              <td>{{ r.port || '—' }}</td>
            </tr>
            <tr v-if="!tradeRecords.length"><td colspan="7" class="empty">暂无数据 — 请先通过下方「采集海关数据」入库</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Buyers -->
    <div class="panel">
      <div class="panel-header">
        <span class="panel-title">采购商实体 / BUYER ENTITIES</span>
        <span class="panel-badge">{{ buyers.length }} ROWS</span>
      </div>
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr><th>采购商</th><th class="num">进口次数</th><th>热门 HS</th><th>热门港口</th><th class="num">估算体量</th></tr>
          </thead>
          <tbody>
            <tr v-for="b in buyers" :key="b.id">
              <td class="desc">{{ b.raw_name }}</td>
              <td class="num">{{ b.import_count }}</td>
              <td><span v-for="h in b.top_hs_codes" :key="h" class="chip">{{ h }}</span></td>
              <td><span v-for="p in b.top_ports" :key="p" class="chip alt">{{ p }}</span></td>
              <td class="num">{{ fmtUsd(b.total_value_usd) }}</td>
            </tr>
            <tr v-if="!buyers.length"><td colspan="5" class="empty">暂无采购商实体（Tier-2 提单数据未入库）</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Ingest -->
    <div class="panel">
      <div class="panel-header"><span class="panel-title">采集海关数据 / INGEST</span></div>
      <div class="search-grid">
        <label>数据源
          <select v-model="ingestForm.provider">
            <option value="un_comtrade">UN Comtrade (Tier-1 统计)</option>
            <option value="importyeti">ImportYeti (Tier-2 提单)</option>
            <option value="zauba">Zauba (Tier-2 提单)</option>
          </select>
        </label>
        <label>API URL<input v-model="ingestForm.url" placeholder="留空=使用默认端点" /></label>
        <label>报告国<input v-model="ingestForm.reporter" placeholder="842=US" /></label>
        <label>年份<input v-model="ingestForm.year" placeholder="2023" /></label>
        <label>HS 编码<input v-model="ingestForm.hs_code" placeholder="ALL" /></label>
        <label>数量<input v-model.number="ingestForm.max_items" type="number" min="1" max="500" /></label>
      </div>
      <button class="primary-btn" :disabled="ingesting" @click="ingest">
        {{ ingesting ? '采集中…' : '采集并入库' }}
      </button>
      <div v-if="ingestMsg" class="ingest-msg">{{ ingestMsg }}</div>
      <div class="hint">合规红线：仅存储聚合后的采购商实体（BuyerEntity），绝不回传原始提单行；对外营销须经制裁筛查与企业渠道校验。</div>
    </div>
  </div>
</template>

<style scoped>
.customs { display: flex; flex-direction: column; gap: 20px; }
.error-banner { background: rgba(239,68,68,0.1); border: 1px solid var(--accent-red); border-radius: 8px; padding: 16px 20px; display: flex; justify-content: space-between; align-items: center; color: var(--accent-red); font-size: 14px; }
.error-banner button { background: var(--accent-red); color: #fff; border: none; border-radius: 6px; padding: 4px 14px; cursor: pointer; }
.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.kpi-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; position: relative; overflow: hidden; }
.kpi-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; }
.kpi-card.purple::before { background: var(--gradient-purple); }
.kpi-card.cyan::before { background: var(--gradient-cyan); }
.kpi-card.green::before { background: var(--gradient-green); }
.kpi-card.red::before { background: var(--gradient-red); }
.kpi-label { font-size: 11px; letter-spacing: 1.5px; color: var(--text-muted); font-weight: 600; }
.kpi-value { font-size: 34px; font-weight: 800; margin-top: 8px; color: var(--text-primary); font-variant-numeric: tabular-nums; }
.kpi-card.purple .kpi-value { color: var(--accent-purple); }
.kpi-card.cyan .kpi-value { color: var(--accent); text-shadow: 0 0 12px var(--accent-glow); }
.kpi-card.green .kpi-value { color: var(--accent-green); }
.kpi-card.red .kpi-value { color: var(--accent-red); }
.kpi-sub { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
.panel { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
.panel-row { display: grid; grid-template-columns: 1fr 1.3fr; gap: 16px; }
.panel-header { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
.panel-title { font-size: 13px; font-weight: 600; color: var(--text-secondary); letter-spacing: 1px; }
.panel-badge { font-size: 10px; padding: 2px 8px; border-radius: 20px; background: var(--bg-secondary); color: var(--text-muted); letter-spacing: 1px; }
.chart-canvas { width: 100%; height: 300px; }
.search-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 14px; }
.search-grid label { display: flex; flex-direction: column; gap: 6px; font-size: 12px; color: var(--text-muted); }
.search-grid input, .search-grid select { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px; padding: 9px 12px; color: var(--text-primary); font-size: 13px; outline: none; }
.search-grid input:focus, .search-grid select:focus { border-color: var(--accent-purple); }
.primary-btn { background: linear-gradient(135deg, var(--accent-purple), #7c3aed); color: #fff; border: none; border-radius: 8px; padding: 10px 20px; font-size: 13px; font-weight: 600; cursor: pointer; letter-spacing: 1px; }
.primary-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.hint { font-size: 11px; color: var(--text-muted); margin-top: 10px; line-height: 1.6; }
.ingest-msg { font-size: 13px; color: var(--accent-green); margin-top: 10px; }
.table-wrap { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th { text-align: left; color: var(--text-muted); font-weight: 600; padding: 10px 12px; border-bottom: 1px solid var(--border); white-space: nowrap; }
.data-table td { padding: 10px 12px; border-bottom: 1px solid var(--border); color: var(--text-secondary); }
.data-table tr:hover td { background: rgba(168,85,247,0.05); }
.data-table .num { text-align: right; font-variant-numeric: tabular-nums; }
.data-table .mono { font-family: 'SF Mono', monospace; color: var(--accent-purple); }
.data-table .desc { max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty { text-align: center; color: var(--text-muted); padding: 24px; }
.tag { font-size: 11px; padding: 2px 8px; border-radius: 4px; }
.tag.imp { background: rgba(0,212,255,0.12); color: var(--accent); }
.tag.exp { background: rgba(34,197,94,0.12); color: var(--accent-green); }
.chip { display: inline-block; font-size: 11px; padding: 2px 6px; border-radius: 4px; background: rgba(168,85,247,0.12); color: var(--accent-purple); margin-right: 4px; }
.chip.alt { background: rgba(0,212,255,0.1); color: var(--accent); }
@media (max-width: 1024px) { .kpi-row { grid-template-columns: repeat(2, 1fr); } .panel-row { grid-template-columns: 1fr; } .search-grid { grid-template-columns: 1fr; } }
</style>
