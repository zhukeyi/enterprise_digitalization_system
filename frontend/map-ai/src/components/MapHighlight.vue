<script setup lang="ts">
/**
 * MapHighlight — Map flyTo + entity highlight (M3-T12).
 *
 * Handles interaction between chart/data views and the map:
 * - flyTo: animated camera movement to an entity location
 * - highlight: adds/removes glowing markers for highlighted entities
 * - fitBounds: zoom to fit all marked entities in view
 */
import { ref, watch } from 'vue'
import type mapboxgl from 'mapbox-gl'
import { useAnalysisStore, type MarkedEntity } from '../stores/analysis'

const props = defineProps<{
  map: mapboxgl.Map | null
  /** Currently highlighted entity IDs (from chart hover) */
  highlightedIds?: string[]
}>()

const analysisStore = useAnalysisStore()
const highlightMarkers = ref<mapboxgl.Marker[]>([])

/** Fly the map camera to an entity location */
function flyTo(entity: MarkedEntity) {
  if (!props.map) return
  if (entity.lng == null || entity.lat == null) return

  props.map.flyTo({
    center: [entity.lng, entity.lat],
    zoom: 10,
    essential: true,
    duration: 1200,
  })
}

/** Zoom map to fit all marked entities in view */
function fitAllEntities() {
  if (!props.map) return
  const entities = analysisStore.markedEntities.filter(
    (e) => e.lng != null && e.lat != null,
  )
  if (entities.length === 0) return

  const bounds = new (window as any).mapboxgl.LngLatBounds()
  for (const e of entities) {
    bounds.extend([e.lng!, e.lat!])
  }

  props.map.fitBounds(bounds, {
    padding: 80,
    maxZoom: 12,
    duration: 1500,
  })
}

/** Add/update highlight markers on the map */
function updateHighlights() {
  if (!props.map) return

  // Remove old highlight markers
  for (const marker of highlightMarkers.value) {
    marker.remove()
  }
  highlightMarkers.value = []

  // Add new ones for highlighted IDs
  const ids = props.highlightedIds || []
  for (const id of ids) {
    const entity = analysisStore.markedEntities.find((e) => e.id === id)
    if (!entity || entity.lng == null || entity.lat == null) continue

    const el = document.createElement('div')
    el.className = 'highlight-marker'
    el.innerHTML = '●'
    el.style.cssText = `
      color: #ff5722;
      font-size: 22px;
      text-shadow: 0 0 8px rgba(255, 87, 34, 0.6);
      animation: highlight-pulse 1.5s ease-in-out infinite;
    `

    const marker = new (window as any).mapboxgl.Marker({ element: el })
      .setLngLat([entity.lng, entity.lat])
      .addTo(props.map)
    highlightMarkers.value.push(marker)
  }
}

// Watch for highlightedIds changes
watch(
  () => props.highlightedIds,
  () => updateHighlights(),
  { deep: true },
)

defineExpose({ flyTo, fitAllEntities, updateHighlights })
</script>

<template>
  <!-- Invisible component — exposes map interaction methods -->
</template>

<style>
@keyframes highlight-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(1.4); }
}
</style>