import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The API runs on 8011 (port 8000 is held by another app in this workspace).
// Client code calls origin-relative /api/* and Vite proxies it here.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // 5173 is held by another app in this workspace; pin a distinct port and
    // fail loudly rather than silently bumping (same rationale as API :8011).
    port: 5180,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8011",
        changeOrigin: true,
      },
    },
  },
});
