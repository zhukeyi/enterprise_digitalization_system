<script setup lang="ts">
/**
 * MapMarkerPlus — "+" button on map markers (M3-T8).
 *
 * When the user clicks a map marker, a popup appears with entity info
 * and a "+" button to add the entity to the analysis store.
 */
import { ref, watch } from 'vue'
import mapboxgl from 'mapbox-gl'
import { useAnalysisStore, type MarkedEntity } from '../stores/analysis'

const props = defineProps<{
  map: mapboxgl.Map | null
  /** Entity data to display when marker is clicked */
  entity: MarkedEntity
  /** Lng/Lat for the marker position */
  lng: number
  lat: number
}>()

const analysisStore = useAnalysisStore()
const popup = ref<mapboxgl.Popup | null>(null)

function createPopup(): mapboxgl.Popup {
  const el = document.createElement('div')
  el.className = 'map-marker-popup'
  el.innerHTML = `
    <div class="popup-entity-info">
      <strong>${props.entity.name}</strong>
      <span class="popup-entity-type">${props.entity.type}</span>
    </div>
    <button class="popup-plus-btn" data-entity-id="${props.entity.id}">
      + 添加到分析
    </button>
  `
  return new mapboxgl.Popup({ offset: 25 }).setDOMContent(el)
}

function setupPopupListener(p: mapboxgl.Popup) {
  p.on('open', () => {
    const btn = p.getElement()?.querySelector('.popup-plus-btn')
    if (btn) {
      btn.addEventListener('click', () => {
        handlePlusClick()
      })
    }
  })
}

function handlePlusClick() {
  analysisStore.addEntity({
    id: props.entity.id,
    name: props.entity.name,
    type: props.entity.type,
    lng: props.lng,
    lat: props.lat,
    metadata: props.entity.metadata,
  })
  popup.value?.remove()
}

watch(
  () => props.map,
  (newMap) => {
    if (!newMap) return
    const marker = new mapboxgl.Marker({ color: '#1a73e8' })
      .setLngLat([props.lng, props.lat])
      .addTo(newMap)
    popup.value = createPopup()
    setupPopupListener(popup.value)
    marker.setPopup(popup.value)
  },
  { immediate: true },
)
</script>

<template>
  <!-- This component is invisible; it attaches markers to the map -->
</template>

<style>
.map-marker-popup {
  padding: 8px 12px;
  min-width: 160px;
}

.popup-entity-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 8px;
}

.popup-entity-type {
  font-size: 12px;
  color: #666;
}

.popup-plus-btn {
  width: 100%;
  padding: 6px 12px;
  border: 1px solid #1a73e8;
  border-radius: 6px;
  background: #1a73e8;
  color: white;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.2s;
}

.popup-plus-btn:hover {
  background: #1557b0;
}

.popup-plus-btn.already-added {
  background: #e0e0e0;
  border-color: #ccc;
  color: #999;
  cursor: default;
}
</style>
