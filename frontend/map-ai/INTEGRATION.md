# MapAI 模块集成指南（即插即用）

MapAI 是一个**独立可嵌入的地图分析模块**，可零后端集成到任何第三方可视化看板中。
支持两种集成方式：

1. **iframe 嵌入**（推荐，跨框架、最简单）
2. **`<script>` 引入 UMD 包**（适合自建前端工程，以组件/全局 API 方式挂载）

---

## 一、数据契约

### MapAIEntity（地图实体 / POI）

```jsonc
{
  "id": "string, 必填",
  "name": "string, 必填",
  "type": "string, 可选",
  "lng": "number, 必填（经度）",
  "lat": "number, 必填（纬度）",
  "tags": ["string, 可选"],
  "note": "string, 可选",
  "metadata": { "可选": "任意" }
}
```

### MapAIMarker（持久化标注点位）

```jsonc
{
  "id": "string, 必填",
  "name": "string, 必填",
  "lng": "number, 必填",
  "lat": "number, 必填",
  "note": "string, 可选",
  "tags": ["string, 可选"]
}
```

### MapAIConfig（模块配置）

| 字段 | 类型 | 说明 |
|---|---|---|
| `provider` | `'baidu' \| 'amap'` | 地图厂商，默认 `baidu` |
| `apiKey` | `string` | 地图 SDK Key（运行时覆盖编译期配置） |
| `securityCode` | `string` | 高德安全密钥（provider=amap 时） |
| `theme` | `'light' \| 'dark'` | 主题（预留） |
| `features` | `{ resourcePanel?, analysis?, markerAdd? }` | 功能开关，默认 `{resourcePanel:true, analysis:有后端时true, markerAdd:true}` |
| `dataSource` | `{ type:'static'\|'remote'\|'backend', dataUrl? }` | 数据来源 |
| `entities` | `MapAIEntity[]` | 静态实体（type=static 时） |
| `markers` | `MapAIMarker[]` | 静态点位（type=static 时） |
| `apiBase` | `string` | FDE 兼容后端基地址，如 `https://host/fde-api` |
| `targetOrigin` | `string` | postMessage 目标 origin，默认 `'*'`（生产建议显式指定） |

---

## 二、方式一：iframe 嵌入（零后端）

把本应用以 `?embed=1` 加载进 iframe，通过 URL 参数配置，通过 `postMessage` 注入数据与监听事件。

```html
<iframe
  id="mapai"
  src="https://your-host/fde/?embed=1&provider=baidu&ak=YOUR_AK&features=resourcePanel,analysis"
  style="width:100%;height:600px;border:0"
  allow="geolocation"
></iframe>

<script>
  const frame = document.getElementById('mapai')

  // 1) 注入数据
  frame.onload = () => {
    frame.contentWindow.postMessage({
      source: 'fde-mapai-host',
      type: 'loadEntities',
      payload: { entities: [
        { id: 'e1', name: '杭州东站', type: 'station', lng: 120.21, lat: 30.29 },
        { id: 'e2', name: '西湖', type: 'scenic', lng: 120.15, lat: 30.25 }
      ]}
    }, '*')
  }

  // 2) 监听事件
  window.addEventListener('message', (e) => {
    if (e.data?.source !== 'fde-mapai') return
    switch (e.data.type) {
      case 'ready': console.log('MapAI ready', e.data.payload.version); break
      case 'markerClick': console.log('点位点击', e.data.payload); break
      case 'entitySelect': console.log('实体选中', e.data.payload); break
      case 'analysisResult': console.log('分析结果', e.data.payload.result); break
    }
  })
</script>
```

### iframe 通信协议

**父 → iframe**（`source: 'fde-mapai-host'`）

| type | payload |
|---|---|
| `loadEntities` | `{ entities: MapAIEntity[] }` |
| `loadMarkers` | `{ markers: MapAIMarker[] }` |
| `flyTo` | `{ lng, lat, zoom? }` |
| `analyze` | `{ entityIds?: string[] }` |
| `clear` | `{}` |

**iframe → 父**（`source: 'fde-mapai'`）

| type | payload |
|---|---|
| `ready` | `{ version }` |
| `markerClick` | `{ id, lng, lat }` |
| `entitySelect` | `{ id, name }` |
| `analysisResult` | `{ result }` |
| `error` | `{ message }` |

### URL 参数速查

`embed=1` · `provider=baidu|amap` · `ak=KEY` · `security=CODE` · `theme=light|dark`
`features=resourcePanel,analysis,markerAdd` · `dataSource=static|remote|backend` · `dataUrl=URL` · `apiBase=URL` · `targetOrigin=URL`

---

## 三、方式二：`<script>` 引入 UMD 包

构建产物：`mapai.umd.cjs` + `mapai.css`（执行 `npm run build:lib` 生成于 `dist-lib/`）。

```html
<link rel="stylesheet" href="mapai.css" />
<div id="map-container" style="width:100%;height:600px"></div>
<script src="mapai.umd.cjs"></script>
<script>
  const ctrl = FdeMapAI.mount('#map-container', {
    provider: 'baidu',
    apiKey: 'YOUR_AK',
    dataSource: { type: 'static' },
    entities: [
      { id: 'e1', name: '上海虹桥', lng: 121.32, lat: 31.19 }
    ]
  })

  // 控制器方法
  ctrl.loadMarkers([{ id:'m1', name:'标注A', lng:121.47, lat:31.23 }])
  ctrl.flyTo(121.32, 31.19, 12)
  ctrl.analyze()          // 需配置 apiBase（FDE 兼容后端）
  ctrl.clearEntities()
  ctrl.destroy()          // 卸载
  console.log(ctrl.version)
</script>
```

> 注意：UMD 模式下面板使用 `fixed` 定位，建议挂载目标本身就是一个全屏/大尺寸的看板区域。

---

## 四、无需后端的静态模式

`dataSource.type` 为 `static` 或 `remote` 时，模块**完全不请求任何后端**：
- 点位由 `config.markers` / `loadMarkers()` 注入，本地增删改、标签统计、搜索过滤全部在浏览器内完成；
- 地图 SDK 通过运行时 `apiKey` 加载，三方只需自备地图厂商 Key；
- 仅当启用 `analysis` 且提供 `apiBase`（指向 FDE 兼容后端）时，才会发起关联分析网络请求。

---

## 五、对外服务（FDE 兼容后端，可选）

若需关联分析能力，将 `apiBase` 指向实现了以下接口的 FDE 后端：
- `POST {apiBase}/map/analysis` — 关联分析（请求体含 `entity_ids` / `entities`）
- `GET  {apiBase}/map/markers` — 点位列表
- `POST {apiBase}/map/markers` — 新建点位
- `PUT/DELETE {apiBase}/map/markers/{id}` — 更新/删除点位
