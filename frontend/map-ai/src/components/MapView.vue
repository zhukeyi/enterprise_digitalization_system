<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import {
  getProvider, getApiKey,
  createMap, addMapControls, switchToSatellite, switchToNormal, flyTo,
  destroyMap, createMarker, loadMapSDK,
} from '../composables/useMap'

const provider = getProvider()
const label = provider === 'amap' ? '高德' : '百度'

const mapContainer = ref<HTMLDivElement>()
let map: any = null

const layerType = ref<'normal' | 'satellite'>('normal')
const layers = [
  { id: 'normal', name: '标准' },
  { id: 'satellite', name: '卫星' },
]
const mapError = ref<string>('')

function switchLayer(type: 'normal' | 'satellite') {
  layerType.value = type
  if (!map) return
  type === 'satellite' ? switchToSatellite(map) : switchToNormal(map)
}

onMounted(async () => {
  if (!mapContainer.value) return
  const key = getApiKey()
  if (!key || key.includes('your_')) {
    mapError.value = `${label}地图 Key 未配置。请在 .env 中设置 VITE_${provider === 'amap' ? 'AMAP_KEY' : 'BAIDU_AK'}`
    return
  }
  try {
    await loadMapSDK()
    map = await createMap(mapContainer.value)
    addMapControls(map)
    createMarker(map, 116.397, 39.908, { title: '北京 — FDE HQ' })
  } catch (e: any) {
    mapError.value = `${label}地图加载失败: ${e.message}`
  }
})

onUnmounted(() => { destroyMap(map); map = null })

defineExpose({ map, flyTo: (lng: number, lat: number) => flyTo(map, lng, lat) })
</script>

<template>
  <section class="map-area">
    <div class="map-overlay">
      <button v-for="l in layers" :key="l.id" @click="switchLayer(l.id as 'normal'|'satellite')"
        :style="layerType === l.id ? { background:'var(--fde-primary)', color:'white' } : {}">{{ l.name }}</button>
    </div>
    <div v-if="mapError" class="map-error">⚠️ {{ mapError }}</div>
    <div ref="mapContainer" class="map-container" />
  </section>
</template>