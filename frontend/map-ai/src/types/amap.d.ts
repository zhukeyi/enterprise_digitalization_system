/// <reference types="vite/client" />

declare module '@amap/amap-jsapi-loader' {
  interface AMapLoaderOptions {
    key: string
    version?: string
    plugins?: string[]
    securityJsCode?: string
  }
  export function load(options: AMapLoaderOptions): Promise<typeof AMap>
}

declare namespace AMap {
  class Map {
    constructor(container: string | HTMLElement, opts: MapOptions)
    destroy(): void
    setZoomAndCenter(zoom: number, center: [number, number]): void
    setLayers(layers: any[]): void
    add(overlay: any): void
    remove(overlay: any): void
    getCenter(): LngLat
    setFitView(overlays: any[], immediately?: boolean, padding?: number[]): void
    addControl(control: any, position?: string): void
  }
  interface MapOptions {
    zoom?: number
    center?: [number, number]
    layers?: any[]
    viewMode?: string
  }

  class TileLayer {
    constructor()
    static Satellite: { new(): TileLayer }
  }

  class Marker {
    constructor(opts: MarkerOptions)
    setPosition(pos: [number, number]): void
    getPosition(): [number, number]
    remove(): void
    on(event: string, handler: Function): void
  }
  interface MarkerOptions {
    position?: [number, number]
    title?: string
    content?: HTMLElement | string
    offset?: Pixel
  }

  class InfoWindow {
    constructor(opts?: InfoWindowOptions)
    open(map: Map, pos: [number, number]): void
    close(): void
  }
  interface InfoWindowOptions {
    content?: string
    offset?: Pixel
  }

  class LngLat {
    constructor(lng: number, lat: number)
  }
  class Pixel {
    constructor(x: number, y: number)
  }
  class Size {
    constructor(w: number, h: number)
  }
  class Bounds {
    constructor()
    extend(pos: [number, number]): void
  }

  class Scale {}
  class ToolBar {
    constructor(opts?: { position?: string })
  }

  const event = {
    addDomListener(el: HTMLElement, event: string, handler: Function): void
  }

  const plugin: string[]
}