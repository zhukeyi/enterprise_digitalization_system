<script setup lang="ts">
/**
 * PronounHint — Pronoun resolution hint (M3-T9).
 *
 * Shows the user which entity is currently "selected" (last added)
 * so that pronouns like "它" or "这个" in the analysis query can be
 * resolved correctly. The backend handles actual pronoun replacement;
 * this component provides visual context.
 */
import { computed } from 'vue'
import { useAnalysisStore } from '../stores/analysis'

const props = defineProps<{
  /** The most recently added entity name */
  entityName: string
}>()

const analysisStore = useAnalysisStore()

const hint = computed(() => {
  if (!props.entityName) return ''
  const count = analysisStore.entityCount
  if (count === 1) {
    return `已选中 "${props.entityName}"，分析中 "它" 指代该实体`
  }
  return `最近选中 "${props.entityName}"，分析中 "它" 指代该实体`
})

const visible = computed(() => props.entityName.length > 0)
</script>

<template>
  <Transition name="hint-fade">
    <div v-if="visible" class="pronoun-hint">
      <span class="hint-icon">💡</span>
      <span class="hint-text">{{ hint }}</span>
    </div>
  </Transition>
</template>

<style scoped>
.pronoun-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: #fff8e1;
  border: 1px solid #ffe082;
  border-radius: 6px;
  font-size: 12px;
  color: #795548;
}

.hint-icon {
  font-size: 13px;
  flex-shrink: 0;
}

.hint-text {
  line-height: 1.4;
}

.hint-fade-enter-active,
.hint-fade-leave-active {
  transition: all 0.3s ease;
}

.hint-fade-enter-from,
.hint-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
