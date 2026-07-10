import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

/**
 * 独立 UMD 库构建：产出 dist-lib/mapai.umd.js + mapai.css
 * 第三方通过 <script> 引入后调用 window.FdeMapAI.mount(el, config)。
 * 所有依赖（vue / tiptap / axios 等）内联，单文件即插即用。
 */
export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: 'dist-lib',
    emptyOutDir: true,
    cssCodeSplit: false,
    lib: {
      entry: resolve(__dirname, 'src/mapai/embed-entry.ts'),
      name: 'FdeMapAI',
      fileName: 'mapai',
      formats: ['umd'],
    },
    rollupOptions: {
      output: {
        // 内联所有依赖，确保单文件可用
        inlineDynamicImports: true,
      },
    },
  },
})
