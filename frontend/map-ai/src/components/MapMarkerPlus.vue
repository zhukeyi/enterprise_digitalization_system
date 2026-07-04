<script setup lang="ts">
/**
 * MapMarkerPlus — "+" 按钮标记组件 (M3-T8)。
 * 使用高德地图 AMap InfoWindow。
 */
import { ref, watch } from 'vue'
import { useAnalysisStore, type MarkedEntity } from '../stores/analysis'

const props = defineProps<{
  map: AMap.Map | null
  entity: MarkedEntity
  lng: number
  lat: number
}>()

const analysisStore = useAnalysisStore()
const infoWindow = ref<any>(null)

function createContent(): string {
  return `
    <div class="map-marker-popup">
      <div class="popup-entity-info">
        <strong>${props.entity.name}</strong>
        <span class="popup-entity-type">${props.entity.type}</span>
      </div>
      <button class="popup-plus-btn" data-entity-id="${props.entity.id}">
        + 添加到分析
      </button>
    </div>
  `
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
  if (infoWindow.value) {
    infoWindow.value.close()
  }
}

watch(
  () => props.map,
  (newMap) => {
    if (!newMap || !AMap) return

    const marker = new AMap.Marker({
      position: [props.lng, props.lat],
      title: props.entity.name,
    })
    newMap.add(marker)

    infoWindow.value = new AMap.InfoWindow({
      content: createContent(),
      offset: new AMap.Pixel(0, -30),
    })

    marker.on('click', () => {
      infoWindow.value.open(newMap, marker.getPosition())
      // Bind click after DOM is ready
      setTimeout(() => {
        const btn = document.querySelector('.popup-plus-btn')
        if (btn) btn.addEventListener('click', handlePlusClick)
      }, 100)
    })
  },
  { immediate: true },
)
</script>

<template>
  <!-- Invisible — attaches markers to the map -->
</template>

<style>
.map-marker-popup { padding: 8px 12px; min-width: 160px; }
.popup-entity-info { display: flex; flex-direction: column; gap: 2px; margin-bottom: 8px; }
.popup-entity-type { font-size: 12px; color: #666; }
.popup-plus-btn {
  width: 100%; padding: 6px 12px; border: 1px solid #1a73e8;
  border-radius: 6px; background: #1a73e8; color: white;
  font-size: 13px; cursor: pointer; transition: background 0.2s;
}
.popup-plus-btn:hover { background: #1557b0; }
.popup-plus-btn.already-added { background: #e0e0e0; border-color: #ccc; color: #999; cursor: default; }
</style>