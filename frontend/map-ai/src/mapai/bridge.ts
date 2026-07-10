/**
 * iframe 通信桥。
 *
 * 父页面（第三方看板） <-> MapAI iframe 之间的 postMessage 协议：
 *
 * 父 → iframe（source: 'fde-mapai-host'）：
 *   { type: 'loadEntities', payload: { entities: MapAIEntity[] } }
 *   { type: 'loadMarkers',  payload: { markers:  MapAIMarker[] } }
 *   { type: 'flyTo',        payload: { lng, lat, zoom? } }
 *   { type: 'analyze',      payload: { entityIds?: string[] } }
 *   { type: 'clear',        payload: {} }
 *
 * iframe → 父（source: 'fde-mapai'）：
 *   { type: 'ready',           payload: { version } }
 *   { type: 'markerClick',     payload: { id, lng, lat } }
 *   { type: 'entitySelect',    payload: { id, name } }
 *   { type: 'analysisResult',  payload: { result } }
 *   { type: 'error',           payload: { message } }
 */

export interface MapAIControllerLike {
  loadEntities?: (entities: unknown[]) => void
  loadMarkers?: (markers: unknown[]) => void
  flyTo?: (lng: number, lat: number, zoom?: number) => void
  analyze?: (entityIds?: string[]) => void
  clearEntities?: () => void
}

export function emitToParent(
  type: string,
  payload: unknown,
  targetOrigin = '*',
): void {
  try {
    window.parent?.postMessage({ source: 'fde-mapai', type, payload }, targetOrigin)
  } catch {
    /* iframe 未嵌入父页面时静默 */
  }
}

const HOST_SOURCE = 'fde-mapai-host'

export function setupBridge(
  controller: MapAIControllerLike,
  targetOrigin = '*',
): () => void {
  void targetOrigin
  const handler = (e: MessageEvent) => {
    const data = e.data
    if (!data || data.source !== HOST_SOURCE) return
    const { type, payload } = data as {
      type: string
      payload?: Record<string, unknown>
    }
    switch (type) {
      case 'loadEntities':
        controller.loadEntities?.((payload?.entities as unknown[]) || [])
        break
      case 'loadMarkers':
        controller.loadMarkers?.((payload?.markers as unknown[]) || [])
        break
      case 'flyTo':
        controller.flyTo?.(
          payload?.lng as number,
          payload?.lat as number,
          payload?.zoom as number | undefined,
        )
        break
      case 'analyze':
        controller.analyze?.(payload?.entityIds as string[] | undefined)
        break
      case 'clear':
        controller.clearEntities?.()
        break
      default:
        break
    }
  }
  window.addEventListener('message', handler)
  return () => window.removeEventListener('message', handler)
}
