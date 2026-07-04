<script setup lang="ts">
import { watch } from 'vue'
import { useAnalysisStore, type MarkedEntity } from '../stores/analysis'
import { createMarker, showInfoWindow } from '../composables/useMap'

const props = defineProps<{ map: any; entity: MarkedEntity; lng: number; lat: number }>()
const store = useAnalysisStore()

function addToAnalysis() {
  store.addEntity({ id: props.entity.id, name: props.entity.name, type: props.entity.type, lng: props.lng, lat: props.lat, metadata: props.entity.metadata })
}

watch(() => props.map, (m) => {
  if (!m) return
  createMarker(m, props.lng, props.lat, {
    title: props.entity.name,
    onClick: () => showInfoWindow(m, props.lng, props.lat,
      `<div style="padding:8px 12px;min-width:160px">
        <div style="margin-bottom:6px"><strong>${props.entity.name}</strong><br><span style="font-size:12px;color:#666">${props.entity.type}</span></div>
        <button style="width:100%;padding:6px;border:none;border-radius:6px;background:#1a73e8;color:#fff;cursor:pointer" onclick="event.target.style.background='#1557b0';setTimeout(()=>window.__fdeAddToAnalysis&&window.__fdeAddToAnalysis(),0)">+ 添加到分析</button>
      </div>`)
  )
  if (!(window as any).__fdeAddToAnalysis) (window as any).__fdeAddToAnalysis = addToAnalysis
}, { immediate: true })
</script>
<template></template>