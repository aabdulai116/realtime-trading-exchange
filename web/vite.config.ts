import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the API runs on :8000; in production FastAPI serves this build.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/docs": "http://localhost:8000",
      "/openapi.json": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
});
