<script setup lang="ts">
/**
 * EntityToast — Ephemeral toast notifications for entity actions (M3-T8).
 *
 * Displays toast messages from the analysis store (add/remove/clear
 * entity actions, warnings, errors). Auto-dismisses based on the
 * duration set in the store.
 */
import { useAnalysisStore } from '../stores/analysis'

const analysisStore = useAnalysisStore()

function iconFor(type: string): string {
  switch (type) {
    case 'success':
      return '✓'
    case 'warning':
      return '⚠'
    case 'error':
      return '✕'
    default:
      return 'ℹ'
  }
}
</script>

<template>
  <TransitionGroup name="toast" tag="div" class="entity-toast-container">
    <div
      v-for="toast in analysisStore.toastMessages"
      :key="toast.id"
      class="entity-toast"
      :class="toast.type"
      @click="analysisStore.removeToast(toast.id)"
    >
      <span class="toast-icon">{{ iconFor(toast.type) }}</span>
      <span class="toast-text">{{ toast.text }}</span>
    </div>
  </TransitionGroup>
</template>

<style scoped>
.entity-toast-container {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10000;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
}

.entity-toast {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-radius: 8px;
  font-size: 13px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  cursor: pointer;
  pointer-events: auto;
  max-width: 360px;
}

.entity-toast.info {
  background: #e3f2fd;
  color: #1565c0;
  border: 1px solid #90caf9;
}

.entity-toast.success {
  background: #e8f5e9;
  color: #2e7d32;
  border: 1px solid #a5d6a7;
}

.entity-toast.warning {
  background: #fff3e0;
  color: #e65100;
  border: 1px solid #ffcc80;
}

.entity-toast.error {
  background: #ffebee;
  color: #c62828;
  border: 1px solid #ef9a9a;
}

.toast-icon {
  font-weight: bold;
  font-size: 14px;
  flex-shrink: 0;
}

.toast-text {
  line-height: 1.4;
}

/* TransitionGroup animations */
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}

.toast-enter-from {
  opacity: 0;
  transform: translateY(20px);
}

.toast-leave-to {
  opacity: 0;
  transform: translateX(100px);
}

.toast-move {
  transition: transform 0.3s ease;
}
</style>
