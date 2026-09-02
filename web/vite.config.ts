import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5027,
    proxy: {
      "/ws": { target: "http://localhost:5026", ws: true },
      "/api": "http://localhost:5026",
      // OpsPage 健康/指标端点走根路径（非 /api 前缀），dev 下需直通后端
      "/health": "http://localhost:5026",
      "/metrics": "http://localhost:5026",
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});

