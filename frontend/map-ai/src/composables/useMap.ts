/**
 * useMap — 地图供应商抽象层。
 * 通过 VITE_MAP_PROVIDER 切换: "baidu" | "amap"
 */

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
  return (import.meta.env.VITE_MAP_PROVIDER as string) === 'amap' ? 'amap' : 'baidu'
}

export function getApiKey(): string {
  const p = getProvider()
  return p === 'amap'
    ? (import.meta.env.VITE_AMAP_KEY as string) || ''
    : (import.meta.env.VITE_BAIDU_AK as string) || ''
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
    const jscode = (import.meta.env.VITE_AMAP_SECURITY_CODE as string) || ''
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
  return new A.Map(container, { zoom: 4, center: [116.397, 39.908], layers: [new A.TileLayer()] })
}

/* ================================================================
 * Baidu Map GL 实现
 * ================================================================ */

let _bmapPromise: Promise<any> | null = null

async function loadBMap(): Promise<any> {
  if (_bmapPromise) return _bmapPromise
  // Baidu Maps is loaded via <script> in index.html (must use document.write)
  // Just poll until BMapGL is available
  _bmapPromise = new Promise((resolve, reject) => {
    const w = window as any
    if (w.BMapGL) { resolve(w); return }
    let attempts = 0
    const interval = setInterval(() => {
      if (w.BMapGL) { clearInterval(interval); resolve(w); return }
      if (++attempts > 50) { clearInterval(interval); reject(new Error('BMapGL 未定义，可能百度地图脚本加载失败')) }
    }, 200)
  })
  return _bmapPromise
}

async function createBMap(container: HTMLElement): Promise<any> {
  const w = await loadBMap()
  const map = new w.BMapGL.Map(container)
  map.centerAndZoom(new w.BMapGL.Point(116.397, 39.908), 4)
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

export function destroyMap(map: any): void {
  if (map?.destroy) map.destroy()
  else if (map?.clearOverlays) { map.clearOverlays(); map = null }
}