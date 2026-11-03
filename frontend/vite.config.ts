/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// Development: the SPA calls /api/v1 on its own origin and Vite proxies to the FastAPI process, so the
// HttpOnly refresh cookie stays first-party. Override the target with VITE_DEV_API_PROXY if needed.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.VITE_DEV_API_PROXY || "http://127.0.0.1:8000";
  return {
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: { "/api": { target, changeOrigin: false } },
    },
    preview: { port: 4173 },
    build: { sourcemap: false, chunkSizeWarningLimit: 4000 },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      css: false,
      restoreMocks: true,
    },
  };
});
