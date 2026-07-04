<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useAnalysisStore } from '../stores/analysis'
import { getProvider, getApiKey, loadMapSDK, createMap, addMapControls, switchToSatellite, switchToNormal, onMapClick, destroyMap } from '../composables/useMap'

const store = useAnalysisStore()
const provider = getProvider()
const label = provider === 'amap' ? '高德' : '百度'

const mapContainer = ref<HTMLDivElement>()
const mapError = ref('')
let map: any = null
let markers: any[] = []
let markerIdCounter = 0

const layerType = ref<'normal' | 'satellite'>('normal')
const layers = [{ id: 'normal', name: '标准' }, { id: 'satellite', name: '卫星' }]
const addingMode = ref(false)
const isDrawing = ref(false)
let drawingManager: any = null
let drawnPolys: any[] = []

function switchLayer(type: 'normal' | 'satellite') {
  layerType.value = type
  if (!map) return
  type === 'satellite' ? switchToSatellite(map) : switchToNormal(map)
}

/* ================================================================
 * 地图点击 → 添加标记
 * ================================================================ */

function handleMapClick(e: any) {
  if (!addingMode.value && !isDrawing.value) return
  if (!map) return

  let lng: number, lat: number
  if (provider === 'baidu') {
    lng = e.latlng.lng
    lat = e.latlng.lat
  } else {
    lng = e.lnglat.getLng()
    lat = e.lnglat.getLat()
  }

  if (!addingMode.value) return

  const id = `marker-${++markerIdCounter}`
  const name = prompt('输入标注名称:', `标记点 ${markerIdCounter}`)
  if (!name) return

  store.addEntity({ id, name, type: 'map-marker', lng, lat })
  addMarkerToMap(id, name, lng, lat)
}

function addMarkerToMap(id: string, name: string, lng: number, lat: number) {
  if (!map) return

  const marker = provider === 'baidu'
    ? createBaiduMarker(id, name, lng, lat)
    : createAmapMarker(id, name, lng, lat)

  markers.push({ id, marker, lng, lat })
}

function createBaiduMarker(id: string, name: string, lng: number, lat: number) {
  const B = (window as any).BMapGL
  const pt = new B.Point(lng, lat)
  const marker = new B.Marker(pt)
  marker.setTitle(name)
  map.addOverlay(marker)
  
  // Click → show info + delete button
  marker.addEventListener('click', () => {
    const html = `<div style="padding:6px 12px;font-size:13px">
      <strong>${name}</strong><br>
      <span style="color:#666;font-size:11px">${lng.toFixed(4)}, ${lat.toFixed(4)}</span><br>
      <button onclick="window.__fdeDelMarker('${id}')" style="margin-top:4px;font-size:11px;color:#e74c3c;border:none;background:none;cursor:pointer">删除</button>
    </div>`
    const iw = new B.InfoWindow(html, { width: 200 })
    map.openInfoWindow(iw, pt)
    ;(window as any).__fdeDelMarker = (mid: string) => {
      removeMarkerById(mid)
      store.removeEntity(mid)
      map.closeInfoWindow()
    }
  })
  return marker
}

function createAmapMarker(id: string, name: string, lng: number, lat: number) {
  const A = (window as any).AMap
  const marker = new A.Marker({ position: [lng, lat], title: name, draggable: true })
  map.add(marker)
  marker.on('click', () => {
    const html = `<div style="padding:6px 12px;font-size:13px">
      <strong>${name}</strong><br>
      <span style="color:#666;font-size:11px">${lng.toFixed(4)}, ${lat.toFixed(4)}</span></div>`
    const iw = new A.InfoWindow({ content: html, offset: new A.Pixel(0, -30) })
    iw.open(map, [lng, lat])
  })
  return marker
}

function removeMarkerById(id: string) {
  const idx = markers.findIndex(m => m.id === id)
  if (idx === -1) return
  const m = markers[idx]
  if (provider === 'baidu') map?.removeOverlay(m.marker)
  else map?.remove(m.marker)
  markers.splice(idx, 1)
}

/* ================================================================
 * 同步 store → map markers
 * ================================================================ */

watch(() => store.markedEntities.length, () => {
  // Clear existing markers and re-add from store
  for (const m of markers) {
    if (provider === 'baidu') map?.removeOverlay(m.marker)
    else map?.remove(m.marker)
  }
  markers = []
  for (const e of store.markedEntities) {
    if (e.lng != null && e.lat != null) addMarkerToMap(e.id, e.name, e.lng, e.lat)
  }
})

/* ================================================================
 * 初始化
 * ================================================================ */

onMounted(async () => {
  if (!mapContainer.value) return
  const key = getApiKey()
  if (!key || key.includes('your_')) {
    mapError.value = `${label}地图 Key 未配置`
    return
  }
  try {
    await loadMapSDK()
    map = await createMap(mapContainer.value)
    addMapControls(map)

    // 点击事件
    onMapClick(map, handleMapClick)

    // 加载已持久化的实体
    for (const e of store.markedEntities) {
      if (e.lng != null && e.lat != null) addMarkerToMap(e.id, e.name, e.lng, e.lat)
    }
  } catch (e: any) {
    mapError.value = `${label}地图加载失败: ${e.message}`
  }
})

onUnmounted(() => {
  if (map) destroyMap(map)
  map = null
})

// Expose map and helper functions
defineExpose({ map, flyTo: (lng: number, lat: number) => {
  if (!map) return
  if (provider === 'baidu') map.flyTo?.({ lng, lat }, 14) || map.centerAndZoom(new (window as any).BMapGL.Point(lng, lat), 14)
  else map.setZoomAndCenter(14, [lng, lat])
}})
</script>

<template>
  <section class="map-area">
    <div class="map-overlay">
      <button v-for="l in layers" :key="l.id" @click="switchLayer(l.id as any)"
        :style="layerType === l.id ? { background:'var(--fde-primary)', color:'white' } : {}">{{ l.name }}</button>
      <button @click="addingMode = !addingMode"
        :style="addingMode ? { background:'#e74c3c', color:'white', borderColor:'#e74c3c' } : { background:'#27ae60', color:'white', borderColor:'#27ae60' }">
        {{ addingMode ? '🛑 停止标注' : '📍 点击标注' }}
      </button>
    </div>
    <div v-if="mapError" class="map-error">⚠️ {{ mapError }}</div>
    <div ref="mapContainer" class="map-container" />
  </section>
</template>