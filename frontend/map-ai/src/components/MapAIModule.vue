<script setup lang="ts">
/**
 * MapAIModule — 可嵌入的地图分析核心模块（即插即用）。
 *
 * 设计目标：让第三方可视化看板无需部署 FDE 后端即可集成地图 + 点位 + 关联分析。
 *
 * 集成方式：
 *  1) iframe：将本应用以 ?embed=1&... 加载，通过 postMessage 通信（见 mapai/bridge.ts）
 *  2) script 标签：引入 UMD 包后调用 window.FdeMapAI.mount(el, config)
 *
 * 数据来源（见 MapAIConfig.dataSource）：
 *  - 'static'  由 config.entities/markers 或 loadEntities()/loadMarkers() 注入
 *  - 'remote'  从 dataUrl 拉取 JSON
 *  - 'backend' 连接 FDE 兼容后端
 *
 * 对外事件（emit + postMessage）：
 *  ready / markerClick / entitySelect / analysisResult / error
 */
import { ref, onMounted, watch, computed } from 'vue'
import MapView from './MapView.vue'
import ResourcePanel from './ResourcePanel.vue'
import AnalysisBox from './AnalysisBox.vue'
import { useAnalysisStore } from '../stores/analysis'
import { useMarkersStore } from '../stores/markers'
import {
  setRuntimeConfig,
  getRuntimeConfig,
  getApiBase,
} from '../mapai/runtime'
import { emitToParent, setupBridge } from '../mapai/bridge'
import type { MapAIConfig, MapAIEntity, MapAIMarker } from '../mapai/types'

const props = defineProps<{ config?: MapAIConfig }>()
const emit = defineEmits<{
  ready: []
  'marker-click': [id: string, lng: number, lat: number]
  'entity-select': [id: string, name: string]
  'analysis-result': [result: unknown]
  error: [message: string]
}>()

const VERSION = '1.0.0'
const analysisStore = useAnalysisStore()
const markersStore = useMarkersStore()
const mapRef = ref<InstanceType<typeof MapView> | null>(null)

/* ---------- 配置解析与默认值 ---------- */
const config = props.config || ({} as MapAIConfig)
const hasApiBase = !!(config.apiBase || getRuntimeConfig().apiBase)

const features = computed(() => {
  const f = config.features || {}
  return {
    resourcePanel: f.resourcePanel ?? true,
    analysis: f.analysis ?? hasApiBase,
    markerAdd: f.markerAdd ?? true,
  }
})

function applyConfig() {
  const useBackend =
    config.dataSource?.type === 'backend'
      ? true
      : config.dataSource?.type
        ? false
        : !!config.apiBase
  setRuntimeConfig({
    provider: config.provider,
    apiKey: config.apiKey,
    securityCode: config.securityCode,
    apiBase: config.apiBase,
    markersBackend: useBackend,
  })
  return useBackend
}

/* ---------- 数据注入 ---------- */
function seedEntities(entities?: MapAIEntity[]) {
  if (!entities) return
  for (const e of entities) {
    if (e.lng == null || e.lat == null) continue
    analysisStore.addEntity({
      id: e.id,
      name: e.name,
      type: e.type || 'poi',
      lng: e.lng,
      lat: e.lat,
      metadata: e.metadata,
    })
  }
}

function seedMarkers(markers?: MapAIMarker[]) {
  if (!markers || markers.length === 0) return
  markersStore.seedMarkers(markers)
}

async function loadRemote(url: string) {
  try {
    const resp = await fetch(url)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const data = await resp.json()
    const list: Array<MapAIEntity | MapAIMarker> = Array.isArray(data)
      ? data
      : (data.entities || []).concat(data.markers || [])
    // 简单分流：有 note/tags 倾向点位，否则实体
    const ents: MapAIEntity[] = []
    const marks: MapAIMarker[] = []
    for (const item of list as any[]) {
      if (item.note !== undefined || item.tags !== undefined) marks.push(item)
      else ents.push(item)
    }
    seedEntities(ents)
    seedMarkers(marks)
  } catch (err: any) {
    emit('error', err.message || 'remote data load failed')
    emitToParent('error', { message: err.message }, config.targetOrigin)
  }
}

/* ---------- 控制器（供 postMessage / 全局 API 调用） ---------- */
function loadEntities(entities: MapAIEntity[]) {
  seedEntities(entities)
}
function loadMarkers(markers: MapAIMarker[]) {
  seedMarkers(markers)
}
function flyTo(lng: number, lat: number, zoom?: number) {
  mapRef.value?.flyTo(lng, lat, zoom)
}
async function analyze(entityIds?: string[]) {
  const ids = entityIds || analysisStore.entityIds
  if (ids.length < 2) {
    analysisStore.addToast('至少需要 2 个实体才能分析', 'warning')
    return
  }
  analysisStore.setAnalyzing(true)
  try {
    const resp = await fetch(`${getApiBase()}/map/analysis`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        entity_ids: ids,
        entities: analysisStore.markedEntities.map((e) => ({
          id: e.id,
          name: e.name,
          type: e.type,
          lng: e.lng,
          lat: e.lat,
          metadata: e.metadata,
        })),
        method: 'pearson',
        query: '',
      }),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const result = await resp.json()
    analysisStore.setAnalysisResult(result)
    analysisStore.addToast('分析完成 ✅', 'success')
  } catch (err: any) {
    analysisStore.setAnalysisResult({
      entityIds: ids,
      correlation_matrix: {},
      timestamp: Date.now(),
      status: 'error',
      message: err.message || '后端未响应',
    })
    emit('error', err.message || 'analysis failed')
    emitToParent('error', { message: err.message }, config.targetOrigin)
  } finally {
    analysisStore.setAnalyzing(false)
  }
}
function clearEntities() {
  analysisStore.clearAll()
}

/* ---------- 生命周期 ---------- */
onMounted(async () => {
  applyConfig()

  // 静态 / 远端数据在地图就绪前注入
  if (config.dataSource?.type === 'remote' && config.dataSource.dataUrl) {
    await loadRemote(config.dataSource.dataUrl)
  } else {
    seedMarkers(config.markers)
    seedEntities(config.entities)
  }

  // 建立 iframe 通信桥
  setupBridge(
    {
      loadEntities: (e) => loadEntities(e as MapAIEntity[]),
      loadMarkers: (m) => loadMarkers(m as MapAIMarker[]),
      flyTo,
      analyze,
      clearEntities,
    },
    config.targetOrigin,
  )
})

/* ---------- 事件转发 ---------- */
function onMapReady() {
  emit('ready')
  emitToParent('ready', { version: VERSION }, config.targetOrigin)
}
function onMarkerClick(id: string, lng: number, lat: number) {
  emit('marker-click', id, lng, lat)
  emitToParent('marker-click', { id, lng, lat }, config.targetOrigin)
}

// 实体新增时转发
watch(
  () => analysisStore.markedEntities.length,
  (now, before) => {
    if (now > before) {
      const last = analysisStore.markedEntities[now - 1]
      if (last) {
        emit('entity-select', last.id, last.name)
        emitToParent('entity-select', { id: last.id, name: last.name }, config.targetOrigin)
      }
    }
  },
)

// 分析结果转发
watch(
  () => analysisStore.lastAnalysisResult,
  (result) => {
    if (result) {
      emit('analysis-result', result)
      emitToParent('analysisResult', { result }, config.targetOrigin)
    }
  },
)

defineExpose({
  version: VERSION,
  loadEntities,
  loadMarkers,
  flyTo,
  analyze,
  clearEntities,
})
</script>

<template>
  <div class="mapai-module">
    <MapView ref="mapRef" @ready="onMapReady" @marker-click="onMarkerClick" />

    <ResourcePanel
      v-if="features.resourcePanel"
      @fly-to="(lng, lat) => mapRef?.flyTo(lng, lat)"
    />

    <AnalysisBox
      v-if="features.analysis"
      @fly-to="(lng, lat) => mapRef?.flyTo(lng, lat)"
    />
  </div>
</template>

<style scoped>
.mapai-module {
  position: relative;
  width: 100%;
  height: 100%;
}
.mapai-module :deep(.map-area) {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.mapai-module :deep(.map-container) {
  width: 100%;
  height: 100%;
}
</style>
