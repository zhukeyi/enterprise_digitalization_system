<script setup lang="ts">
import { watch } from 'vue'
import { useAnalysisStore, type MarkedEntity } from '../stores/analysis'
import { createMarker, showInfoWindow } from '../composables/useMap'

const props = defineProps<{ map: any; entity: MarkedEntity; lng: number; lat: number }>()
const store = useAnalysisStore()

function handleAdd() {
  store.addEntity({ id: props.entity.id, name: props.entity.name, type: props.entity.type, lng: props.lng, lat: props.lat, metadata: props.entity.metadata })
}

const popupHtml = `<div style="padding:8px 12px;min-width:160px">
  <div style="margin-bottom:6px"><strong>${props.entity.name.replace(/'/g, "\\'")}</strong><br>
  <span style="font-size:12px;color:#666">${props.entity.type}</span></div>
  <button class="fde-popup-add-btn">+ 添加到分析</button>
</div>`

watch(() => props.map, (m) => {
  if (!m) return
  createMarker(m, props.lng, props.lat, {
    title: props.entity.name,
    onClick: () => {
      setTimeout(() => {
        document.querySelector('.fde-popup-add-btn')?.addEventListener('click', handleAdd)
      }, 50)
      showInfoWindow(m, props.lng, props.lat, popupHtml)
    }
  })
}, { immediate: true })
</script>
<template></template>