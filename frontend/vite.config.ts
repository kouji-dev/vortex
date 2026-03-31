import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { tanstackStart } from '@tanstack/react-start/plugin/vite'
import { defineConfig } from 'vite'

const devApiTarget = process.env.VITE_DEV_API_PROXY_TARGET ?? 'http://127.0.0.1:8000'

export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      '/api': { target: devApiTarget, changeOrigin: true },
      '/health': { target: devApiTarget, changeOrigin: true },
    },
  },
  resolve: {
    tsconfigPaths: true,
  },
  plugins: [tailwindcss(), tanstackStart(), react()],
})
