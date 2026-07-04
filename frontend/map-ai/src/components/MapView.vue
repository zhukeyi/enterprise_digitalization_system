<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

// 高德地图 Key — 通过 .env 的 VITE_AMAP_KEY 设置
const amapKey = import.meta.env.VITE_AMAP_KEY as string | undefined
// 高德安全密钥（JS API 2.0 需要）— 可选
const amapSecurityCode = import.meta.env.VITE_AMAP_SECURITY_CODE as string | undefined

const mapContainer = ref<HTMLDivElement>()
let map: AMap.Map | null = null

const layerType = ref<'normal' | 'satellite'>('normal')
const layers = [
  { id: 'normal', name: '标准' },
  { id: 'satellite', name: '卫星' },
]

const mapError = ref<string>('')

function switchLayer(type: 'normal' | 'satellite') {
  layerType.value = type
  if (!map) return
  if (type === 'satellite') {
    map.setLayers([new AMap.TileLayer.Satellite()])
  } else {
    map.setLayers([new AMap.TileLayer()])
  }
}

async function loadAMap(): Promise<typeof AMap> {
  // Dynamically load AMap JS API 2.0
  const key = amapKey
  if (!key) throw new Error('VITE_AMAP_KEY not set')

  const security = amapSecurityCode
    ? `&jscode=${encodeURIComponent(amapSecurityCode)}`
    : ''
  const src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}${security}`

  return new Promise((resolve, reject) => {
    if ((window as any).AMap) {
      resolve((window as any).AMap)
      return
    }
    const script = document.createElement('script')
    script.src = src
    script.onload = () => resolve((window as any).AMap)
    script.onerror = () => reject(new Error('高德地图 JS API 加载失败'))
    document.head.appendChild(script)
  })
}

onMounted(async () => {
  if (!mapContainer.value) return

  if (!amapKey || amapKey === 'your_amap_key_here') {
    mapError.value =
      '高德地图 Key 未配置。请在 .env 文件中设置 VITE_AMAP_KEY=你的Key（在 https://console.amap.com 申请）'
    return
  }

  try {
    await loadAMap()

    map = new AMap.Map(mapContainer.value, {
      zoom: 4,
      center: [116.397, 39.908], // 北京
      layers: [new AMap.TileLayer()],
    })

    // 控件
    map.addControl(new AMap.Scale())
    map.addControl(new AMap.ToolBar({ position: 'RT' }))

    // 示例标记
    const marker = new AMap.Marker({
      position: [116.397, 39.908],
      title: '北京 — FDE HQ',
    })
    map.add(marker)
  } catch (e: any) {
    mapError.value = `地图加载失败: ${e.message}`
    console.error('AMap load error:', e)
  }
})

onUnmounted(() => {
  map?.destroy()
  map = null
})

defineExpose({ map, flyTo: (lng: number, lat: number) => map?.setZoomAndCenter(12, [lng, lat]) })
</script>

<template>
  <section class="map-area">
    <div class="map-overlay">
      <button
        v-for="l in layers"
        :key="l.id"
        @click="switchLayer(l.id as 'normal' | 'satellite')"
        :style="layerType === l.id ? { background: 'var(--fde-primary)', color: 'white' } : {}"
      >
        {{ l.name }}
      </button>
    </div>
    <div v-if="mapError" class="map-error">⚠️ {{ mapError }}</div>
    <div ref="mapContainer" class="map-container" />
  </section>
</template>