import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 本地开发时前端跑在 5173，/api 请求代理到 8000 的 FastAPI；
// 生产（Docker）下由 FastAPI 直接托管构建产物。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
