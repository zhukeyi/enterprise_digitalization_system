import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// MVS 极简门户：部署在 nginx `/portal/` 路径下（与 /fde/ 地图、/fde-api/ 后端共存）。
// 注：P2a 阶段 build 仅做 vite build（esbuild 转译 TS），不含 vue-tsc 类型检查；
// 类型检查在 H1 门户骨架阶段补入 CI（见 master-delivery-plan.md §F7）。
export default defineConfig({
  plugins: [vue()],
  base: '/portal/',
})
