<script setup lang="ts">
/**
 * MapHighlight — Map flyTo + entity highlight (M3-T12).
 * 使用高德地图 AMap API。
 */
import { ref, watch } from 'vue'
import { useAnalysisStore, type MarkedEntity } from '../stores/analysis'

const props = defineProps<{
  map: AMap.Map | null
  highlightedIds?: string[]
}>()

const analysisStore = useAnalysisStore()
const highlightMarkers = ref<AMap.Marker[]>([])

function flyTo(entity: MarkedEntity) {
  if (!props.map) return
  if (entity.lng == null || entity.lat == null) return
  props.map.setZoomAndCenter(12, [entity.lng, entity.lat])
}

function fitAllEntities() {
  if (!props.map) return
  const entities = analysisStore.markedEntities.filter(
    (e) => e.lng != null && e.lat != null,
  )
  if (entities.length === 0) return
  props.map.setFitView(
    entities.map((e) => new AMap.Marker({ position: [e.lng!, e.lat!] })),
    false,
    [80, 80, 80, 80],
  )
}

function updateHighlights() {
  if (!props.map) return
  for (const m of highlightMarkers.value) m.remove()
  highlightMarkers.value = []

  const ids = props.highlightedIds || []
  for (const id of ids) {
    const entity = analysisStore.markedEntities.find((e) => e.id === id)
    if (!entity || entity.lng == null || entity.lat == null) continue

    const el = document.createElement('div')
    el.className = 'highlight-marker'
    el.innerHTML = '●'
    el.style.cssText = `
      color: #ff5722; font-size: 22px;
      text-shadow: 0 0 8px rgba(255,87,34,0.6);
      animation: highlight-pulse 1.5s ease-in-out infinite;
    `
    const marker = new AMap.Marker({
      position: [entity.lng, entity.lat],
      content: el,
      offset: new AMap.Pixel(-11, -11),
    })
    props.map.add(marker)
    highlightMarkers.value.push(marker)
  }
}

watch(
  () => props.highlightedIds,
  () => updateHighlights(),
  { deep: true },
)

defineExpose({ flyTo, fitAllEntities, updateHighlights })
</script>

<template>
  <!-- Invisible — exposes map interaction methods -->
</template>

<style>
@keyframes highlight-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(1.4); }
}
</style>