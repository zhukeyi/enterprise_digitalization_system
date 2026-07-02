<script setup lang="ts">
import MapView from './components/MapView.vue'
import AgentChat from './components/AgentChat.vue'
import TiptapEditor from './components/TiptapEditor.vue'
import EntityToast from './components/EntityToast.vue'
import AnalysisBox from './components/AnalysisBox.vue'
</script>

<template>
  <header class="app-header">
    <div class="logo">
      FDE <span class="accent">MapAI</span>
    </div>
    <span style="color: var(--fde-text-light); font-size: 13px">
      Enterprise Intelligence Platform
    </span>
  </header>

  <MapView />

  <aside class="side-panel">
    <AgentChat />
    <TiptapEditor />
  </aside>

  <!-- Global toast notifications for entity actions -->
  <EntityToast />

  <!-- Floating analysis collection box -->
  <AnalysisBox />
</template>
