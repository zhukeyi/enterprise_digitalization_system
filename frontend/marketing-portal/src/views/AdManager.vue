<script setup lang="ts">
import { ref, onMounted } from 'vue'
import * as echarts from 'echarts'
import {
  getBrands, generateAds, abTest, allocateBudget,
  type Brand, type AdVariant, type ABTestResult, type BudgetAllocation,
} from '../api/client'

const brands = ref<Brand[]>([])
const brand = ref('')
const area = ref('企业AI平台')
const nVariants = ref(5)
const variants = ref<AdVariant[]>([])
const genLoading = ref(false)

// A/B test
const impA = ref(10000); const clkA = ref(300)
const impB = ref(10000); const clkB = ref(420)
const abResult = ref<ABTestResult | null>(null)
const abLoading = ref(false)

// Budget
const totalBudget = ref(100000)
const allocation = ref<BudgetAllocation | null>(null)
const budLoading = ref(false)
const budChart = ref<HTMLElement | null>(null)
let budInst: echarts.ECharts | null = null

const fmt = (n: number, d = 1) => n.toLocaleString('zh-CN', { maximumFractionDigits: d })
const pct = (n: number) => (n * 100).toFixed(2) + '%'

async function runGen() {
  genLoading.value = true
  try {
    const r = await generateAds({ brand: brand.value, topic: area.value, area: area.value, n_variants: nVariants.value })
    variants.value = r.variants
  } finally {
    genLoading.value = false
  }
}

async function runAB() {
  abLoading.value = true
  try {
    abResult.value = await abTest({
      variant_a: 'A', variant_b: 'B',
      impressions_a: impA.value, clicks_a: clkA.value,
      impressions_b: impB.value, clicks_b: clkB.value,
    })
  } finally {
    abLoading.value = false
  }
}

async function runBudget() {
  if (!brand.value) return
  budLoading.value = true
  try {
    allocation.value = await allocateBudget({ brand_id: brand.value, total_budget: totalBudget.value })
    renderBudgetChart()
  } finally {
    budLoading.value = false
  }
}

function renderBudgetChart() {
  if (!budChart.value || !allocation.value) return
  budInst = echarts.init(budChart.value, 'dark')
  const allocs = allocation.value.allocations
  budInst.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', formatter: (p: any) => `${p[0].name}<br/>分配 ¥${fmt(p[0].value)}<br/>ROAS ${p[0].data.roas}×` },
    grid: { left: 80, right: 24, top: 16, bottom: 24 },
    xAxis: { type: 'value', axisLabel: { color: '#b9a8e8', formatter: (v: number) => '¥' + (v / 1000) + 'k' } },
    yAxis: { type: 'category', data: allocs.map((a) => a.platform), axisLabel: { color: '#b9a8e8' } },
    series: [{
      type: 'bar',
      data: allocs.map((a) => ({ value: a.allocated_budget, roas: a.projected_roas })),
      itemStyle: {
        borderRadius: [0, 6, 6, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
          { offset: 0, color: '#fb923c' }, { offset: 1, color: '#a855f7' },
        ]),
      },
      label: { show: true, position: 'right', color: '#f1ecff', formatter: (p: any) => '¥' + fmt(p.value, 0) },
    }],
  })
}

onMounted(async () => {
  brands.value = await getBrands()
  if (brands.value.length) brand.value = brands.value[0].name
})
</script>

<template>
  <div class="fade-in">
    <!-- Variant generator -->
    <div class="panel">
      <div class="panel-title"><span class="bar" /> 广告多变体生成（质量评分 + 预测 CTR）</div>
      <div class="grid-3">
        <div class="field"><label>品牌</label>
          <select v-model="brand" class="select">
            <option v-for="b in brands" :key="b.brand_id" :value="b.name">{{ b.name }}</option>
          </select>
        </div>
        <div class="field"><label>卖点 / 领域</label><input v-model="area" class="input" /></div>
        <div class="field"><label>变体数量</label><input v-model.number="nVariants" type="number" min="2" max="8" class="input" /></div>
      </div>
      <button class="btn" :disabled="genLoading" @click="runGen">{{ genLoading ? '生成中…' : '生成广告变体' }}</button>

      <div v-if="variants.length" style="margin-top:16px">
        <div v-for="v in variants" :key="v.variant_id" class="variant-card">
          <div class="variant-head">
            <span class="variant-headline">{{ v.headline }}</span>
            <span class="tag tag-violet">{{ v.angle }}</span>
            <span class="tag tag-orange">{{ v.variant_id }}</span>
          </div>
          <div class="variant-body">{{ v.body }}</div>
          <div class="variant-foot">
            <strong>CTA：</strong>{{ v.cta }}
            <span class="tag tag-green" style="margin-left:8px">质量 {{ v.quality_score }}</span>
            <span class="tag tag-cyan" style="margin-left:8px">预测 CTR {{ pct(v.predicted_ctr) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- A/B test -->
    <div class="grid-2">
      <div class="panel">
        <div class="panel-title"><span class="bar" /> A/B 测试显著性检验</div>
        <div class="grid-2">
          <div class="field"><label>变体 A 曝光</label><input v-model.number="impA" type="number" class="input" /></div>
          <div class="field"><label>变体 A 点击</label><input v-model.number="clkA" type="number" class="input" /></div>
          <div class="field"><label>变体 B 曝光</label><input v-model.number="impB" type="number" class="input" /></div>
          <div class="field"><label>变体 B 点击</label><input v-model.number="clkB" type="number" class="input" /></div>
        </div>
        <button class="btn" :disabled="abLoading" @click="runAB">{{ abLoading ? '检验中…' : '运行检验' }}</button>

        <div v-if="abResult" class="metric-row">
          <div class="metric"><div class="metric-label">CTR A</div><div class="metric-value">{{ pct(abResult.ctr_a) }}</div></div>
          <div class="metric"><div class="metric-label">CTR B</div><div class="metric-value">{{ pct(abResult.ctr_b) }}</div></div>
          <div class="metric"><div class="metric-label">提升</div><div class="metric-value" :class="abResult.lift_pct >= 0 ? 'kpi-up' : 'kpi-down'">{{ abResult.lift_pct >= 0 ? '+' : '' }}{{ abResult.lift_pct }}%</div></div>
          <div class="metric"><div class="metric-label">置信度</div><div class="metric-value">{{ abResult.confidence }}%</div></div>
          <div class="metric"><div class="metric-label">胜者</div><div class="metric-value" style="color:var(--up)">{{ abResult.winner ?? '无显著差异' }}</div></div>
        </div>
      </div>

      <!-- Budget allocation -->
      <div class="panel">
        <div class="panel-title"><span class="bar" /> 跨平台预算分配（按 ROAS 加权）</div>
        <div class="field"><label>总预算（¥）</label><input v-model.number="totalBudget" type="number" class="input" /></div>
        <button class="btn" :disabled="budLoading" @click="runBudget">{{ budLoading ? '分配中…' : '智能分配' }}</button>
        <div ref="budChart" class="chart-sm" style="margin-top:14px" />
        <div v-if="allocation" class="metric-row">
          <div class="metric"><div class="metric-label">综合 ROAS</div><div class="metric-value" style="color:var(--accent-3)">{{ allocation.blended_roas }}×</div></div>
          <div class="metric"><div class="metric-label">均分 ROAS</div><div class="metric-value">{{ allocation.even_split_roas }}×</div></div>
          <div class="metric"><div class="metric-label">提升</div><div class="metric-value kpi-up">+{{ allocation.uplift_pct }}%</div></div>
          <div class="metric"><div class="metric-label">预计营收</div><div class="metric-value">¥{{ fmt(allocation.projected_revenue, 0) }}</div></div>
        </div>
      </div>
    </div>
  </div>
</template>
