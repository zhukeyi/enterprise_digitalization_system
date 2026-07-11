/**
 * useMap — 地图供应商抽象层。
 * 通过 VITE_MAP_PROVIDER 切换: "baidu" | "amap"
 * 运行时可通过 setRuntimeConfig() 覆盖（用于嵌入/即插即用场景）。
 */

import { getRuntimeConfig } from '../mapai/runtime'

export type MapProvider = 'baidu' | 'amap'

export interface MapInstance {
  destroy(): void
  flyTo(lng: number, lat: number, zoom?: number): void
  fitView(positions: Array<[number, number]>, padding?: number[]): void
}

export interface MarkerInstance {
  setPosition(pos: [number, number]): void
  remove(): void
}

export function getProvider(): MapProvider {
  const rt = getRuntimeConfig().provider
  if (rt) return rt
  return (import.meta.env.VITE_MAP_PROVIDER as string) === 'amap' ? 'amap' : 'baidu'
}

export function getApiKey(): string {
  const rt = getRuntimeConfig().apiKey
  if (rt) return rt
  const p = getProvider()
  return p === 'amap'
    ? (import.meta.env.VITE_AMAP_KEY as string) || ''
    : (import.meta.env.VITE_BAIDU_AK as string) || ''
}

export function getSecurityCode(): string {
  const rt = getRuntimeConfig().securityCode
  if (rt) return rt
  return (import.meta.env.VITE_AMAP_SECURITY_CODE as string) || ''
}

/* ================================================================
 * AMap 实现
 * ================================================================ */

let _amapPromise: Promise<any> | null = null

async function loadAMap(): Promise<any> {
  if (_amapPromise) return _amapPromise
  _amapPromise = new Promise((resolve, reject) => {
    const w = window as any
    if (w.AMap) { resolve(w.AMap); return }
    const key = getApiKey()
    const jscode = getSecurityCode()
    const extra = jscode ? `&jscode=${encodeURIComponent(jscode)}` : ''
    const s = document.createElement('script')
    s.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}${extra}`
    s.onload = () => resolve(w.AMap)
    s.onerror = () => reject(new Error('AMap 加载失败'))
    document.head.appendChild(s)
  })
  return _amapPromise
}

async function createAMap(container: HTMLElement): Promise<any> {
  const A = await loadAMap()
  return new A.Map(container, { zoom: 10, center: [120.155, 30.273], layers: [new A.TileLayer()] })
}

/* ================================================================
 * Baidu Map GL 实现
 * ================================================================ */

let _bmapPromise: Promise<any> | null = null
const BMAP_CALLBACK = '__fdeBMapReady'

/**
 * 百度地图 WebGL 异步加载（官方 callback 机制）。
 *
 * 百度 v1.0 loader 内部通过 document.write 同步注入核心模块（BMapGL.Map）。
 * 若以「无 callback」方式动态注入 <script>（DOMContentLoaded 之后），
 * document.write 会失效甚至清空页面，导致 BMapGL.Map 永不就绪——这正是此前
 * 生产环境「加载超时」的根因。
 *
 * 正确做法：URL 携带 `&callback=__fdeBMapReady`。此时 loader 走【异步】分支，
 * 不依赖 document.write，核心模块就绪后回调该全局函数。此方式对主站与嵌入
 * （运行时 AK）场景统一适用，无需 index.html 预加载。已用 Playwright 实测验证。
 */
async function loadBMap(): Promise<any> {
  const w = window as any
  // 快路径：SDK 已就绪（宿主页或前一次加载已完成）。
  if (w.BMapGL && typeof w.BMapGL.Map === 'function') return w
  if (_bmapPromise) return _bmapPromise

  _bmapPromise = new Promise((resolve, reject) => {
    let pollTimer: ReturnType<typeof setInterval> | null = null
    const deadline = Date.now() + 15000

    const cleanup = () => {
      if (pollTimer !== null) {
        clearInterval(pollTimer)
        pollTimer = null
      }
      try {
        delete w[BMAP_CALLBACK]
      } catch {
        w[BMAP_CALLBACK] = undefined
      }
    }
    const done = () => {
      cleanup()
      resolve(w)
    }
    const fail = (msg: string) => {
      cleanup()
      _bmapPromise = null
      reject(new Error(msg))
    }

    // 全局 callback：loader 异步就绪后触发。
    w[BMAP_CALLBACK] = () => {
      if (w.BMapGL && typeof w.BMapGL.Map === 'function') done()
    }

    if (!w.BMapGL) {
      const s = document.createElement('script')
      s.type = 'text/javascript'
      s.src =
        `https://api.map.baidu.com/api?type=webgl&v=1.0&ak=${encodeURIComponent(getApiKey())}` +
        `&callback=${BMAP_CALLBACK}`
      s.onerror = () => fail('百度地图脚本加载失败（请检查 AK 或网络）')
      document.head.appendChild(s)
    }

    // 兜底轮询：callback 已覆盖绝大多数情况，此处防御 callback 未触发但模块已就绪。
    // 注意：百度在 AK 服务校验失败时（如 error 240「APP 服务被禁用」/域名白名单不匹配）
    // 会显式把 window.BMapGL 置为 null 并终止渲染（加载中为 undefined，仅失败时才是 null）。
    // 据此可即时给出精准提示，而非等到超时。
    const tick = () => {
      if (w.BMapGL && typeof w.BMapGL.Map === 'function') {
        done()
      } else if (w.BMapGL === null) {
        fail('百度地图 AK 校验失败：请在百度地图开放平台确认该 AK 已开通「JavaScript API GL」服务且当前域名在白名单内（错误码 240）')
      } else if (Date.now() > deadline) {
        fail('BMapGL.Map 未就绪：百度地图 WebGL 模块加载超时，请检查 AK 或网络')
      }
    }
    pollTimer = setInterval(tick, 100)
  })
  return _bmapPromise
}

async function createBMap(container: HTMLElement): Promise<any> {
  const w = await loadBMap()
  const map = new w.BMapGL.Map(container)
  map.centerAndZoom(new w.BMapGL.Point(120.155, 30.273), 10)
  map.enableScrollWheelZoom(true)
  return map
}

/* ================================================================
 * 对外 API
 * ================================================================ */

export async function createMap(container: HTMLElement): Promise<any> {
  return getProvider() === 'amap' ? createAMap(container) : createBMap(container)
}

export async function loadMapSDK(): Promise<any> {
  return getProvider() === 'amap' ? loadAMap() : loadBMap()
}

export function addMapControls(map: any): void {
  if (getProvider() === 'amap') {
    map.addControl(new (window as any).AMap.Scale())
    map.addControl(new (window as any).AMap.ToolBar({ position: 'RT' }))
  } else {
    map.addControl(new (window as any).BMapGL.ScaleControl())
    map.addControl(new (window as any).BMapGL.ZoomControl())
    map.addControl(new (window as any).BMapGL.NavigationControl3D())
  }
}

export function switchToSatellite(map: any): void {
  if (getProvider() === 'amap') {
    map.setLayers([new (window as any).AMap.TileLayer.Satellite()])
  } else {
    map.setMapType((window as any).BMapGL.MapTypeId.EARTH)
  }
}

export function switchToNormal(map: any): void {
  if (getProvider() === 'amap') {
    map.setLayers([new (window as any).AMap.TileLayer()])
  } else {
    map.setMapType((window as any).BMapGL.MapTypeId.NORMAL)
  }
}

export function flyTo(map: any, lng: number, lat: number, zoom = 12): void {
  if (getProvider() === 'amap') {
    map.setZoomAndCenter(zoom, [lng, lat])
  } else {
    map.flyTo({ lng, lat }, zoom)
  }
}

export function fitAllMarkers(map: any, positions: Array<[number, number]>): void {
  if (positions.length === 0) return
  if (getProvider() === 'amap') {
    const A = (window as any).AMap
    const markers = positions.map((p) => new A.Marker({ position: p }))
    map.setFitView(markers, false, [80, 80, 80, 80])
  } else {
    const B = (window as any).BMapGL
    const points = positions.map((p) => new B.Point(p[0], p[1]))
    const v = map.getViewport(points)
    if (v) map.setViewport(points)
  }
}

export function createMarker(map: any, lng: number, lat: number, opts?: { title?: string; content?: HTMLElement | string; onClick?: () => void }): any {
  if (getProvider() === 'amap') {
    const A = (window as any).AMap
    const m = new A.Marker({ position: [lng, lat], title: opts?.title, content: opts?.content, offset: opts?.content ? new A.Pixel(-11, -11) : undefined })
    map.add(m)
    if (opts?.onClick) m.on('click', opts.onClick)
    return m
  } else {
    const B = (window as any).BMapGL
    const pt = new B.Point(lng, lat)
    const m = new B.Marker(pt)
    if (opts?.title) m.setTitle(opts.title)
    map.addOverlay(m)
    if (opts?.onClick) m.addEventListener('click', opts.onClick)
    return m
  }
}

export function showInfoWindow(map: any, lng: number, lat: number, content: string): any {
  if (getProvider() === 'amap') {
    const A = (window as any).AMap
    const iw = new A.InfoWindow({ content, offset: new A.Pixel(0, -30) })
    iw.open(map, [lng, lat])
    return iw
  } else {
    const B = (window as any).BMapGL
    const pt = new B.Point(lng, lat)
    const iw = new B.InfoWindow(content, { width: 200 })
    map.openInfoWindow(iw, pt)
    return iw
  }
}

export function onMapClick(map: any, handler: (e: any) => void) {
  if (getProvider() === 'amap') {
    map.on('click', handler)
  } else {
    map.addEventListener('click', handler)
  }
}

export function offMapClick(map: any, handler: (e: any) => void) {
  if (getProvider() === 'amap') {
    map.off('click', handler)
  } else if (map.removeEventListener) {
    map.removeEventListener('click', handler)
  }
}

export function destroyMap(map: any): void {
  if (map?.destroy) map.destroy()
  else if (map?.clearOverlays) { map.clearOverlays(); map = null }
}