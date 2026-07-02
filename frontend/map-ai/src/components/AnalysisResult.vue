<script setup lang="ts">
/**
 * AnalysisResult — Full analysis results dashboard (M3-T12).
 *
 * Integrates all visualization components and AI interpretation
 * into a single scrollable dashboard view:
 * 1. AI interpretation header (text + key metrics)
 * 2. Correlation heatmap
 * 3. Time series comparison (if available)
 * 4. Scatter matrix (if available)
 * 5. Entity summary cards
 *
 * Uses tabs to switch between views on smaller screens.
 */
import { ref, computed } from 'vue'
import HeatmapChart from './HeatmapChart.vue'
import TimeSeriesChart from './TimeSeriesChart.vue'
import ScatterMatrix from './ScatterMatrix.vue'

interface CorrelationPair {
  pair: [string, string]
  coefficient: number
  p_value?: number
}

interface TimeSeriesData {
  name: string
  points: { timestamp: string; value: number }[]
  color?: string
}

interface ScatterPairData {
  xDim: string
  yDim: string
  points: { x: number; y: number; label?: string }[]
  r?: number
}

const props = defineProps<{
  /** AI-generated interpretation text */
  interpretation?: string
  /** Correlation pairs from the analysis */
  correlationPairs?: CorrelationPair[]
  /** Time series data (one per entity) */
  timeSeries?: TimeSeriesData[]
  /** Scatter matrix pair data */
  scatterPairs?: ScatterPairData[]
  /** Entity names for labeling */
  entityNames?: string[]
  /** Execution time in ms */
  executionTimeMs?: number
  /** Whether analysis is still loading */
  loading?: boolean
}>()

const activeTab = ref<'heatmap' | 'timeseries' | 'scatter'>('heatmap')

const heatmapData = computed(() => {
  return (props.correlationPairs || []).map((p) => ({
    pair: p.pair,
    coefficient: p.coefficient,
    pValue: p.p_value,
  }))
})

const tabOptions = computed(() => {
  const options = [
    { key: 'heatmap' as const, label: '相关性热力', count: props.correlationPairs?.length || 0 },
    { key: 'timeseries' as const, label: '时间序列', count: props.timeSeries?.length || 0 },
    { key: 'scatter' as const, label: '散点矩阵', count: props.scatterPairs?.length || 0 },
  ]
  return options.filter((o) => o.count > 0)
})

const topCorrelations = computed(() => {
  const pairs = [...(props.correlationPairs || [])]
  pairs.sort((a, b) => Math.abs(b.coefficient) - Math.abs(a.coefficient))
  return pairs.slice(0, 5)
})

const correlationStrength = computed(() => {
  const pairs = props.correlationPairs || []
  if (pairs.length === 0) return '无'
  const avgAbs = pairs.reduce((sum, p) => sum + Math.abs(p.coefficient), 0) / pairs.length
  if (avgAbs > 0.7) return '强相关'
  if (avgAbs > 0.4) return '中度相关'
  if (avgAbs > 0.2) return '弱相关'
  return '极弱相关'
})
</script>

<template>
  <div class="analysis-result" v-if="!loading">
    <!-- AI Interpretation Header -->
    <section class="result-interpretation" v-if="interpretation">
      <div class="interpretation-header">
        <span class="interpretation-icon">🤖</span>
        <span class="interpretation-label">AI 分析解读</span>
      </div>
      <p class="interpretation-text">{{ interpretation }}</p>

      <div class="key-metrics" v-if="correlationPairs && correlationPairs.length > 0">
        <div class="metric-card">
          <span class="metric-value">{{ correlationStrength }}</span>
          <span class="metric-label">相关性强度</span>
        </div>
        <div class="metric-card">
          <span class="metric-value">{{ entityNames?.length || 0 }}</span>
          <span class="metric-label">分析实体数</span>
        </div>
        <div class="metric-card">
          <span class="metric-value">{{ correlationPairs.length }}</span>
          <span class="metric-label">关联对数</span>
        </div>
        <div class="metric-card" v-if="executionTimeMs != null">
          <span class="metric-value">{{ (executionTimeMs / 1000).toFixed(2) }}s</span>
          <span class="metric-label">执行耗时</span>
        </div>
      </div>
    </section>

    <!-- Top Correlations -->
    <section class="top-correlations" v-if="topCorrelations.length > 0">
      <h3 class="section-title">关联排行</h3>
      <div class="correlation-list">
        <div
          v-for="(pair, idx) in topCorrelations"
          :key="idx"
          class="correlation-row"
        >
          <div class="corr-entities">
            <span class="corr-entity-a">{{ pair.pair[0] }}</span>
            <span class="corr-arrow">↔</span>
            <span class="corr-entity-b">{{ pair.pair[1] }}</span>
          </div>
          <div class="corr-bar-wrapper">
            <div class="corr-bar-track">
              <div
                class="corr-bar-fill"
                :style="{
                  width: `${Math.abs(pair.coefficient) * 100}%`,
                  background: pair.coefficient >= 0
                    ? `hsl(${(1 - Math.abs(pair.coefficient)) * 100 + 200}, 70%, 50%)`
                    : '#c62828',
                }"
              />
            </div>
            <span class="corr-value">{{ pair.coefficient.toFixed(4) }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Chart Tabs -->
    <section class="chart-tabs" v-if="tabOptions.length > 0">
      <div class="tab-header">
        <button
          v-for="tab in tabOptions"
          :key="tab.key"
          class="tab-btn"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="tab-content">
        <HeatmapChart
          v-if="activeTab === 'heatmap' && heatmapData.length > 0"
          :data="heatmapData"
          :entity-names="entityNames"
          title="实体相关性矩阵"
        />
        <TimeSeriesChart
          v-if="activeTab === 'timeseries' && timeSeries && timeSeries.length > 0"
          :series="timeSeries"
          title="时间序列对比"
        />
        <ScatterMatrix
          v-if="activeTab === 'scatter' && scatterPairs && scatterPairs.length > 0"
          :pairs="scatterPairs"
          title="散点矩阵分析"
        />
      </div>
    </section>

    <!-- Entity Summary -->
    <section class="entity-summary" v-if="entityNames && entityNames.length > 0">
      <h3 class="section-title">参与分析的实体</h3>
      <div class="entity-chips">
        <span
          v-for="name in entityNames"
          :key="name"
          class="entity-chip"
        >
          {{ name }}
        </span>
      </div>
    </section>
  </div>

  <!-- Loading State -->
  <div v-else class="analysis-loading">
    <div class="loading-spinner-lg" />
    <p class="loading-text">分析中...</p>
    <p class="loading-sub">正在计算实体关联性并生成解读</p>
  </div>
</template>

<style scoped>
.analysis-result {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 16px;
}

/* AI Interpretation */
.result-interpretation {
  background: linear-gradient(135deg, #f0f4ff, #e8f5e9);
  border: 1px solid #c8e6c9;
  border-radius: 10px;
  padding: 16px;
}

.interpretation-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.interpretation-icon {
  font-size: 18px;
}

.interpretation-label {
  font-size: 13px;
  font-weight: 600;
  color: #1a73e8;
}

.interpretation-text {
  font-size: 13px;
  line-height: 1.6;
  color: #333;
  margin: 0 0 12px 0;
}

.key-metrics {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.metric-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px 16px;
  background: white;
  border-radius: 8px;
  min-width: 80px;
}

.metric-value {
  font-size: 20px;
  font-weight: bold;
  color: #1a73e8;
}

.metric-label {
  font-size: 11px;
  color: #888;
  margin-top: 4px;
}

/* Sections */
.section-title {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 10px 0;
  color: #333;
}

/* Top Correlations */
.top-correlations {
  background: #fafafa;
  border: 1px solid #eee;
  border-radius: 8px;
  padding: 12px;
}

.correlation-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
}

.corr-entities {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.corr-entity-a,
.corr-entity-b {
  font-weight: 500;
}

.corr-arrow {
  color: #999;
}

.corr-bar-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

.corr-bar-track {
  flex: 1;
  height: 8px;
  background: #f0f0f0;
  border-radius: 4px;
  overflow: hidden;
}

.corr-bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.5s ease;
}

.corr-value {
  font-size: 12px;
  font-family: monospace;
  color: #555;
  min-width: 48px;
  text-align: right;
}

/* Chart Tabs */
.chart-tabs {
  background: #fafafa;
  border: 1px solid #eee;
  border-radius: 8px;
  overflow: hidden;
}

.tab-header {
  display: flex;
  gap: 0;
  border-bottom: 1px solid #eee;
}

.tab-btn {
  flex: 1;
  padding: 10px 16px;
  border: none;
  background: transparent;
  font-size: 13px;
  color: #888;
  cursor: pointer;
  transition: all 0.2s;
  border-bottom: 2px solid transparent;
}

.tab-btn:hover {
  color: #1a73e8;
}

.tab-btn.active {
  color: #1a73e8;
  border-bottom-color: #1a73e8;
  font-weight: 500;
}

.tab-content {
  padding: 12px;
}

/* Entity Summary */
.entity-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.entity-chip {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  background: #e8f0fe;
  border: 1px solid #c5d9f7;
  border-radius: 16px;
  font-size: 12px;
  color: #1a73e8;
  font-weight: 500;
}

/* Loading */
.analysis-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  gap: 12px;
}

.loading-spinner-lg {
  width: 40px;
  height: 40px;
  border: 3px solid #e0e0e0;
  border-top-color: #1a73e8;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-text {
  font-size: 15px;
  font-weight: 500;
  color: #333;
  margin: 0;
}

.loading-sub {
  font-size: 12px;
  color: #999;
  margin: 0;
}
</style>