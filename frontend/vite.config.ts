import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import path from "path"

const API_URL = process.env.VITE_API_URL || "https://backend-api-0pn1.onrender.com"

export default defineConfig({
  plugins: [react()],
  base: "/",

  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },

  server: {
    port: 5174,
    proxy: {
      "/api": {
        target: API_URL,
        changeOrigin: true,
        secure: false,
      },
    },
  },
})