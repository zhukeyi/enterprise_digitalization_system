<script setup lang="ts">
/**
 * HeatmapChart — Correlation heatmap (M3-T12).
 *
 * Displays a correlation matrix as an ECharts heatmap with:
 * - Color scale from red (positive correlation) to blue (negative)
 * - Hover tooltip showing r-value and p-value
 * - Entity name labels on both axes
 */
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { HeatmapChart } from 'echarts/charts'
import {
  TooltipComponent,
  VisualMapComponent,
  GridComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([HeatmapChart, TooltipComponent, VisualMapComponent, GridComponent, CanvasRenderer])

interface HeatmapPoint {
  pair: [string, string]
  coefficient: number
  pValue?: number
}

const props = defineProps<{
  data: HeatmapPoint[]
  /** Optional list of entity names (derived from data if not provided) */
  entityNames?: string[]
  /** Chart title */
  title?: string
}>()

const entityNames = computed(() => {
  if (props.entityNames && props.entityNames.length > 0) return props.entityNames
  const names = new Set<string>()
  for (const d of props.data) {
    names.add(d.pair[0])
    names.add(d.pair[1])
  }
  return Array.from(names)
})

const option = computed(() => {
  const names = entityNames.value
  const data: [number, number, number][] = []

  for (const d of props.data) {
    const xi = names.indexOf(d.pair[0])
    const yi = names.indexOf(d.pair[1])
    if (xi >= 0 && yi >= 0) {
      data.push([xi, yi, +d.coefficient.toFixed(3)])
      if (xi !== yi) {
        data.push([yi, xi, +d.coefficient.toFixed(3)])
      }
    }
  }

  return {
    title: {
      text: props.title || '相关性矩阵',
      left: 'center',
      textStyle: { fontSize: 14, fontWeight: 'bold' },
    },
    tooltip: {
      formatter: (params: any) => {
        const [xi, yi, val] = params.data || [0, 0, 0]
        const found = props.data.find(
          (d) => d.pair[0] === names[xi] && d.pair[1] === names[yi],
        )
        const pv = found?.pValue != null ? `p=${found.pValue.toFixed(4)}` : ''
        return `${names[xi]} × ${names[yi]}<br/>r = ${val.toFixed(4)}${pv ? '<br/>' + pv : ''}`
      },
    },
    grid: { left: 100, right: 40, top: 50, bottom: 60 },
    xAxis: {
      type: 'category',
      data: names,
      axisLabel: { rotate: 45, fontSize: 11 },
      position: 'bottom',
    },
    yAxis: {
      type: 'category',
      data: names,
      axisLabel: { fontSize: 11 },
    },
    visualMap: {
      min: -1,
      max: 1,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      inRange: {
        color: ['#1a73e8', '#e0e0e0', '#c62828'],
      },
      text: ['高', '低'],
      textStyle: { fontSize: 11 },
    },
    series: [
      {
        type: 'heatmap',
        data,
        label: { show: true, fontSize: 11 },
        emphasis: {
          itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' },
        },
      },
    ],
  }
})
</script>

<template>
  <div class="heatmap-chart" v-if="data.length > 0">
    <VChart :option="option" autoresize />
  </div>
  <div v-else class="chart-empty">
    暂无相关性数据
  </div>
</template>

<style scoped>
.heatmap-chart {
  width: 100%;
  height: 400px;
}
.chart-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: #999;
  font-size: 13px;
}
</style>