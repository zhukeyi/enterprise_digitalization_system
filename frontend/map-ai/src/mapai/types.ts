/**
 * MapAI 集成契约类型定义。
 *
 * 第三方可视化看板通过这些类型与 MapAI 模块交互：
 * - 传入配置（MapAIConfig）
 * - 传入数据（MapAIEntity / MapAIMarker）
 * - 监听事件（见 bridge.ts 的 postMessage 协议）
 */

export type MapProvider = 'baidu' | 'amap'

/** 地图上的一个被分析实体（POI / 标记点） */
export interface MapAIEntity {
  id: string
  name: string
  type?: string
  lng: number
  lat: number
  tags?: string[]
  note?: string
  metadata?: Record<string, unknown>
}

/** 持久化标注点位 */
export interface MapAIMarker {
  id: string
  name: string
  lng: number
  lat: number
  note?: string
  tags?: string[]
  created_at?: string
  updated_at?: string
}

/** 可选功能开关（默认见 MapAIModule 的 applyDefaults） */
export interface MapAIFeatures {
  /** 左侧点位资源列表面板 */
  resourcePanel?: boolean
  /** 关联分析收纳盒 + 提交分析 */
  analysis?: boolean
  /** 允许在地图上点击新增标注 */
  markerAdd?: boolean
}

/**
 * 数据源配置：
 * - 'static'  : 由集成方通过 config.entities / config.markers 或 loadEntities()/loadMarkers() 注入，不请求后端
 * - 'remote'  : 从 dataUrl 拉取 JSON（数组，元素为 MapAIEntity 或 { entities, markers }）
 * - 'backend' : 连接 FDE 兼容后端（apiBase），使用 /map/* 接口
 */
export interface MapAIDataSource {
  type: 'static' | 'remote' | 'backend'
  dataUrl?: string
}

/** MapAI 模块完整配置（iframe URL 参数 或 全局配置 或 mount() 入参） */
export interface MapAIConfig {
  provider?: MapProvider
  apiKey?: string
  securityCode?: string
  theme?: 'light' | 'dark'
  features?: MapAIFeatures
  dataSource?: MapAIDataSource
  entities?: MapAIEntity[]
  markers?: MapAIMarker[]
  /** FDE 兼容后端地址，例如 https://your-host/fde-api */
  apiBase?: string
  /** postMessage 目标 origin，默认 '*'（生产建议显式指定） */
  targetOrigin?: string
}

/** loadEntities / loadMarkers 入参兼容形态 */
export interface MapAIRemotePayload {
  entities?: MapAIEntity[]
  markers?: MapAIMarker[]
}
