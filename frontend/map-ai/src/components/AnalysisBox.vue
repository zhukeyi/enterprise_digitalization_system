<script setup lang="ts">
/**
 * AnalysisBox — Floating analysis collection box (M3-T9).
 *
 * Global floating panel that displays all marked entities as draggable cards.
 * Supports:
 * - Minimize/expand toggle
 * - Drag-and-drop reordering of entity cards
 * - Clear all button
 * - Submit analysis button (disabled if < 2 entities)
 * - Real-time entity count and validation feedback
 */
import { ref } from 'vue'
import { useAnalysisStore } from '../stores/analysis'
import EntityCard from './EntityCard.vue'
import VoiceTextInput from './VoiceTextInput.vue'
import PronounHint from './PronounHint.vue'

const emit = defineEmits<{
  'fly-to': [lng: number, lat: number]
}>()

const analysisStore = useAnalysisStore()
const isMinimized = ref(false)
const dragFromIndex = ref<number | null>(null)

function toggleMinimize() {
  isMinimized.value = !isMinimized.value
}

function handleDragStart(index: number) {
  dragFromIndex.value = index
}

function handleDrop(toIndex: number) {
  if (dragFromIndex.value === null) return
  const from = dragFromIndex.value
  if (from === toIndex) return

  const entities = [...analysisStore.markedEntities]
  const [moved] = entities.splice(from, 1)
  entities.splice(toIndex, 0, moved)
  analysisStore.reorderEntities(entities)
  dragFromIndex.value = null
}

function clearAll() {
  analysisStore.clearAll()
}

async function submitAnalysis() {
  if (!analysisStore.canAnalyze) return
  analysisStore.setAnalyzing(true)
  try {
    const apiBase = import.meta.env.VITE_API_URL || '/fde-api'
    const resp = await fetch(`${apiBase}/map/analysis`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        entity_ids: analysisStore.entityIds,
        entities: analysisStore.markedEntities.map((e) => ({
          id: e.id,
          name: e.name,
          type: e.type,
          lng: e.lng,
          lat: e.lat,
          metadata: e.metadata,
        })),
        method: 'pearson',
        query: '',
      }),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const result = await resp.json()
    analysisStore.setAnalysisResult(result)
    analysisStore.addToast('分析完成 ✅', 'success')
  } catch (err: any) {
    analysisStore.setAnalysisResult({
      entityIds: analysisStore.entityIds,
      correlation_matrix: {},
      timestamp: Date.now(),
      status: 'error',
      message: err.message || '后端未响应',
    })
    analysisStore.addToast(`分析失败: ${err.message || '后端未响应'}`, 'error')
  } finally {
    analysisStore.setAnalyzing(false)
  }
}
</script>

<template>
  <div
    v-if="analysisStore.isAnalysisBoxOpen"
    class="analysis-box"
    :class="{ minimized: isMinimized }"
  >
    <!-- Header -->
    <div class="analysis-box-header" @click="toggleMinimize">
      <div class="header-left">
        <span class="header-icon">📊</span>
        <span class="header-title">分析收纳盒</span>
        <span class="entity-count-badge">
          {{ analysisStore.entityCount }}
        </span>
      </div>
      <div class="header-right">
        <button
          v-if="!isMinimized && analysisStore.entityCount > 0"
          class="header-btn clear-btn"
          title="清空"
          @click.stop="clearAll"
        >
          清空
        </button>
        <button class="header-btn minimize-btn" title="最小化">
          {{ isMinimized ? '▲' : '▼' }}
        </button>
      </div>
    </div>

    <!-- Body (hidden when minimized) -->
    <div v-if="!isMinimized" class="analysis-box-body">
      <!-- Entity list -->
      <div class="entity-list">
        <div
          v-if="analysisStore.markedEntities.length === 0"
          class="empty-state"
        >
          <span class="empty-icon">📌</span>
          <p>在地图或列表中点击 "+" 按钮<br />添加实体进行关联分析</p>
        </div>
        <EntityCard
          v-for="(entity, index) in analysisStore.markedEntities"
          :key="entity.id"
          :entity="entity"
          :index="index"
          @dragstart="handleDragStart"
          @drop="handleDrop"
          @click="entity.lng != null && entity.lat != null && emit('fly-to', entity.lng, entity.lat)"
        />
      </div>

      <!-- Pronoun hint -->
      <PronounHint
        v-if="analysisStore.entityCount > 0"
        :entity-name="analysisStore.markedEntities[analysisStore.entityCount - 1]?.name || ''"
      />

      <!-- Voice + text input -->
      <VoiceTextInput
        v-if="analysisStore.canAnalyze"
        placeholder="补充分析指令 (可选)..."
      />

      <!-- Submit -->
      <div class="submit-area">
        <div v-if="!analysisStore.canAnalyze" class="submit-hint">
          至少需要 2 个实体才能进行关联分析
        </div>
        <button
          class="submit-btn"
          :disabled="!analysisStore.canAnalyze || analysisStore.isAnalyzing"
          @click="submitAnalysis"
        >
          <span v-if="analysisStore.isAnalyzing" class="loading-spinner" />
          {{ analysisStore.isAnalyzing ? '分析中...' : '提交关联分析' }}
        </button>
      </div>
    </div>

      <!-- Analysis Result Panel -->
      <div v-if="analysisStore.lastAnalysisResult" class="analysis-result-panel">
        <div class="result-header">📋 分析结果</div>

        <!-- AI Interpretation -->
        <div v-if="analysisStore.lastAnalysisResult.interpretation" class="interpretation-box">
          {{ analysisStore.lastAnalysisResult.interpretation }}
        </div>

        <!-- Entities -->
        <div class="result-section">
          <div class="result-section-title">已分析实体 ({{ (analysisStore.lastAnalysisResult.entities as any[] || []).length }})</div>
          <div v-for="e in (analysisStore.lastAnalysisResult.entities as any[] || [])" :key="e.entity_id" class="result-entity-item">
            <span class="result-entity-name">{{ e.name }}</span>
            <span class="result-entity-type">{{ e.entity_type }}</span>
            <span v-if="e.location" class="result-entity-loc">📍 {{ (e.location.lng as number).toFixed(2) }}, {{ (e.location.lat as number).toFixed(2) }}</span>
          </div>
        </div>

        <!-- Correlation -->
        <div v-if="analysisStore.lastAnalysisResult.correlation" class="result-section">
          <div class="result-section-title">相关性分析</div>
          <div class="correlation-summary">
            {{ (analysisStore.lastAnalysisResult.correlation as any).summary }}
          </div>
          <div v-if="(analysisStore.lastAnalysisResult.correlation as any).pair_count > 0">
            <div v-for="(r, i) in (analysisStore.lastAnalysisResult.correlation as any).results" :key="i" class="correlation-pair">
              <span>{{ r.entity_a }} ↔ {{ r.entity_b }}</span>
              <span :style="{ color: r.coefficient > 0 ? '#e74c3c' : '#27ae60' }">
                {{ r.coefficient > 0 ? '+' : '' }}{{ (r.coefficient as number).toFixed(3) }}
              </span>
            </div>
          </div>
        </div>

        <button class="dismiss-btn" @click="analysisStore.lastAnalysisResult = null">关闭结果</button>
      </div>

  </div>
</template>

<style scoped>
.analysis-box {
  position: fixed;
  bottom: 20px;
  right: 400px;
  width: 340px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  z-index: 9000;
  overflow: hidden;
  transition: all 0.3s ease;
}

.analysis-box.minimized {
  width: 220px;
}

.analysis-box-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: linear-gradient(135deg, #1a73e8, #4285f4);
  color: white;
  cursor: pointer;
  user-select: none;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-icon {
  font-size: 16px;
}

.header-title {
  font-size: 14px;
  font-weight: 600;
}

.entity-count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  background: rgba(255, 255, 255, 0.25);
  border-radius: 10px;
  font-size: 12px;
  font-weight: bold;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 4px;
}

.header-btn {
  padding: 4px 8px;
  border: none;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.2);
  color: white;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.2s;
}

.header-btn:hover {
  background: rgba(255, 255, 255, 0.35);
}

.analysis-box-body {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 500px;
  overflow-y: auto;
}

.entity-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  text-align: center;
  color: #999;
  font-size: 13px;
}

.empty-icon {
  font-size: 32px;
  margin-bottom: 8px;
  opacity: 0.5;
}

.submit-area {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 8px;
  border-top: 1px solid #eee;
}

.submit-hint {
  font-size: 12px;
  color: #999;
  text-align: center;
}

.submit-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 16px;
  border: none;
  border-radius: 8px;
  background: #1a73e8;
  color: white;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.submit-btn:hover:not(:disabled) {
  background: #1557b0;
  transform: translateY(-1px);
}

.submit-btn:disabled {
  background: #e0e0e0;
  color: #999;
  cursor: not-allowed;
}

.loading-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.analysis-result-panel {
  border-top: 2px solid var(--fde-primary, #1a73e8);
  padding: 12px 16px;
  max-height: 280px;
  overflow-y: auto;
  background: #f8fafc;
}
.result-header {
  font-weight: 700;
  font-size: 14px;
  margin-bottom: 8px;
  color: #1a73e8;
}
.interpretation-box {
  background: white;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.6;
  color: #333;
  margin-bottom: 10px;
  border-left: 3px solid #1a73e8;
}
.result-section { margin-bottom: 10px; }
.result-section-title {
  font-size: 12px;
  font-weight: 600;
  color: #666;
  margin-bottom: 6px;
  text-transform: uppercase;
}
.result-entity-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  background: white;
  border-radius: 6px;
  margin-bottom: 4px;
  font-size: 12px;
}
.result-entity-name { font-weight: 600; }
.result-entity-type {
  background: #e8f0fe;
  color: #1a73e8;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
}
.result-entity-loc { color: #999; }
.correlation-summary {
  font-size: 13px;
  color: #666;
  margin-bottom: 6px;
}
.correlation-pair {
  display: flex;
  justify-content: space-between;
  padding: 4px 8px;
  background: white;
  border-radius: 6px;
  margin-bottom: 3px;
  font-size: 12px;
}
.dismiss-btn {
  width: 100%;
  margin-top: 8px;
  padding: 6px;
  background: #eee;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  color: #666;
}
.dismiss-btn:hover { background: #ddd; }
</style>
