<script setup lang="ts">
/**
 * ScatterMatrix — Pairwise scatter plot matrix (M3-T12).
 *
 * Shows scatter plots for all pairs of numeric dimensions,
 * with correlation coefficients displayed in each cell.
 * Helps visually identify relationships between variables.
 */
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { ScatterChart } from 'echarts/charts'
import { GridComponent, TitleComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([ScatterChart, GridComponent, TitleComponent, CanvasRenderer])

interface ScatterPoint {
  x: number
  y: number
  label?: string
}

interface ScatterPair {
  /** Dimension name for X axis */
  xDim: string
  /** Dimension name for Y axis */
  yDim: string
  /** Data points */
  points: ScatterPoint[]
  /** Optional correlation coefficient */
  r?: number
}

const props = defineProps<{
  /** Pairs of data series to plot as scatter matrix */
  pairs: ScatterPair[]
  title?: string
}>()

/** Build a grid of scatter charts */
const option = computed(() => {
  const dims = new Set<string>()
  for (const p of props.pairs) {
    dims.add(p.xDim)
    dims.add(p.yDim)
  }
  const dimList = Array.from(dims)
  const n = dimList.length

  if (n === 0) return {}

  const baseGrid: any[] = []
  const baseXAxis: any[] = []
  const baseYAxis: any[] = []
  const series: any[] = []

  const cellW = (100 / (n + 1)).toFixed(2)
  const gridTop = n > 3 ? 60 : 40
  const gridBottom = 50

  // Build grid and axes for each cell
  for (let row = 0; row < n; row++) {
    for (let col = 0; col < n; col++) {
      const left = `${((col + 1) * parseFloat(cellW)).toFixed(0)}%`
      const top = `${(row * (100 - gridTop - gridBottom)) / n + gridTop}%`
      const width = `${cellW}%`
      const height = `${((100 - gridTop - gridBottom) / n).toFixed(0)}%`

      baseGrid.push({ left, top, width, height, containLabel: true })
      baseXAxis.push({
        gridIndex: row * n + col,
        type: 'value',
        name: col === 0 ? dimList[row] : '',
        nameLocation: 'middle',
        nameGap: 25,
        axisLabel: { fontSize: 9 },
      })
      baseYAxis.push({
        gridIndex: row * n + col,
        type: 'value',
        name: row === 0 ? dimList[col] : '',
        nameLocation: 'middle',
        nameGap: 30,
        axisLabel: { fontSize: 9 },
      })

      // Find matching pair
      const pair = props.pairs.find(
        (p) => p.xDim === dimList[col] && p.yDim === dimList[row],
      )
      const data = (pair?.points || []).map((p) => [p.x, p.y])

      series.push({
        type: 'scatter',
        xAxisIndex: row * n + col,
        yAxisIndex: row * n + col,
        data,
        symbolSize: 6,
        itemStyle: { color: '#1a73e8', opacity: 0.6 },
      })
    }
  }

  return {
    title: {
      text: props.title || '散点矩阵',
      left: 'center',
      top: 5,
      textStyle: { fontSize: 14, fontWeight: 'bold' },
    },
    grid: baseGrid,
    xAxis: baseXAxis,
    yAxis: baseYAxis,
    series,
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        return `(${params.value?.[0]}, ${params.value?.[1]})`
      },
    },
  }
})
</script>

<template>
  <div class="scatter-matrix" v-if="pairs.length > 0">
    <VChart :option="option" autoresize />
  </div>
  <div v-else class="chart-empty">
    暂无散点数据
  </div>
</template>

<style scoped>
.scatter-matrix {
  width: 100%;
  height: 500px;
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