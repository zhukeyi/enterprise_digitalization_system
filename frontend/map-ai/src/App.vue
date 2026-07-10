<script setup lang="ts">
import { ref } from 'vue'
import MapView from './components/MapView.vue'
import AgentChat from './components/AgentChat.vue'
import TiptapEditor from './components/TiptapEditor.vue'
import EntityToast from './components/EntityToast.vue'
import AnalysisBox from './components/AnalysisBox.vue'
import ResourcePanel from './components/ResourcePanel.vue'
import VoiceTextInput from './components/VoiceTextInput.vue'

const mapRef = ref<InstanceType<typeof MapView> | null>(null)

function flyToEntity(lng: number, lat: number) {
  mapRef.value?.flyTo(lng, lat)
}

// Expose for child components
;(window as any).__fdeMapRef = mapRef
;(window as any).__fdeFlyToEntity = flyToEntity
</script>

<template>
  <header class="app-header">
    <div class="logo">FDE <span class="accent">MapAI</span></div>
    <span style="flex:1;color:var(--fde-text-light);font-size:13px">智慧地图分析平台</span>
    <VoiceTextInput />
  </header>

  <MapView ref="mapRef" />

  <!-- Right floating dock (Agent + Notes) — same floating style as left panel -->
  <div class="right-dock">
    <AgentChat />
    <TiptapEditor />
  </div>

  <!-- Floating resource panel (left side) -->
  <ResourcePanel @fly-to="flyToEntity" />

  <!-- Floating analysis box -->
  <AnalysisBox @fly-to="flyToEntity" />

  <!-- Toast notifications -->
  <EntityToast />
</template>