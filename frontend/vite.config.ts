import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: process.env.EDUTOY_API_TARGET || "http://127.0.0.1:8000",
      },
    },
  },
  preview: {
    proxy: {
      "/api": {
        target: process.env.EDUTOY_API_TARGET || "http://127.0.0.1:8000",
      },
    },
  },
});
