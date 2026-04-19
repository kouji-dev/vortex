#!/usr/bin/env node
/**
 * Writes a large text file to stress-test KB upload progress in the UI.
 *
 * Usage (from frontend/):
 *   node scripts/generate-kb-upload-test-file.mjs [size_mb] [output_path]
 *
 * Default: 10 MB → tmp/kb-upload-test-10mb.txt (frontend/tmp is gitignored)
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const mbArg = process.argv[2]
const mb = mbArg === undefined ? 10 : Number(mbArg)
const outArg = process.argv[3]
const out =
  outArg ??
  path.join(__dirname, '..', 'tmp', `kb-upload-test-${Number.isFinite(mb) ? mb : 'x'}mb.txt`)

if (!Number.isFinite(mb) || mb < 1 || mb > 500) {
  console.error('Usage: node scripts/generate-kb-upload-test-file.mjs <size_mb 1-500> [output_path]')
  process.exit(1)
}

const dir = path.dirname(out)
fs.mkdirSync(dir, { recursive: true })

const chunk = Buffer.alloc(1024 * 1024, 'x')
const fd = fs.openSync(out, 'w')
try {
  for (let i = 0; i < mb; i += 1) {
    fs.writeSync(fd, chunk)
  }
} finally {
  fs.closeSync(fd)
}

console.log(`Wrote ${mb} MiB → ${path.resolve(out)}`)
