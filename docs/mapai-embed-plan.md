# MapAI 即插即用集成方案 — 技术评估

> 2026-07-09 | 3 种方案对比 | 推荐 Web Component + CDN

---

## 一、现状分析

| 维度 | 当前状态 |
|------|---------|
| 前端框架 | Vue 3 + TypeScript + Pinia + Vite |
| 外部依赖 | 百度地图 WebGL SDK (document.write 加载) |
| 编辑/图表 | Tiptap + ECharts (vue-echarts) |
| 构建产物 | 503KB JS + 18KB CSS |
| API 端点 | 15 个 REST 端点 (已通过 nginx 反向代理) |
| 当前部署 | 静态文件通过 nginx serve，路径 `/fde/` |

**关键约束**：百度地图 WebGL SDK 使用 `document.write()`，**必须在页面解析阶段加载**（不能异步加载），这对嵌入方案有直接影响。

---

## 二、方案对比

### 方案 A：Web Component（即插即用首选）

```
消费者页面：
  <script src="https://host/fde-widget.js"></script>
  <fde-map-ai api="https://host/fde-api" token="xxx"></fde-map-ai>
```

| 维度 | 评价 |
|------|------|
| 框架无关 | ✅ 原生 Custom Element，React/Vue/Angular/HTML 均可使用 |
| 样式隔离 | ✅ Shadow DOM 隔离，不污染宿主页面 |
| 事件通信 | ✅ 通过 CustomEvent 暴露分析完成/实体选中等事件 |
| 百度地图兼容 | ⚠️ 需在 Shadow DOM 外创建百度脚本加载点 |
| 构建复杂度 | 中等，需 Vite library mode + vue 运行时 ~50KB 打入 |
| 包体积 | ~600KB (当前 524KB + Vue runtime ~50KB) |
| 可维护性 | ✅ 与当前 MapAI 代码共享，改动一处同时生效 |

**实施要点**：
1. 改用 Vite library mode，入口改为自定义元素注册
2. 百度地图脚本用 `document.createElement('script')` 在 light DOM 加载
3. MAP AI 核心功能保留：地图点击标点 → POI 增强 → 相关性分析 → 结果展示
4. 配置化：通过 HTML attributes 传递 `api`, `token`, `language`, `theme`
5. 交互式 API：`mapWidget.on('analysis-complete', (result) => {...})`

### 方案 B：iframe 嵌入（最简单但最受限）

```
消费者页面：
  <iframe src="https://host/fde/embed" width="100%" height="600"></iframe>
```

| 维度 | 评价 |
|------|------|
| 框架无关 | ✅ 任意页面可用 |
| 样式隔离 | ✅ 天然隔离 |
| 跨窗口通信 | ⚠️ 仅通过 postMessage，复杂交互难实现 |
| 百度地图兼容 | ✅ 独立页面，与现有部署方式一致 |
| 响应式适配 | ❌ iframe 尺寸固定，难以自适应 |
| 父页面主题同步 | ❌ iframe 内独立样式，无法跟随宿主主题 |
| 性能 | ⚠️ 每个 iframe 启动一个独立浏览器上下文 |

### 方案 C：npm 包（Vue 生态专用）

```
安装：
  npm install @fde/map-ai
使用：
  import { MapAI } from '@fde/map-ai'
  <MapAI api="/fde-api" />
```

| 维度 | 评价 |
|------|------|
| 框架无关 | ❌ 仅 Vue 3 可用（可用 React wrapper 包装） |
| Tree-shaking | ✅ 按需加载 |
| 版本管理 | ✅ npm semver 管理 |
| 百度地图兼容 | ✅ 宿主页面控制加载时机 |
| 适用场景 | Vue 技术栈的内部看板系统 |

---

## 三、推荐方案：A（Web Component）+ C（npm 包）并行

```
               ┌────────────────────┐
               │   fde-map-ai       │
               │   SPA (现有)       │
               └────────┬───────────┘
                        │
          ┌─────────────┴─────────────┐
          │     library mode build     │
          └─────────────┬─────────────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
  ┌──────────┐   ┌──────────┐   ┌──────────┐
  │  CDN JS  │   │  npm 包  │   │  独立SPA │
  │ <script> │   │  import  │   │  /fde/   │
  │ 即插即用 │   │  Vue项目 │   │  现有部署 │
  └──────────┘   └──────────┘   └──────────┘
```

**为什么推荐这种组合**：

1. **CDN JS（Web Component）** — 覆盖 95% 的"即插即用"场景。消费者只需一行 `<script>` 标签，不关心你用了什么框架
2. **npm 包** — 覆盖 Vue 3 项目深度集成场景（组件组合、Store 共享）
3. **独立 SPA** — 保留现有部署，向后兼容

两者共享同一份源代码，通过 Vite 的多入口构建产出不同格式。

---

## 四、实施步骤

### Phase 1：重构入口（0.5 天）

```
frontend/map-ai/
├── src/
│   ├── main.ts              → 现有 SPA 入口（保留）
│   ├── widget.ts             → Web Component 入口（新建）
│   ├── widgets/
│   │   └── FdeMapAI.ce.ts    → 自定义元素定义（新建）
│   └── composables/
│       └── useMapWidget.ts   → 公有 API hook（新建）
├── vite.config.ts            → 添加 library mode
├── vite.config.widget.ts     → Web Component 构建配置
└── package.json              → 添加 library 导出
```

### Phase 2：自定义元素实现（1 天）

`widgets/FdeMapAI.ce.ts` 核心逻辑：

```typescript
class FdeMapAI extends HTMLElement {
  // 从 attributes 读取配置
  get apiBase(): string   // data-api
  get authToken(): string // data-token  
  get theme(): string     // data-theme: light|dark
  get language(): string  // data-lang: zh|en

  // 公有方法
  addMarker(lng, lat, name, note): Promise<Marker>
  submitAnalysis(): Promise<AnalysisResult>
  clearAll(): void

  // 事件
  // 'marker-added', 'analysis-complete', 'entity-selected'
}
```

### Phase 3：百度地图加载适配（0.5 天）

关键问题：百度 SDK 依赖 `document.write()`，在 Shadow DOM 内无法工作。

解决方案：自定义元素在 `connectedCallback` 中检测全局 `window.BMapGL`：
- 如果已存在 → 直接初始化
- 如果不存在 → 在宿主 document 中动态创建 `<script>` 标签加载
- 多个 `<fde-map-ai>` 实例共享同一个百度 SDK 实例

### Phase 4：Vite 多入口构建（0.5 天）

```typescript
// vite.config.ts
export default defineConfig({
  build: {
    lib: {
      entry: {
        'fde-map-ai': './src/widget.ts',    // CDN + npm
        'fde-map-ai-spa': './src/main.ts',   // 独立 SPA
      },
      formats: ['es', 'iife'],
    },
  },
})
```

产物体积预估：
- `fde-map-ai.iife.js`: ~620KB (含 Vue runtime)
- `fde-map-ai.es.js`: ~600KB (ESM, 宿主项目 tree-shake Vue)

### Phase 5：CDN 部署 + 文档（0.5 天）

部署到服务器：
```
https://217.142.246.70:8443/fde-widget/fde-map-ai.js   ← CDN 入口
https://217.142.246.70:8443/fde/                        ← 独立 SPA（保留）
```

使用示例文档：

```html
<!-- 1. 加载百度地图 SDK（如果宿主页面还没有） -->
<script src="https://api.map.baidu.com/api?v=1.0&type=webgl&ak=YOUR_KEY"></script>

<!-- 2. 加载 MapAI Widget -->
<script src="https://217.142.246.70:8443/fde-widget/fde-map-ai.js"></script>

<!-- 3. 放置组件 -->
<fde-map-ai
  data-api="https://217.142.246.70:8443/fde-api"
  data-lang="zh"
  style="width:100%;height:600px"
></fde-map-ai>

<script>
  const widget = document.querySelector('fde-map-ai');
  widget.addEventListener('analysis-complete', (e) => {
    console.log('分析结果:', e.detail);
  });
</script>
```

---

## 五、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 百度 SDK document.write 约束 | 嵌入时加载失败 | 在 light DOM 创建 script 节点，检测全局 BMapGL 共享 |
| Shadow DOM 样式穿透 | ECharts 弹出层定位错乱 | ECharts 容器放在 light DOM 子节点 |
| 多个 Widget 实例冲突 | 地图实例重复创建 | 全局单例注册表，共享百度地图实例 |
| 包体积过大 | 首屏加载慢 | 地图 SDK 已 CDN 加载，Widget JS 控制在 600KB 以内 |
| CORS 问题 | CDN 跨域加载失败 | 同域名部署，无需额外 CORS 配置 |

---

## 六、成本估算

| 阶段 | 工作内容 | 预估耗时 |
|------|---------|---------|
| Phase 1 | 入口重构 + 目录调整 | 2h |
| Phase 2 | 自定义元素实现 | 4h |
| Phase 3 | 百度地图加载适配 | 2h |
| Phase 4 | Vite 多入口构建 | 2h |
| Phase 5 | CDN 部署 + 示例文档 | 2h |
| **合计** | | **~1.5 天** |

技术风险低，代码改动集中在 `frontend/map-ai/`，后端 API 零改动。