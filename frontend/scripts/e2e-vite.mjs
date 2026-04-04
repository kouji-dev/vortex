/**
 * Playwright webServer entry: ensure Vite’s proxy target is set before spawning Vite.
 * On some Windows setups, env vars on the Playwright `webServer` object do not reach `pnpm`/Vite;
 * this script runs in Node with a guaranteed env block.
 */
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const frontendRoot = path.join(path.dirname(fileURLToPath(import.meta.url)), '..')
const api = (process.env.E2E_API_URL ?? 'http://127.0.0.1:8001').replace(/\/$/, '')

process.env.VITE_DEV_API_PROXY_TARGET = api
// frontend/.env often pins VITE_API_URL=:8000; E2E creates conversations on E2E_API_URL (:8001).
// Shell env wins over .env in Vite — clear direct API URL so the app uses same-origin `/api` → proxy.
process.env.VITE_API_URL = ''

// Spawn Vite directly so Windows `pnpm`/`cmd` chains do not drop custom env vars.
const viteCli = path.join(frontendRoot, 'node_modules', 'vite', 'bin', 'vite.js')
const child = spawn(process.execPath, [viteCli, 'dev', '--port', '5175'], {
  cwd: frontendRoot,
  stdio: 'inherit',
  env: process.env,
  windowsHide: true,
})

child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal)
  process.exit(code ?? 1)
})
