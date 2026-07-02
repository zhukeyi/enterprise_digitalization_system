<script setup lang="ts">
/**
 * DrillDownPlus — "+" button in drill-down info box (M3-T8).
 *
 * Displays in drill-down data rows, allowing the user to add
 * the drilled-down entity (e.g., a specific province or city)
 * to the analysis store.
 */
import { useAnalysisStore } from '../stores/analysis'

const props = defineProps<{
  /** Entity ID from the drill-down row */
  id: string
  /** Display name from the drill-down row */
  name: string
  /** Dimension label (e.g., "region", "province", "city") */
  dimension: string
  /** Optional aggregated value for context */
  value?: number | string
}>()

const analysisStore = useAnalysisStore()

function handleClick() {
  analysisStore.addEntity({
    id: props.id,
    name: props.name,
    type: props.dimension,
    metadata: props.value !== undefined ? { value: props.value } : undefined,
  })
}
</script>

<template>
  <button
    class="drilldown-plus-btn"
    :class="{ 'already-marked': analysisStore.isMarked(id) }"
    :disabled="analysisStore.isMarked(id)"
    @click.stop="handleClick"
  >
    <span v-if="analysisStore.isMarked(id)">✓</span>
    <span v-else>+ 添加</span>
  </button>
</template>

<style scoped>
.drilldown-plus-btn {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 4px 10px;
  border: 1px solid #1a73e8;
  border-radius: 4px;
  background: transparent;
  color: #1a73e8;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.drilldown-plus-btn:hover:not(:disabled) {
  background: #1a73e8;
  color: white;
}

.drilldown-plus-btn:disabled {
  border-color: #4caf50;
  color: #4caf50;
  background: #e8f5e9;
  cursor: default;
}
</style>
