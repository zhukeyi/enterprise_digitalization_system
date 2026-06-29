<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import mapboxgl from 'mapbox-gl'

// Mapbox token — set via env variable VITE_MAPBOX_TOKEN
mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN || 'pk.placeholder'

const mapContainer = ref<HTMLDivElement>()
let map: mapboxgl.Map | null = null

const mapStyle = ref('streets-v12')
const styles = [
  { id: 'streets-v12', name: '街道' },
  { id: 'satellite-v9', name: '卫星' },
  { id: 'dark-v11', name: '暗色' },
]

function switchStyle(styleId: string) {
  mapStyle.value = styleId
  if (map) {
    map.setStyle(`mapbox://styles/mapbox/${styleId}`)
  }
}

onMounted(() => {
  if (!mapContainer.value) return

  map = new mapboxgl.Map({
    container: mapContainer.value,
    style: `mapbox://styles/mapbox/${mapStyle.value}`,
    center: [116.397, 39.908], // Beijing
    zoom: 4,
    projection: 'mercator',
  })

  map.addControl(new mapboxgl.NavigationControl(), 'top-right')
  map.addControl(new mapboxgl.ScaleControl(), 'bottom-left')

  // Add a demo marker
  new mapboxgl.Marker({ color: '#1a73e8' })
    .setLngLat([116.397, 39.908])
    .setPopup(new mapboxgl.Popup().setText('北京 — FDE HQ'))
    .addTo(map)
})

onUnmounted(() => {
  map?.remove()
})
</script>

<template>
  <section class="map-area">
    <div class="map-overlay">
      <button v-for="s in styles" :key="s.id"
        @click="switchStyle(s.id)"
        :style="mapStyle === s.id ? { background: 'var(--fde-primary)', color: 'white' } : {}">
        {{ s.name }}
      </button>
    </div>
    <div ref="mapContainer" class="map-container" />
  </section>
</template>
