/**
 * 解析嵌入配置。
 *
 * 优先级：URL 查询参数 / window.__FDE_MAPAI_CONFIG__ 全局对象。
 * 当 URL 含 embed=1 或存在全局配置时返回非 null（表示进入嵌入模式）。
 */
import type { MapAIConfig, MapAIFeatures } from './types'

export function resolveEmbedConfig(): MapAIConfig | null {
  const w = window as unknown as { __FDE_MAPAI_CONFIG__?: MapAIConfig }
  const params = new URLSearchParams(location.search)
  const hasEmbedFlag = params.get('embed') === '1'
  const globalCfg = w.__FDE_MAPAI_CONFIG__

  if (!hasEmbedFlag && !globalCfg) return null

  const cfg: MapAIConfig = globalCfg ? { ...globalCfg } : {}

  const get = (k: string) => params.get(k)

  if (get('provider')) cfg.provider = get('provider') as MapAIConfig['provider']
  if (get('ak')) cfg.apiKey = get('ak') as string
  if (get('security')) cfg.securityCode = get('security') as string
  if (get('theme')) cfg.theme = get('theme') as 'light' | 'dark'
  if (get('apiBase')) cfg.apiBase = get('apiBase') as string
  if (get('targetOrigin')) cfg.targetOrigin = get('targetOrigin') as string

  const featuresParam = get('features')
  if (featuresParam) {
    const f: Record<string, boolean> = {}
    featuresParam
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
      .forEach((key) => {
        f[key] = true
      })
    cfg.features = f as MapAIFeatures
  }

  const ds = get('dataSource')
  if (ds) {
    cfg.dataSource = {
      type: ds as 'static' | 'remote' | 'backend',
      dataUrl: get('dataUrl') || undefined,
    }
  }

  return cfg
}
