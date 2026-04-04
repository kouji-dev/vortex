import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

/** Absolute path to `frontend/e2e/fixtures` (stable from any spec depth). */
export const E2E_FIXTURES_DIR = path.join(__dirname, '..', 'fixtures')
