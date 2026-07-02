<script setup lang="ts">
/**
 * EntityCard — Draggable entity card in the analysis box (M3-T9).
 *
 * Displays a single marked entity with its name, type, and a remove button.
 * Supports drag-and-drop reordering via HTML5 drag events.
 */
import { useAnalysisStore, type MarkedEntity } from '../stores/analysis'

const props = defineProps<{
  entity: MarkedEntity
  index: number
}>()

const analysisStore = useAnalysisStore()

const emit = defineEmits<{
  dragstart: [index: number]
  dragover: [index: number]
  drop: [index: number]
}>()

function onDragStart(event: DragEvent) {
  event.dataTransfer?.setData('text/plain', String(props.index))
  emit('dragstart', props.index)
}

function onDragOver(event: DragEvent) {
  event.preventDefault()
  emit('dragover', props.index)
}

function onDrop(event: DragEvent) {
  event.preventDefault()
  emit('drop', props.index)
}

function removeEntity() {
  analysisStore.removeEntity(props.entity.id)
}
</script>

<template>
  <div
    class="entity-card"
    draggable="true"
    @dragstart="onDragStart"
    @dragover="onDragOver"
    @drop="onDrop"
  >
    <div class="entity-drag-handle">⠿</div>
    <div class="entity-info">
      <span class="entity-name">{{ entity.name }}</span>
      <span class="entity-type">{{ entity.type }}</span>
    </div>
    <button class="entity-remove" title="移除" @click.stop="removeEntity">
      ✕
    </button>
  </div>
</template>

<style scoped>
.entity-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: #f5f7fa;
  border: 1px solid #e0e4e8;
  border-radius: 8px;
  cursor: grab;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.entity-card:hover {
  border-color: #1a73e8;
  box-shadow: 0 2px 8px rgba(26, 115, 232, 0.1);
}

.entity-card:active {
  cursor: grabbing;
}

.entity-drag-handle {
  color: #b0b8c1;
  font-size: 16px;
  cursor: grab;
  flex-shrink: 0;
}

.entity-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.entity-name {
  font-size: 13px;
  font-weight: 500;
  color: #1a1a1a;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.entity-type {
  font-size: 11px;
  color: #888;
  text-transform: capitalize;
}

.entity-remove {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: #999;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.entity-remove:hover {
  background: #ffebee;
  color: #c62828;
}
</style>
