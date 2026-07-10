<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useAnalysisStore } from '../stores/analysis'
import { useMarkersStore } from '../stores/markers'
import { getProvider, getApiKey, loadMapSDK, createMap, addMapControls, switchToSatellite, switchToNormal, onMapClick, destroyMap } from '../composables/useMap'

const emit = defineEmits<{
  'marker-click': [id: string, lng: number, lat: number]
  'ready': []
}>()

const store = useAnalysisStore()
const markersStore = useMarkersStore()
const provider = getProvider()
const label = provider === 'amap' ? '高德' : '百度'

const mapContainer = ref<HTMLDivElement>()
const mapError = ref('')
const map = ref<any>(null)
let markers: any[] = []
let markerIdCounter = 0

// Track which entity IDs have been rendered to avoid duplicates
const renderedIds = new Set<string>()

// Persisted markers (from backend) rendered on the map
let persistedMarkers: any[] = []

const layerType = ref<'normal' | 'satellite'>('normal')
const layers = [{ id: 'normal', name: '标准' }, { id: 'satellite', name: '卫星' }]
const addingMode = ref(false)
const isDrawing = ref(false)

// Marker creation modal state
const showMarkerModal = ref(false)
const newMarkerName = ref('')
const newMarkerNote = ref('')
const pendingMarker = ref<{ lng: number; lat: number } | null>(null)

function switchLayer(type: 'normal' | 'satellite') {
  layerType.value = type
  if (!map.value) return
  type === 'satellite' ? switchToSatellite(map.value) : switchToNormal(map.value)
}

/* ================================================================
 * HTML escape utility (prevent XSS in InfoWindow)
 * ================================================================ */

function escapeHtml(text: string): string {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}

/* ================================================================
 * 地图点击 → 弹出标注弹窗（名称 + 备注）
 * ================================================================ */

function handleMapClick(e: any) {
  if (!addingMode.value && !isDrawing.value) return
  if (!map.value) return

  let lng: number, lat: number
  if (provider === 'baidu') {
    lng = e.latlng.lng
    lat = e.latlng.lat
  } else {
    lng = e.lnglat.getLng()
    lat = e.lnglat.getLat()
  }

  if (!addingMode.value) return

  // Open the marker creation modal instead of using prompt()
  pendingMarker.value = { lng, lat }
  newMarkerName.value = `标记点 ${++markerIdCounter}`
  newMarkerNote.value = ''
  showMarkerModal.value = true
}

async function confirmCreateMarker() {
  if (!pendingMarker.value || !newMarkerName.value.trim()) return

  const { lng, lat } = pendingMarker.value
  const name = newMarkerName.value.trim()
  const note = newMarkerNote.value.trim()

  // Optimistic: add to analysis store immediately
  const tempId = `marker-${markerIdCounter}`
  store.addEntity({ id: tempId, name, type: 'map-marker', lng, lat })
  addMarkerToMap(tempId, name, lng, lat)

  // Persist to backend (async)
  const saved = await markersStore.createMarker({ name, lng, lat, note })
  if (saved) {
    // Replace temp marker with saved one on the map
    removeMarkerById(tempId)
    store.removeEntity(tempId)
    store.addEntity({ id: saved.id, name: saved.name, type: 'map-marker', lng, lat })
    addMarkerToMap(saved.id, saved.name, lng, lat, saved.tags, saved.note)
  }

  // Close modal
  showMarkerModal.value = false
  pendingMarker.value = null
  newMarkerName.value = ''
  newMarkerNote.value = ''
}

function cancelCreateMarker() {
  showMarkerModal.value = false
  pendingMarker.value = null
  newMarkerName.value = ''
  newMarkerNote.value = ''
}

/* ================================================================
 * Marker rendering
 * ================================================================ */

function addMarkerToMap(
  id: string,
  name: string,
  lng: number,
  lat: number,
  tags: string[] = [],
  note: string = '',
) {
  if (!map.value) return

  const marker = provider === 'baidu'
    ? createBaiduMarker(id, name, lng, lat, tags, note)
    : createAmapMarker(id, name, lng, lat, tags, note)

  markers.push({ id, marker, lng, lat })
}

function createBaiduMarker(
  id: string,
  name: string,
  lng: number,
  lat: number,
  tags: string[] = [],
  note: string = '',
) {
  const B = (window as any).BMapGL
  const pt = new B.Point(lng, lat)
  const marker = new B.Marker(pt)
  marker.setTitle(name)
  map.value.addOverlay(marker)

  marker.addEventListener('click', () => {
    emit('marker-click', id, lng, lat)
    const safeName = escapeHtml(name)
    const safeTags = tags.map((t: string) => escapeHtml(t))
    const safeNote = note ? escapeHtml(note.slice(0, 80) + (note.length > 80 ? '...' : '')) : ''
    const tagsHtml = safeTags.length > 0
      ? `<div style="margin-top:4px">${safeTags.map((t: string) => `<span style="display:inline-block;background:#e8f0fe;color:#1a73e8;padding:1px 6px;border-radius:4px;font-size:10px;margin-right:3px">${t}</span>`).join('')}</div>`
      : ''
    const noteHtml = safeNote
      ? `<div style="margin-top:4px;color:#666;font-size:11px;max-width:180px;word-break:break-all">${safeNote}</div>`
      : ''
    const html = `<div style="padding:6px 12px;font-size:13px">
      <strong>${safeName}</strong><br>
      <span style="color:#666;font-size:11px">${lng.toFixed(4)}, ${lat.toFixed(4)}</span>
      ${tagsHtml}
      ${noteHtml}
      <br><button onclick="window.__fdeDelMarker('${escapeHtml(id)}')" style="margin-top:4px;font-size:11px;color:#e74c3c;border:none;background:none;cursor:pointer">删除</button>
    </div>`
    const iw = new B.InfoWindow(html, { width: 220 })
    map.value.openInfoWindow(iw, pt)
    ;(window as any).__fdeDelMarker = async (mid: string) => {
      removeMarkerById(mid)
      store.removeEntity(mid)
      await markersStore.deleteMarker(mid)
      map.value.closeInfoWindow()
    }
  })
  return marker
}

function createAmapMarker(
  _id: string,
  name: string,
  lng: number,
  lat: number,
  tags: string[] = [],
  note: string = '',
) {
  const A = (window as any).AMap
  const marker = new A.Marker({ position: [lng, lat], title: name, draggable: true })
  map.value.add(marker)

  const safeName = escapeHtml(name)
  const safeTags = tags.map((t: string) => escapeHtml(t))
  const safeNote = note ? escapeHtml(note.slice(0, 80) + (note.length > 80 ? '...' : '')) : ''
  const tagsHtml = safeTags.length > 0
    ? `<div style="margin-top:4px">${safeTags.map((t: string) => `<span style="display:inline-block;background:#e8f0fe;color:#1a73e8;padding:1px 6px;border-radius:4px;font-size:10px;margin-right:3px">${t}</span>`).join('')}</div>`
    : ''
  const noteHtml = safeNote
    ? `<div style="margin-top:4px;color:#666;font-size:11px;max-width:180px;word-break:break-all">${safeNote}</div>`
    : ''

  marker.on('click', () => {
    emit('marker-click', _id, lng, lat)
    const html = `<div style="padding:6px 12px;font-size:13px">
      <strong>${safeName}</strong><br>
      <span style="color:#666;font-size:11px">${lng.toFixed(4)}, ${lat.toFixed(4)}</span>
      ${tagsHtml}
      ${noteHtml}
    </div>`
    const iw = new A.InfoWindow({ content: html, offset: new A.Pixel(0, -30) })
    iw.open(map.value, [lng, lat])
  })
  return marker
}

function removeMarkerById(id: string) {
  const idx = markers.findIndex(m => m.id === id)
  if (idx === -1) return
  const m = markers[idx]
  if (provider === 'baidu') map.value?.removeOverlay(m.marker)
  else map.value?.remove(m.marker)
  markers.splice(idx, 1)
}

/* ================================================================
 * 渲染已持久化的点位（从后端加载）
 * ================================================================ */

function renderPersistedMarkers() {
  if (!map.value) return

  // Clear old persisted markers
  for (const m of persistedMarkers) {
    if (provider === 'baidu') map.value?.removeOverlay(m.marker)
    else map.value?.remove(m.marker)
  }
  persistedMarkers = []
  renderedIds.clear()

  // Add all markers from the store
  for (const m of markersStore.markers) {
    if (renderedIds.has(m.id)) continue
    const marker = provider === 'baidu'
      ? createBaiduMarker(m.id, m.name, m.lng, m.lat, m.tags, m.note)
      : createAmapMarker(m.id, m.name, m.lng, m.lat, m.tags, m.note)
    persistedMarkers.push({ id: m.id, marker, lng: m.lng, lat: m.lat })
    renderedIds.add(m.id)
  }
}

// Watch for changes in persisted markers
watch(() => markersStore.markers.length, () => {
  renderPersistedMarkers()
})

/* ================================================================
 * 同步 analysis store → map markers (only for entities not already
 * rendered as persisted markers)
 * ================================================================ */

watch(() => store.markedEntities.length, () => {
  if (!map.value) return
  // Clear existing analysis markers
  for (const m of markers) {
    if (provider === 'baidu') map.value?.removeOverlay(m.marker)
    else map.value?.remove(m.marker)
  }
  markers = []
  for (const e of store.markedEntities) {
    if (renderedIds.has(e.id)) continue
    if (e.lng != null && e.lat != null) {
      addMarkerToMap(e.id, e.name, e.lng, e.lat)
      renderedIds.add(e.id)
    }
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
    map.value = await createMap(mapContainer.value)
    addMapControls(map.value)
    emit('ready')

    // 点击事件
    onMapClick(map.value, handleMapClick)

    // 加载已持久化的实体 (localStorage)
    for (const e of store.markedEntities) {
      if (e.lng != null && e.lat != null) addMarkerToMap(e.id, e.name, e.lng, e.lat)
    }

    // 加载服务端持久化的点位
    await markersStore.fetchMarkers()
    renderPersistedMarkers()
  } catch (e: any) {
    mapError.value = `${label}地图加载失败: ${e.message}`
  }
})

onUnmounted(() => {
  if (map.value) destroyMap(map.value)
  map.value = null
})

// Expose map and helper functions
function flyTo(lng: number, lat: number, zoom = 14) {
  if (!map.value) return
  if (provider === 'baidu') {
    map.value.flyTo?.({ lng, lat }, zoom) || map.value.centerAndZoom(new (window as any).BMapGL.Point(lng, lat), zoom)
  } else {
    map.value.setZoomAndCenter(zoom, [lng, lat])
  }
}
defineExpose({ map: map, flyTo })
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

    <!-- Marker creation modal -->
    <div v-if="showMarkerModal" class="marker-modal-overlay" @click.self="cancelCreateMarker">
      <div class="marker-modal">
        <div class="marker-modal-header">添加标注</div>
        <div class="marker-modal-body">
          <label class="modal-label">名称</label>
          <input
            v-model="newMarkerName"
            type="text"
            class="modal-input"
            placeholder="标注名称"
            @keyup.enter="confirmCreateMarker"
          />
          <label class="modal-label">备注 <span class="modal-hint">（将自动生成标签）</span></label>
          <textarea
            v-model="newMarkerNote"
            class="modal-textarea"
            placeholder="输入备注信息，如：杭州东站是高铁枢纽站..."
            rows="3"
          />
          <div v-if="pendingMarker" class="modal-coords">
            📍 {{ pendingMarker.lng.toFixed(4) }}, {{ pendingMarker.lat.toFixed(4) }}
          </div>
        </div>
        <div class="marker-modal-footer">
          <button class="modal-btn cancel" @click="cancelCreateMarker">取消</button>
          <button class="modal-btn confirm" @click="confirmCreateMarker">保存</button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* Marker creation modal */
.marker-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
}

.marker-modal {
  background: white;
  border-radius: 12px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.2);
  width: 400px;
  max-width: 90vw;
  overflow: hidden;
}

.marker-modal-header {
  padding: 12px 20px;
  background: linear-gradient(135deg, #1a73e8, #4285f4);
  color: white;
  font-weight: 600;
  font-size: 15px;
}

.marker-modal-body {
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.modal-label {
  font-size: 12px;
  font-weight: 600;
  color: #4a5568;
  margin-top: 4px;
}

.modal-hint {
  font-weight: 400;
  color: #999;
}

.modal-input {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
}

.modal-input:focus {
  border-color: #1a73e8;
}

.modal-textarea {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 13px;
  outline: none;
  resize: vertical;
  font-family: inherit;
  transition: border-color 0.2s;
}

.modal-textarea:focus {
  border-color: #1a73e8;
}

.modal-coords {
  font-size: 11px;
  color: #999;
  margin-top: 4px;
}

.marker-modal-footer {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  padding: 12px 20px;
  border-top: 1px solid #f0f0f0;
}

.modal-btn {
  border: none;
  border-radius: 8px;
  padding: 8px 20px;
  font-size: 13px;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s;
}

.modal-btn.cancel {
  background: #f5f7fa;
  color: #666;
}

.modal-btn.cancel:hover {
  background: #e2e8f0;
}

.modal-btn.confirm {
  background: #1a73e8;
  color: white;
}

.modal-btn.confirm:hover {
  background: #1557b0;
}
</style>
