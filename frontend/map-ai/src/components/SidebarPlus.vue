<script setup lang="ts">
/**
 * SidebarPlus — "+" button in sidebar entries (M3-T8).
 *
 * Used in the sidebar list of entities/regions to add them to
 * the analysis store without opening the map marker popup.
 */
import { useAnalysisStore } from '../stores/analysis'

const props = defineProps<{
  /** Entity ID */
  id: string
  /** Entity display name */
  name: string
  /** Entity type (e.g., "region", "company", "facility") */
  type: string
  /** Optional coordinates */
  lng?: number
  lat?: number
}>()

const analysisStore = useAnalysisStore()

function handleClick() {
  analysisStore.addEntity({
    id: props.id,
    name: props.name,
    type: props.type,
    lng: props.lng,
    lat: props.lat,
  })
}
</script>

<template>
  <button
    class="sidebar-plus-btn"
    :class="{ 'already-marked': analysisStore.isMarked(id) }"
    :disabled="analysisStore.isMarked(id)"
    :title="analysisStore.isMarked(id) ? '已添加' : `添加 "${name}" 到分析`"
    @click.stop="handleClick"
  >
    <span v-if="analysisStore.isMarked(id)" class="check-icon">✓</span>
    <span v-else class="plus-icon">+</span>
  </button>
</template>

<style scoped>
.sidebar-plus-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid #1a73e8;
  border-radius: 6px;
  background: transparent;
  color: #1a73e8;
  font-size: 16px;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.sidebar-plus-btn:hover:not(:disabled) {
  background: #1a73e8;
  color: white;
}

.sidebar-plus-btn:disabled {
  border-color: #4caf50;
  color: #4caf50;
  cursor: default;
}

.already-marked {
  background: #e8f5e9;
}

.plus-icon,
.check-icon {
  line-height: 1;
  font-weight: bold;
}
</style>
