import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_DEV_API_TARGET || "http://127.0.0.1:8765";

  return {
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true
        },
        "/oauth": {
          target: apiTarget,
          changeOrigin: true
        }
      }
    },
    build: {
      outDir: "dist"
    }
  };
});
