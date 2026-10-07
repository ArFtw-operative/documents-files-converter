import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const api = process.env.FOLIO_API_ORIGIN ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": { target: api, ws: true, changeOrigin: false } },
  },
  build: { target: "es2022", sourcemap: true, chunkSizeWarningLimit: 2500 },
});
