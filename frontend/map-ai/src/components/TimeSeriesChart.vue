<script setup lang="ts">
/**
 * TimeSeriesChart — Time series line/area chart (M3-T12).
 *
 * Displays time series data with:
 * - Multi-series support (multiple entities on same chart)
 * - Zoom/pan via ECharts dataZoom
 * - Area fill option
 * - Date axis formatting
 */
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import {
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  GridComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([
  LineChart,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  GridComponent,
  CanvasRenderer,
])

interface TimeSeriesPoint {
  timestamp: string
  value: number
}

interface TimeSeries {
  name: string
  points: TimeSeriesPoint[]
  color?: string
  areaFill?: boolean
}

const props = defineProps<{
  series: TimeSeries[]
  title?: string
  xLabel?: string
  yLabel?: string
}>()

const defaultColors = ['#1a73e8', '#c62828', '#2e7d32', '#e65100', '#6a1b9a', '#00695c']

const option = computed(() => {
  // Collect all unique timestamps
  const allTs = new Set<string>()
  for (const s of props.series) {
    for (const p of s.points) {
      allTs.add(p.timestamp)
    }
  }
  const timestamps = Array.from(allTs).sort()

  const chartSeries = props.series.map((s, idx) => {
    const tsMap = new Map(s.points.map((p) => [p.timestamp, p.value]))
    return {
      name: s.name,
      type: 'line',
      data: timestamps.map((t) => tsMap.get(t) ?? null),
      smooth: true,
      lineStyle: { color: s.color || defaultColors[idx % defaultColors.length] },
      itemStyle: { color: s.color || defaultColors[idx % defaultColors.length] },
      areaStyle: s.areaFill
        ? { opacity: 0.1 }
        : undefined,
      emphasis: { focus: 'series' },
    }
  })

  return {
    title: {
      text: props.title || '时间序列',
      left: 'center',
      textStyle: { fontSize: 14, fontWeight: 'bold' },
    },
    tooltip: {
      trigger: 'axis',
    },
    legend: {
      data: props.series.map((s) => s.name),
      bottom: 0,
      textStyle: { fontSize: 11 },
    },
    grid: {
      left: 60,
      right: 30,
      top: 40,
      bottom: props.series.length > 3 ? 60 : 40,
    },
    xAxis: {
      type: 'category',
      data: timestamps,
      name: props.xLabel || '',
      axisLabel: { rotate: timestamps.length > 5 ? 30 : 0, fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      name: props.yLabel || '',
      nameTextStyle: { fontSize: 11 },
      axisLabel: { fontSize: 11 },
    },
    dataZoom: timestamps.length > 10
      ? [
          {
            type: 'inside',
            start: 0,
            end: 100,
          },
          {
            type: 'slider',
            start: 0,
            end: 100,
            bottom: 25,
            height: 20,
          },
        ]
      : [],
    series: chartSeries,
  }
})
</script>

<template>
  <div class="timeseries-chart" v-if="series.length > 0">
    <VChart :option="option" autoresize />
  </div>
  <div v-else class="chart-empty">
    暂无时序数据
  </div>
</template>

<style scoped>
.timeseries-chart {
  width: 100%;
  height: 350px;
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