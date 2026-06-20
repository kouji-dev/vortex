import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { tanstackStart } from '@tanstack/react-start/plugin/vite'
import { defineConfig } from 'vite'

const devApiTarget = process.env.VITE_DEV_API_PROXY_TARGET ?? `http://127.0.0.1:${process.env.API_PORT ?? '8000'}`
const frontendPort = Number(process.env.FRONTEND_PORT ?? '5173')

export default defineConfig({
  server: {
    port: frontendPort,
    allowedHosts: true,
    proxy: {
      '/api': { target: devApiTarget, changeOrigin: true },
      '/health': { target: devApiTarget, changeOrigin: true },
      // Password auth endpoints (register/login/accept-invite) post to /auth/*
      // with no /api prefix (see register.tsx). Proxy them to the backend/mock
      // so the UI-driven E2E auth-seeding flow reaches a token issuer.
      '/auth': { target: devApiTarget, changeOrigin: true },
    },
  },
  resolve: {
    tsconfigPaths: true,
  },
  plugins: [tailwindcss(), tanstackStart(), react()],
})
