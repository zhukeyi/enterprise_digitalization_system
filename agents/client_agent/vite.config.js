// vite.config.js
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  root: "src",
  build: {
    outDir: "../out",
    emptyOutDir: true,
  },
  server: {
    port: 1420,
    strictPort: true,
  },
});