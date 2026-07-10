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

/**
 * 百度地图 WebGL 异步加载（callback 方式，兼容运行时 Key）。
 * 不再依赖 index.html 的 document.write，从而支持嵌入场景动态指定 AK。
 */
async function loadBMap(): Promise<any> {
  if (_bmapPromise) return _bmapPromise
  const w = window as any
  if (w.BMapGL) return w

  _bmapPromise = new Promise((resolve, reject) => {
    const cbName = '__fdeBMapReady'
    const prev = (w as any)[cbName]
    ;(w as any)[cbName] = () => {
      ;(w as any)[cbName] = prev
      resolve(w)
    }
    const key = getApiKey()
    const s = document.createElement('script')
    s.type = 'text/javascript'
    s.src = `https://api.map.baidu.com/api?type=webgl&v=1.0&ak=${encodeURIComponent(
      key,
    )}&callback=${cbName}`
    s.onerror = () => {
      _bmapPromise = null
      reject(new Error('百度地图脚本加载失败（请检查 AK 或网络）'))
    }
    document.head.appendChild(s)

    // 兜底：若 callback 未触发，轮询 BMapGL
    let attempts = 0
    const iv = setInterval(() => {
      if (w.BMapGL) {
        clearInterval(iv)
        ;(w as any)[cbName] = prev
        resolve(w)
      } else if (++attempts > 60) {
        clearInterval(iv)
        _bmapPromise = null
        reject(new Error('BMapGL 未定义，可能百度地图脚本加载失败'))
      }
    }, 200)
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