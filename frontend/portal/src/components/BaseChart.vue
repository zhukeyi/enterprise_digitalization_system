<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = withDefaults(
  defineProps<{
    option: Record<string, unknown>
    height?: string
  }>(),
  { height: '280px' },
)

const el = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

function render() {
  if (!el.value) return
  if (!chart) chart = echarts.init(el.value)
  chart.setOption(props.option, true)
}

function handleResize() {
  chart?.resize()
}

onMounted(() => {
  nextTick(render)
  window.addEventListener('resize', handleResize)
})

watch(
  () => props.option,
  () => render(),
  { deep: true },
)

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="el" class="base-chart" :style="{ height }" />
</template>

<style scoped>
.base-chart {
  width: 100%;
}
</style>
