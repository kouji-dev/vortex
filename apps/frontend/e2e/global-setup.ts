function assertE2eApiUrlNotDevDefault(raw: string) {
  try {
    const u = new URL(raw)
    const port = u.port || (u.protocol === 'https:' ? '443' : '80')
    if (port === '8000') {
      throw new Error(
        `E2E_API_URL must not use port 8000 (that is the default dev API / main database). ` +
          `Use http://127.0.0.1:8001 after ./scripts/e2e-up.sh, or set E2E_ALLOW_DEV_API_URL=1 to override.`,
      )
    }
  } catch (e) {
    if (e instanceof TypeError) {
      throw new Error(`Invalid E2E_API_URL: ${raw}`)
    }
    throw e
  }
}

export default async function globalSetup() {
  const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
  if (!process.env.E2E_ALLOW_DEV_API_URL) {
    assertE2eApiUrlNotDevDefault(base)
  }
  const url = `${base.replace(/\/$/, '')}/health`
  const deadline = Date.now() + 60_000
  let lastErr: unknown
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url)
      if (res.ok) return
      lastErr = new Error(`health not ok: ${res.status}`)
    } catch (e) {
      lastErr = e
    }
    await new Promise((r) => setTimeout(r, 500))
  }
  const msg = lastErr instanceof Error ? lastErr.message : String(lastErr)
  throw new Error(
    `E2E backend not reachable at ${url} after 60 s (${msg}).\n` +
      'Run  ./scripts/e2e-up.sh  from the repo root to start it.',
  )
}
