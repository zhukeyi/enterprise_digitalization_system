<script setup lang="ts">
import { ref, watch } from 'vue'
import { useAnalysisStore, type MarkedEntity } from '../stores/analysis'
import { flyTo, fitAllMarkers, createMarker } from '../composables/useMap'

const props = defineProps<{ map: any; highlightedIds?: string[] }>()
const analysisStore = useAnalysisStore()
const highlightMarkers = ref<any[]>([])

function fly(entity: MarkedEntity) {
  if (!props.map || entity.lng == null || entity.lat == null) return
  flyTo(props.map, entity.lng, entity.lat)
}

function fitAll() {
  if (!props.map) return
  const positions = analysisStore.markedEntities
    .filter(e => e.lng != null && e.lat != null)
    .map(e => [e.lng!, e.lat!] as [number, number])
  fitAllMarkers(props.map, positions)
}

function updateHighlights() {
  if (!props.map) return
  for (const m of highlightMarkers.value) m.remove()
  highlightMarkers.value = []
  for (const id of (props.highlightedIds || [])) {
    const e = analysisStore.markedEntities.find(x => x.id === id)
    if (!e || e.lng == null || e.lat == null) continue
    const el = document.createElement('div'); el.innerHTML = '●'
    el.style.cssText = 'color:#ff5722;font-size:22px;text-shadow:0 0 8px rgba(255,87,34,0.6);animation:highlight-pulse 1.5s ease-in-out infinite'
    const m = createMarker(props.map, e.lng, e.lat, { content: el })
    highlightMarkers.value.push(m)
  }
}

watch(() => props.highlightedIds, updateHighlights, { deep: true })
defineExpose({ flyTo: fly, fitAllEntities: fitAll, updateHighlights })
</script>
<template></template>
<style>@keyframes highlight-pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.6;transform:scale(1.4)} }</style>