/**
 * 运行时配置中心。
 *
 * 编译期环境变量（import.meta.env）只作为默认值；
 * 通过本模块可以在运行时（embed URL 参数 / 全局配置 / mount 入参）覆盖
 * 地图厂商、Key、后端地址以及"是否连接后端"的开关。
 */
import type { MapProvider } from './types'

interface RuntimeState {
  provider?: MapProvider
  apiKey?: string
  securityCode?: string
  apiBase?: string
  /** 点位是否走后端持久化；static/remote 模式下为 false */
  markersBackend: boolean
}

const _state: RuntimeState = {
  markersBackend: true,
}

export function setRuntimeConfig(c: Partial<RuntimeState>): void {
  if (c.provider !== undefined) _state.provider = c.provider
  if (c.apiKey !== undefined) _state.apiKey = c.apiKey
  if (c.securityCode !== undefined) _state.securityCode = c.securityCode
  if (c.apiBase !== undefined) _state.apiBase = c.apiBase
  if (c.markersBackend !== undefined) _state.markersBackend = c.markersBackend
}

export function getRuntimeConfig(): Readonly<RuntimeState> {
  return _state
}

/** 统一返回当前生效的后端基地址 */
export function getApiBase(): string {
  return (
    _state.apiBase ||
    (import.meta.env.VITE_API_URL as string | undefined) ||
    '/fde-api'
  )
}
