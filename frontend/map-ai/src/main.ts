import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import MapAIModule from './components/MapAIModule.vue'
import { resolveEmbedConfig } from './mapai/config'
import { setRuntimeConfig } from './mapai/runtime'
import './style.css'

const embedConfig = resolveEmbedConfig()

if (embedConfig) {
  // 嵌入模式：仅挂载可嵌入地图模块，不加载 FDE Agent / 笔记等专属面板。
  // postMessage 桥由 MapAIModule 自身在 onMounted 内建立（iframe 与 UMD 共用）。
  document.getElementById('app')?.classList.add('embed-mode')
  setRuntimeConfig(embedConfig)
  const app = createApp(MapAIModule, { config: embedConfig })
  app.use(createPinia())
  app.mount('#app')
} else {
  // 完整 FDE MapAI 应用
  const app = createApp(App)
  app.use(createPinia())
  app.mount('#app')
}
