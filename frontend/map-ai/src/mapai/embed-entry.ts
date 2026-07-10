/**
 * UMD 库入口：供第三方通过 <script> 标签直接集成。
 *
 * 使用方式：
 *   <link rel="stylesheet" href="mapai.css" />
 *   <script src="mapai.umd.js"></script>
 *   <script>
 *     const ctrl = FdeMapAI.mount('#map-container', {
 *       provider: 'baidu',
 *       apiKey: 'YOUR_AK',
 *       dataSource: { type: 'static' },
 *       entities: [ ... ],
 *     })
 *     ctrl.flyTo(120.15, 30.27)
 *   </script>
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import MapAIModule from '../components/MapAIModule.vue'
import { setRuntimeConfig } from './runtime'
import type { MapAIConfig, MapAIEntity, MapAIMarker } from './types'
import '../style.css'

export interface MapAIController {
  loadEntities(entities: MapAIEntity[]): void
  loadMarkers(markers: MapAIMarker[]): void
  flyTo(lng: number, lat: number, zoom?: number): void
  analyze(entityIds?: string[]): void
  clearEntities(): void
  destroy(): void
  version: string
}

export const version = '1.0.0'

function resolveTarget(target: string | HTMLElement): HTMLElement {
  if (typeof target === 'string') {
    const el = document.querySelector(target)
    if (!el) throw new Error(`FdeMapAI: 找不到挂载目标 "${target}"`)
    return el as HTMLElement
  }
  return target
}

export function mount(
  target: string | HTMLElement,
  config: MapAIConfig = {},
): MapAIController {
  const el = resolveTarget(target)
  setRuntimeConfig(config)
  const app = createApp(MapAIModule, { config })
  app.use(createPinia())
  const inst = app.mount(el) as any
  return {
    loadEntities: (e) => inst.loadEntities(e),
    loadMarkers: (m) => inst.loadMarkers(m),
    flyTo: (lng, lat, zoom) => inst.flyTo(lng, lat, zoom),
    analyze: (ids) => inst.analyze(ids),
    clearEntities: () => inst.clearEntities(),
    destroy: () => app.unmount(),
    version,
  }
}

const globalApi = { mount, version }
;(window as unknown as { FdeMapAI: typeof globalApi }).FdeMapAI = globalApi
